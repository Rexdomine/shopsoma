"""Idempotent reconciliation script for out-of-step ShipBubble orders.

Usage (dry-run by default):
    python scripts/reconcile_shipbubble_orders.py
    python scripts/reconcile_shipbubble_orders.py --database-url postgresql://... --apply --report-path report.json
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
from app.models.order import FulfillmentStatus, Order, OrderItem
from app.models.shipbubble_shipment import ShipbubbleShipment
from app.models.vendor_pickup import VendorPickup
from app.services.orders.fulfillment_sync import (
    can_apply_carrier_status_transition,
    sync_vendor_items_and_pickups_for_order_status,
)
from app.services.orders.made_to_order_readiness import is_picked_up

SHIPBUBBLE_STATUS_TO_FULFILLMENT: dict[str, FulfillmentStatus] = {
    "pending": FulfillmentStatus.PREPARING_FOR_PICKUP,
    "confirmed": FulfillmentStatus.PICKUP_SCHEDULED,
    "picked_up": FulfillmentStatus.PICKED_UP,
    "pickup_completed": FulfillmentStatus.PICKED_UP,
    "in_transit": FulfillmentStatus.IN_TRANSIT,
    "in-transit": FulfillmentStatus.IN_TRANSIT,
    "out_for_delivery": FulfillmentStatus.OUT_FOR_DELIVERY,
    "out-for-delivery": FulfillmentStatus.OUT_FOR_DELIVERY,
    "completed": FulfillmentStatus.DELIVERED,
    "delivered": FulfillmentStatus.DELIVERED,
    "delivery_failed": FulfillmentStatus.DELIVERY_FAILED,
    "failed": FulfillmentStatus.DELIVERY_FAILED,
    "returned": FulfillmentStatus.RETURNED,
    "cancelled": FulfillmentStatus.CANCELLED,
    "canceled": FulfillmentStatus.CANCELLED,
}


def _build_async_url(raw_url: str) -> str:
    url = make_url(raw_url)
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    if sslmode is not None and "ssl" not in query:
        query["ssl"] = sslmode
    query.pop("application_name", None)
    return url.set(drivername="postgresql+asyncpg", query=query).render_as_string(
        hide_password=False
    )


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt is not None else None


def _snapshot_order_state(
    order: Order,
    shipment: Optional[ShipbubbleShipment],
    items: list[OrderItem],
    pickups: list[VendorPickup],
) -> dict[str, Any]:
    return {
        "order_id": str(order.id),
        "order_number": order.order_number,
        "workflow_cohort": order.workflow_cohort,
        "order_status": order.fulfillment_status.value,
        "delivered_at": _iso(order.delivered_at),
        "cancelled_at": _iso(order.cancelled_at),
        "shipbubble_order_id": shipment.shipbubble_order_id if shipment else None,
        "shipbubble_status": shipment.status if shipment else None,
        "items": [
            {
                "id": str(item.id),
                "product_title": item.product_title,
                "inventory_policy": item.inventory_policy,
                "fulfillment_status": item.fulfillment_status.value,
            }
            for item in sorted(items, key=lambda row: str(row.id))
        ],
        "pickups": [
            {
                "id": str(pickup.id),
                "order_item_id": str(pickup.order_item_id),
                "status": pickup.status.value,
                "actual_pickup_date": _iso(pickup.actual_pickup_date),
                "completed_at": _iso(pickup.completed_at),
            }
            for pickup in sorted(pickups, key=lambda row: str(row.id))
        ],
    }


async def reconcile_shipbubble_orders(
    *,
    database_url: str,
    order_numbers: Optional[list[str]] = None,
    apply: bool = False,
) -> dict[str, Any]:
    async_url = _build_async_url(database_url)
    engine = create_async_engine(async_url, future=True)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    records: list[dict[str, Any]] = []
    changed_count = 0

    try:
        async with session_factory() as db:
            stmt = (
                select(Order)
                .outerjoin(ShipbubbleShipment, ShipbubbleShipment.order_id == Order.id)
                .where(
                    or_(
                        ShipbubbleShipment.id.isnot(None),
                        Order.delivery_provider.ilike("shipbubble%"),
                    )
                )
                .options(selectinload(Order.items))
                .order_by(Order.created_at.asc())
            )
            if order_numbers:
                normalized_numbers = [num.strip().upper() for num in order_numbers if num.strip()]
                stmt = stmt.where(Order.order_number.in_(normalized_numbers))

            orders = (await db.scalars(stmt)).unique().all()

            for order in orders:
                shipment = await db.scalar(
                    select(ShipbubbleShipment).where(ShipbubbleShipment.order_id == order.id)
                )
                items = (
                    await db.scalars(
                        select(OrderItem)
                        .where(OrderItem.order_id == order.id)
                        .order_by(OrderItem.id.asc())
                    )
                ).all()
                pickups = (
                    await db.scalars(
                        select(VendorPickup)
                        .where(VendorPickup.order_id == order.id)
                        .order_by(VendorPickup.id.asc())
                    )
                ).all()

                before = _snapshot_order_state(order, shipment, items, pickups)
                actions: list[str] = []

                sb_status_raw = (shipment.status or "").lower().strip() if shipment else ""
                mapped_sb_status = SHIPBUBBLE_STATUS_TO_FULFILLMENT.get(sb_status_raw)
                if mapped_sb_status is not None and can_apply_carrier_status_transition(
                    order.fulfillment_status,
                    mapped_sb_status,
                    is_webhook=False,
                ):
                    actions.append(
                        f"order.fulfillment_status: {order.fulfillment_status.value} -> {mapped_sb_status.value} (from shipbubble:{sb_status_raw})"
                    )
                    order.fulfillment_status = mapped_sb_status
                    fallback_event_ts = (
                        (shipment.updated_at if shipment else None)
                        or order.updated_at
                        or datetime.now(timezone.utc)
                    )
                    if mapped_sb_status == FulfillmentStatus.DELIVERED and order.delivered_at is None:
                        order.delivered_at = fallback_event_ts
                    elif mapped_sb_status == FulfillmentStatus.CANCELLED and order.cancelled_at is None:
                        order.cancelled_at = fallback_event_ts

                active_pickups = [p for p in pickups if p.status.value != "CANCELLED"]
                if (
                    order.fulfillment_status == FulfillmentStatus.PICKUP_SCHEDULED
                    and active_pickups
                    and all(is_picked_up(p) for p in active_pickups)
                ):
                    actions.append(
                        "order.fulfillment_status: pickup_scheduled -> picked_up (pickups already collected)"
                    )
                    order.fulfillment_status = FulfillmentStatus.PICKED_UP

                fallback_ts = (
                    (
                        order.delivered_at
                        if order.fulfillment_status == FulfillmentStatus.DELIVERED
                        and order.delivered_at is not None
                        else None
                    )
                    or next((p.actual_pickup_date for p in pickups if p.actual_pickup_date is not None), None)
                    or order.delivered_at
                    or (shipment.updated_at if shipment else None)
                    or order.updated_at
                    or datetime.now(timezone.utc)
                )

                await sync_vendor_items_and_pickups_for_order_status(
                    db,
                    order=order,
                    new_status=order.fulfillment_status,
                    now_utc=fallback_ts,
                )
                db.add(order)
                await db.flush()

                after = _snapshot_order_state(order, shipment, items, pickups)
                changed = before != after
                if changed:
                    changed_count += 1
                    if not actions:
                        actions.append("synced items and/or vendor pickups to order status")

                records.append(
                    {
                        "order_number": order.order_number,
                        "changed": changed,
                        "actions": actions,
                        "before": before,
                        "after": after,
                    }
                )

            if apply:
                await db.commit()
            else:
                await db.rollback()
    finally:
        await engine.dispose()

    return {
        "mode": "apply" if apply else "dry_run",
        "total_inspected": len(records),
        "total_changed": changed_count,
        "orders": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile out-of-step ShipBubble orders across orders, order_items, and vendor_pickups."
    )
    parser.add_argument(
        "--database-url",
        default=settings.DATABASE_URL,
        help="PostgreSQL connection string (defaults to settings.DATABASE_URL)",
    )
    parser.add_argument(
        "--order-number",
        action="append",
        dest="order_numbers",
        help="Optional order number to reconcile (repeatable)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes (omit for read-only dry-run)",
    )
    parser.add_argument(
        "--report-path",
        help="Optional path to write JSON before/after reconciliation report",
    )
    args = parser.parse_args()

    report = asyncio.run(
        reconcile_shipbubble_orders(
            database_url=args.database_url,
            order_numbers=args.order_numbers,
            apply=args.apply,
        )
    )
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.report_path:
        Path(args.report_path).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
