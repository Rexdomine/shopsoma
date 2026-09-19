"""Regressions for exact-head review findings on PR 117."""

import asyncio
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.product import ProductVariant, SizeEnum, SizeStock, Variation
from app.models.stock_payment_persistence import (
    PaymentAttemptEvidence,
    PaymentAttemptReservation,
    coordinate_catalog_write,
)


def _lane_helpers():
    path = Path(__file__).with_name("test_stock_payment_persistence.py")
    spec = importlib.util.spec_from_file_location("stock_payment_review_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _coordinate(session, *keys: tuple[str, uuid.UUID]) -> None:
    payload = json.dumps(
        [
            {"subject_kind": kind, "subject_id": str(subject_id)}
            for kind, subject_id in keys
        ]
    )
    await session.execute(
        text("SELECT coordinate_stock_payment_write(CAST(:keys AS jsonb))"),
        {"keys": payload},
    )


async def _coordinate_attempt(
    session, attempt_id: uuid.UUID, order_id: uuid.UUID
) -> None:
    await session.execute(
        text("SELECT coordinate_payment_attempt_write(:attempt_id, :order_id)"),
        {"attempt_id": attempt_id, "order_id": order_id},
    )


async def _wait_for_postgres_lock(observer, backend_pid: int) -> None:
    """Wait until PostgreSQL reports that a backend is blocked by another backend."""

    async with asyncio.timeout(5):
        while not await observer.scalar(
            text("SELECT cardinality(pg_blocking_pids(:backend_pid)) > 0"),
            {"backend_pid": backend_pid},
        ):
            await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_postgres_lock_probe_observes_a_blocked_backend(db_session) -> None:
    """Concurrency tests can synchronize on PostgreSQL, not scheduler timing."""

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    holder = factory()
    contender = factory()
    observer = factory()
    lock_key = uuid.uuid4().int % (2**31)
    contend_task = None
    try:
        await holder.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
        backend_pid = await contender.scalar(text("SELECT pg_backend_pid()"))

        async def contend_for_lock() -> None:
            await contender.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key}
            )

        contend_task = asyncio.create_task(contend_for_lock())
        await _wait_for_postgres_lock(observer, backend_pid)
        assert not contend_task.done()
        await holder.commit()
        await asyncio.wait_for(contend_task, timeout=5)
    finally:
        if contend_task is not None and not contend_task.done():
            contend_task.cancel()
            await asyncio.gather(contend_task, return_exceptions=True)
        await holder.rollback()
        await contender.rollback()
        await observer.rollback()
        await holder.close()
        await contender.close()
        await observer.close()


async def _alternate_selection(
    session,
    lane,
    graph,
    customer_id,
    *,
    quantity: int = 1,
    selected: bool = True,
):
    """Create a second package/intent/quote, optionally selected, for one order."""

    from app.models.customer_shipping_quote import CustomerShippingQuoteSelection
    from app.models.package_custody import OutboundShipmentIntent

    quote_helpers = lane._load_helpers(
        "test_customer_shipping_quote_persistence.py",
        f"stock_payment_alternate_quote_helpers_{uuid.uuid4().hex}",
    )
    custody = quote_helpers._custody_helpers()
    package, _version, _item, seal = await custody._ready_package(
        session, graph, quantity=quantity
    )
    intent = OutboundShipmentIntent(
        package_id=package.id,
        package_version=1,
        seal_id=seal.id,
        order_id=graph["order"].id,
        origin_hub_id=graph["hub"].id,
        destination_name="Payment Customer",
        destination_phone="+234****0000",
        destination_address_line1="1 Payment Street",
        destination_city="Lagos",
        destination_state="Lagos",
        destination_postal_code="100213",
        source_command="create_outbound_intent",
        idempotency_key=f"alternate-intent-{uuid.uuid4().hex}",
        created_by_id=graph["operator_id"],
    )
    session.add(intent)
    await session.flush()
    quote = quote_helpers._quote(graph, package, seal, intent, customer_id)
    session.add(quote)
    await session.flush()
    option = quote_helpers._option(quote.id, f"alternate-{uuid.uuid4().hex[:8]}")
    session.add(option)
    await session.flush()
    if not selected:
        return intent, quote, option, None
    selection = CustomerShippingQuoteSelection(
        quote_id=quote.id,
        intent_id=intent.id,
        option_id=option.id,
        customer_id=customer_id,
        selected_by_id=customer_id,
        source_command="select_shipping_quote_option",
        idempotency_key=f"alternate-selection-{uuid.uuid4().hex}",
    )
    session.add(selection)
    await session.flush()
    return intent, quote, option, selection


async def _multi_package_attempt_subject(
    session, lane, graph, subject, customer_id, sku
):
    """Create one full-order attempt anchored to A but reserving packages A and B."""

    intent, quote, option, selection = subject
    alternate_intent, alternate_quote, alternate_option, alternate_selection = (
        await _alternate_selection(session, lane, graph, customer_id)
    )
    reservations = (
        lane._reservation(graph, intent, quote, option, selection, customer_id, sku),
        lane._reservation(
            graph,
            alternate_intent,
            alternate_quote,
            alternate_option,
            alternate_selection,
            customer_id,
            sku,
        ),
    )
    session.add_all(reservations)
    await session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_id
    )
    session.add(attempt)
    await session.flush()
    session.add_all(
        [
            PaymentAttemptReservation(
                attempt_id=attempt.id, reservation_id=reservation.id
            )
            for reservation in reservations
        ]
    )
    await session.flush()
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    return attempt, alternate_intent


async def _transition_multi_package_attempt(session, attempt, state: str) -> None:
    lease_token = uuid.uuid4()
    await session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": lease_token, "attempt_id": attempt.id},
    )
    if state == "call_started":
        return

    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="provider_reconciliation",
        event_id=f"multi-package-{state}-{uuid.uuid4().hex}",
        evidence_type=(
            "outcome_unknown" if state == "abandoned_unknown" else "payment_verified"
        ),
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    session.add(evidence)
    await session.flush()
    if state == "abandoned_unknown":
        await session.execute(text("SET LOCAL session_replication_role = replica"))
        await session.execute(
            text(
                "UPDATE payment_attempts "
                "SET claim_expires_at=clock_timestamp() - interval '1 second' "
                "WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
        await session.execute(text("SET LOCAL session_replication_role = origin"))
    await _present_payment_lease(session, lease_token)
    await session.execute(
        text(
            "UPDATE payment_attempts SET state=:state, "
            "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
        ),
        {"state": state, "evidence_id": evidence.id, "attempt_id": attempt.id},
    )


async def _present_payment_lease(session, lease_token: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('shopsoma.payment_lease_token', :token, true)"),
        {"token": str(lease_token)},
    )


async def _set_attempt_state_for_interlock_matrix(session, attempt, state: str) -> None:
    """Reach each persisted state while preserving the real transition contract."""

    if state == "pending":
        return
    if state == "expired":
        await session.execute(text("SET LOCAL session_replication_role = replica"))
        await session.execute(
            text(
                "UPDATE payment_attempts SET state='expired', terminal_at=clock_timestamp(), "
                "row_version=2 WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
        await session.execute(text("SET LOCAL session_replication_role = origin"))
        return

    lease_token = uuid.uuid4()
    if state == "failed":
        evidence_type = "payment_failed"
        next_version = 2
    else:
        await session.execute(
            text(
                "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                "row_version=2 WHERE id=:attempt_id"
            ),
            {"token": lease_token, "attempt_id": attempt.id},
        )
        if state == "call_started":
            return
        evidence_type = (
            "outcome_unknown" if state == "abandoned_unknown" else "payment_verified"
        )
        next_version = 3

    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="interlock_matrix",
        event_id=f"{state}-{uuid.uuid4().hex}",
        evidence_type=evidence_type,
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    session.add(evidence)
    await session.flush()
    if state == "abandoned_unknown":
        await session.execute(text("SET LOCAL session_replication_role = replica"))
        await session.execute(
            text(
                "UPDATE payment_attempts SET claim_expires_at=clock_timestamp() - interval '1 second' "
                "WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
        await session.execute(text("SET LOCAL session_replication_role = origin"))
    if state in {"verified", "abandoned_unknown"}:
        await _present_payment_lease(session, lease_token)
    await session.execute(
        text(
            "UPDATE payment_attempts SET state=:state, terminal_evidence_id=:evidence_id, "
            "row_version=:row_version WHERE id=:attempt_id"
        ),
        {
            "state": state,
            "evidence_id": evidence.id,
            "row_version": next_version,
            "attempt_id": attempt.id,
        },
    )


async def _abandoned_unknown_subject(session, vendor_user, customer_user):
    """Create one evidence-backed unknown provider outcome with an active reservation."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        session, vendor_user, customer_user, stock=1
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    session.add(reservation)
    await session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    session.add(attempt)
    await session.flush()
    session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await session.flush()
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    lease_token = uuid.uuid4()
    provider = attempt.provider
    provider_reference = attempt.provider_reference
    await session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": lease_token, "attempt_id": attempt.id},
    )
    await session.refresh(attempt)
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="provider_reconciliation",
        event_id=f"unknown-{uuid.uuid4().hex}",
        evidence_type="outcome_unknown",
        provider=provider,
        provider_reference=provider_reference,
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    session.add(evidence)
    await session.flush()
    await session.execute(text("SET LOCAL session_replication_role = replica"))
    await session.execute(
        text(
            "UPDATE payment_attempts SET claim_expires_at=clock_timestamp() - interval '1 second' "
            "WHERE id=:attempt_id"
        ),
        {"attempt_id": attempt.id},
    )
    await session.execute(text("SET LOCAL session_replication_role = origin"))
    await _present_payment_lease(session, lease_token)
    await session.execute(
        text(
            "UPDATE payment_attempts SET state='abandoned_unknown', "
            "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
        ),
        {"evidence_id": evidence.id, "attempt_id": attempt.id},
    )
    return lane, graph, intent, quote, option, selection, sku, reservation, attempt


async def _pending_payment_subject(session, vendor_user, customer_user):
    """Create one provider-bound pending attempt with an active reservation."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        session, vendor_user, customer_user, stock=1
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    session.add(reservation)
    await session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    session.add(attempt)
    await session.flush()
    session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await session.flush()
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    return attempt


async def _call_started_subject(session, vendor_user, customer_user):
    """Create one provider-bound call-started attempt with an active reservation."""

    attempt = await _pending_payment_subject(session, vendor_user, customer_user)
    lease_token = uuid.uuid4()
    await session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": lease_token, "attempt_id": attempt.id},
    )
    await session.refresh(attempt)
    return attempt, lease_token


async def _definitive_reconciliation_evidence(
    session,
    attempt,
    target_state: str,
    *,
    evidence_type: str | None = None,
    source: str = "provider_reconciliation",
    event_id: str | None = None,
    provider: str | None = None,
    provider_reference: str | None = None,
):
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source=source,
        event_id=event_id or f"definitive-{target_state}-{uuid.uuid4().hex}",
        evidence_type=evidence_type
        or ("payment_verified" if target_state == "verified" else "payment_failed"),
        provider=provider or attempt.provider,
        provider_reference=provider_reference or attempt.provider_reference,
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    session.add(evidence)
    await session.flush()
    return evidence


async def _unvalidated_definitive_reconciliation_evidence(
    session,
    attempt,
    target_state: str,
    **overrides,
):
    """Inject migration-era evidence to exercise the terminal fail-closed guard."""

    await session.execute(text("SET LOCAL session_replication_role = replica"))
    try:
        return await _definitive_reconciliation_evidence(
            session, attempt, target_state, **overrides
        )
    finally:
        await session.execute(text("SET LOCAL session_replication_role = origin"))


async def _force_evidence_chronology(
    session,
    evidence_id,
    *,
    created_at: datetime | None = None,
    observed_at: datetime | None = None,
) -> None:
    """Inject migration-era chronology without weakening the live append-only path."""

    await session.execute(text("SET LOCAL session_replication_role = replica"))
    try:
        await session.execute(
            text(
                "UPDATE payment_attempt_evidence "
                "SET created_at=COALESCE(:created_at, created_at), "
                "observed_at=COALESCE(:observed_at, observed_at) WHERE id=:evidence_id"
            ),
            {
                "created_at": created_at,
                "observed_at": observed_at,
                "evidence_id": evidence_id,
            },
        )
    finally:
        await session.execute(text("SET LOCAL session_replication_role = origin"))


async def _expire_reservation_without_lifecycle_transition(
    session, reservation_id
) -> None:
    await session.execute(text("SET LOCAL session_replication_role = replica"))
    await session.execute(
        text(
            "UPDATE stock_reservations SET created_at=statement_timestamp() - interval '2 seconds', "
            "expires_at=statement_timestamp() - interval '1 second' WHERE id=:reservation_id"
        ),
        {"reservation_id": reservation_id},
    )
    await session.execute(text("SET LOCAL session_replication_role = origin"))


async def _refresh_call_start_deadlines(session, reservation_id, attempt_id) -> None:
    """Keep the test subject live until the race explicitly forces its expiry."""

    await session.execute(text("SET LOCAL session_replication_role = replica"))
    try:
        await session.execute(
            text(
                "UPDATE stock_reservations "
                "SET created_at=statement_timestamp(), ttl_seconds=1800, "
                "expires_at=statement_timestamp() + interval '1800 seconds' "
                "WHERE id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        )
        await session.execute(
            text(
                "UPDATE payment_attempts "
                "SET created_at=statement_timestamp(), payment_window_seconds=1800, "
                "expires_at=statement_timestamp() + interval '1800 seconds', "
                "authorization_deadline_at=statement_timestamp() + interval '1805 seconds' "
                "WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt_id},
        )
    finally:
        await session.execute(text("SET LOCAL session_replication_role = origin"))


async def _split_package_item_across_cohorts(session, graph, quote) -> None:
    """Represent one order item as two cohort-keyed rows in one package version."""

    from app.models.fulfillment_cohort import CohortItemAllocation, FulfillmentCohort
    from app.models.package_custody import HubPackageItem

    second_cohort = FulfillmentCohort(
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        readiness_type=graph["cohort"].readiness_type,
        ready_from=graph["cohort"].ready_from + timedelta(seconds=1),
        ready_through=graph["cohort"].ready_through + timedelta(seconds=1),
    )
    session.add(second_cohort)
    await session.flush()

    await session.execute(text("SET LOCAL session_replication_role = replica"))
    await session.execute(
        text(
            "UPDATE cohort_item_allocations SET allocated_quantity = 2 "
            "WHERE cohort_id = :cohort_id AND order_item_id = :order_item_id"
        ),
        {"cohort_id": graph["cohort"].id, "order_item_id": graph["item"].id},
    )
    await session.execute(
        text(
            "UPDATE hub_package_items SET quantity = 2 "
            "WHERE package_id = :package_id AND package_version = :package_version "
            "AND cohort_id = :cohort_id AND order_item_id = :order_item_id"
        ),
        {
            "package_id": quote.package_id,
            "package_version": quote.package_version,
            "cohort_id": graph["cohort"].id,
            "order_item_id": graph["item"].id,
        },
    )
    session.add_all(
        [
            CohortItemAllocation(
                cohort_id=second_cohort.id,
                order_item_id=graph["item"].id,
                order_id=graph["order"].id,
                vendor_id=graph["vendor_id"],
                allocated_quantity=1,
            ),
            HubPackageItem(
                package_id=quote.package_id,
                package_version=quote.package_version,
                order_id=graph["order"].id,
                hub_id=graph["hub"].id,
                cohort_id=second_cohort.id,
                vendor_id=graph["vendor_id"],
                order_item_id=graph["item"].id,
                quantity=1,
            ),
        ]
    )
    await session.flush()
    await session.execute(text("SET LOCAL session_replication_role = origin"))


@pytest.mark.asyncio
async def test_verified_linked_reservation_remains_inventory_effective_after_ttl(
    db_session, vendor_user, customer_user
) -> None:
    """A paid unit cannot age out before its reservation is consumed."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:lease_token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"lease_token": lease_token, "attempt_id": attempt.id},
    )
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway_webhook",
        event_id=f"verified-{uuid.uuid4().hex}",
        evidence_type="payment_verified",
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()
    await _present_payment_lease(db_session, lease_token)
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='verified', "
            "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
        ),
        {"evidence_id": evidence.id, "attempt_id": attempt.id},
    )

    # Model a crashed consumer after payment verification without sleeping in real time.
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE stock_reservations "
            "SET created_at=statement_timestamp() - interval '2 seconds', "
            "expires_at=statement_timestamp() - interval '1 second' WHERE id=:id"
        ),
        {"id": reservation.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))

    competing = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    with pytest.raises(
        DBAPIError, match="stock reservation exceeds available inventory"
    ):
        async with db_session.begin_nested():
            db_session.add(competing)
            await db_session.flush()


@pytest.mark.asyncio
async def test_size_stock_is_the_locked_inventory_subject(
    db_session, vendor_user, customer_user
) -> None:
    """Vendor size stock is reserved independently of products.total_stock."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    variation = Variation(
        product_id=graph["item"].product_id,
        title="Black",
        type="color",
        price=graph["item"].unit_price,
    )
    db_session.add(variation)
    await db_session.flush()
    size_stock = SizeStock(variation_id=variation.id, size=SizeEnum.M, stock=1)
    db_session.add(size_stock)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE order_items SET variant_details=CAST(:details AS jsonb) "
            "WHERE id=:order_item_id"
        ),
        {
            "details": json.dumps(
                {
                    "size": "M",
                    "color": "Black",
                    "size_stock_id": str(size_stock.id),
                    "variation_id": str(variation.id),
                }
            ),
            "order_item_id": graph["item"].id,
        },
    )
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        None,
        size_stock_id=size_stock.id,
    )
    db_session.add(reservation)
    await db_session.flush()

    competing = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        None,
        size_stock_id=size_stock.id,
    )
    with pytest.raises(
        DBAPIError, match="stock reservation exceeds available inventory"
    ):
        async with db_session.begin_nested():
            db_session.add(competing)
            await db_session.flush()
    with pytest.raises(
        DBAPIError, match="inventory cannot be reduced below active reservations"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE size_stocks SET stock=0 WHERE id=:id"),
                {"id": size_stock.id},
            )


@pytest.mark.asyncio
async def test_made_to_order_reservation_does_not_require_finite_stock(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    await db_session.execute(
        text("UPDATE products SET made_to_order=true WHERE id=:id"),
        {"id": graph["item"].product_id},
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    assert reservation.state == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("subject_kind", ["product", "variant"])
async def test_null_sku_uses_collision_free_inventory_subject_identity(
    db_session, vendor_user, customer_user, subject_kind
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    variant_id = None
    if subject_kind == "variant":
        variant = ProductVariant(
            product_id=graph["item"].product_id,
            size="M",
            color=f"null-sku-{uuid.uuid4().hex[:8]}",
            price=graph["item"].unit_price,
            stock=1,
            sku=None,
        )
        db_session.add(variant)
        await db_session.flush()
        variant_id = variant.id
        await db_session.execute(
            text(
                "UPDATE order_items SET variant_id=:variant_id WHERE id=:order_item_id"
            ),
            {"variant_id": variant.id, "order_item_id": graph["item"].id},
        )
    else:
        await db_session.execute(
            text("UPDATE products SET sku=NULL WHERE id=:id"),
            {"id": graph["item"].product_id},
        )

    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        None,
        variant_id=variant_id,
    )
    db_session.add(reservation)
    await db_session.flush()
    assert reservation.sku is None


@pytest.mark.asyncio
async def test_size_stock_binding_rejects_mismatched_order_size(
    db_session, vendor_user, customer_user
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=10
    )
    variation = Variation(
        product_id=graph["item"].product_id,
        title="Blue",
        type="color",
        price=graph["item"].unit_price,
    )
    db_session.add(variation)
    await db_session.flush()
    size_stock = SizeStock(variation_id=variation.id, size=SizeEnum.M, stock=1)
    db_session.add(size_stock)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE order_items SET variant_details=CAST(:details AS jsonb) "
            "WHERE id=:order_item_id"
        ),
        {
            "details": json.dumps(
                {
                    "size": "L",
                    "color": "Blue",
                    "variation_id": str(variation.id),
                    "size_stock_id": str(size_stock.id),
                    "stock_source": "legacy_variation",
                }
            ),
            "order_item_id": graph["item"].id,
        },
    )
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        None,
        size_stock_id=size_stock.id,
    )
    db_session.add(reservation)
    with pytest.raises(
        DBAPIError, match="stock reservation subject binding is invalid"
    ):
        await db_session.flush()


@pytest.mark.asyncio
async def test_size_stock_parent_cannot_move_during_reservation(
    db_session, vendor_user, customer_user
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    other_graph, *_ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    variation = Variation(
        product_id=graph["item"].product_id,
        title="Black",
        type="color",
        price=graph["item"].unit_price,
    )
    db_session.add(variation)
    await db_session.flush()
    size_stock = SizeStock(variation_id=variation.id, size=SizeEnum.M, stock=1)
    db_session.add(size_stock)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE order_items SET variant_details=CAST(:details AS jsonb) "
            "WHERE id=:order_item_id"
        ),
        {
            "details": json.dumps(
                {
                    "size": "M",
                    "color": "Black",
                    "variation_id": str(variation.id),
                    "size_stock_id": str(size_stock.id),
                }
            ),
            "order_item_id": graph["item"].id,
        },
    )
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    mover = factory()
    reserver = factory()
    try:
        await _coordinate(
            mover,
            ("product", graph["item"].product_id),
            ("product", other_graph["item"].product_id),
            ("variation", variation.id),
        )
        await mover.execute(
            text("UPDATE variations SET product_id=:product_id WHERE id=:id"),
            {"product_id": other_graph["item"].product_id, "id": variation.id},
        )

        async def reserve_after_parent_move():
            candidate = lane._reservation(
                graph,
                intent,
                quote,
                option,
                selection,
                customer_user["user"].id,
                None,
                size_stock_id=size_stock.id,
            )
            reserver.add(candidate)
            try:
                await reserver.flush()
                await reserver.commit()
                return None
            except DBAPIError as exc:
                await reserver.rollback()
                return str(exc)

        result_task = asyncio.create_task(reserve_after_parent_move())
        await asyncio.sleep(0.2)
        await mover.commit()
        result = await asyncio.wait_for(result_task, timeout=5)
        assert result is not None
        assert "stock reservation subject binding is invalid" in result
    finally:
        await mover.close()
        await reserver.close()


@pytest.mark.asyncio
async def test_size_stock_reservation_prevents_parent_move_after_binding(
    db_session, vendor_user, customer_user
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    other_graph, *_ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    variation = Variation(
        product_id=graph["item"].product_id,
        title="Black",
        type="color",
        price=graph["item"].unit_price,
    )
    db_session.add(variation)
    await db_session.flush()
    size_stock = SizeStock(variation_id=variation.id, size=SizeEnum.M, stock=1)
    db_session.add(size_stock)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE order_items SET variant_details=CAST(:details AS jsonb) "
            "WHERE id=:order_item_id"
        ),
        {
            "details": json.dumps(
                {
                    "size": "M",
                    "color": "Black",
                    "variation_id": str(variation.id),
                    "size_stock_id": str(size_stock.id),
                }
            ),
            "order_item_id": graph["item"].id,
        },
    )
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    reserver = factory()
    mover = factory()
    try:
        candidate = lane._reservation(
            graph,
            intent,
            quote,
            option,
            selection,
            customer_user["user"].id,
            None,
            size_stock_id=size_stock.id,
        )
        reserver.add(candidate)
        await reserver.flush()

        async def move_parent_after_binding():
            try:
                await mover.execute(
                    text("UPDATE variations SET product_id=:product_id WHERE id=:id"),
                    {
                        "product_id": other_graph["item"].product_id,
                        "id": variation.id,
                    },
                )
                await mover.commit()
                return None
            except DBAPIError as exc:
                await mover.rollback()
                return str(exc)

        result_task = asyncio.create_task(move_parent_after_binding())
        await asyncio.sleep(0.2)
        await reserver.commit()
        result = await asyncio.wait_for(result_task, timeout=5)
        assert result is not None
        assert "reserved product identity is immutable" in result
    finally:
        await reserver.close()
        await mover.close()


@pytest.mark.asyncio
async def test_verification_serializes_with_reservation_after_ttl(
    db_session, vendor_user, customer_user
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    second_graph, second_intent, second_quote, second_option, second_selection, _ = (
        await lane._checkout_subject(db_session, vendor_user, customer_user, stock=1)
    )
    second_graph["item"].product_id = graph["item"].product_id
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        ttl_seconds=2,
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    lease_token = uuid.uuid4()
    attempt.state = "call_started"
    attempt.lease_token = lease_token
    attempt.row_version += 1
    await db_session.flush()
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    verifier = factory()
    competitor = factory()
    try:
        evidence_id = uuid.uuid4()
        verifier.add(
            PaymentAttemptEvidence(
                id=evidence_id,
                attempt_id=attempt.id,
                source="provider_webhook",
                event_id=f"verify-race-{uuid.uuid4().hex}",
                evidence_type="payment_verified",
                evidence_hash="6" * 64,
                observed_at=datetime.now(timezone.utc),
            )
        )
        await verifier.flush()
        await _present_payment_lease(verifier, lease_token)
        await _coordinate_attempt(verifier, attempt.id, graph["order"].id)
        await verifier.execute(
            text(
                "UPDATE payment_attempts SET state='verified', terminal_evidence_id=:evidence_id, "
                "row_version=row_version+1 WHERE id=:attempt_id"
            ),
            {"evidence_id": evidence_id, "attempt_id": attempt.id},
        )
        await asyncio.sleep(2.1)

        async def reserve_competing_unit():
            candidate = lane._reservation(
                second_graph,
                second_intent,
                second_quote,
                second_option,
                second_selection,
                customer_user["user"].id,
                sku,
            )
            competitor.add(candidate)
            try:
                await competitor.flush()
                await competitor.commit()
                return None
            except DBAPIError as exc:
                await competitor.rollback()
                return str(exc)

        result_task = asyncio.create_task(reserve_competing_unit())
        await asyncio.sleep(0.2)
        await verifier.commit()
        result = await asyncio.wait_for(result_task, timeout=5)
        assert result is not None
        assert "stock reservation exceeds available inventory" in result
    finally:
        await verifier.close()
        await competitor.close()


@pytest.mark.asyncio
async def test_verification_serializes_with_stock_reduction_after_ttl(
    db_session, vendor_user, customer_user
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        ttl_seconds=2,
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    lease_token = uuid.uuid4()
    attempt.state = "call_started"
    attempt.lease_token = lease_token
    attempt.row_version += 1
    await db_session.flush()
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    verifier = factory()
    reducer = factory()
    try:
        evidence_id = uuid.uuid4()
        verifier.add(
            PaymentAttemptEvidence(
                id=evidence_id,
                attempt_id=attempt.id,
                source="provider_webhook",
                event_id=f"verify-stock-race-{uuid.uuid4().hex}",
                evidence_type="payment_verified",
                evidence_hash="7" * 64,
                observed_at=datetime.now(timezone.utc),
            )
        )
        await verifier.flush()
        await _present_payment_lease(verifier, lease_token)
        await _coordinate_attempt(verifier, attempt.id, graph["order"].id)
        await verifier.execute(
            text(
                "UPDATE payment_attempts SET state='verified', terminal_evidence_id=:evidence_id, "
                "row_version=row_version+1 WHERE id=:attempt_id"
            ),
            {"evidence_id": evidence_id, "attempt_id": attempt.id},
        )
        await asyncio.sleep(2.1)

        async def reduce_paid_inventory():
            try:
                await _coordinate(reducer, ("product", graph["item"].product_id))
                await reducer.execute(
                    text("UPDATE products SET total_stock=0 WHERE id=:product_id"),
                    {"product_id": graph["item"].product_id},
                )
                await reducer.commit()
                return None
            except DBAPIError as exc:
                await reducer.rollback()
                return str(exc)

        result_task = asyncio.create_task(reduce_paid_inventory())
        await asyncio.sleep(0.2)
        await verifier.commit()
        result = await asyncio.wait_for(result_task, timeout=5)
        assert result is not None
        assert "inventory cannot be reduced below active reservations" in result
    finally:
        await verifier.close()
        await reducer.close()


@pytest.mark.asyncio
async def test_full_order_payment_attempts_serialize_across_package_selections(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=3
    )
    alternate = await _alternate_selection(
        db_session, lane, graph, customer_user["user"].id
    )
    alternate_intent, alternate_quote, alternate_option, alternate_selection = alternate
    first_reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    second_reservation = lane._reservation(
        graph,
        alternate_intent,
        alternate_quote,
        alternate_option,
        alternate_selection,
        customer_user["user"].id,
        sku,
    )
    db_session.add_all([first_reservation, second_reservation])
    await db_session.flush()

    first_attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(first_attempt)
    await db_session.flush()
    db_session.add_all(
        [
            PaymentAttemptReservation(
                attempt_id=first_attempt.id, reservation_id=reservation.id
            )
            for reservation in (first_reservation, second_reservation)
        ]
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    with pytest.raises(DBAPIError, match="payment attempt already active for order"):
        async with db_session.begin_nested():
            db_session.add(
                lane._payment_attempt(
                    graph,
                    alternate_intent,
                    alternate_quote,
                    alternate_option,
                    alternate_selection,
                    customer_user["user"].id,
                )
            )
            await db_session.flush()

    evidence = PaymentAttemptEvidence(
        attempt_id=first_attempt.id,
        source="payment_worker",
        event_id=f"failed-{uuid.uuid4().hex}",
        evidence_type="payment_failed",
        evidence_hash="8" * 64,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='failed', terminal_evidence_id=:evidence_id, "
            "row_version=row_version+1 WHERE id=:attempt_id"
        ),
        {"evidence_id": evidence.id, "attempt_id": first_attempt.id},
    )

    retry = lane._payment_attempt(
        graph,
        alternate_intent,
        alternate_quote,
        alternate_option,
        alternate_selection,
        customer_user["user"].id,
        supersedes_attempt_id=first_attempt.id,
    )
    db_session.add(retry)
    await db_session.flush()
    db_session.add_all(
        [
            PaymentAttemptReservation(
                attempt_id=retry.id, reservation_id=reservation.id
            )
            for reservation in (first_reservation, second_reservation)
        ]
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.asyncio
async def test_in_flight_authorization_grace_keeps_inventory_and_can_verify(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    (
        competing_graph,
        competing_intent,
        competing_quote,
        competing_option,
        competing_selection,
        _,
    ) = await lane._checkout_subject(db_session, vendor_user, customer_user, stock=1)
    competing_graph["item"].product_id = graph["item"].product_id
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        ttl_seconds=1,
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        payment_window_seconds=1,
        authorization_grace_seconds=5,
        claim_ttl_seconds=5,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:lease_token, "
            "row_version=row_version+1 WHERE id=:attempt_id"
        ),
        {"lease_token": lease_token, "attempt_id": attempt.id},
    )
    await db_session.commit()
    await asyncio.sleep(1.1)

    competing = lane._reservation(
        competing_graph,
        competing_intent,
        competing_quote,
        competing_option,
        competing_selection,
        customer_user["user"].id,
        sku,
    )
    with pytest.raises(
        DBAPIError, match="stock reservation exceeds available inventory"
    ):
        async with db_session.begin_nested():
            db_session.add(competing)
            await db_session.flush()

    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="provider_webhook",
        event_id=f"grace-verified-{uuid.uuid4().hex}",
        evidence_type="payment_verified",
        evidence_hash="9" * 64,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()
    await _present_payment_lease(db_session, lease_token)
    await _coordinate_attempt(db_session, attempt.id, graph["order"].id)
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='verified', terminal_evidence_id=:evidence_id, "
            "row_version=row_version+1 WHERE id=:attempt_id"
        ),
        {"evidence_id": evidence.id, "attempt_id": attempt.id},
    )


@pytest.mark.asyncio
async def test_in_flight_authorization_grace_keeps_inventory_identity_immutable(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        ttl_seconds=1,
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        payment_window_seconds=1,
        authorization_grace_seconds=5,
        claim_ttl_seconds=5,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": uuid.uuid4(), "attempt_id": attempt.id},
    )
    await db_session.commit()
    await asyncio.sleep(1.1)

    with pytest.raises(DBAPIError, match="reserved product identity is immutable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE products SET sku=:sku WHERE id=:product_id"),
                {
                    "sku": f"grace-{uuid.uuid4().hex[:8]}",
                    "product_id": graph["item"].product_id,
                },
            )


@pytest.mark.asyncio
async def test_expired_call_lease_keeps_inventory_identity_unresolved(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": uuid.uuid4(), "attempt_id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE stock_reservations SET created_at=statement_timestamp() - interval '2 seconds', "
            "expires_at=statement_timestamp() - interval '1 second' WHERE id=:reservation_id"
        ),
        {"reservation_id": reservation.id},
    )
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET claim_expires_at=statement_timestamp() - interval '1 second' "
            "WHERE id=:attempt_id"
        ),
        {"attempt_id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))

    with pytest.raises(DBAPIError, match="reserved product identity is immutable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE products SET sku=:sku WHERE id=:product_id"),
                {
                    "sku": f"expired-lease-{uuid.uuid4().hex[:8]}",
                    "product_id": graph["item"].product_id,
                },
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("truth_target", ["order_item", "order"])
async def test_reservation_locks_order_truth_before_waiting_on_inventory(
    db_session, vendor_user, customer_user, truth_target
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    inventory_locker = factory()
    reserver = factory()
    truth_editor = factory()
    observer = factory()
    try:
        await inventory_locker.execute(
            text("SELECT 1 FROM products WHERE id=:product_id FOR UPDATE"),
            {"product_id": graph["item"].product_id},
        )

        async def reserve_unit():
            candidate = lane._reservation(
                graph,
                intent,
                quote,
                option,
                selection,
                customer_user["user"].id,
                sku,
            )
            reserver.add(candidate)
            try:
                await reserver.flush()
                await reserver.commit()
                return None
            except DBAPIError as exc:
                await reserver.rollback()
                return str(exc)

        reserver_pid = await reserver.scalar(text("SELECT pg_backend_pid()"))
        reserve_task = asyncio.create_task(reserve_unit())
        await _wait_for_postgres_lock(observer, reserver_pid)

        async def edit_truth():
            try:
                if truth_target == "order_item":
                    await truth_editor.execute(
                        text(
                            "UPDATE order_items SET unit_price=unit_price + 1 "
                            "WHERE id=:subject_id"
                        ),
                        {"subject_id": graph["item"].id},
                    )
                else:
                    await truth_editor.execute(
                        text(
                            "UPDATE orders SET total_amount=total_amount + 1 "
                            "WHERE id=:subject_id"
                        ),
                        {"subject_id": graph["order"].id},
                    )
                await truth_editor.commit()
                return None
            except DBAPIError as exc:
                await truth_editor.rollback()
                return str(exc)

        truth_editor_pid = await truth_editor.scalar(text("SELECT pg_backend_pid()"))
        edit_task = asyncio.create_task(edit_truth())
        await _wait_for_postgres_lock(observer, truth_editor_pid)
        await inventory_locker.commit()
        reserve_result = await asyncio.wait_for(reserve_task, timeout=5)
        edit_result = await asyncio.wait_for(edit_task, timeout=5)
        assert reserve_result is None
        expected = (
            "reserved order item truth is immutable"
            if truth_target == "order_item"
            else "reserved order payment truth is immutable"
        )
        assert edit_result is not None
        assert expected in edit_result
    finally:
        await inventory_locker.close()
        await reserver.close()
        await truth_editor.close()
        await observer.close()


@pytest.mark.asyncio
async def test_reservation_quantity_cannot_exceed_quoted_package_composition(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=3
    )
    oversized = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        quantity=2,
        line_amount=graph["item"].unit_price * 2,
    )
    with pytest.raises(
        DBAPIError, match="stock reservation exceeds quoted package item quantity"
    ):
        async with db_session.begin_nested():
            db_session.add(oversized)
            await db_session.flush()


@pytest.mark.asyncio
async def test_payment_attempt_requires_exact_quoted_package_composition(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, _intent, _quote, _option, _selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=3
    )
    intent, quote, option, selection = await _alternate_selection(
        db_session,
        lane,
        graph,
        customer_user["user"].id,
        quantity=2,
    )
    partial = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        quantity=1,
        line_amount=graph["item"].unit_price,
    )
    db_session.add(partial)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=partial.id)
    )
    await db_session.flush()
    with pytest.raises(
        DBAPIError, match="payment attempt must cover exact quoted package composition"
    ):
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.asyncio
async def test_order_total_payment_attempt_requires_every_selected_package_reservation(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=3
    )
    alternate = await _alternate_selection(
        db_session, lane, graph, customer_user["user"].id
    )
    alternate_intent, alternate_quote, alternate_option, alternate_selection = alternate
    first = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    second = lane._reservation(
        graph,
        alternate_intent,
        alternate_quote,
        alternate_option,
        alternate_selection,
        customer_user["user"].id,
        sku,
    )
    db_session.add_all([first, second])
    await db_session.flush()

    with pytest.raises(
        DBAPIError, match="payment attempt must cover the exact active reservation set"
    ):
        async with db_session.begin_nested():
            attempt = lane._payment_attempt(
                graph, intent, quote, option, selection, customer_user["user"].id
            )
            db_session.add(attempt)
            await db_session.flush()
            db_session.add(
                PaymentAttemptReservation(
                    attempt_id=attempt.id, reservation_id=first.id
                )
            )
            await db_session.flush()
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.asyncio
async def test_order_total_payment_attempt_accepts_all_selected_package_reservations(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=3
    )
    alternate = await _alternate_selection(
        db_session, lane, graph, customer_user["user"].id
    )
    alternate_intent, alternate_quote, alternate_option, alternate_selection = alternate
    reservations = [
        lane._reservation(
            graph, intent, quote, option, selection, customer_user["user"].id, sku
        ),
        lane._reservation(
            graph,
            alternate_intent,
            alternate_quote,
            alternate_option,
            alternate_selection,
            customer_user["user"].id,
            sku,
        ),
    ]
    db_session.add_all(reservations)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add_all(
        [
            PaymentAttemptReservation(
                attempt_id=attempt.id, reservation_id=reservation.id
            )
            for reservation in reservations
        ]
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.asyncio
async def test_repacked_order_requires_only_non_invalidated_selected_package(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, old_intent, _old_quote, _old_option, _old_selection, sku = (
        await lane._checkout_subject(db_session, vendor_user, customer_user, stock=3)
    )
    await _invalidate_intent(db_session, old_intent, graph["operator_id"])
    replacement = await _alternate_selection(
        db_session, lane, graph, customer_user["user"].id
    )
    intent, quote, option, selection = replacement
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()

    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.asyncio
async def test_repacked_multi_package_attempt_revalidates_only_current_selections(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, old_intent, _old_quote, _old_option, _old_selection, sku = (
        await lane._checkout_subject(db_session, vendor_user, customer_user, stock=4)
    )
    await _invalidate_intent(db_session, old_intent, graph["operator_id"])
    replacement = await _alternate_selection(
        db_session, lane, graph, customer_user["user"].id
    )
    attempt, _second_current_intent = await _multi_package_attempt_subject(
        db_session,
        lane,
        graph,
        replacement,
        customer_user["user"].id,
        sku,
    )

    await _transition_multi_package_attempt(db_session, attempt, "verified")

    assert (
        await db_session.scalar(
            text("SELECT state FROM payment_attempts WHERE id=:attempt_id"),
            {"attempt_id": attempt.id},
        )
        == "verified"
    )


@pytest.mark.asyncio
async def test_cohort_split_package_quantity_is_aggregated_for_reservation_and_attempt(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=3
    )
    await _split_package_item_across_cohorts(db_session, graph, quote)
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        quantity=3,
        line_amount=graph["item"].unit_price * 3,
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.asyncio
async def test_split_reservations_accept_inventory_deducted_by_order_creation(
    db_session, vendor_user, customer_user
) -> None:
    """A durable order deduction supports split reservations without double charging."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=4
    )
    assert graph["item"].quantity == 3
    await _split_package_item_across_cohorts(db_session, graph, quote)
    await db_session.execute(
        text(
            "UPDATE products SET total_stock = total_stock - :quantity "
            "WHERE id = :product_id"
        ),
        {"quantity": graph["item"].quantity, "product_id": graph["item"].product_id},
    )
    deduction = await db_session.execute(
        text(
            "SELECT order_item_id, product_id, event_type, quantity "
            "FROM inventory_deduction_events"
        )
    )
    assert deduction.one() == (
        graph["item"].id,
        graph["item"].product_id,
        "deducted",
        graph["item"].quantity,
    )
    with pytest.raises(
        DBAPIError,
        match="inventory deduction provenance is append-only and trigger-owned",
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO inventory_deduction_events "
                    "(id, order_item_id, product_id, event_type, quantity) "
                    "VALUES (:id, :item_id, :product_id, 'restored', :quantity)"
                ),
                {
                    "id": uuid.uuid4(),
                    "item_id": graph["item"].id,
                    "product_id": graph["item"].product_id,
                    "quantity": graph["item"].quantity,
                },
            )

    first = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        quantity=2,
        line_amount=graph["item"].unit_price * 2,
    )
    second = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(first)
    await db_session.flush()
    db_session.add(second)
    await db_session.flush()

    remaining_stock = await db_session.scalar(
        text("SELECT total_stock FROM products WHERE id = :product_id"),
        {"product_id": graph["item"].product_id},
    )
    assert remaining_stock == 1


@pytest.mark.asyncio
async def test_reservation_rejects_non_deducted_direct_sql_oversell(
    db_session, vendor_user, customer_user
) -> None:
    """Order-item quantity alone is not proof that inventory was deducted."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    assert graph["item"].quantity == 3
    await _split_package_item_across_cohorts(db_session, graph, quote)
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        quantity=2,
        line_amount=graph["item"].unit_price * 2,
    )

    with pytest.raises(
        DBAPIError, match="stock reservation exceeds available inventory"
    ):
        async with db_session.begin_nested():
            db_session.add(reservation)
            await db_session.flush()


@pytest.mark.asyncio
async def test_inventory_deduction_provenance_rolls_back_with_stock_change(
    db_session, vendor_user, customer_user
) -> None:
    """A rolled-back deduction cannot leave durable provenance credit."""

    lane = _lane_helpers()
    graph, *_ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=4
    )

    with pytest.raises(RuntimeError, match="force inventory rollback"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE products SET total_stock = total_stock - :quantity "
                    "WHERE id = :product_id"
                ),
                {
                    "quantity": graph["item"].quantity,
                    "product_id": graph["item"].product_id,
                },
            )
            raise RuntimeError("force inventory rollback")

    assert (
        await db_session.scalar(
            text("SELECT total_stock FROM products WHERE id = :product_id"),
            {"product_id": graph["item"].product_id},
        )
        == 4
    )
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM inventory_deduction_events "
                "WHERE order_item_id = :item_id"
            ),
            {"item_id": graph["item"].id},
        )
        == 0
    )


@pytest.mark.asyncio
async def test_cancellation_restoration_nets_only_prior_deduction_provenance(
    db_session, vendor_user, customer_user
) -> None:
    """Cancellation restoration nets a real deduction but cannot fabricate one."""

    lane = _lane_helpers()
    graph, *_ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=4
    )
    await db_session.execute(
        text(
            "UPDATE products SET total_stock = total_stock - :quantity "
            "WHERE id = :product_id"
        ),
        {
            "quantity": graph["item"].quantity,
            "product_id": graph["item"].product_id,
        },
    )
    await db_session.execute(
        text("UPDATE orders SET fulfillment_status = 'cancelled' WHERE id = :order_id"),
        {"order_id": graph["order"].id},
    )
    await db_session.execute(
        text(
            "UPDATE products SET total_stock = total_stock + :quantity "
            "WHERE id = :product_id"
        ),
        {
            "quantity": graph["item"].quantity,
            "product_id": graph["item"].product_id,
        },
    )

    events = (
        await db_session.execute(
            text(
                "SELECT event_type, quantity FROM inventory_deduction_events "
                "WHERE order_item_id = :item_id ORDER BY event_type"
            ),
            {"item_id": graph["item"].id},
        )
    ).all()
    assert events == [
        ("deducted", graph["item"].quantity),
        ("restored", graph["item"].quantity),
    ]

    undeducted, *_ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=4
    )
    await db_session.execute(
        text("UPDATE orders SET fulfillment_status = 'cancelled' WHERE id = :order_id"),
        {"order_id": undeducted["order"].id},
    )
    await db_session.execute(
        text(
            "UPDATE products SET total_stock = total_stock + :quantity "
            "WHERE id = :product_id"
        ),
        {
            "quantity": undeducted["item"].quantity,
            "product_id": undeducted["item"].product_id,
        },
    )
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM inventory_deduction_events "
                "WHERE order_item_id = :item_id"
            ),
            {"item_id": undeducted["item"].id},
        )
        == 0
    )


@pytest.mark.asyncio
async def test_payment_attempt_rejects_unreserved_selected_package(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=3
    )
    await _alternate_selection(db_session, lane, graph, customer_user["user"].id)
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()

    with pytest.raises(
        DBAPIError, match="payment attempt must cover exact quoted package composition"
    ):
        await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.asyncio
async def test_payment_attempt_rejects_cancelled_order_authoritative_status(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    await db_session.execute(
        text("UPDATE orders SET fulfillment_status = 'cancelled' WHERE id = :order_id"),
        {"order_id": graph["order"].id},
    )

    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    with pytest.raises(DBAPIError, match="cancelled order cannot start payment"):
        async with db_session.begin_nested():
            db_session.add(attempt)
            await db_session.flush()


@pytest.mark.asyncio
async def test_payment_attempt_rejects_already_paid_order(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    await db_session.execute(
        text("UPDATE orders SET payment_status='PAID' WHERE id=:order_id"),
        {"order_id": graph["order"].id},
    )
    with pytest.raises(DBAPIError, match="paid order cannot start payment"):
        async with db_session.begin_nested():
            db_session.add(
                lane._payment_attempt(
                    graph, intent, quote, option, selection, customer_user["user"].id
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_historical_reservation_does_not_block_product_sku_edit(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE stock_reservations SET state='released', terminal_reason='checkout abandoned', "
            "row_version=row_version+1 WHERE id=:reservation_id"
        ),
        {"reservation_id": reservation.id},
    )
    await db_session.execute(
        text("UPDATE products SET sku=:sku WHERE id=:product_id"),
        {
            "sku": f"replacement-{uuid.uuid4().hex[:8]}",
            "product_id": graph["item"].product_id,
        },
    )


async def _invalidate_intent(session, intent, operator_id) -> None:
    from app.models.package_custody import OutboundShipmentIntentInvalidation

    now = datetime.now(timezone.utc)
    session.add(
        OutboundShipmentIntentInvalidation(
            intent_id=intent.id,
            reason="package replaced",
            actor_type="user",
            actor_id=str(operator_id),
            source_command="invalidate_outbound_intent",
            idempotency_key=f"invalidate-{uuid.uuid4().hex}",
            invalidated_at=now,
            created_at=now,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_reservation_rejects_invalidated_outbound_intent(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user
    )
    await _invalidate_intent(db_session, intent, graph["operator_id"])
    with pytest.raises(
        DBAPIError, match="stock reservation subject binding is invalid"
    ):
        async with db_session.begin_nested():
            db_session.add(
                lane._reservation(
                    graph,
                    intent,
                    quote,
                    option,
                    selection,
                    customer_user["user"].id,
                    sku,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_payment_rejects_intent_invalidated_after_reservation(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    await _invalidate_intent(db_session, intent, graph["operator_id"])
    with pytest.raises(DBAPIError, match="payment attempt subject binding is invalid"):
        async with db_session.begin_nested():
            db_session.add(
                lane._payment_attempt(
                    graph, intent, quote, option, selection, customer_user["user"].id
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_pending_attempt_rechecks_order_cancellation_before_provider_call(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await db_session.execute(
        text("UPDATE orders SET fulfillment_status='cancelled' WHERE id=:order_id"),
        {"order_id": graph["order"].id},
    )

    with pytest.raises(DBAPIError, match="cancelled order cannot start payment call"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                    "row_version=2 WHERE id=:attempt_id"
                ),
                {"token": uuid.uuid4(), "attempt_id": attempt.id},
            )


@pytest.mark.asyncio
async def test_cancellation_wins_race_before_provider_call_starts(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    canceller = factory()
    caller = factory()
    call_task = None
    try:
        await canceller.execute(
            text("UPDATE orders SET fulfillment_status='cancelled' WHERE id=:order_id"),
            {"order_id": graph["order"].id},
        )

        async def start_provider_call():
            try:
                await _coordinate_attempt(caller, attempt.id, graph["order"].id)
                await caller.execute(
                    text(
                        "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                        "row_version=2 WHERE id=:attempt_id"
                    ),
                    {"token": uuid.uuid4(), "attempt_id": attempt.id},
                )
                await caller.commit()
                return None
            except DBAPIError as exc:
                await caller.rollback()
                return str(exc)

        call_task = asyncio.create_task(start_provider_call())
        await asyncio.sleep(0.2)
        assert not call_task.done()
        await canceller.commit()
        result = await asyncio.wait_for(call_task, timeout=5)
        assert result is not None
        assert "cancelled order cannot start payment call" in result
    finally:
        if call_task is not None and not call_task.done():
            call_task.cancel()
            await asyncio.gather(call_task, return_exceptions=True)
        await canceller.rollback()
        await caller.rollback()
        await canceller.close()
        await caller.close()


@pytest.mark.asyncio
async def test_unknown_outcome_keeps_linked_reservation_locked_after_ttl(
    db_session, vendor_user, customer_user
) -> None:
    *_, reservation, _attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    await _expire_reservation_without_lifecycle_transition(db_session, reservation.id)

    with pytest.raises(
        DBAPIError, match="reservation set is locked by active payment attempt"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE stock_reservations SET state='expired', "
                    "terminal_reason='ttl elapsed', row_version=2 WHERE id=:reservation_id"
                ),
                {"reservation_id": reservation.id},
            )


@pytest.mark.asyncio
async def test_unknown_outcome_blocks_shipment_intent_invalidation(
    db_session, vendor_user, customer_user
) -> None:
    _lane, graph, intent, *_ = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )

    with pytest.raises(
        DBAPIError, match="payment attempt prevents intent invalidation"
    ):
        async with db_session.begin_nested():
            await _invalidate_intent(db_session, intent, graph["operator_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attempt_state", ["call_started", "abandoned_unknown", "verified"]
)
async def test_full_order_attempt_fences_every_linked_package_intent(
    db_session, vendor_user, customer_user, attempt_state
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=2
    )
    attempt, alternate_intent = await _multi_package_attempt_subject(
        db_session,
        lane,
        graph,
        (intent, quote, option, selection),
        customer_user["user"].id,
        sku,
    )
    await _transition_multi_package_attempt(db_session, attempt, attempt_state)

    with pytest.raises(
        DBAPIError, match="payment attempt prevents intent invalidation"
    ):
        async with db_session.begin_nested():
            await _invalidate_intent(db_session, alternate_intent, graph["operator_id"])


@pytest.mark.asyncio
async def test_full_order_call_start_rejects_invalidated_linked_package_intent(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=2
    )
    attempt, alternate_intent = await _multi_package_attempt_subject(
        db_session,
        lane,
        graph,
        (intent, quote, option, selection),
        customer_user["user"].id,
        sku,
    )
    await _invalidate_intent(db_session, alternate_intent, graph["operator_id"])

    with pytest.raises(
        DBAPIError, match="invalidated intent cannot start payment call"
    ):
        async with db_session.begin_nested():
            await _transition_multi_package_attempt(db_session, attempt, "call_started")


@pytest.mark.asyncio
async def test_full_order_verification_rechecks_every_linked_package_intent(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=2
    )
    attempt, alternate_intent = await _multi_package_attempt_subject(
        db_session,
        lane,
        graph,
        (intent, quote, option, selection),
        customer_user["user"].id,
        sku,
    )
    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": lease_token, "attempt_id": attempt.id},
    )
    # Model an invalidation committed by the pre-fix fence or imported historical data.
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await _invalidate_intent(db_session, alternate_intent, graph["operator_id"])
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="provider_reconciliation",
        event_id=f"multi-package-verify-{uuid.uuid4().hex}",
        evidence_type="payment_verified",
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()
    await _present_payment_lease(db_session, lease_token)

    with pytest.raises(DBAPIError, match="invalidated intent cannot verify payment"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='verified', "
                    "terminal_evidence_id=:evidence_id, row_version=3 "
                    "WHERE id=:attempt_id"
                ),
                {"evidence_id": evidence.id, "attempt_id": attempt.id},
            )


@pytest.mark.asyncio
async def test_unknown_outcome_keeps_inventory_identity_live_after_ttl(
    db_session, vendor_user, customer_user
) -> None:
    _lane, graph, _intent, *_prefix, reservation, _attempt = (
        await _abandoned_unknown_subject(db_session, vendor_user, customer_user)
    )
    await _expire_reservation_without_lifecycle_transition(db_session, reservation.id)

    with pytest.raises(DBAPIError, match="reserved product identity is immutable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE products SET sku=:sku WHERE id=:product_id"),
                {
                    "sku": f"replacement-{uuid.uuid4().hex[:8]}",
                    "product_id": graph["item"].product_id,
                },
            )


def test_migration_quarantines_ambiguous_legacy_inventory_deductions() -> None:
    migration = (
        Path(__file__).parents[1]
        / "alembic/versions/f9d1b3e5a7c9_add_stock_payment_persistence.py"
    ).read_text(encoding="utf-8")
    assert "Conservatively leave ambiguous legacy deductions uncredited" in migration
    assert "INSERT INTO inventory_deduction_events" not in migration


def test_frozen_alembic_program_uses_valid_rowtype_syntax() -> None:
    frozen = (Path(__file__).parents[1] / "alembic/stock_payment_ddl_f9.py").read_text(
        encoding="utf-8"
    )
    assert "payment_attempts%ROWTYPE" in frozen
    assert "payment_attempts%%ROWTYPE" not in frozen


@pytest.mark.asyncio
async def test_unresolved_provider_call_blocks_late_order_cancellation(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(reservation)
    await db_session.flush()
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": uuid.uuid4(), "attempt_id": attempt.id},
    )

    with pytest.raises(
        DBAPIError, match="unresolved or verified payment prevents order cancellation"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE orders SET fulfillment_status='cancelled' WHERE id=:order_id"
                ),
                {"order_id": graph["order"].id},
            )


def test_capacity_credit_covers_every_counted_order_item() -> None:
    source = (
        Path(__file__).parents[1] / "app/models/stock_payment_persistence.py"
    ).read_text(encoding="utf-8")
    assert "SELECT DISTINCT sr.order_item_id" in source
    assert "UNION SELECT NEW.order_item_id" in source
    assert "GROUP BY ide.order_item_id" in source


def test_stock_update_guard_nets_durable_deduction_credit() -> None:
    source = (
        Path(__file__).parents[1] / "app/models/stock_payment_persistence.py"
    ).read_text(encoding="utf-8")
    assert "deducted_quantity bigint" in source
    assert source.count("new_stock + deducted_quantity < active_quantity") == 3


def test_unknown_attempt_has_evidence_backed_reconciliation_path() -> None:
    source = (
        Path(__file__).parents[1] / "app/models/stock_payment_persistence.py"
    ).read_text(encoding="utf-8")
    assert "OLD.state = 'abandoned_unknown'" in source
    assert (
        "attempt_state NOT IN ('pending', 'call_started', 'abandoned_unknown')"
        in source
    )


def test_unresolved_reservations_keep_inventory_identity_live_after_ttl() -> None:
    source = (
        Path(__file__).parents[1] / "app/models/stock_payment_persistence.py"
    ).read_text(encoding="utf-8")
    assert source.count("pa.state IN ('verified', 'abandoned_unknown')") >= 15
    assert "Its inventory identity stays live" in source


def test_intent_invalidation_is_fenced_by_payment_outcome() -> None:
    source = (
        Path(__file__).parents[1] / "app/models/stock_payment_persistence.py"
    ).read_text(encoding="utf-8")
    assert "protect_payment_intent_invalidation" in source
    assert "ORDER BY pa.id FOR UPDATE OF pa" in source
    assert "pa.state IN ('call_started', 'abandoned_unknown', 'verified')" in source
    assert "payment attempt prevents intent invalidation" in source


async def _attempt_with_late_selection_candidate(session, vendor_user, customer_user):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        session, vendor_user, customer_user, stock=2
    )
    alternate_intent, alternate_quote, alternate_option, _ = await _alternate_selection(
        session,
        lane,
        graph,
        customer_user["user"].id,
        selected=False,
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    session.add(reservation)
    await session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    session.add(attempt)
    await session.flush()
    session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await session.flush()
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    return (
        lane,
        graph,
        attempt,
        alternate_intent,
        alternate_quote,
        alternate_option,
    )


def _late_selection(graph, customer_id, intent, quote, option):
    from app.models.customer_shipping_quote import CustomerShippingQuoteSelection

    return CustomerShippingQuoteSelection(
        quote_id=quote.id,
        intent_id=intent.id,
        option_id=option.id,
        customer_id=customer_id,
        selected_by_id=customer_id,
        source_command="select_shipping_quote_option",
        idempotency_key=f"late-selection-{uuid.uuid4().hex}",
        selected_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("attempt_state", "legacy_write_blocked", "selection_blocked"),
    [
        ("pending", True, True),
        ("call_started", True, True),
        ("abandoned_unknown", True, True),
        ("verified", False, True),
        ("failed", False, False),
        ("expired", False, False),
    ],
)
async def test_attempt_state_cartesian_interlock_matrix(
    db_session,
    vendor_user,
    customer_user,
    attempt_state,
    legacy_write_blocked,
    selection_blocked,
) -> None:
    (
        _lane,
        graph,
        attempt,
        alternate_intent,
        alternate_quote,
        alternate_option,
    ) = await _attempt_with_late_selection_candidate(
        db_session, vendor_user, customer_user
    )
    await _set_attempt_state_for_interlock_matrix(db_session, attempt, attempt_state)

    legacy_savepoint = await db_session.begin_nested()
    try:
        if legacy_write_blocked:
            with pytest.raises(
                DBAPIError, match="payment attempt prevents legacy payment status write"
            ):
                await db_session.execute(
                    text("UPDATE orders SET payment_status='PAID' WHERE id=:order_id"),
                    {"order_id": graph["order"].id},
                )
        else:
            await db_session.execute(
                text("UPDATE orders SET payment_status='PAID' WHERE id=:order_id"),
                {"order_id": graph["order"].id},
            )
    finally:
        await legacy_savepoint.rollback()

    late = _late_selection(
        graph,
        customer_user["user"].id,
        alternate_intent,
        alternate_quote,
        alternate_option,
    )
    selection_savepoint = await db_session.begin_nested()
    try:
        db_session.add(late)
        if selection_blocked:
            with pytest.raises(
                DBAPIError, match="payment attempt prevents later package selection"
            ):
                await db_session.flush()
        else:
            await db_session.flush()
    finally:
        await selection_savepoint.rollback()


@pytest.mark.asyncio
async def test_call_start_rejects_historical_late_selected_package(
    db_session, vendor_user, customer_user
) -> None:
    (
        _lane,
        graph,
        attempt,
        alternate_intent,
        alternate_quote,
        alternate_option,
    ) = await _attempt_with_late_selection_candidate(
        db_session, vendor_user, customer_user
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    db_session.add(
        _late_selection(
            graph,
            customer_user["user"].id,
            alternate_intent,
            alternate_quote,
            alternate_option,
        )
    )
    await db_session.flush()
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))

    with pytest.raises(
        DBAPIError, match="payment attempt selected package set changed"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                    "row_version=2 WHERE id=:attempt_id"
                ),
                {"token": uuid.uuid4(), "attempt_id": attempt.id},
            )


@pytest.mark.asyncio
async def test_verification_rejects_historical_late_selected_package(
    db_session, vendor_user, customer_user
) -> None:
    (
        _lane,
        graph,
        attempt,
        alternate_intent,
        alternate_quote,
        alternate_option,
    ) = await _attempt_with_late_selection_candidate(
        db_session, vendor_user, customer_user
    )
    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": lease_token, "attempt_id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    db_session.add(
        _late_selection(
            graph,
            customer_user["user"].id,
            alternate_intent,
            alternate_quote,
            alternate_option,
        )
    )
    await db_session.flush()
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="interlock_matrix",
        event_id=f"late-verify-{uuid.uuid4().hex}",
        evidence_type="payment_verified",
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()
    await _present_payment_lease(db_session, lease_token)

    with pytest.raises(
        DBAPIError, match="payment attempt selected package set changed"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='verified', "
                    "terminal_evidence_id=:evidence_id, row_version=3 "
                    "WHERE id=:attempt_id"
                ),
                {"evidence_id": evidence.id, "attempt_id": attempt.id},
            )


@pytest.mark.asyncio
async def test_call_start_serializes_before_late_selection_across_connections(
    db_session, vendor_user, customer_user
) -> None:
    (
        _lane,
        graph,
        attempt,
        alternate_intent,
        alternate_quote,
        alternate_option,
    ) = await _attempt_with_late_selection_candidate(
        db_session, vendor_user, customer_user
    )
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    caller = factory()
    selector = factory()
    selection_task = None
    try:
        await _coordinate_attempt(caller, attempt.id, graph["order"].id)
        await caller.execute(
            text(
                "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                "row_version=2 WHERE id=:attempt_id"
            ),
            {"token": uuid.uuid4(), "attempt_id": attempt.id},
        )

        async def select_late_package():
            selector.add(
                _late_selection(
                    graph,
                    customer_user["user"].id,
                    alternate_intent,
                    alternate_quote,
                    alternate_option,
                )
            )
            try:
                await selector.flush()
                await selector.commit()
                return None
            except DBAPIError as exc:
                await selector.rollback()
                return str(exc)

        selection_task = asyncio.create_task(select_late_package())
        await asyncio.sleep(0.2)
        assert not selection_task.done()
        await caller.commit()
        result = await asyncio.wait_for(selection_task, timeout=5)
        assert result is not None
        assert "payment attempt prevents later package selection" in result
    finally:
        if selection_task is not None and not selection_task.done():
            selection_task.cancel()
            await asyncio.gather(selection_task, return_exceptions=True)
        await caller.rollback()
        await selector.rollback()
        await caller.close()
        await selector.close()


@pytest.mark.asyncio
async def test_legacy_payment_write_serializes_before_call_start(
    db_session, vendor_user, customer_user
) -> None:
    (
        _lane,
        graph,
        attempt,
        _alternate_intent,
        _alternate_quote,
        _alternate_option,
    ) = await _attempt_with_late_selection_candidate(
        db_session, vendor_user, customer_user
    )
    await db_session.commit()
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    legacy = factory()
    caller = factory()
    call_task = None
    try:
        await legacy.execute(
            text("UPDATE orders SET updated_at=updated_at WHERE id=:order_id"),
            {"order_id": graph["order"].id},
        )

        async def start_call():
            await _coordinate_attempt(caller, attempt.id, graph["order"].id)
            await caller.execute(
                text(
                    "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                    "row_version=2 WHERE id=:attempt_id"
                ),
                {"token": uuid.uuid4(), "attempt_id": attempt.id},
            )
            await caller.commit()

        call_task = asyncio.create_task(start_call())
        await asyncio.sleep(0.2)
        assert not call_task.done()
        with pytest.raises(
            DBAPIError, match="payment attempt prevents legacy payment status write"
        ):
            async with legacy.begin_nested():
                await legacy.execute(
                    text("UPDATE orders SET payment_status='PAID' WHERE id=:order_id"),
                    {"order_id": graph["order"].id},
                )
        await legacy.rollback()
        await asyncio.wait_for(call_task, timeout=5)
    finally:
        if call_task is not None and not call_task.done():
            call_task.cancel()
            await asyncio.gather(call_task, return_exceptions=True)
        await legacy.rollback()
        await caller.rollback()
        await legacy.close()
        await caller.close()


def test_verified_payment_blocks_late_order_cancellation() -> None:
    source = (
        Path(__file__).parents[1] / "app/models/stock_payment_persistence.py"
    ).read_text(encoding="utf-8")
    assert "pa.state IN ('call_started', 'abandoned_unknown', 'verified')" in source
    assert "unresolved or verified payment prevents order cancellation" in source


async def _pending_call_race_subject(
    session, vendor_user, customer_user, *, include_competing_order: bool = False
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        session, vendor_user, customer_user, stock=1
    )
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        ttl_seconds=1,
    )
    session.add(reservation)
    await session.flush()
    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        payment_window_seconds=1,
        authorization_grace_seconds=5,
        claim_ttl_seconds=5,
    )
    session.add(attempt)
    await session.flush()
    session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await session.flush()
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    competing = None
    if include_competing_order:
        other_graph, other_intent, other_quote, other_option, other_selection, _ = (
            await lane._checkout_subject(session, vendor_user, customer_user, stock=1)
        )
        other_graph["item"].product_id = graph["item"].product_id
        await session.flush()
        competing = lane._reservation(
            other_graph,
            other_intent,
            other_quote,
            other_option,
            other_selection,
            customer_user["user"].id,
            sku,
        )

    await session.commit()
    return lane, graph, reservation, attempt, competing


@pytest.mark.asyncio
async def test_uncommitted_call_start_fences_identity_mutation_across_reservation_ttl(
    db_session, vendor_user, customer_user
) -> None:
    _lane, graph, _reservation_row, attempt, _competing = (
        await _pending_call_race_subject(db_session, vendor_user, customer_user)
    )
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    caller = factory()
    mutator = factory()
    observer = factory()
    mutation_task = None
    replacement_sku = f"raced-{uuid.uuid4().hex[:8]}"
    try:
        await _coordinate_attempt(caller, attempt.id, graph["order"].id)
        await _refresh_call_start_deadlines(caller, _reservation_row.id, attempt.id)
        await caller.execute(
            text(
                "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                "row_version=2 WHERE id=:attempt_id"
            ),
            {"token": uuid.uuid4(), "attempt_id": attempt.id},
        )
        await _expire_reservation_without_lifecycle_transition(
            caller, _reservation_row.id
        )

        async def mutate_identity():
            try:
                await _coordinate(mutator, ("product", graph["item"].product_id))
                await mutator.execute(
                    text("UPDATE products SET sku=:sku WHERE id=:product_id"),
                    {"sku": replacement_sku, "product_id": graph["item"].product_id},
                )
                await mutator.commit()
                return None
            except DBAPIError as exc:
                await mutator.rollback()
                return str(exc)

        mutator_pid = await mutator.scalar(text("SELECT pg_backend_pid()"))
        mutation_task = asyncio.create_task(mutate_identity())
        await _wait_for_postgres_lock(observer, mutator_pid)
        assert not mutation_task.done()
        await caller.commit()
        result = await asyncio.wait_for(mutation_task, timeout=5)
        assert result is not None
        assert "reserved product identity is immutable" in result
    finally:
        if mutation_task is not None and not mutation_task.done():
            mutation_task.cancel()
            await asyncio.gather(mutation_task, return_exceptions=True)
        await caller.rollback()
        await mutator.rollback()
        await observer.rollback()
        await caller.close()
        await mutator.close()
        await observer.close()


@pytest.mark.asyncio
async def test_uncommitted_call_start_fences_competing_reservation_across_ttl(
    db_session, vendor_user, customer_user
) -> None:
    _lane, _graph, _reservation_row, attempt, competing = (
        await _pending_call_race_subject(
            db_session, vendor_user, customer_user, include_competing_order=True
        )
    )
    assert competing is not None
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    caller = factory()
    reserver = factory()
    observer = factory()
    reservation_task = None
    try:
        await _coordinate_attempt(caller, attempt.id, attempt.order_id)
        await _refresh_call_start_deadlines(caller, _reservation_row.id, attempt.id)
        await caller.execute(
            text(
                "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                "row_version=2 WHERE id=:attempt_id"
            ),
            {"token": uuid.uuid4(), "attempt_id": attempt.id},
        )
        await _expire_reservation_without_lifecycle_transition(
            caller, _reservation_row.id
        )

        async def reserve_competing_unit():
            try:
                reserver.add(competing)
                await reserver.flush()
                await reserver.commit()
                return None
            except DBAPIError as exc:
                await reserver.rollback()
                return str(exc)

        reserver_pid = await reserver.scalar(text("SELECT pg_backend_pid()"))
        reservation_task = asyncio.create_task(reserve_competing_unit())
        await _wait_for_postgres_lock(observer, reserver_pid)
        assert not reservation_task.done()
        await caller.commit()
        result = await asyncio.wait_for(reservation_task, timeout=5)
        assert result is not None
        assert "stock reservation exceeds available inventory" in result
    finally:
        if reservation_task is not None and not reservation_task.done():
            reservation_task.cancel()
            await asyncio.gather(reservation_task, return_exceptions=True)
        await caller.rollback()
        await reserver.rollback()
        await observer.rollback()
        await caller.close()
        await reserver.close()
        await observer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("target_state", ["verified", "failed"])
async def test_call_started_terminal_rejects_definitive_evidence_prestaged_while_pending(
    db_session, vendor_user, customer_user, target_state
) -> None:
    attempt = await _pending_payment_subject(db_session, vendor_user, customer_user)
    evidence = await _definitive_reconciliation_evidence(
        db_session, attempt, target_state
    )
    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": lease_token, "attempt_id": attempt.id},
    )
    await _present_payment_lease(db_session, lease_token)

    with pytest.raises(DBAPIError, match="payment evidence chronology is invalid"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state=:target_state, "
                    "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
                ),
                {
                    "target_state": target_state,
                    "evidence_id": evidence.id,
                    "attempt_id": attempt.id,
                },
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("target_state", ["verified", "failed"])
@pytest.mark.parametrize("chronology_field", ["created_at", "observed_at"])
@pytest.mark.parametrize(
    ("tick_offset", "accepted"), [(-1, False), (0, True), (1, True)]
)
async def test_call_started_terminal_requires_definitive_evidence_at_or_after_call_start(
    db_session,
    vendor_user,
    customer_user,
    target_state,
    chronology_field,
    tick_offset,
    accepted,
) -> None:
    attempt, lease_token = await _call_started_subject(
        db_session, vendor_user, customer_user
    )
    evidence = await _definitive_reconciliation_evidence(
        db_session, attempt, target_state
    )
    call_started_at = await db_session.scalar(
        text("SELECT call_started_at FROM payment_attempts WHERE id=:attempt_id"),
        {"attempt_id": attempt.id},
    )
    valid_time = call_started_at + timedelta(microseconds=2)
    chronology = {"created_at": valid_time, "observed_at": valid_time}
    chronology[chronology_field] = call_started_at + timedelta(microseconds=tick_offset)
    await _force_evidence_chronology(db_session, evidence.id, **chronology)
    await _present_payment_lease(db_session, lease_token)
    transition = text(
        "UPDATE payment_attempts SET state=:target_state, "
        "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
    )
    params = {
        "target_state": target_state,
        "evidence_id": evidence.id,
        "attempt_id": attempt.id,
    }

    if not accepted:
        with pytest.raises(DBAPIError, match="payment evidence chronology is invalid"):
            async with db_session.begin_nested():
                await db_session.execute(transition, params)
        return

    await db_session.execute(transition, params)
    assert (
        await db_session.scalar(
            text("SELECT state FROM payment_attempts WHERE id=:attempt_id"),
            {"attempt_id": attempt.id},
        )
        == target_state
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("target_state", ["verified", "failed"])
async def test_abandoned_unknown_resolution_rejects_definitive_evidence_from_call_started(
    db_session, vendor_user, customer_user, target_state
) -> None:
    attempt, lease_token = await _call_started_subject(
        db_session, vendor_user, customer_user
    )
    prestaged = await _definitive_reconciliation_evidence(
        db_session, attempt, target_state
    )
    unknown = await _definitive_reconciliation_evidence(
        db_session,
        attempt,
        "failed",
        evidence_type="outcome_unknown",
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE payment_attempts "
            "SET claim_expires_at=clock_timestamp() - interval '1 second' "
            "WHERE id=:attempt_id"
        ),
        {"attempt_id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await _present_payment_lease(db_session, lease_token)
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='abandoned_unknown', "
            "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
        ),
        {"evidence_id": unknown.id, "attempt_id": attempt.id},
    )

    with pytest.raises(DBAPIError, match="payment evidence chronology is invalid"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state=:target_state, "
                    "terminal_evidence_id=:evidence_id, row_version=4 WHERE id=:attempt_id"
                ),
                {
                    "target_state": target_state,
                    "evidence_id": prestaged.id,
                    "attempt_id": attempt.id,
                },
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("target_state", ["verified", "failed"])
@pytest.mark.parametrize("chronology_field", ["created_at", "observed_at"])
@pytest.mark.parametrize("boundary_kind", ["unknown_terminal", "prior_uncertainty"])
@pytest.mark.parametrize(
    ("tick_offset", "accepted"), [(-1, False), (0, False), (1, True)]
)
async def test_abandoned_unknown_resolution_requires_strictly_new_definitive_evidence(
    db_session,
    vendor_user,
    customer_user,
    target_state,
    chronology_field,
    boundary_kind,
    tick_offset,
    accepted,
) -> None:
    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    attempt_row = (
        await db_session.execute(
            text(
                "SELECT terminal_at, terminal_evidence_id FROM payment_attempts "
                "WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
    ).one()
    prior_row = (
        await db_session.execute(
            text(
                "SELECT created_at, observed_at FROM payment_attempt_evidence "
                "WHERE id=:evidence_id"
            ),
            {"evidence_id": attempt_row.terminal_evidence_id},
        )
    ).one()
    prior_times = {
        "created_at": prior_row.created_at,
        "observed_at": prior_row.observed_at,
    }
    if boundary_kind == "unknown_terminal":
        prior_times[chronology_field] = attempt_row.terminal_at - timedelta(
            microseconds=10
        )
    else:
        prior_times[chronology_field] = attempt_row.terminal_at + timedelta(
            microseconds=10
        )
    await _force_evidence_chronology(
        db_session,
        attempt_row.terminal_evidence_id,
        **prior_times,
    )
    boundary = (
        attempt_row.terminal_at
        if boundary_kind == "unknown_terminal"
        else prior_times[chronology_field]
    )
    evidence = await _definitive_reconciliation_evidence(
        db_session, attempt, target_state
    )
    other_field = "observed_at" if chronology_field == "created_at" else "created_at"
    chronology = {
        chronology_field: boundary + timedelta(microseconds=tick_offset),
        other_field: max(attempt_row.terminal_at, prior_times[other_field])
        + timedelta(microseconds=20),
    }
    await _force_evidence_chronology(db_session, evidence.id, **chronology)
    transition = text(
        "UPDATE payment_attempts SET state=:target_state, "
        "terminal_evidence_id=:evidence_id, row_version=4 WHERE id=:attempt_id"
    )
    params = {
        "target_state": target_state,
        "evidence_id": evidence.id,
        "attempt_id": attempt.id,
    }

    if not accepted:
        with pytest.raises(DBAPIError, match="payment evidence chronology is invalid"):
            async with db_session.begin_nested():
                await db_session.execute(transition, params)
        return

    await db_session.execute(transition, params)
    assert (
        await db_session.scalar(
            text("SELECT state FROM payment_attempts WHERE id=:attempt_id"),
            {"attempt_id": attempt.id},
        )
        == target_state
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_state", "wrong_evidence_type"),
    [
        ("verified", "payment_failed"),
        ("verified", "outcome_unknown"),
        ("failed", "payment_verified"),
        ("failed", "outcome_unknown"),
        ("abandoned_unknown", "payment_verified"),
        ("abandoned_unknown", "payment_failed"),
    ],
)
async def test_call_started_terminal_transition_rejects_wrong_evidence_type(
    db_session,
    vendor_user,
    customer_user,
    target_state,
    wrong_evidence_type,
) -> None:
    attempt, lease_token = await _call_started_subject(
        db_session, vendor_user, customer_user
    )
    evidence = await _definitive_reconciliation_evidence(
        db_session,
        attempt,
        target_state,
        evidence_type=wrong_evidence_type,
    )
    if target_state == "abandoned_unknown":
        await db_session.execute(text("SET LOCAL session_replication_role = replica"))
        await db_session.execute(
            text(
                "UPDATE payment_attempts "
                "SET claim_expires_at=clock_timestamp() - interval '1 second' "
                "WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
        await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await _present_payment_lease(db_session, lease_token)

    with pytest.raises(
        DBAPIError, match="payment evidence does not match target state"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state=:target_state, "
                    "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
                ),
                {
                    "target_state": target_state,
                    "evidence_id": evidence.id,
                    "attempt_id": attempt.id,
                },
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("target_state", ["verified", "failed"])
async def test_abandoned_unknown_resolution_rejects_reused_unknown_evidence(
    db_session, vendor_user, customer_user, target_state
) -> None:
    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    unknown_evidence_id = await db_session.scalar(
        text("SELECT terminal_evidence_id FROM payment_attempts WHERE id=:attempt_id"),
        {"attempt_id": attempt.id},
    )

    with pytest.raises(DBAPIError, match="definitive reconciliation evidence required"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state=:target_state, row_version=4 "
                    "WHERE id=:attempt_id"
                ),
                {"target_state": target_state, "attempt_id": attempt.id},
            )

    row = (
        await db_session.execute(
            text(
                "SELECT state, terminal_evidence_id FROM payment_attempts WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
    ).one()
    assert row.state == "abandoned_unknown"
    assert row.terminal_evidence_id == unknown_evidence_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target_state", "wrong_evidence_type"),
    [
        ("verified", "payment_failed"),
        ("failed", "payment_verified"),
        ("verified", "authorization_result"),
        ("failed", "authorization_result"),
        ("verified", "outcome_unknown"),
        ("failed", "outcome_unknown"),
    ],
)
async def test_abandoned_unknown_resolution_rejects_wrong_disposition_evidence(
    db_session,
    vendor_user,
    customer_user,
    target_state,
    wrong_evidence_type,
) -> None:
    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    evidence = await _unvalidated_definitive_reconciliation_evidence(
        db_session,
        attempt,
        target_state,
        evidence_type=wrong_evidence_type,
    )

    with pytest.raises(DBAPIError, match="definitive reconciliation evidence required"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state=:target_state, "
                    "terminal_evidence_id=:evidence_id, row_version=4 WHERE id=:attempt_id"
                ),
                {
                    "target_state": target_state,
                    "evidence_id": evidence.id,
                    "attempt_id": attempt.id,
                },
            )


@pytest.mark.asyncio
async def test_abandoned_unknown_resolution_rejects_other_attempt_evidence(
    db_session, vendor_user, customer_user
) -> None:
    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    *_, other_attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    evidence = await _definitive_reconciliation_evidence(
        db_session, other_attempt, "verified"
    )

    with pytest.raises(
        DBAPIError, match="payment attempt terminal evidence is invalid"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='verified', "
                    "terminal_evidence_id=:evidence_id, row_version=4 WHERE id=:attempt_id"
                ),
                {"evidence_id": evidence.id, "attempt_id": attempt.id},
            )


@pytest.mark.asyncio
async def test_definitive_reconciliation_evidence_replay_is_idempotently_unique(
    db_session, vendor_user, customer_user
) -> None:
    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    event_id = f"definitive-replay-{uuid.uuid4().hex}"
    evidence = await _definitive_reconciliation_evidence(
        db_session, attempt, "verified", event_id=event_id
    )

    with pytest.raises(DBAPIError, match="uq_payment_attempt_evidence_external_event"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "INSERT INTO payment_attempt_evidence "
                    "(id, attempt_id, source, event_id, evidence_type, evidence_hash, observed_at) "
                    "VALUES (:id, :attempt_id, :source, :event_id, 'payment_verified', "
                    ":evidence_hash, clock_timestamp())"
                ),
                {
                    "id": uuid.uuid4(),
                    "attempt_id": attempt.id,
                    "source": evidence.source,
                    "event_id": event_id,
                    "evidence_hash": uuid.uuid4().hex * 2,
                },
            )

    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM payment_attempt_evidence "
            "WHERE source=:source AND event_id=:event_id"
        ),
        {"source": evidence.source, "event_id": event_id},
    )
    assert count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("target_state", ["verified", "failed"])
async def test_abandoned_unknown_resolution_accepts_distinct_definitive_evidence(
    db_session, vendor_user, customer_user, target_state
) -> None:
    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    unknown_evidence_id = await db_session.scalar(
        text("SELECT terminal_evidence_id FROM payment_attempts WHERE id=:attempt_id"),
        {"attempt_id": attempt.id},
    )
    evidence = await _definitive_reconciliation_evidence(
        db_session, attempt, target_state
    )

    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state=:target_state, "
            "terminal_evidence_id=:evidence_id, row_version=4 WHERE id=:attempt_id"
        ),
        {
            "target_state": target_state,
            "evidence_id": evidence.id,
            "attempt_id": attempt.id,
        },
    )

    row = (
        await db_session.execute(
            text(
                "SELECT state, terminal_evidence_id FROM payment_attempts WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
    ).one()
    assert row.state == target_state
    assert row.terminal_evidence_id == evidence.id
    assert row.terminal_evidence_id != unknown_evidence_id


@pytest.mark.asyncio
@pytest.mark.parametrize("target_state", ["verified", "failed"])
@pytest.mark.parametrize(
    ("binding_field", "spoofed_value"),
    [("provider", "stripe"), ("provider_reference", "spoofed-reference")],
)
async def test_abandoned_unknown_resolution_rejects_spoofed_provider_binding(
    db_session,
    vendor_user,
    customer_user,
    target_state,
    binding_field,
    spoofed_value,
) -> None:
    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    evidence = await _unvalidated_definitive_reconciliation_evidence(
        db_session,
        attempt,
        target_state,
        **{binding_field: spoofed_value},
    )

    with pytest.raises(DBAPIError, match="payment provider binding does not match"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state=:target_state, "
                    "terminal_evidence_id=:evidence_id, row_version=4 "
                    "WHERE id=:attempt_id"
                ),
                {
                    "target_state": target_state,
                    "evidence_id": evidence.id,
                    "attempt_id": attempt.id,
                },
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("target_state", ["verified", "failed"])
async def test_abandoned_unknown_resolution_rejects_source_only_spoofing(
    db_session, vendor_user, customer_user, target_state
) -> None:
    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    evidence = await _unvalidated_definitive_reconciliation_evidence(
        db_session,
        attempt,
        target_state,
        source="provider_reconciliation",
        provider="stripe",
        provider_reference="source-alone-is-not-provider-proof",
    )

    with pytest.raises(DBAPIError, match="payment provider binding does not match"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state=:target_state, "
                    "terminal_evidence_id=:evidence_id, row_version=4 "
                    "WHERE id=:attempt_id"
                ),
                {
                    "target_state": target_state,
                    "evidence_id": evidence.id,
                    "attempt_id": attempt.id,
                },
            )


@pytest.mark.asyncio
async def test_definitive_reconciliation_rejects_attempt_reference_drift(
    db_session, vendor_user, customer_user
) -> None:
    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    evidence = await _definitive_reconciliation_evidence(
        db_session, attempt, "verified"
    )

    with pytest.raises(DBAPIError, match="payment provider binding is immutable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='verified', "
                    "provider_reference='drifted-reference', "
                    "terminal_evidence_id=:evidence_id, row_version=4 "
                    "WHERE id=:attempt_id"
                ),
                {"evidence_id": evidence.id, "attempt_id": attempt.id},
            )


@pytest.mark.asyncio
async def test_ambiguous_historical_unknown_binding_fails_closed(
    db_session, vendor_user, customer_user
) -> None:
    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET provider=NULL, provider_reference=NULL "
            "WHERE id=:attempt_id"
        ),
        {"attempt_id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await db_session.refresh(attempt)
    evidence = await _unvalidated_definitive_reconciliation_evidence(
        db_session,
        attempt,
        "verified",
        provider="paystack",
        provider_reference="cannot-backfill-ambiguous-history",
    )

    with pytest.raises(DBAPIError, match="payment provider binding is unavailable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='verified', "
                    "terminal_evidence_id=:evidence_id, row_version=4 "
                    "WHERE id=:attempt_id"
                ),
                {"evidence_id": evidence.id, "attempt_id": attempt.id},
            )


@pytest.mark.asyncio
async def test_outcome_unknown_evidence_requires_call_started_attempt(
    db_session, vendor_user, customer_user
) -> None:
    """The live evidence path rejects an unknown outcome before any provider call."""

    attempt = await _pending_payment_subject(db_session, vendor_user, customer_user)
    with pytest.raises(
        DBAPIError, match="unknown evidence requires started provider call"
    ):
        async with db_session.begin_nested():
            db_session.add(
                PaymentAttemptEvidence(
                    attempt_id=attempt.id,
                    source="provider_reconciliation",
                    event_id=f"pending-unknown-{uuid.uuid4().hex}",
                    evidence_type="outcome_unknown",
                    provider=attempt.provider,
                    provider_reference=attempt.provider_reference,
                    evidence_hash=uuid.uuid4().hex * 2,
                    observed_at=datetime.now(timezone.utc),
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_abandoned_unknown_rejects_evidence_staged_before_provider_call(
    db_session, vendor_user, customer_user
) -> None:
    """Unknown evidence must describe this provider call, not a pending attempt."""

    attempt = await _pending_payment_subject(db_session, vendor_user, customer_user)
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="provider_reconciliation",
        event_id=f"pre-call-unknown-{uuid.uuid4().hex}",
        evidence_type="outcome_unknown",
        provider=attempt.provider,
        provider_reference=attempt.provider_reference,
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    db_session.add(evidence)
    await db_session.flush()
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))

    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": lease_token, "attempt_id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE payment_attempts "
            "SET claim_expires_at=clock_timestamp() - interval '1 second' "
            "WHERE id=:attempt_id"
        ),
        {"attempt_id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await _present_payment_lease(db_session, lease_token)

    with pytest.raises(DBAPIError, match="unknown evidence predates provider call"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='abandoned_unknown', "
                    "terminal_evidence_id=:evidence_id, row_version=3 "
                    "WHERE id=:attempt_id"
                ),
                {"evidence_id": evidence.id, "attempt_id": attempt.id},
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("target_state", ["verified", "failed"])
@pytest.mark.parametrize(
    "call_started_mutation", ["NULL", "call_started_at + interval '1 second'"]
)
async def test_abandoned_unknown_resolution_preserves_call_started_audit(
    db_session,
    vendor_user,
    customer_user,
    target_state,
    call_started_mutation,
) -> None:
    """Definitive reconciliation cannot erase or rewrite the provider-call start."""

    *_, attempt = await _abandoned_unknown_subject(
        db_session, vendor_user, customer_user
    )
    evidence = await _definitive_reconciliation_evidence(
        db_session, attempt, target_state
    )

    with pytest.raises(
        DBAPIError, match="payment attempt call start audit is immutable"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state=:target_state, "
                    f"call_started_at={call_started_mutation}, "
                    "terminal_evidence_id=:evidence_id, row_version=4 "
                    "WHERE id=:attempt_id"
                ),
                {
                    "target_state": target_state,
                    "evidence_id": evidence.id,
                    "attempt_id": attempt.id,
                },
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("chronology_field", ["created_at", "observed_at"])
@pytest.mark.parametrize(
    ("boundary_delta", "accepted"),
    [
        (timedelta(microseconds=-1), False),
        (timedelta(0), True),
        (timedelta(microseconds=1), True),
    ],
)
async def test_abandoned_unknown_evidence_respects_claim_expiry_boundary(
    db_session,
    vendor_user,
    customer_user,
    chronology_field,
    boundary_delta,
    accepted,
) -> None:
    """Both durable evidence clocks must be at/after the elapsed claim boundary."""

    attempt, lease_token = await _call_started_subject(
        db_session, vendor_user, customer_user
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE payment_attempts "
            "SET call_started_at=clock_timestamp() - interval '2 seconds', "
            "claim_expires_at=clock_timestamp() - interval '1 second' "
            "WHERE id=:attempt_id"
        ),
        {"attempt_id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await db_session.refresh(attempt)
    boundary = attempt.claim_expires_at
    assert boundary is not None

    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="provider_reconciliation",
        event_id=f"expiry-boundary-{chronology_field}-{uuid.uuid4().hex}",
        evidence_type="outcome_unknown",
        provider=attempt.provider,
        provider_reference=attempt.provider_reference,
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=boundary + timedelta(seconds=1),
    )
    db_session.add(evidence)
    await db_session.flush()
    chronology = {
        "created_at": boundary + timedelta(seconds=1),
        "observed_at": boundary + timedelta(seconds=1),
    }
    chronology[chronology_field] = boundary + boundary_delta
    await _force_evidence_chronology(db_session, evidence.id, **chronology)
    await _present_payment_lease(db_session, lease_token)

    transition = text(
        "UPDATE payment_attempts SET state='abandoned_unknown', "
        "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
    )
    params = {"evidence_id": evidence.id, "attempt_id": attempt.id}
    if accepted:
        await db_session.execute(transition, params)
    else:
        with pytest.raises(
            DBAPIError, match="unknown evidence predates provider call or lease expiry"
        ):
            async with db_session.begin_nested():
                await db_session.execute(transition, params)


async def _catalog_replacement_sized_subject(session, vendor_user, customer_user):
    """Build the real sized-order subject used by catalog replacement regressions."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        session, vendor_user, customer_user, stock=0
    )
    variation = Variation(
        product_id=graph["item"].product_id,
        title="Original",
        type="color",
        price=graph["item"].unit_price,
    )
    session.add(variation)
    await session.flush()
    size_stock = SizeStock(variation_id=variation.id, size=SizeEnum.M, stock=3)
    session.add(size_stock)
    await session.flush()
    await session.execute(
        text(
            "UPDATE order_items SET variant_details=CAST(:details AS jsonb) "
            "WHERE id=:order_item_id"
        ),
        {
            "details": json.dumps(
                {
                    "size": "M",
                    "color": "Original",
                    "size_stock_id": str(size_stock.id),
                    "variation_id": str(variation.id),
                }
            ),
            "order_item_id": graph["item"].id,
        },
    )
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        None,
        size_stock_id=size_stock.id,
    )
    await session.execute(
        text(
            "SELECT coordinate_stock_reservation_write("
            ":reservation_id,:order_id,:product_id,NULL,:size_stock_id)"
        ),
        {
            "reservation_id": reservation.id,
            "order_id": reservation.order_id,
            "product_id": reservation.product_id,
            "size_stock_id": reservation.size_stock_id,
        },
    )
    session.add(reservation)
    await session.flush()
    return (
        lane,
        graph,
        intent,
        quote,
        option,
        selection,
        variation,
        size_stock,
        reservation,
    )


async def _make_sized_reservation_terminal(
    session, lane, graph, intent, quote, option, selection, reservation, state: str
) -> None:
    if state == "released":
        await session.execute(
            text(
                "UPDATE stock_reservations SET state='released', "
                "terminal_reason='checkout abandoned', row_version=2 WHERE id=:id"
            ),
            {"id": reservation.id},
        )
        return
    if state == "expired":
        await _expire_reservation_without_lifecycle_transition(session, reservation.id)
        await session.execute(
            text(
                "UPDATE stock_reservations SET state='expired', "
                "terminal_reason='ttl elapsed', row_version=2 WHERE id=:id"
            ),
            {"id": reservation.id},
        )
        return

    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        reservation.customer_id,
    )
    session.add(attempt)
    await session.flush()
    session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await session.flush()
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await _set_attempt_state_for_interlock_matrix(session, attempt, "verified")
    await session.execute(
        text(
            "UPDATE stock_reservations SET state='consumed', "
            "terminal_reason='verified payment consumed stock', row_version=2 WHERE id=:id"
        ),
        {"id": reservation.id},
    )


async def _inject_catalog_replacement_audit_rows(
    session, graph, size_stock, state: str
) -> None:
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET LOCAL session_replication_role = replica"))
    await session.execute(
        text(
            "INSERT INTO legacy_inventory_deduction_candidates "
            "(order_item_id,product_id,size_stock_id,quantity,state,decision_source,"
            "decision_event_id,evidence_hash,actor_id,decided_at) VALUES "
            "(:item_id,:product_id,:size_stock_id,1,CAST(:state AS varchar),:source,:event_id,"
            ":evidence_hash,:actor_id,CASE WHEN CAST(:state AS varchar)='unresolved' THEN NULL "
            "ELSE statement_timestamp() END)"
        ),
        {
            "item_id": graph["item"].id,
            "product_id": graph["item"].product_id,
            "size_stock_id": size_stock.id,
            "state": state,
            "source": None if state == "unresolved" else "legacy_inventory_audit",
            "event_id": None if state == "unresolved" else f"catalog-{state}",
            "evidence_hash": None if state == "unresolved" else "a" * 64,
            "actor_id": None if state == "unresolved" else graph["order"].customer_id,
        },
    )
    if state == "credited":
        await session.execute(
            text(
                "INSERT INTO inventory_deduction_events "
                "(order_item_id,product_id,size_stock_id,event_type,quantity) "
                "VALUES (:item_id,:product_id,:size_stock_id,'deducted',1)"
            ),
            {
                "item_id": graph["item"].id,
                "product_id": graph["item"].product_id,
                "size_stock_id": size_stock.id,
            },
        )
    await session.execute(text("SET LOCAL session_replication_role = origin"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reservation_state", "candidate_state"),
    [("released", "unresolved"), ("expired", "not_deducted"), ("consumed", "credited")],
)
async def test_vendor_variation_replacement_preserves_safe_size_stock_audit_identity(
    client,
    db_session,
    vendor_user,
    customer_user,
    reservation_state,
    candidate_state,
) -> None:
    """Safe history keeps immutable UUID evidence without pinning mutable catalog rows."""

    (
        lane,
        graph,
        intent,
        quote,
        option,
        selection,
        variation,
        size_stock,
        reservation,
    ) = await _catalog_replacement_sized_subject(db_session, vendor_user, customer_user)
    await _make_sized_reservation_terminal(
        db_session,
        lane,
        graph,
        intent,
        quote,
        option,
        selection,
        reservation,
        reservation_state,
    )
    await _inject_catalog_replacement_audit_rows(
        db_session, graph, size_stock, candidate_state
    )
    old_variation_id = variation.id
    old_size_stock_id = size_stock.id
    product_id = graph["item"].product_id
    await db_session.commit()

    response = await client.put(
        f"/api/v1/products/{product_id}",
        json={
            "variations": [
                {
                    "title": "Replacement",
                    "type": "color",
                    "price": "10.00",
                    "sizes": [{"size": "L", "stock": 4}],
                }
            ]
        },
        headers=vendor_user["headers"],
    )

    assert response.status_code == 200, response.text
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM variations WHERE id=:id"),
            {"id": old_variation_id},
        )
        == 0
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM size_stocks WHERE id=:id"),
            {"id": old_size_stock_id},
        )
        == 0
    )
    for table in ("stock_reservations", "legacy_inventory_deduction_candidates"):
        assert (
            await db_session.scalar(
                text(f"SELECT size_stock_id FROM {table} WHERE order_item_id=:item_id"),
                {"item_id": graph["item"].id},
            )
            == old_size_stock_id
        )
    if candidate_state == "credited":
        assert (
            await db_session.scalar(
                text(
                    "SELECT size_stock_id FROM inventory_deduction_events "
                    "WHERE order_item_id=:item_id AND event_type='deducted'"
                ),
                {"item_id": graph["item"].id},
            )
            == old_size_stock_id
        )


@pytest.mark.asyncio
async def test_customer_cancellation_allows_retired_size_stock_snapshot(
    client, db_session, vendor_user, customer_user
) -> None:
    """A historical SizeStock UUID cannot strand an otherwise eligible cancellation."""

    (
        lane,
        graph,
        intent,
        quote,
        option,
        selection,
        _variation,
        size_stock,
        reservation,
    ) = await _catalog_replacement_sized_subject(db_session, vendor_user, customer_user)
    await _make_sized_reservation_terminal(
        db_session,
        lane,
        graph,
        intent,
        quote,
        option,
        selection,
        reservation,
        "released",
    )
    await _inject_catalog_replacement_audit_rows(
        db_session, graph, size_stock, "unresolved"
    )
    old_size_stock_id = size_stock.id
    product_id = graph["item"].product_id
    order_id = graph["order"].id
    await db_session.commit()

    replacement = await client.put(
        f"/api/v1/products/{product_id}",
        json={
            "variations": [
                {
                    "title": "Replacement",
                    "type": "color",
                    "price": "10.00",
                    "sizes": [{"size": "L", "stock": 4}],
                }
            ]
        },
        headers=vendor_user["headers"],
    )
    assert replacement.status_code == 200, replacement.text
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM size_stocks WHERE id=:id"),
            {"id": old_size_stock_id},
        )
        == 0
    )

    response = await client.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={"cancellation_reason": "No longer needed"},
        headers=customer_user["headers"],
    )

    assert response.status_code == 200, response.text
    assert response.json()["fulfillment_status"] == "cancelled"
    assert (
        await db_session.scalar(
            text(
                "SELECT stock FROM size_stocks ss JOIN variations v "
                "ON v.id=ss.variation_id WHERE v.product_id=:product_id"
            ),
            {"product_id": product_id},
        )
        == 4
    )


@pytest.mark.asyncio
async def test_cancellation_rejects_same_binding_size_stock_resurrection(
    db_session, vendor_user, customer_user
) -> None:
    """A deleted/reinserted UUID is not the inventory lifecycle that was deducted."""

    (
        lane,
        graph,
        intent,
        quote,
        option,
        selection,
        variation,
        size_stock,
        reservation,
    ) = await _catalog_replacement_sized_subject(db_session, vendor_user, customer_user)
    await _make_sized_reservation_terminal(
        db_session,
        lane,
        graph,
        intent,
        quote,
        option,
        selection,
        reservation,
        "released",
    )
    await _inject_catalog_replacement_audit_rows(
        db_session, graph, size_stock, "unresolved"
    )
    subject_id = size_stock.id
    variation_id = variation.id
    product_id = graph["item"].product_id
    order_id = graph["order"].id
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    canceller = factory()
    replacer = factory()
    observer = factory()
    cancellation_task = None
    try:
        # Hold the complete production catalog lock hierarchy so cancellation
        # snapshots the original row before waiting on the catalog writer.
        await _coordinate(
            replacer,
            ("product", product_id),
            ("variation", variation_id),
            ("size_stock", subject_id),
        )
        canceller_pid = await canceller.scalar(text("SELECT pg_backend_pid()"))

        async def cancel_and_restore() -> str:
            try:
                extant_ids = await coordinate_catalog_write(
                    canceller,
                    order_ids=[order_id],
                    product_ids=[product_id],
                    size_stock_ids=[subject_id],
                    allow_missing_size_stock_ids=True,
                )
                if subject_id in extant_ids:
                    await canceller.execute(
                        text("UPDATE size_stocks SET stock=stock + 1 WHERE id=:id"),
                        {"id": subject_id},
                    )
                await canceller.commit()
                return "committed"
            except ValueError as exc:
                await canceller.rollback()
                return str(exc)

        cancellation_task = asyncio.create_task(cancel_and_restore())
        for _ in range(100):
            blockers = await observer.scalar(
                text("SELECT pg_blocking_pids(:pid)"), {"pid": canceller_pid}
            )
            if blockers:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail(
                "cancellation never reached the expected catalog coordinator wait"
            )

        # Use the real coordinated catalog trigger path: the terminal reservation
        # and immutable audit snapshots allow replacement without bypassing guards.
        await replacer.execute(
            text("DELETE FROM size_stocks WHERE id=:id"), {"id": subject_id}
        )
        await replacer.execute(
            text(
                "INSERT INTO size_stocks (id,variation_id,size,stock) "
                "VALUES (:id,:variation_id,'M',7)"
            ),
            {"id": subject_id, "variation_id": variation_id},
        )
        await replacer.commit()

        outcome = await asyncio.wait_for(cancellation_task, timeout=5)
        durable_stock = await observer.scalar(
            text("SELECT stock FROM size_stocks WHERE id=:id"), {"id": subject_id}
        )
        assert (outcome, durable_stock) == (
            "catalog coordinator size-stock lifecycle changed during preflight",
            7,
        )
    finally:
        if cancellation_task is not None and not cancellation_task.done():
            cancellation_task.cancel()
        await canceller.rollback()
        await replacer.rollback()
        await observer.rollback()
        await canceller.close()
        await replacer.close()
        await observer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attempt_state", ["pending", "call_started", "verified", "abandoned_unknown"]
)
async def test_vendor_variation_replacement_fails_while_payment_outcome_is_live(
    client, db_session, vendor_user, customer_user, attempt_state
) -> None:
    """Expired-by-clock stock stays pinned while payment remains unresolved."""

    (
        lane,
        graph,
        intent,
        quote,
        option,
        selection,
        _variation,
        _size_stock,
        reservation,
    ) = await _catalog_replacement_sized_subject(db_session, vendor_user, customer_user)
    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await _set_attempt_state_for_interlock_matrix(db_session, attempt, attempt_state)
    await _expire_reservation_without_lifecycle_transition(db_session, reservation.id)
    product_id = graph["item"].product_id
    await db_session.commit()

    with pytest.raises(DBAPIError, match="reserved product identity is immutable"):
        await client.put(
            f"/api/v1/products/{product_id}",
            json={
                "variations": [
                    {
                        "title": "Blocked replacement",
                        "type": "color",
                        "price": "10.00",
                        "sizes": [{"size": "L", "stock": 4}],
                    }
                ]
            },
            headers=vendor_user["headers"],
        )


async def _catalog_product_variant_subject(
    session, vendor_user, customer_user, *, persist_reservation: bool = True
):
    """Build a finite-stock ProductVariant reservation subject."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        session, vendor_user, customer_user, stock=0
    )
    sku = f"VAR-{uuid.uuid4().hex[:12]}"
    variant = ProductVariant(
        product_id=graph["item"].product_id,
        size="M",
        color="Delete fence",
        price=graph["item"].unit_price,
        stock=3,
        sku=sku,
    )
    session.add(variant)
    await session.flush()
    await session.execute(
        text("UPDATE order_items SET variant_id=:variant_id WHERE id=:order_item_id"),
        {"variant_id": variant.id, "order_item_id": graph["item"].id},
    )
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        variant_id=variant.id,
    )
    if persist_reservation:
        await session.execute(
            text(
                "SELECT coordinate_stock_reservation_write("
                ":reservation_id,:order_id,:product_id,:variant_id,NULL)"
            ),
            {
                "reservation_id": reservation.id,
                "order_id": reservation.order_id,
                "product_id": reservation.product_id,
                "variant_id": reservation.variant_id,
            },
        )
        session.add(reservation)
        await session.flush()
    return lane, graph, intent, quote, option, selection, variant, reservation


async def _detach_order_item_variant_fk(session, order_item_id) -> None:
    """Isolate the Lane 2A-4B UUID audit fence from the legacy OrderItem FK."""

    await session.execute(text("SET LOCAL session_replication_role = replica"))
    await session.execute(
        text("UPDATE order_items SET variant_id=NULL WHERE id=:order_item_id"),
        {"order_item_id": order_item_id},
    )
    await session.execute(text("SET LOCAL session_replication_role = origin"))


@pytest.mark.asyncio
async def test_admin_product_variant_delete_rejects_unexpired_active_reservation(
    client, db_session, admin_user, vendor_user, customer_user
) -> None:
    """The real admin delete path cannot orphan live variant stock identity."""

    lane, graph, intent, quote, option, selection, variant, reservation = (
        await _catalog_product_variant_subject(db_session, vendor_user, customer_user)
    )
    del lane, intent, quote, option, selection, reservation
    await _detach_order_item_variant_fk(db_session, graph["item"].id)
    product_id = variant.product_id
    variant_id = variant.id
    await db_session.commit()

    with pytest.raises(DBAPIError, match="reserved product identity is immutable"):
        await client.delete(
            f"/api/v1/admin/products/{product_id}/variants/{variant_id}",
            headers=admin_user["headers"],
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "attempt_state", ["pending", "call_started", "verified", "abandoned_unknown"]
)
async def test_product_variant_delete_rejects_expired_active_payment_truth(
    db_session, vendor_user, customer_user, attempt_state
) -> None:
    """Expired active stock stays fenced while any live payment truth remains."""

    lane, graph, intent, quote, option, selection, variant, reservation = (
        await _catalog_product_variant_subject(db_session, vendor_user, customer_user)
    )
    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await _set_attempt_state_for_interlock_matrix(db_session, attempt, attempt_state)
    await _expire_reservation_without_lifecycle_transition(db_session, reservation.id)
    await _detach_order_item_variant_fk(db_session, graph["item"].id)

    with pytest.raises(DBAPIError, match="reserved product identity is immutable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("DELETE FROM product_variants WHERE id=:variant_id"),
                {"variant_id": variant.id},
            )


@pytest.mark.asyncio
async def test_admin_product_variant_delete_preserves_safe_terminal_uuid_evidence(
    client, db_session, admin_user, vendor_user, customer_user
) -> None:
    """Released history keeps its immutable variant UUID without pinning catalog rows."""

    lane, graph, intent, quote, option, selection, variant, reservation = (
        await _catalog_product_variant_subject(db_session, vendor_user, customer_user)
    )
    del lane, intent, quote, option, selection
    await db_session.execute(
        text(
            "UPDATE stock_reservations SET state='released', "
            "terminal_reason='checkout abandoned', row_version=2 WHERE id=:id"
        ),
        {"id": reservation.id},
    )
    await _detach_order_item_variant_fk(db_session, graph["item"].id)
    product_id = variant.product_id
    variant_id = variant.id
    reservation_id = reservation.id
    await db_session.commit()

    response = await client.delete(
        f"/api/v1/admin/products/{product_id}/variants/{variant_id}",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200, response.text
    assert (
        await db_session.scalar(
            text("SELECT variant_id FROM stock_reservations WHERE id=:id"),
            {"id": reservation_id},
        )
        == variant_id
    )


@pytest.mark.asyncio
async def test_two_connections_variant_delete_waits_for_reservation_then_revalidates(
    db_session, vendor_user, customer_user
) -> None:
    """Lock order is order -> item -> product -> variant; DELETE waits then rechecks."""

    lane, graph, intent, quote, option, selection, variant, reservation = (
        await _catalog_product_variant_subject(
            db_session, vendor_user, customer_user, persist_reservation=False
        )
    )
    del lane, intent, quote, option, selection
    order_item_id = graph["item"].id
    variant_id = variant.id
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    creator = factory()
    deleter = factory()
    observer = factory()
    try:
        creator.add(reservation)
        await creator.flush()
        await _detach_order_item_variant_fk(creator, order_item_id)

        deleter_pid = await deleter.scalar(text("SELECT pg_backend_pid()"))

        delete_task = asyncio.create_task(
            deleter.execute(
                text("DELETE FROM product_variants WHERE id=:variant_id"),
                {"variant_id": variant_id},
            )
        )
        for _ in range(100):
            blockers = await observer.scalar(
                text("SELECT pg_blocking_pids(:pid)"), {"pid": deleter_pid}
            )
            if blockers:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("variant DELETE never reached the expected row-lock wait")
        assert not delete_task.done()

        await creator.commit()
        with pytest.raises(DBAPIError, match="reserved product identity is immutable"):
            await asyncio.wait_for(delete_task, timeout=5)
    finally:
        await creator.rollback()
        await deleter.rollback()
        await creator.close()
        await deleter.close()
        await observer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("inventory_kind", ["product_variant", "size_stock"])
@pytest.mark.parametrize("constraints_consumed", [False, True])
async def test_two_connections_attempt_locks_inventory_subject_through_ttl(
    db_session,
    vendor_user,
    customer_user,
    inventory_kind,
    constraints_consumed,
) -> None:
    """Attempt creation serializes subject deletion through commit."""

    if inventory_kind == "product_variant":
        lane, graph, intent, quote, option, selection, subject, reservation = (
            await _catalog_product_variant_subject(
                db_session, vendor_user, customer_user
            )
        )
        await _detach_order_item_variant_fk(db_session, graph["item"].id)
        table = "product_variants"
        catalog_keys = [
            {"subject_kind": "product", "subject_id": str(reservation.product_id)},
            {"subject_kind": "product_variant", "subject_id": str(subject.id)},
        ]
    else:
        (
            lane,
            graph,
            intent,
            quote,
            option,
            selection,
            _variation,
            subject,
            reservation,
        ) = await _catalog_replacement_sized_subject(
            db_session, vendor_user, customer_user
        )
        table = "size_stocks"
        catalog_keys = [
            {"subject_kind": "product", "subject_id": str(reservation.product_id)},
            {"subject_kind": "variation", "subject_id": str(_variation.id)},
            {"subject_kind": "size_stock", "subject_id": str(subject.id)},
        ]
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    subject_id = subject.id
    reservation_id = reservation.id
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE stock_reservations SET created_at=statement_timestamp(), "
            "expires_at=statement_timestamp() + interval '2 seconds' WHERE id=:id"
        ),
        {"id": reservation_id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    creator = factory()
    deleter = factory()
    observer = factory()
    try:
        await creator.execute(
            text("SELECT coordinate_payment_attempt_write(:attempt_id, :order_id)"),
            {"attempt_id": attempt.id, "order_id": graph["order"].id},
        )
        creator.add(attempt)
        await creator.flush()
        creator.add(
            PaymentAttemptReservation(
                attempt_id=attempt.id, reservation_id=reservation_id
            )
        )
        await creator.flush()
        if constraints_consumed:
            # Force and consume the deferred event before the TTL boundary.
            # Subject locks must still serialize deletion with this attempt.
            await creator.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            await creator.execute(text("SET CONSTRAINTS ALL DEFERRED"))
        await asyncio.sleep(2.1)

        async def delete_subject() -> None:
            await deleter.execute(
                text("SELECT coordinate_stock_payment_write(CAST(:keys AS jsonb))"),
                {"keys": json.dumps(catalog_keys)},
            )
            await deleter.execute(
                text(f"DELETE FROM {table} WHERE id=:subject_id"),
                {"subject_id": subject_id},
            )
            await deleter.commit()

        delete_task = asyncio.create_task(delete_subject())
        await asyncio.sleep(0.2)
        assert not delete_task.done()
        if constraints_consumed:
            await creator.commit()
            with pytest.raises(
                DBAPIError, match="reserved product identity is immutable"
            ):
                await asyncio.wait_for(delete_task, timeout=2)
            await deleter.rollback()
            expected_attempts = 1
            expected_subjects = 1
        else:
            with pytest.raises(
                DBAPIError,
                match="payment attempt must cover the exact active reservation set",
            ):
                await creator.commit()
            await creator.rollback()
            await asyncio.wait_for(delete_task, timeout=2)
            expected_attempts = 0
            expected_subjects = 0

        assert (
            await observer.scalar(
                text("SELECT count(*) FROM payment_attempts WHERE id=:attempt_id"),
                {"attempt_id": attempt.id},
            )
            == expected_attempts
        )
        assert (
            await observer.scalar(
                text(f"SELECT count(*) FROM {table} WHERE id=:subject_id"),
                {"subject_id": subject_id},
            )
            == expected_subjects
        )
    finally:
        await creator.rollback()
        await deleter.rollback()
        await observer.rollback()
        await creator.close()
        await deleter.close()
        await observer.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("inventory_kind", ["product_variant", "size_stock"])
async def test_attempt_revalidates_inventory_binding_after_lock_wait(
    db_session, vendor_user, customer_user, inventory_kind
) -> None:
    """A stale pre-wait snapshot cannot admit a reparented inventory subject."""

    if inventory_kind == "product_variant":
        lane, graph, intent, quote, option, selection, subject, reservation = (
            await _catalog_product_variant_subject(
                db_session, vendor_user, customer_user
            )
        )
        table = "product_variants"
        binding_column = "product_id"
    else:
        (
            lane,
            graph,
            intent,
            quote,
            option,
            selection,
            _variation,
            subject,
            reservation,
        ) = await _catalog_replacement_sized_subject(
            db_session, vendor_user, customer_user
        )
        table = "size_stocks"
        binding_column = "variation_id"
    (
        _other_lane,
        other_graph,
        _other_intent,
        _other_quote,
        _other_option,
        _other_selection,
        _other_variant,
        _other_reservation,
    ) = await _catalog_product_variant_subject(
        db_session, vendor_user, customer_user, persist_reservation=False
    )
    if inventory_kind == "product_variant":
        await _detach_order_item_variant_fk(db_session, other_graph["item"].id)
        await db_session.delete(_other_variant)
        await db_session.flush()
        replacement_binding = other_graph["item"].product_id
    else:
        replacement_variation = Variation(
            product_id=other_graph["item"].product_id,
            title="Replacement target",
            type="color",
            price=graph["item"].unit_price,
        )
        db_session.add(replacement_variation)
        await db_session.flush()
        replacement_binding = replacement_variation.id

    reservation_id = reservation.id
    subject_id = subject.id
    order_id = graph["order"].id
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE stock_reservations SET created_at=statement_timestamp(), "
            "expires_at=statement_timestamp() + interval '2 seconds' WHERE id=:id"
        ),
        {"id": reservation_id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    blocker = factory()
    creator = factory()
    mutator = factory()
    observer = factory()
    try:
        await blocker.execute(
            text("SELECT id FROM orders WHERE id=:order_id FOR UPDATE"),
            {"order_id": order_id},
        )
        creator_pid = await creator.scalar(text("SELECT pg_backend_pid()"))
        creator.add(attempt)
        create_task = asyncio.create_task(creator.flush())
        for _ in range(100):
            blockers = await observer.scalar(
                text("SELECT pg_blocking_pids(:pid)"), {"pid": creator_pid}
            )
            if blockers:
                break
            await asyncio.sleep(0.01)
        else:
            pytest.fail("attempt INSERT never reached the expected order-lock wait")

        # The attempt statement's timestamp still sees the reservation as active,
        # but the catalog mutation starts after TTL and cannot see the attempt.
        await asyncio.sleep(2.1)
        # Bypass write guards only to model an independently committed identity
        # change and prove the waiting attempt revalidates authoritative bindings.
        await mutator.execute(text("SET LOCAL session_replication_role = replica"))
        await mutator.execute(
            text(
                f"UPDATE {table} SET {binding_column}=:replacement_binding "
                "WHERE id=:subject_id"
            ),
            {
                "replacement_binding": replacement_binding,
                "subject_id": subject_id,
            },
        )
        await mutator.execute(text("SET LOCAL session_replication_role = origin"))
        await mutator.commit()
        await blocker.commit()

        with pytest.raises(
            DBAPIError, match="payment attempt requires active reservations"
        ):
            await asyncio.wait_for(create_task, timeout=5)
        await creator.rollback()
        assert (
            await observer.scalar(
                text("SELECT count(*) FROM payment_attempts WHERE id=:attempt_id"),
                {"attempt_id": attempt.id},
            )
            == 0
        )
    finally:
        await blocker.rollback()
        await creator.rollback()
        await mutator.rollback()
        await observer.rollback()
        await blocker.close()
        await creator.close()
        await mutator.close()
        await observer.close()


@pytest.mark.asyncio
async def test_attempt_lock_order_avoids_fk_reparent_deadlock(
    db_session, vendor_user, customer_user
) -> None:
    """Attempt locking follows child-to-parent FK order during a reparent race."""

    lane, graph, intent, quote, option, selection, variant, reservation = (
        await _catalog_product_variant_subject(db_session, vendor_user, customer_user)
    )
    (
        _other_lane,
        other_graph,
        _other_intent,
        _other_quote,
        _other_option,
        _other_selection,
        other_variant,
        _other_reservation,
    ) = await _catalog_product_variant_subject(
        db_session, vendor_user, customer_user, persist_reservation=False
    )
    other_variant.color = "Other parent"
    await db_session.flush()
    # A real multi-item order can reserve both products. This fixture isolates
    # the physical lock graph by adding the second subject under replica mode;
    # all referenced rows and foreign keys remain real.
    second_reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        other_variant.sku,
        variant_id=other_variant.id,
    )
    second_reservation.product_id = other_graph["item"].product_id
    second_reservation.expires_at = datetime.now(timezone.utc) + timedelta(seconds=2)
    second_reservation.creation_txid = await db_session.scalar(
        text("SELECT txid_current()")
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    db_session.add(second_reservation)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE stock_reservations SET created_at=statement_timestamp(), "
            "expires_at=statement_timestamp() + interval '2 seconds' "
            "WHERE id IN (:first_id,:second_id)"
        ),
        {"first_id": reservation.id, "second_id": second_reservation.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await db_session.commit()

    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    creator = factory()
    mutator = factory()
    create_task = None
    try:
        await _coordinate(
            mutator,
            ("product", graph["item"].product_id),
            ("product", other_graph["item"].product_id),
            ("product_variant", variant.id),
        )
        await mutator.execute(
            text("SELECT id FROM product_variants WHERE id=:id FOR UPDATE"),
            {"id": variant.id},
        )
        creator.add(attempt)
        create_task = asyncio.create_task(creator.flush())
        await asyncio.sleep(0.2)
        assert not create_task.done()
        await asyncio.sleep(2.1)
        await mutator.execute(
            text("UPDATE product_variants SET product_id=:product_id WHERE id=:id"),
            {"product_id": other_graph["item"].product_id, "id": variant.id},
        )
        await mutator.commit()

        with pytest.raises(
            DBAPIError,
            match="payment attempt requires active reservations",
        ):
            await asyncio.wait_for(create_task, timeout=5)
        await creator.rollback()
    finally:
        if create_task is not None and not create_task.done():
            create_task.cancel()
        await creator.rollback()
        await mutator.rollback()
        await creator.close()
        await mutator.close()
