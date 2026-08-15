"""Celery dispatch for the persisted checkout outbox."""

import asyncio
import socket

from app.core.database import AsyncSessionLocal
from app.services.checkout.outbox import (
    claim_checkout_events,
    complete_checkout_event,
    fail_checkout_event,
    retry_checkout_event,
)
from app.services.orders.vendor_fulfilment import start_verified_order_fulfilment


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
                await complete_checkout_event(
                    session,
                    event_id=event.id,
                    owner=owner,
                    claim_token=event.claim_token,
                    effect_identity=event.effect_identity,
                )
                await session.commit()
                counts["completed"] += 1
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


def dispatch_checkout_outbox() -> dict[str, int]:
    """Synchronous Celery boundary around one bounded async dispatch tick."""
    return asyncio.run(dispatch_checkout_events_once())
