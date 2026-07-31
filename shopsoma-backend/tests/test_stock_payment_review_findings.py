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
)


def _lane_helpers():
    path = Path(__file__).with_name("test_stock_payment_persistence.py")
    spec = importlib.util.spec_from_file_location("stock_payment_review_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _alternate_selection(session, lane, graph, customer_id, *, quantity: int = 1):
    """Create a second package/intent/selection for the same order."""

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
    await session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"token": lease_token, "attempt_id": attempt.id},
    )
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="provider_reconciliation",
        event_id=f"unknown-{uuid.uuid4().hex}",
        evidence_type="outcome_unknown",
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
        evidence_type="authorization_result",
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

        reserve_task = asyncio.create_task(reserve_unit())
        await asyncio.sleep(0.2)

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

        edit_task = asyncio.create_task(edit_truth())
        await asyncio.sleep(0.2)
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
    mutation_task = None
    replacement_sku = f"raced-{uuid.uuid4().hex[:8]}"
    try:
        await caller.execute(
            text(
                "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                "row_version=2 WHERE id=:attempt_id"
            ),
            {"token": uuid.uuid4(), "attempt_id": attempt.id},
        )
        await asyncio.sleep(1.1)

        async def mutate_identity():
            try:
                await mutator.execute(
                    text("UPDATE products SET sku=:sku WHERE id=:product_id"),
                    {"sku": replacement_sku, "product_id": graph["item"].product_id},
                )
                await mutator.commit()
                return None
            except DBAPIError as exc:
                await mutator.rollback()
                return str(exc)

        mutation_task = asyncio.create_task(mutate_identity())
        await asyncio.sleep(0.2)
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
        await caller.close()
        await mutator.close()


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
    reservation_task = None
    try:
        await caller.execute(
            text(
                "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                "row_version=2 WHERE id=:attempt_id"
            ),
            {"token": uuid.uuid4(), "attempt_id": attempt.id},
        )
        await asyncio.sleep(1.1)

        async def reserve_competing_unit():
            try:
                reserver.add(competing)
                await reserver.flush()
                await reserver.commit()
                return None
            except DBAPIError as exc:
                await reserver.rollback()
                return str(exc)

        reservation_task = asyncio.create_task(reserve_competing_unit())
        await asyncio.sleep(0.2)
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
        await caller.close()
        await reserver.close()
