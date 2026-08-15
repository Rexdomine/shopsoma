"""Transactional checkout-outbox persistence and lease operations only."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checkout_outbox import CheckoutOutboxEvent

_ALLOWED_PAYLOAD_KEYS = {
    "payment_verified_start_order": {"version", "order_id", "workflow_cohort"},
    "payment_failed_release": {"version", "order_id", "workflow_cohort"},
    "late_payment_exception": {
        "version",
        "order_id",
        "workflow_cohort",
        "reason_code",
    },
}
_SENSITIVE_FRAGMENTS = (
    "secret",
    "token",
    "authorization",
    "provider_payload",
    "raw_provider",
    "email",
    "phone",
    "address",
    "customer_name",
)


def _validate_payload(event_type: str, order_id: uuid.UUID, payload: dict) -> None:
    allowed = _ALLOWED_PAYLOAD_KEYS.get(event_type)
    if allowed is None:
        raise ValueError("unsupported checkout outbox event")
    if not isinstance(payload, dict):
        raise ValueError("checkout outbox payload allowlist violation")

    def contains_sensitive(value: object) -> bool:
        if isinstance(value, dict):
            return any(
                any(
                    fragment in str(key).casefold() for fragment in _SENSITIVE_FRAGMENTS
                )
                or contains_sensitive(nested)
                for key, nested in value.items()
            )
        if isinstance(value, list):
            return any(contains_sensitive(nested) for nested in value)
        return False

    if contains_sensitive(payload):
        raise ValueError("sensitive checkout outbox payload is forbidden")
    if set(payload) != allowed:
        raise ValueError("checkout outbox payload allowlist violation")
    if payload.get("version") != 1 or payload.get("order_id") != str(order_id):
        raise ValueError("checkout outbox payload truth mismatch")
    if payload.get("workflow_cohort") not in {
        "legacy_pre_bridge",
        "domestic_checkout_v1",
    }:
        raise ValueError("checkout outbox payload truth mismatch")
    if event_type == "late_payment_exception" and payload.get("reason_code") not in {
        "reservation_released",
        "stock_unavailable",
    }:
        raise ValueError("checkout outbox payload truth mismatch")


async def enqueue_checkout_event(
    session: AsyncSession,
    *,
    event_type: str,
    source_id: uuid.UUID,
    order_id: uuid.UUID,
    payload: dict,
) -> CheckoutOutboxEvent:
    """Insert or return one deterministic logical event without committing."""
    _validate_payload(event_type, order_id, payload)
    existing = await session.scalar(
        select(CheckoutOutboxEvent).where(
            CheckoutOutboxEvent.event_type == event_type,
            CheckoutOutboxEvent.source_id == source_id,
        )
    )
    if existing is not None:
        if existing.order_id != order_id or existing.payload != payload:
            raise ValueError("checkout outbox logical event conflict")
        return existing
    event_id = uuid.uuid4()
    event = CheckoutOutboxEvent(
        id=event_id,
        event_type=event_type,
        source_id=source_id,
        order_id=order_id,
        payload_version=1,
        payload=payload,
        effect_identity=f"checkout-outbox:{event_id}",
    )
    session.add(event)
    await session.flush()
    return event


async def claim_checkout_events(
    session: AsyncSession,
    *,
    owner: str,
    now: datetime | None = None,
    limit: int = 25,
    lease_seconds: int = 60,
) -> list[CheckoutOutboxEvent]:
    """Bounded SKIP LOCKED claim, including recovery of expired leases."""
    if not owner or len(owner) > 100:
        raise ValueError("invalid checkout outbox owner")
    if limit < 1 or limit > 100 or lease_seconds < 1 or lease_seconds > 900:
        raise ValueError("invalid checkout outbox claim bounds")
    now = now or datetime.now(timezone.utc)
    rows = list(
        await session.scalars(
            select(CheckoutOutboxEvent)
            .where(
                CheckoutOutboxEvent.available_at <= now,
                or_(
                    CheckoutOutboxEvent.status == "pending",
                    (
                        (CheckoutOutboxEvent.status == "claimed")
                        & (CheckoutOutboxEvent.claim_expires_at <= now)
                    ),
                ),
            )
            .order_by(CheckoutOutboxEvent.available_at, CheckoutOutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
    )
    for row in rows:
        row.status = "claimed"
        row.claim_owner = owner
        row.claim_token = uuid.uuid4()
        row.claim_expires_at = now + timedelta(seconds=lease_seconds)
        row.attempt_count += 1
        row.updated_at = now
    await session.flush()
    return rows


async def complete_checkout_event(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    owner: str,
    claim_token: uuid.UUID,
    effect_identity: str,
) -> CheckoutOutboxEvent:
    event = await session.scalar(
        select(CheckoutOutboxEvent)
        .where(CheckoutOutboxEvent.id == event_id)
        .with_for_update()
    )
    if (
        event is None
        or event.status != "claimed"
        or event.claim_owner != owner
        or event.claim_token != claim_token
        or event.claim_expires_at <= datetime.now(timezone.utc)
    ):
        raise ValueError("checkout outbox claim is not owned")
    if event.effect_identity != effect_identity:
        raise ValueError("checkout outbox effect identity mismatch")
    event.status = "completed"
    event.claim_owner = None
    event.claim_token = None
    event.claim_expires_at = None
    event.completed_at = datetime.now(timezone.utc)
    event.updated_at = event.completed_at
    await session.flush()
    return event


async def fail_checkout_event(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    owner: str,
    claim_token: uuid.UUID,
    failure_code: str,
) -> CheckoutOutboxEvent:
    event = await session.scalar(
        select(CheckoutOutboxEvent)
        .where(CheckoutOutboxEvent.id == event_id)
        .with_for_update()
    )
    if (
        event is None
        or event.status != "claimed"
        or event.claim_owner != owner
        or event.claim_token != claim_token
        or event.claim_expires_at <= datetime.now(timezone.utc)
    ):
        raise ValueError("checkout outbox claim is not owned")
    event.status = "failed"
    event.claim_owner = None
    event.claim_token = None
    event.claim_expires_at = None
    event.failed_at = datetime.now(timezone.utc)
    event.failure_code = failure_code
    event.updated_at = event.failed_at
    await session.flush()
    return event


async def retry_checkout_event(
    session: AsyncSession,
    *,
    event_id: uuid.UUID,
    owner: str,
    claim_token: uuid.UUID,
    delay_seconds: int = 30,
) -> CheckoutOutboxEvent:
    """Release an owned claim for a bounded delayed retry."""
    if delay_seconds < 1 or delay_seconds > 900:
        raise ValueError("invalid checkout outbox retry delay")
    event = await session.scalar(
        select(CheckoutOutboxEvent)
        .where(CheckoutOutboxEvent.id == event_id)
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if (
        event is None
        or event.status != "claimed"
        or event.claim_owner != owner
        or event.claim_token != claim_token
        or event.claim_expires_at <= now
    ):
        raise ValueError("checkout outbox claim is not owned")
    event.status = "pending"
    event.claim_owner = None
    event.claim_token = None
    event.claim_expires_at = None
    event.available_at = now + timedelta(seconds=delay_seconds)
    event.updated_at = now
    await session.flush()
    return event


__all__ = [
    "claim_checkout_events",
    "complete_checkout_event",
    "enqueue_checkout_event",
    "fail_checkout_event",
    "retry_checkout_event",
]
