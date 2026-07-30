"""Observed regressions for the final Lane 2A-4B persistence blockers."""

import asyncio
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.stock_payment_persistence import (
    PaymentAttemptEvidence,
    PaymentAttemptReservation,
    STOCK_PAYMENT_TRIGGER_DDLS,
)


def _lane_helpers():
    path = Path(__file__).with_name("test_stock_payment_persistence.py")
    spec = importlib.util.spec_from_file_location("stock_payment_blocker_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _present_payment_lease(session, lease_token: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('shopsoma.payment_lease_token', :token, true)"),
        {"token": str(lease_token)},
    )


async def _attempt_subject(db_session, vendor_user, customer_user, **attempt_overrides):
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
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        **attempt_overrides,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    return lane, graph, intent, quote, option, selection, reservation, attempt


@pytest.mark.asyncio
async def test_expired_pending_attempt_cannot_start_provider_call(
    db_session, vendor_user, customer_user
) -> None:
    *_, reservation, attempt = await _attempt_subject(
        db_session, vendor_user, customer_user
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET created_at=statement_timestamp() - interval '2 seconds', "
            "expires_at=statement_timestamp() - interval '1 second', "
            "authorization_deadline_at=statement_timestamp() - interval '1 second' "
            "+ authorization_grace_seconds * interval '1 second' WHERE id=:id"
        ),
        {"id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))

    with pytest.raises(DBAPIError, match="payment attempt window elapsed"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
                    "row_version=2 WHERE id=:id"
                ),
                {"token": uuid.uuid4(), "id": attempt.id},
            )

    row = (
        await db_session.execute(
            text(
                "SELECT state, lease_token, row_version FROM payment_attempts WHERE id=:id"
            ),
            {"id": attempt.id},
        )
    ).one()
    assert row == ("pending", None, 1)
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM payment_attempt_reservations WHERE attempt_id=:id"
            ),
            {"id": attempt.id},
        )
        == 1
    )
    assert (
        await db_session.scalar(
            text("SELECT state FROM stock_reservations WHERE id=:id"),
            {"id": reservation.id},
        )
        == "active"
    )


@pytest.mark.asyncio
async def test_call_started_completion_requires_exact_lease_owner(
    db_session, vendor_user, customer_user
) -> None:
    *_, reservation, attempt = await _attempt_subject(
        db_session, vendor_user, customer_user
    )
    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:id"
        ),
        {"token": lease_token, "id": attempt.id},
    )
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway",
        event_id=f"evt-owner-{uuid.uuid4().hex}",
        evidence_type="authorization",
        evidence_hash="a" * 64,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()

    await _present_payment_lease(db_session, uuid.uuid4())
    with pytest.raises(DBAPIError, match="payment lease token does not own claim"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='verified', "
                    "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:id"
                ),
                {"evidence_id": evidence.id, "id": attempt.id},
            )

    state = (
        await db_session.execute(
            text(
                "SELECT state, lease_token, row_version FROM payment_attempts WHERE id=:id"
            ),
            {"id": attempt.id},
        )
    ).one()
    assert state == ("call_started", lease_token, 2)

    await _present_payment_lease(db_session, lease_token)
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='verified', "
            "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:id"
        ),
        {"evidence_id": evidence.id, "id": attempt.id},
    )
    assert (
        await db_session.scalar(
            text("SELECT state FROM stock_reservations WHERE id=:id"),
            {"id": reservation.id},
        )
        == "active"
    )


@pytest.mark.asyncio
async def test_reservation_unit_price_rejects_postgresql_nan(
    db_session, vendor_user, customer_user
) -> None:
    *_, reservation, _ = await _attempt_subject(db_session, vendor_user, customer_user)

    with pytest.raises(DBAPIError, match="ck_stock_reservations_money"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("SET LOCAL session_replication_role = replica")
            )
            await db_session.execute(
                text(
                    "UPDATE stock_reservations SET unit_price='NaN'::numeric, "
                    "line_amount='NaN'::numeric WHERE id=:id"
                ),
                {"id": reservation.id},
            )


@pytest.mark.asyncio
async def test_payment_amount_rejects_postgresql_nan(
    db_session, vendor_user, customer_user
) -> None:
    *_, attempt = await _attempt_subject(db_session, vendor_user, customer_user)

    with pytest.raises(DBAPIError, match="ck_payment_attempts_money"):
        async with db_session.begin_nested():
            await db_session.execute(
                text("SET LOCAL session_replication_role = replica")
            )
            await db_session.execute(
                text("UPDATE payment_attempts SET amount='NaN'::numeric WHERE id=:id"),
                {"id": attempt.id},
            )


@pytest.mark.asyncio
async def test_verification_honors_authorization_grace_after_reservation_lock_wait(
    db_session, vendor_user, customer_user
) -> None:
    *_, reservation, attempt = await _attempt_subject(
        db_session, vendor_user, customer_user
    )
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE stock_reservations SET expires_at=statement_timestamp() + interval '1 second' "
            "WHERE id=:id"
        ),
        {"id": reservation.id},
    )
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET expires_at=statement_timestamp() + interval '1 second', "
            "authorization_deadline_at=statement_timestamp() + interval '301 seconds' "
            "WHERE id=:id"
        ),
        {"id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:id"
        ),
        {"token": lease_token, "id": attempt.id},
    )
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway",
        event_id=f"evt-clock-{uuid.uuid4().hex}",
        evidence_type="authorization",
        evidence_hash="b" * 64,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    locker = factory()
    verifier = factory()
    try:
        await locker.execute(
            text("SELECT 1 FROM stock_reservations WHERE id=:id FOR UPDATE"),
            {"id": reservation.id},
        )
        await _present_payment_lease(verifier, lease_token)
        verification_task = asyncio.create_task(
            verifier.execute(
                text(
                    "UPDATE payment_attempts SET state='verified', "
                    "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:id"
                ),
                {"evidence_id": evidence.id, "id": attempt.id},
            )
        )
        await asyncio.sleep(0.1)
        assert not verification_task.done(), "verification bypassed reservation lock"
        await asyncio.sleep(1.0)
        await locker.commit()
        await asyncio.wait_for(verification_task, timeout=2)
        await verifier.commit()
        state = await db_session.scalar(
            text("SELECT state FROM payment_attempts WHERE id=:id"),
            {"id": attempt.id},
        )
        assert state == "verified"
    finally:
        await locker.close()
        await verifier.close()


@pytest.mark.asyncio
async def test_reservation_creation_rechecks_quote_expiry_after_inventory_lock_wait(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user
    )
    await db_session.commit()
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE customer_shipping_quotes "
            "SET expires_at=clock_timestamp() + interval '800 milliseconds' "
            "WHERE id=:id"
        ),
        {"id": quote.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    locker = factory()
    creator = factory()
    create_task = None
    try:
        await locker.execute(
            text("SELECT id FROM products WHERE id=:id FOR UPDATE"),
            {"id": graph["item"].product_id},
        )
        reservation = lane._reservation(
            graph,
            intent,
            quote,
            option,
            selection,
            customer_user["user"].id,
            sku,
        )
        creator.add(reservation)
        create_task = asyncio.create_task(creator.flush())
        await asyncio.sleep(0.1)
        assert not create_task.done(), "reservation insert did not wait on inventory"
        await asyncio.sleep(0.9)
        await locker.commit()
        with pytest.raises(
            DBAPIError, match="stock reservation subject binding is invalid"
        ):
            await create_task
        await creator.rollback()
    finally:
        if create_task is not None and not create_task.done():
            create_task.cancel()
        await locker.close()
        await creator.close()


@pytest.mark.asyncio
async def test_pending_claim_rechecks_database_clock_after_row_lock_wait(
    db_session, vendor_user, customer_user
) -> None:
    lane, graph, intent, quote, option, selection, reservation, attempt = (
        await _attempt_subject(db_session, vendor_user, customer_user)
    )
    await db_session.commit()

    try:
        await db_session.execute(
            text(
                "ALTER TABLE payment_attempts DISABLE TRIGGER "
                "trg_payment_attempts_validate"
            )
        )
        await db_session.execute(
            text(
                "UPDATE payment_attempts "
                "SET expires_at=deadline.expires_at, "
                "authorization_deadline_at=deadline.expires_at "
                "+ authorization_grace_seconds * interval '1 second' "
                "FROM (SELECT clock_timestamp() + interval '800 milliseconds' "
                "AS expires_at) AS deadline WHERE id=:id"
            ),
            {"id": attempt.id},
        )
        await db_session.execute(
            text(
                "ALTER TABLE payment_attempts ENABLE TRIGGER "
                "trg_payment_attempts_validate"
            )
        )
        await db_session.commit()
    finally:
        await db_session.rollback()
        await db_session.execute(
            text(
                "ALTER TABLE payment_attempts ENABLE TRIGGER "
                "trg_payment_attempts_validate"
            )
        )
        await db_session.commit()

    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    locker = factory()
    claimant = factory()
    claim_task = None
    try:
        await locker.execute(
            text("SELECT id FROM payment_attempts WHERE id=:id FOR UPDATE"),
            {"id": attempt.id},
        )
        claim_task = asyncio.create_task(
            claimant.execute(
                text(
                    "UPDATE payment_attempts SET state='call_started', "
                    "lease_token=:token, row_version=2 WHERE id=:id"
                ),
                {"token": uuid.uuid4(), "id": attempt.id},
            )
        )
        await asyncio.sleep(0.1)
        assert not claim_task.done(), "claim did not wait on the attempt row"
        await asyncio.sleep(0.9)
        await locker.commit()
        with pytest.raises(DBAPIError, match="payment attempt window elapsed"):
            await claim_task
        await claimant.rollback()
    finally:
        if claim_task is not None and not claim_task.done():
            claim_task.cancel()
        await locker.close()
        await claimant.close()


@pytest.mark.asyncio
async def test_terminal_transition_preserves_call_started_audit_timestamp(
    db_session, vendor_user, customer_user
) -> None:
    lane, graph, intent, quote, option, selection, reservation, attempt = (
        await _attempt_subject(db_session, vendor_user, customer_user)
    )
    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:token, "
            "row_version=2 WHERE id=:id"
        ),
        {"token": lease_token, "id": attempt.id},
    )
    evidence = lane.PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway",
        event_id=f"evt-{uuid.uuid4().hex}",
        evidence_type="failure",
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()
    await _present_payment_lease(db_session, lease_token)

    with pytest.raises(DBAPIError, match="call start audit is immutable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='failed', "
                    "call_started_at=call_started_at + interval '1 second', "
                    "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:id"
                ),
                {"evidence_id": evidence.id, "id": attempt.id},
            )


@pytest.mark.asyncio
async def test_pending_failure_cannot_fabricate_call_started_audit_timestamp(
    db_session, vendor_user, customer_user
) -> None:
    lane, graph, intent, quote, option, selection, reservation, attempt = (
        await _attempt_subject(db_session, vendor_user, customer_user)
    )
    evidence = lane.PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway",
        event_id=f"evt-{uuid.uuid4().hex}",
        evidence_type="failure",
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()

    with pytest.raises(DBAPIError, match="call start audit is immutable"):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE payment_attempts SET state='failed', "
                    "call_started_at=clock_timestamp(), "
                    "terminal_evidence_id=:evidence_id, row_version=2 WHERE id=:id"
                ),
                {"evidence_id": evidence.id, "id": attempt.id},
            )


def test_claim_expiry_checks_are_fail_closed_at_boundary() -> None:
    source = "\n".join(STOCK_PAYMENT_TRIGGER_DDLS)
    assert source.count("now_at >= OLD.claim_expires_at") >= 2


@pytest.mark.asyncio
async def test_payment_and_quote_successor_follow_order_then_quote_lock_order(
    db_session, vendor_user, customer_user
) -> None:
    """The cross-aggregate paths serialize instead of deadlocking order/quote locks."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.commit()

    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
    )
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    payment_session = factory()
    quote_session = factory()

    async def create_payment_attempt() -> None:
        payment_session.add(attempt)
        await payment_session.flush()
        payment_session.add(
            PaymentAttemptReservation(
                attempt_id=attempt.id, reservation_id=reservation.id
            )
        )
        await payment_session.flush()
        await payment_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        await payment_session.commit()

    payment_task = None
    try:
        await quote_session.execute(
            text("SELECT 1 FROM orders WHERE id=:id FOR UPDATE"),
            {"id": graph["order"].id},
        )
        payment_task = asyncio.create_task(create_payment_attempt())
        await asyncio.sleep(0.1)
        assert (
            not payment_task.done()
        ), "payment path did not wait on the order lock first"

        successor_id = uuid.uuid4()
        with pytest.raises(DBAPIError, match="selected quote cannot be superseded"):
            await quote_session.execute(
                text(
                    """
                    INSERT INTO customer_shipping_quotes (
                        id, order_id, customer_id, intent_id, package_id,
                        package_version, seal_id, origin_hub_id,
                        destination_snapshot_hash, source_rate_response_id,
                        supersedes_quote_id, currency, ttl_seconds,
                        initiating_actor_type, initiating_actor_id, source_command,
                        idempotency_key, request_fingerprint, schema_version
                    )
                    SELECT
                        :successor_id, order_id, customer_id, intent_id, package_id,
                        package_version, seal_id, origin_hub_id,
                        destination_snapshot_hash, source_rate_response_id,
                        id, currency, ttl_seconds, initiating_actor_type,
                        initiating_actor_id, source_command, :idempotency_key,
                        :request_fingerprint, schema_version
                    FROM customer_shipping_quotes WHERE id=:predecessor_id
                    """
                ),
                {
                    "successor_id": successor_id,
                    "predecessor_id": quote.id,
                    "idempotency_key": f"quote-successor-{successor_id.hex}",
                    "request_fingerprint": uuid.uuid4().hex * 2,
                },
            )
        await quote_session.rollback()
        await asyncio.wait_for(payment_task, timeout=3)
    finally:
        if payment_task is not None and not payment_task.done():
            payment_task.cancel()
            await asyncio.gather(payment_task, return_exceptions=True)
        await payment_session.rollback()
        await quote_session.rollback()
        await payment_session.close()
        await quote_session.close()
