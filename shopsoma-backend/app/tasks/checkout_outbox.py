"""Celery dispatch for the persisted checkout outbox."""

import asyncio
import socket

from app.core.database import AsyncSessionLocal, engine
from app.models.checkout_outbox import CheckoutOutboxEvent
from app.services.checkout.outbox import (
    claim_checkout_events,
    complete_checkout_event,
    fail_checkout_event,
    retry_checkout_event,
)
from app.services.orders.vendor_fulfilment import start_verified_order_fulfilment


class LatePaymentExceptionRequiresReview(RuntimeError):
    """Late payment exception needs durable staff reconciliation."""


async def _route_late_payment_exception(session, *, event: CheckoutOutboxEvent) -> None:
    payload = event.payload if isinstance(event.payload, dict) else {}
    reason_code = payload.get("reason_code")
    if reason_code not in {"reservation_released", "stock_unavailable"}:
        raise ValueError("late payment exception payload truth mismatch")
    raise LatePaymentExceptionRequiresReview(
        f"late-payment:{reason_code}:manual-reconciliation-required"
    )


async def dispatch_checkout_events_once(
    *, session_factory=AsyncSessionLocal, owner: str | None = None, limit: int = 25
) -> dict[str, int]:
    owner = owner or f"checkout-outbox:{socket.gethostname()}"
    counts = {"claimed": 0, "completed": 0, "retried": 0, "failed": 0}
    async with session_factory() as session:
        events = await claim_checkout_events(session, owner=owner, limit=limit)
        counts["claimed"] = len(events)
        await session.commit()

    for event in events:
        try:
            async with session_factory() as session:
                if event.event_type == "payment_verified_start_order":
                    await start_verified_order_fulfilment(
                        session, order_id=event.order_id
                    )
                elif event.event_type == "late_payment_exception":
                    await _route_late_payment_exception(session, event=event)
                await complete_checkout_event(
                    session,
                    event_id=event.id,
                    owner=owner,
                    claim_token=event.claim_token,
                    effect_identity=event.effect_identity,
                )
                await session.commit()
                counts["completed"] += 1
        except LatePaymentExceptionRequiresReview as error:
            async with session_factory() as session:
                await fail_checkout_event(
                    session,
                    event_id=event.id,
                    owner=owner,
                    claim_token=event.claim_token,
                    failure_code=str(error),
                )
                counts["failed"] += 1
                await session.commit()
        except Exception:
            async with session_factory() as session:
                if event.attempt_count < 3:
                    await retry_checkout_event(
                        session,
                        event_id=event.id,
                        owner=owner,
                        claim_token=event.claim_token,
                    )
                    counts["retried"] += 1
                else:
                    await fail_checkout_event(
                        session,
                        event_id=event.id,
                        owner=owner,
                        claim_token=event.claim_token,
                        failure_code="dispatch_failed",
                    )
                    counts["failed"] += 1
                await session.commit()
    return counts


async def _dispatch_checkout_outbox_tick() -> dict[str, int]:
    """Run one tick and release loop-bound pooled connections before loop close."""
    try:
        return await dispatch_checkout_events_once()
    finally:
        await engine.dispose()


def dispatch_checkout_outbox() -> dict[str, int]:
    """Synchronous Celery boundary around one bounded async dispatch tick."""
    return asyncio.run(_dispatch_checkout_outbox_tick())
