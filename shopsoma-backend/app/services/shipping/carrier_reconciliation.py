"""Periodic fallback reconciliation for active carrier shipments."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.order import FulfillmentStatus, Order, PaymentStatus
from app.models.shipbubble_shipment import ShipbubbleShipment
from app.services.shipping.shipbubble_tracking import sync_shipbubble_shipment_status

logger = logging.getLogger(__name__)

_TERMINAL_RECONCILIATION_STATUSES = (
    FulfillmentStatus.DELIVERED,
    FulfillmentStatus.RETURNED,
    FulfillmentStatus.CANCELLED,
)


async def reconcile_active_carrier_shipments_once(
    *,
    batch_size: Optional[int] = None,
    session_factory=AsyncSessionLocal,
) -> dict[str, int]:
    """Poll active non-terminal ShipBubble shipments when webhooks have not arrived."""
    if not (settings.SHIPBUBBLE_API_KEY and settings.SHIPBUBBLE_API_KEY.strip()):
        logger.warning("[Carrier Reconciliation] Skipped: SHIPBUBBLE_API_KEY is not configured")
        return {
            "scanned": 0,
            "updated": 0,
            "unchanged": 0,
            "errors": 0,
            "skipped_unconfigured": 1,
        }

    effective_batch_size = batch_size or settings.CARRIER_RECONCILIATION_BATCH_SIZE

    async with session_factory() as db:
        order_ids = (
            await db.scalars(
                select(Order.id)
                .join(ShipbubbleShipment, ShipbubbleShipment.order_id == Order.id)
                .where(
                    ShipbubbleShipment.shipbubble_order_id.isnot(None),
                    Order.payment_status == PaymentStatus.PAID,
                    Order.fulfillment_status.notin_(_TERMINAL_RECONCILIATION_STATUSES),
                )
                .order_by(ShipbubbleShipment.updated_at.asc())
                .limit(effective_batch_size)
            )
        ).all()

    scanned = len(order_ids)
    updated = 0
    unchanged = 0
    errors = 0

    for order_id in order_ids:
        async with session_factory() as db:
            try:
                order = await db.scalar(
                    select(Order)
                    .where(Order.id == order_id)
                    .with_for_update(skip_locked=True)
                )
                if order is None:
                    continue
                if (
                    order.payment_status != PaymentStatus.PAID
                    or order.fulfillment_status in _TERMINAL_RECONCILIATION_STATUSES
                ):
                    continue

                before_status = order.fulfillment_status
                await sync_shipbubble_shipment_status(db, order=order, strict=True)
                if order.fulfillment_status != before_status:
                    updated += 1
                else:
                    unchanged += 1
            except Exception as exc:
                errors += 1
                await db.rollback()
                logger.warning(
                    "[Carrier Reconciliation] Failed syncing order %s: %s",
                    order_id,
                    exc,
                )

    if scanned > 0 or errors > 0:
        logger.info(
            "[Carrier Reconciliation] scanned=%s updated=%s unchanged=%s errors=%s",
            scanned,
            updated,
            unchanged,
            errors,
        )

    return {
        "scanned": scanned,
        "updated": updated,
        "unchanged": unchanged,
        "errors": errors,
        "skipped_unconfigured": 0,
    }
