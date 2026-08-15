"""Milestone 4 checkout-outbox lease and delivery guarantees."""

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.checkout_outbox import CheckoutOutboxEvent
from app.services.checkout.outbox import (
    claim_checkout_events,
    complete_checkout_event,
    enqueue_checkout_event,
    fail_checkout_event,
)
from tests.test_stock_payment_persistence import _checkout_subject


@pytest.mark.asyncio
async def test_expired_claim_is_recovered_without_duplicate_effect_identity(
    db_session, vendor_user, customer_user
):
    graph, *_ = await _checkout_subject(db_session, vendor_user, customer_user)
    event = await enqueue_checkout_event(
        db_session,
        event_type="payment_verified_start_order",
        source_id=uuid.uuid4(),
        order_id=graph["order"].id,
        payload={
            "version": 1,
            "order_id": str(graph["order"].id),
            "workflow_cohort": "legacy_pre_bridge",
        },
    )
    await db_session.commit()
    now = datetime.now(timezone.utc)
    first = await claim_checkout_events(
        db_session, owner="worker-a", now=now, limit=1, lease_seconds=30
    )
    assert [row.id for row in first] == [event.id]
    await db_session.commit()

    before_expiry = await claim_checkout_events(
        db_session,
        owner="worker-b",
        now=now + timedelta(seconds=29),
        limit=1,
        lease_seconds=30,
    )
    assert before_expiry == []
    recovered = await claim_checkout_events(
        db_session,
        owner="worker-b",
        now=now + timedelta(seconds=31),
        limit=1,
        lease_seconds=30,
    )
    assert [row.id for row in recovered] == [event.id]
    effect_identity = f"checkout-outbox:{event.id}"
    await complete_checkout_event(
        db_session,
        event_id=event.id,
        owner="worker-b",
        claim_token=recovered[0].claim_token,
        effect_identity=effect_identity,
    )
    await db_session.commit()
    replay = await claim_checkout_events(
        db_session,
        owner="worker-c",
        now=now + timedelta(seconds=100),
        limit=1,
        lease_seconds=30,
    )
    assert replay == []
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(CheckoutOutboxEvent)
            .where(CheckoutOutboxEvent.effect_identity == effect_identity)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_claim_is_bounded_and_payload_rejects_sensitive_keys(db_session):
    from app.services.checkout.outbox import enqueue_checkout_event

    with pytest.raises(ValueError, match="sensitive"):
        await enqueue_checkout_event(
            db_session,
            event_type="payment_verified_start_order",
            source_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            payload={"version": 1, "raw_provider_payload": {"secret": "forbidden"}},
        )


@pytest.mark.asyncio
async def test_two_connections_skip_locked_and_claim_each_event_once(
    db_session, vendor_user, customer_user
):
    graph, *_ = await _checkout_subject(db_session, vendor_user, customer_user)
    events = []
    for event_type in ("payment_verified_start_order", "payment_failed_release"):
        events.append(
            await enqueue_checkout_event(
                db_session,
                event_type=event_type,
                source_id=uuid.uuid4(),
                order_id=graph["order"].id,
                payload={
                    "version": 1,
                    "order_id": str(graph["order"].id),
                    "workflow_cohort": "legacy_pre_bridge",
                },
            )
        )
    await db_session.commit()
    event_ids = {event.id for event in events}

    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with sessions() as worker_a, sessions() as worker_b:
        first = await claim_checkout_events(
            worker_a, owner="worker-a", now=now, limit=1, lease_seconds=30
        )
        assert len(first) == 1
        second = await claim_checkout_events(
            worker_b, owner="worker-b", now=now, limit=2, lease_seconds=30
        )
        assert len(second) == 1
        assert {first[0].id, second[0].id} == event_ids
        await worker_b.commit()
        await worker_a.commit()

    db_session.expire_all()
    claimed = list(
        await db_session.scalars(
            select(CheckoutOutboxEvent).where(CheckoutOutboxEvent.id.in_(event_ids))
        )
    )
    assert {event.claim_owner for event in claimed} == {"worker-a", "worker-b"}
    assert all(event.attempt_count == 1 for event in claimed)


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_action", ["complete", "fail"])
async def test_same_owner_reclaim_fences_stale_claim_generation(
    db_session, vendor_user, customer_user, terminal_action
):
    graph, *_ = await _checkout_subject(db_session, vendor_user, customer_user)
    event = await enqueue_checkout_event(
        db_session,
        event_type="payment_verified_start_order",
        source_id=uuid.uuid4(),
        order_id=graph["order"].id,
        payload={
            "version": 1,
            "order_id": str(graph["order"].id),
            "workflow_cohort": "legacy_pre_bridge",
        },
    )
    await db_session.commit()

    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    claimed_at = datetime.now(timezone.utc)
    async with sessions() as first_session:
        first_claim = await claim_checkout_events(
            first_session,
            owner="worker-x",
            now=claimed_at,
            limit=1,
            lease_seconds=30,
        )
        token_a = first_claim[0].claim_token
        await first_session.commit()

    async with sessions() as second_session:
        second_claim = await claim_checkout_events(
            second_session,
            owner="worker-x",
            now=claimed_at + timedelta(seconds=31),
            limit=1,
            lease_seconds=30,
        )
        token_b = second_claim[0].claim_token
        await second_session.commit()

    assert token_a != token_b
    async with sessions() as stale_session:
        with pytest.raises(ValueError, match="claim is not owned"):
            await complete_checkout_event(
                stale_session,
                event_id=event.id,
                owner="worker-x",
                claim_token=token_a,
                effect_identity=event.effect_identity,
            )
        with pytest.raises(ValueError, match="claim is not owned"):
            await fail_checkout_event(
                stale_session,
                event_id=event.id,
                owner="worker-x",
                claim_token=token_a,
                failure_code="delivery_failed",
            )

    async with sessions() as current_session:
        if terminal_action == "complete":
            terminal_event = await complete_checkout_event(
                current_session,
                event_id=event.id,
                owner="worker-x",
                claim_token=token_b,
                effect_identity=event.effect_identity,
            )
        else:
            terminal_event = await fail_checkout_event(
                current_session,
                event_id=event.id,
                owner="worker-x",
                claim_token=token_b,
                failure_code="delivery_failed",
            )
        await current_session.commit()

    assert terminal_event.status == (
        "completed" if terminal_action == "complete" else "failed"
    )


def test_outbox_migration_matches_orm_and_real_upgrade_downgrade_cycle() -> None:
    root = Path(__file__).parents[1]
    migration = root / "alembic" / "versions" / "b3c4d5e6f7a8_add_checkout_outbox.py"
    source = migration.read_text(encoding="utf-8")
    for constraint in CheckoutOutboxEvent.__table__.constraints:
        if constraint.name:
            assert constraint.name in source
    for index in CheckoutOutboxEvent.__table__.indexes:
        assert index.name in source

    base_url = make_url(os.environ["DATABASE_URL"])
    sync_driver = base_url.drivername.split("+", 1)[0]
    admin_url = base_url.set(drivername=sync_driver, database="postgres")
    database = f"shopsoma_outbox_cycle_{uuid.uuid4().hex[:10]}"
    database_url = base_url.set(
        drivername=sync_driver, database=database
    ).render_as_string(hide_password=False)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    try:
        env = os.environ.copy()
        env.update(DATABASE_URL=database_url, SECRET_KEY="m4-test-key")

        def migrate(command: str, revision: str) -> None:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", command, revision],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr

        migrate("upgrade", "a2b3c4d5e6f7")
        target = create_engine(database_url)
        try:
            assert "checkout_outbox_events" not in inspect(target).get_table_names()
        finally:
            target.dispose()
        migrate("upgrade", "b3c4d5e6f7a8")
        target = create_engine(database_url)
        try:
            inspector = inspect(target)
            assert "checkout_outbox_events" in inspector.get_table_names()
            assert {
                column["name"]
                for column in inspector.get_columns("checkout_outbox_events")
            } == {column.name for column in CheckoutOutboxEvent.__table__.columns}
        finally:
            target.dispose()
        migrate("downgrade", "a2b3c4d5e6f7")
        target = create_engine(database_url)
        try:
            assert "checkout_outbox_events" not in inspect(target).get_table_names()
        finally:
            target.dispose()
    finally:
        with admin.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
            )
        admin.dispose()
