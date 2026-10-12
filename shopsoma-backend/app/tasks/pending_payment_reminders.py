"""Celery worker entrypoint for pending checkout payment reminders."""

import asyncio

from app.core.database import engine
from app.services.payments.reminders import dispatch_pending_payment_reminders_once


async def _dispatch_pending_payment_reminders_tick() -> dict[str, int]:
    """Run one bounded scan-and-dispatch pass and dispose engine before event loop closes."""
    try:
        return await dispatch_pending_payment_reminders_once()
    finally:
        await engine.dispose()


def dispatch_pending_payment_reminders() -> dict[str, int]:
    """Synchronous Celery boundary around one bounded async reminder dispatch tick."""
    return asyncio.run(_dispatch_pending_payment_reminders_tick())


__all__ = ["dispatch_pending_payment_reminders"]
