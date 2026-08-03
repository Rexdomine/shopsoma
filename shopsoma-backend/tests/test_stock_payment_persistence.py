"""Phase 2A-4B stock reservation and payment persistence contracts."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import uuid

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
import pytest

from app.models.stock_payment_persistence import (
    PaymentAttemptEvidence,
    PaymentAttemptReservation,
)


def _load_helpers(filename: str, module_name: str):
    spec = importlib.util.spec_from_file_location(
        module_name, Path(__file__).with_name(filename)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _present_payment_lease(session, lease_token: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('shopsoma.payment_lease_token', :token, true)"),
        {"token": str(lease_token)},
    )


async def _coordinate_payment_attempt(
    session, attempt_id: uuid.UUID, order_id: uuid.UUID
) -> None:
    await session.execute(
        text("SELECT coordinate_payment_attempt_write(:attempt_id, :order_id)"),
        {"attempt_id": attempt_id, "order_id": order_id},
    )


async def _coordinate_reservation(session, reservation) -> None:
    await session.execute(
        text(
            "SELECT coordinate_stock_reservation_write("
            ":reservation_id, :order_id, :product_id, :variant_id, :size_stock_id)"
        ),
        {
            "reservation_id": reservation.id,
            "order_id": reservation.order_id,
            "product_id": reservation.product_id,
            "variant_id": reservation.variant_id,
            "size_stock_id": reservation.size_stock_id,
        },
    )


async def _checkout_subject(db_session, vendor_user, customer_user, *, stock=2):
    quote_helpers = _load_helpers(
        "test_customer_shipping_quote_persistence.py", "lane_4b_quote_helpers"
    )
    domestic = quote_helpers._domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    sku = f"SKU-{uuid.uuid4().hex[:12]}"
    await db_session.execute(
        text("SELECT coordinate_stock_payment_write(CAST(:keys AS jsonb))"),
        {
            "keys": json.dumps(
                [
                    {
                        "subject_kind": "product",
                        "subject_id": str(graph["item"].product_id),
                    }
                ]
            )
        },
    )
    await db_session.execute(
        text("UPDATE products SET sku=:sku, total_stock=:stock WHERE id=:product_id"),
        {"sku": sku, "stock": stock, "product_id": graph["item"].product_id},
    )
    quote = quote_helpers._quote(graph, package, seal, intent, customer_user["user"].id)
    db_session.add(quote)
    await db_session.flush()
    option = quote_helpers._option(quote.id, "checkout")
    db_session.add(option)
    await db_session.flush()
    from app.models.customer_shipping_quote import CustomerShippingQuoteSelection

    selection = CustomerShippingQuoteSelection(
        quote_id=quote.id,
        intent_id=intent.id,
        option_id=option.id,
        customer_id=customer_user["user"].id,
        selected_by_id=customer_user["user"].id,
        source_command="select_shipping_quote_option",
        idempotency_key=f"selection-{uuid.uuid4().hex}",
    )
    db_session.add(selection)
    await db_session.flush()
    return graph, intent, quote, option, selection, sku


def _reservation(
    graph, intent, quote, option, selection, customer_id, sku, **overrides
):
    from app.models.stock_payment_persistence import StockReservation

    values = {
        "id": uuid.uuid4(),
        "order_id": graph["order"].id,
        "order_item_id": graph["item"].id,
        "customer_id": customer_id,
        "quote_id": quote.id,
        "quote_selection_id": selection.id,
        "quote_option_id": option.id,
        "intent_id": intent.id,
        "product_id": graph["item"].product_id,
        "variant_id": None,
        "sku": sku,
        "quantity": 1,
        "unit_price": graph["item"].unit_price,
        "line_amount": graph["item"].unit_price,
        "currency": graph["item"].currency,
        "ttl_seconds": 900,
        "source_command": "reserve_checkout_stock",
        "idempotency_key": f"reservation-{uuid.uuid4().hex}",
    }
    values.update(overrides)
    return StockReservation(**values)


def _payment_attempt(graph, intent, quote, option, selection, customer_id, **overrides):
    from app.models.stock_payment_persistence import PaymentAttempt

    values = {
        "id": uuid.uuid4(),
        "order_id": graph["order"].id,
        "customer_id": customer_id,
        "quote_id": quote.id,
        "quote_selection_id": selection.id,
        "quote_option_id": option.id,
        "intent_id": intent.id,
        "amount": graph["order"].total_amount,
        "currency": graph["order"].currency,
        "provider": "paystack",
        "provider_reference": f"paystack-{uuid.uuid4().hex}",
        "payment_window_seconds": 600,
        "authorization_grace_seconds": 300,
        "claim_ttl_seconds": 300,
        "source_command": "start_checkout_payment",
        "idempotency_key": f"payment-{uuid.uuid4().hex}",
    }
    values.update(overrides)
    return PaymentAttempt(**values)


RESERVATION_COLUMNS = {
    "id",
    "order_id",
    "order_item_id",
    "customer_id",
    "quote_id",
    "quote_selection_id",
    "quote_option_id",
    "intent_id",
    "product_id",
    "variant_id",
    "size_stock_id",
    "sku",
    "quantity",
    "unit_price",
    "line_amount",
    "currency",
    "ttl_seconds",
    "expires_at",
    "state",
    "terminal_reason",
    "terminal_at",
    "source_command",
    "idempotency_key",
    "row_version",
    "creation_txid",
    "created_at",
    "updated_at",
}
ATTEMPT_COLUMNS = {
    "id",
    "order_id",
    "customer_id",
    "quote_id",
    "quote_selection_id",
    "quote_option_id",
    "intent_id",
    "amount",
    "currency",
    "provider",
    "provider_reference",
    "state",
    "payment_window_seconds",
    "authorization_grace_seconds",
    "expires_at",
    "authorization_deadline_at",
    "claim_ttl_seconds",
    "lease_token",
    "call_started_at",
    "claim_expires_at",
    "supersedes_attempt_id",
    "terminal_evidence_id",
    "terminal_at",
    "source_command",
    "idempotency_key",
    "row_version",
    "creation_txid",
    "created_at",
    "updated_at",
}
MEMBERSHIP_COLUMNS = {
    "attempt_id",
    "reservation_id",
    "creation_txid",
    "created_at",
}
EVIDENCE_COLUMNS = {
    "id",
    "attempt_id",
    "source",
    "event_id",
    "evidence_type",
    "provider",
    "provider_reference",
    "evidence_hash",
    "observed_at",
    "created_at",
}


def _columns(model) -> set[str]:
    return {column.name for column in inspect(model).columns}


def test_lane_2a_4b_models_are_normalized_provider_neutral_and_secret_free() -> None:
    from app.models.stock_payment_persistence import (
        PaymentAttempt,
        PaymentAttemptEvidence,
        PaymentAttemptReservation,
        StockReservation,
    )

    assert StockReservation.__tablename__ == "stock_reservations"
    assert PaymentAttempt.__tablename__ == "payment_attempts"
    assert PaymentAttemptReservation.__tablename__ == "payment_attempt_reservations"
    assert PaymentAttemptEvidence.__tablename__ == "payment_attempt_evidence"
    assert _columns(StockReservation) == RESERVATION_COLUMNS
    assert _columns(PaymentAttempt) == ATTEMPT_COLUMNS
    assert _columns(PaymentAttemptReservation) == MEMBERSHIP_COLUMNS
    assert _columns(PaymentAttemptEvidence) == EVIDENCE_COLUMNS

    forbidden = {
        "credentials",
        "authorization_header",
        "account_number",
        "provider_payload",
        "gateway_response",
        "customer_phone",
        "customer_address",
    }
    for model in (
        StockReservation,
        PaymentAttempt,
        PaymentAttemptReservation,
        PaymentAttemptEvidence,
    ):
        assert forbidden.isdisjoint(_columns(model))


def test_lane_2a_4b_models_are_registered_in_canonical_exports() -> None:
    import app.models as models

    assert models.StockReservation.__tablename__ == "stock_reservations"
    assert models.PaymentAttempt.__tablename__ == "payment_attempts"
    assert (
        models.PaymentAttemptReservation.__tablename__ == "payment_attempt_reservations"
    )
    assert models.PaymentAttemptEvidence.__tablename__ == "payment_attempt_evidence"


def test_lane_2a_4b_models_expose_database_enforced_contracts() -> None:
    from app.models.stock_payment_persistence import (
        STOCK_PAYMENT_TRIGGER_DDLS,
        PaymentAttempt,
        StockReservation,
    )

    ddl = "\n".join(STOCK_PAYMENT_TRIGGER_DDLS)
    for table in (
        "stock_reservations",
        "payment_attempts",
        "payment_attempt_reservations",
        "payment_attempt_evidence",
    ):
        assert table in ddl
    for invariant in (
        "stock reservation subject binding is invalid",
        "stock reservation exceeds available inventory",
        "stock reservation identity is immutable",
        "stock reservation transition is illegal",
        "stock reservation expiry has not elapsed",
        "stock reservation is terminal",
        "inventory cannot be reduced below active reservations",
        "payment attempt subject binding is invalid",
        "payment amount is server-owned",
        "payment attempt must cover the exact active reservation set",
        "payment attempt already active for order",
        "payment attempt lease has not expired",
        "payment attempt authorization deadline elapsed",
        "payment verification requires live reservations",
        "payment attempt evidence is append-only",
        "payment attempt is terminal",
        "superseded payment attempt cannot complete",
    ):
        assert invariant in ddl

    active_index = next(
        index
        for index in PaymentAttempt.__table__.indexes
        if index.name == "uq_payment_attempts_active_subject"
    )
    assert active_index.dialect_options["postgresql"]["where"] is not None
    inventory_index = next(
        index
        for index in StockReservation.__table__.indexes
        if index.name == "ix_stock_reservations_inventory_subject"
    )
    assert tuple(column.name for column in inventory_index.columns) == (
        "product_id",
        "variant_id",
        "size_stock_id",
        "state",
        "expires_at",
    )


@pytest.mark.asyncio
async def test_lane_2a_4b_schema_installs_all_authoritative_triggers(
    db_session,
) -> None:
    function_names = [
        "validate_stock_reservation_write",
        "protect_reserved_inventory",
        "protect_reserved_order_item",
        "protect_reserved_order",
        "validate_payment_attempt_write",
        "validate_payment_attempt_membership_write",
        "validate_payment_attempt_exact_reservations",
        "validate_payment_attempt_evidence_write",
    ]
    functions = set(
        (
            await db_session.execute(
                text("SELECT proname FROM pg_proc WHERE proname = ANY(:names)"),
                {"names": function_names},
            )
        ).scalars()
    )
    assert functions == set(function_names)

    trigger_names = [
        "trg_stock_reservations_validate",
        "trg_products_reserved_inventory",
        "trg_product_variants_reserved_inventory",
        "trg_size_stocks_reserved_inventory",
        "trg_variations_reserved_inventory",
        "trg_order_items_reserved_truth",
        "trg_orders_reserved_payment_truth",
        "trg_payment_attempts_validate",
        "trg_payment_attempt_reservations_validate",
        "trg_payment_attempts_exact_reservations",
        "trg_payment_attempt_reservations_exact_set",
        "trg_payment_attempt_evidence_validate",
    ]
    triggers = set(
        (
            await db_session.execute(
                text(
                    "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
                    "AND tgname = ANY(:names)"
                ),
                {"names": trigger_names},
            )
        ).scalars()
    )
    assert triggers == set(trigger_names)


@pytest.mark.asyncio
async def test_stock_reservation_binds_exact_truth_and_protects_inventory(
    db_session, vendor_user, customer_user
) -> None:
    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    reservation = _reservation(
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

    assert reservation.state == "active"
    assert reservation.creation_txid > 0
    assert int((reservation.expires_at - reservation.created_at).total_seconds()) == 900

    spoofed = _reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        unit_price=Decimal("1.0000"),
        line_amount=Decimal("1.0000"),
    )
    with pytest.raises(
        DBAPIError, match="stock reservation subject binding is invalid"
    ):
        async with db_session.begin_nested():
            db_session.add(spoofed)
            await db_session.flush()

    oversold = _reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
    )
    with pytest.raises(
        DBAPIError, match="stock reservation exceeds available inventory"
    ):
        async with db_session.begin_nested():
            db_session.add(oversold)
            await db_session.flush()

    with pytest.raises(
        DBAPIError, match="inventory cannot be reduced below active reservations"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE products SET total_stock=0 WHERE id=:product_id"),
                {"product_id": graph["item"].product_id},
            )


@pytest.mark.asyncio
async def test_payment_attempt_exact_set_lease_evidence_and_consumption_lifecycle(
    db_session, vendor_user, customer_user
) -> None:
    from app.models.stock_payment_persistence import (
        PaymentAttemptEvidence,
        PaymentAttemptReservation,
    )

    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = _reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()

    attempt = _payment_attempt(
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
    await db_session.refresh(attempt)
    assert attempt.expires_at <= reservation.expires_at
    assert attempt.authorization_deadline_at > attempt.expires_at

    duplicate = _payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    with pytest.raises(DBAPIError, match="payment attempt already active for order"):
        async with db_session.begin_nested():
            db_session.add(duplicate)
            await db_session.flush()

    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:lease_token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"lease_token": lease_token, "attempt_id": attempt.id},
    )
    unknown_evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway_webhook",
        event_id=f"unknown-{uuid.uuid4().hex}",
        evidence_type="outcome_unknown",
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(unknown_evidence)
    await db_session.flush()
    await _present_payment_lease(db_session, lease_token)

    with pytest.raises(
        DBAPIError, match="unknown evidence predates provider call or lease expiry"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='abandoned_unknown', "
                    "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
                ),
                {"evidence_id": unknown_evidence.id, "attempt_id": attempt.id},
            )

    verified_evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway_webhook",
        event_id=f"verified-{uuid.uuid4().hex}",
        evidence_type="payment_verified",
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(verified_evidence)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='verified', "
            "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
        ),
        {"evidence_id": verified_evidence.id, "attempt_id": attempt.id},
    )
    await db_session.execute(
        text(
            "UPDATE stock_reservations SET state='consumed', "
            "terminal_reason='verified payment', row_version=2 WHERE id=:reservation_id"
        ),
        {"reservation_id": reservation.id},
    )

    with pytest.raises(DBAPIError, match="payment attempt evidence is append-only"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempt_evidence SET evidence_type='changed' WHERE id=:id"
                ),
                {"id": verified_evidence.id},
            )
    with pytest.raises(DBAPIError, match="payment attempt is terminal"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE payment_attempts SET row_version=4 WHERE id=:attempt_id"),
                {"attempt_id": attempt.id},
            )


@pytest.mark.asyncio
async def test_reservation_freezes_authoritative_product_and_order_facts(
    db_session, vendor_user, customer_user
) -> None:
    """Parent facts already snapshotted by an active reservation cannot drift."""

    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = _reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()

    with pytest.raises(DBAPIError, match="reserved product identity is immutable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE products SET sku='MUTATED-AFTER-RESERVATION' WHERE id=:id"
                ),
                {"id": graph["item"].product_id},
            )

    with pytest.raises(DBAPIError, match="reserved order payment truth is immutable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE orders SET total_amount=total_amount + 1 WHERE id=:id"),
                {"id": graph["order"].id},
            )


@pytest.mark.asyncio
async def test_reservation_expiry_cannot_outlive_selected_quote(
    db_session, vendor_user, customer_user
) -> None:
    """Database-assigned reservation expiry is capped by quote validity."""

    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = _reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        ttl_seconds=1800,
    )
    db_session.add(reservation)
    await db_session.flush()

    assert reservation.expires_at <= quote.expires_at


@pytest.mark.asyncio
async def test_retry_must_supersede_current_terminal_payment_leaf(
    db_session, vendor_user, customer_user
) -> None:
    """A new attempt cannot bypass the auditable retry lineage."""

    from app.models.stock_payment_persistence import (
        PaymentAttemptEvidence,
        PaymentAttemptReservation,
    )

    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = _reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    first = _payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(first)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=first.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    evidence = PaymentAttemptEvidence(
        attempt_id=first.id,
        source="gateway_webhook",
        event_id=f"evt-{uuid.uuid4().hex}",
        evidence_type="payment_failed",
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='failed', terminal_evidence_id=:evidence_id, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"evidence_id": evidence.id, "attempt_id": first.id},
    )

    bypass = _payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    with pytest.raises(
        DBAPIError, match="payment retry must supersede current terminal leaf"
    ):
        async with db_session.begin_nested():
            db_session.add(bypass)
            await db_session.flush()


@pytest.mark.asyncio
async def test_payment_evidence_cannot_predate_its_attempt(
    db_session, vendor_user, customer_user
) -> None:
    """Evidence chronology is database-bound to the attempt it proves."""

    from app.models.stock_payment_persistence import (
        PaymentAttemptEvidence,
        PaymentAttemptReservation,
    )

    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = _reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = _payment_attempt(
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
    await db_session.refresh(attempt)

    with pytest.raises(DBAPIError, match="payment evidence predates attempt"):
        async with db_session.begin_nested():
            db_session.add(
                PaymentAttemptEvidence(
                    attempt_id=attempt.id,
                    source="gateway_webhook",
                    event_id=f"evt-{uuid.uuid4().hex}",
                    evidence_type="payment_failed",
                    evidence_hash=uuid.uuid4().hex * 2,
                    observed_at=(
                        attempt.created_at.replace(tzinfo=timezone.utc)
                        if attempt.created_at.tzinfo is None
                        else attempt.created_at
                    )
                    - timedelta(seconds=1),
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_two_connections_serialize_stock_oversell(
    db_session, vendor_user, customer_user
) -> None:
    """The inventory row lock makes exactly one of two competing claims win."""

    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    await db_session.commit()
    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    async with sessions() as first, sessions() as second:
        first.add(
            _reservation(
                graph, intent, quote, option, selection, customer_user["user"].id, sku
            )
        )
        await first.flush()
        second.add(
            _reservation(
                graph, intent, quote, option, selection, customer_user["user"].id, sku
            )
        )
        second_commit = asyncio.create_task(second.commit())
        await asyncio.sleep(0.1)
        assert (
            not second_commit.done()
        ), "competing reservation did not wait on inventory lock"
        await first.commit()
        with pytest.raises(DBAPIError, match="stock reservation exceeds"):
            await second_commit
        await second.rollback()

    count = await db_session.scalar(
        text("SELECT count(*) FROM stock_reservations WHERE state='active'")
    )
    assert count == 1


@pytest.mark.asyncio
async def test_two_connections_serialize_payment_claim(
    db_session, vendor_user, customer_user
) -> None:
    """Only one worker can advance a pending attempt into provider-call ownership."""

    from app.models.stock_payment_persistence import PaymentAttemptReservation

    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = _reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = _payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.commit()
    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)

    async with sessions() as first, sessions() as second:
        first_token = uuid.uuid4()
        second_token = uuid.uuid4()
        await _coordinate_payment_attempt(first, attempt.id, attempt.order_id)
        await first.execute(
            text(
                "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                "row_version=2 WHERE id=:id"
            ),
            {"token": first_token, "id": attempt.id},
        )

        async def competing_claim():
            await _coordinate_payment_attempt(second, attempt.id, attempt.order_id)
            await second.execute(
                text(
                    "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                    "row_version=2 WHERE id=:id"
                ),
                {"token": second_token, "id": attempt.id},
            )
            await second.commit()

        second_claim = asyncio.create_task(competing_claim())
        await asyncio.sleep(0.1)
        assert (
            not second_claim.done()
        ), "competing payment claim did not wait on row lock"
        await first.commit()
        with pytest.raises(DBAPIError, match="payment attempt transition is illegal"):
            await second_claim
        await second.rollback()

    row = (
        await db_session.execute(
            text(
                "SELECT state, lease_token, row_version FROM payment_attempts WHERE id=:id"
            ),
            {"id": attempt.id},
        )
    ).one()
    assert row == ("call_started", first_token, 2)


@pytest.mark.asyncio
async def test_active_payment_attempt_locks_its_exact_reservation_set(
    db_session, vendor_user, customer_user
) -> None:
    """No reservation may appear after an attempt snapshots the exact active set."""

    from app.models.stock_payment_persistence import PaymentAttemptReservation

    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user, stock=2
    )
    reservation = _reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = _payment_attempt(
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

    with pytest.raises(
        DBAPIError, match="reservation set is locked by active payment attempt"
    ):
        async with db_session.begin_nested():
            db_session.add(
                _reservation(
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
async def test_expired_payment_lease_requires_reconciliation_before_retry(
    db_session, vendor_user, customer_user
) -> None:
    """Unknown provider work is terminal but not safely retryable."""

    from app.models.stock_payment_persistence import (
        PaymentAttemptEvidence,
        PaymentAttemptReservation,
    )

    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = _reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = _payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        claim_ttl_seconds=1,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    recovery_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:id"
        ),
        {"token": recovery_token, "id": attempt.id},
    )
    await asyncio.sleep(1.1)
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="recovery_worker",
        event_id=f"evt-{uuid.uuid4().hex}",
        evidence_type="outcome_unknown",
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()

    await _present_payment_lease(db_session, recovery_token)
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='abandoned_unknown', "
            "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:id"
        ),
        {"evidence_id": evidence.id, "id": attempt.id},
    )

    successor = _payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    successor.supersedes_attempt_id = attempt.id
    with pytest.raises(
        DBAPIError, match="payment retry must supersede current terminal leaf"
    ):
        async with db_session.begin_nested():
            db_session.add(successor)
            await db_session.flush()


@pytest.mark.asyncio
async def test_verification_serializes_against_reservation_release(
    db_session, vendor_user, customer_user
) -> None:
    """Verification locks the exact reservation set before committing success."""
    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    reservation = _reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = _payment_attempt(
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
            "UPDATE payment_attempts SET state='call_started', "
            "lease_token=:lease_token, row_version=2 WHERE id=:id"
        ),
        {"lease_token": lease_token, "id": attempt.id},
    )
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway",
        event_id="evt-race-verify-release",
        evidence_type="payment_verified",
        evidence_hash="c" * 64,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    verifier = factory()
    releaser = factory()
    try:
        await _present_payment_lease(verifier, lease_token)
        await _coordinate_payment_attempt(verifier, attempt.id, attempt.order_id)
        await verifier.execute(
            text(
                "UPDATE payment_attempts SET state='verified', "
                "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:id"
            ),
            {"evidence_id": evidence.id, "id": attempt.id},
        )

        async def competing_release():
            await _coordinate_reservation(releaser, reservation)
            return await releaser.execute(
                text(
                    "UPDATE stock_reservations SET state='released', "
                    "terminal_reason='payment cancelled', row_version=2 WHERE id=:id"
                ),
                {"id": reservation.id},
            )

        release_task = asyncio.create_task(competing_release())
        await asyncio.sleep(0.1)
        assert not release_task.done(), "release bypassed verification reservation lock"
        await verifier.commit()
        with pytest.raises(DBAPIError, match="verified payment"):
            await release_task
        await releaser.rollback()
    finally:
        await verifier.close()
        await releaser.close()


@pytest.mark.asyncio
async def test_verification_sees_release_committed_while_waiting(
    db_session, vendor_user, customer_user
) -> None:
    """READ COMMITTED verification re-reads a reservation after its lock wait."""
    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    reservation = _reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = _payment_attempt(
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
            "UPDATE payment_attempts SET state='call_started', "
            "lease_token=:lease_token, row_version=2 WHERE id=:id"
        ),
        {"lease_token": lease_token, "id": attempt.id},
    )
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway",
        event_id="evt-race-release-verify",
        evidence_type="payment_verified",
        evidence_hash="e" * 64,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    releaser = factory()
    verifier = factory()
    try:
        # Simulate independently persisted terminal truth while retaining a real
        # row lock. The verification trigger remains enabled in its own session.
        await releaser.execute(text("SET LOCAL session_replication_role = replica"))
        await releaser.execute(
            text(
                "UPDATE stock_reservations SET state='released', "
                "terminal_reason='reservation released', terminal_at=statement_timestamp(), "
                "updated_at=statement_timestamp(), row_version=2 WHERE id=:id"
            ),
            {"id": reservation.id},
        )
        await _present_payment_lease(verifier, lease_token)

        async def competing_verification():
            await _coordinate_payment_attempt(verifier, attempt.id, attempt.order_id)
            return await verifier.execute(
                text(
                    "UPDATE payment_attempts SET state='verified', "
                    "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:id"
                ),
                {"evidence_id": evidence.id, "id": attempt.id},
            )

        verification_task = asyncio.create_task(competing_verification())
        await asyncio.sleep(0.1)
        assert not verification_task.done(), "verification bypassed reservation lock"
        await releaser.commit()
        with pytest.raises(DBAPIError, match="requires live reservations"):
            await asyncio.wait_for(verification_task, timeout=2)
        await verifier.rollback()
    finally:
        await releaser.close()
        await verifier.close()


@pytest.mark.asyncio
async def test_expired_claim_holder_cannot_complete(
    db_session, vendor_user, customer_user
) -> None:
    graph, intent, quote, option, selection, sku = await _checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    reservation = _reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = _payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        claim_ttl_seconds=1,
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
            "UPDATE payment_attempts SET state='call_started', "
            "lease_token=:lease_token, row_version=2 WHERE id=:id"
        ),
        {"lease_token": lease_token, "id": attempt.id},
    )
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway",
        event_id="evt-expired-holder",
        evidence_type="payment_verified",
        evidence_hash="d" * 64,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.commit()
    await asyncio.sleep(1.1)
    await _present_payment_lease(db_session, lease_token)

    with pytest.raises(DBAPIError, match="payment claim lease expired"):
        async with db_session.begin_nested():
            await _coordinate_payment_attempt(db_session, attempt.id, attempt.order_id)
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='verified', "
                    "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:id"
                ),
                {"evidence_id": evidence.id, "id": attempt.id},
            )
