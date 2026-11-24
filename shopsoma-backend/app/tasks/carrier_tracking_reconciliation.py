"""Celery worker entrypoint for scheduled carrier tracking reconciliation."""

import asyncio

from app.core.database import engine
from app.services.shipping.carrier_reconciliation import (
    reconcile_active_carrier_shipments_once,
)


async def _reconcile_carrier_tracking_tick() -> dict[str, int]:
    """Run one bounded reconciliation pass and dispose engine before event loop closes."""
    try:
        return await reconcile_active_carrier_shipments_once()
    finally:
        await engine.dispose()


def reconcile_carrier_tracking() -> dict[str, int]:
    """Synchronous Celery boundary around one bounded async carrier reconciliation tick."""
    return asyncio.run(_reconcile_carrier_tracking_tick())


__all__ = ["reconcile_carrier_tracking"]
