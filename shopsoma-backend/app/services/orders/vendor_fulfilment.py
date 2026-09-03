"""Idempotent internal vendor fulfilment start after verified payment."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.order import Order, PaymentStatus
from app.models.vendor import Vendor
from app.models.vendor_pickup import (
    OrderType,
    PickupStatus,
    VendorNotification,
    VendorPickup,
)


async def start_verified_order_fulfilment(session, *, order_id) -> None:
    """Create internal vendor work only; never contact a carrier or send email."""
    order = await session.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id)
        .with_for_update()
    )
    if order is None or order.payment_status != PaymentStatus.PAID:
        raise ValueError("verified order fulfilment is not eligible")

    existing_pickups = {
        row.order_item_id
        for row in await session.scalars(
            select(VendorPickup).where(VendorPickup.order_id == order.id)
        )
    }
    existing_notifications = {
        row.vendor_id
        for row in await session.scalars(
            select(VendorNotification).where(
                VendorNotification.order_id == order.id,
                VendorNotification.notification_type == "order_placed",
            )
        )
    }
    vendors = {}
    for item in order.items:
        vendor = vendors.get(item.vendor_id)
        if vendor is None:
            vendor = await session.get(Vendor, item.vendor_id)
            if vendor is None:
                raise ValueError("verified order vendor is unavailable")
            vendors[item.vendor_id] = vendor
        if item.id not in existing_pickups:
            order_type = (
                OrderType.MADE_TO_ORDER
                if item.inventory_policy == "made_to_order"
                else OrderType.RTW
            )
            estimated_production_days = None
            scheduled_at = (
                None
                if order_type == OrderType.MADE_TO_ORDER
                else datetime.now(timezone.utc) + timedelta(hours=48)
            )
            session.add(
                VendorPickup(
                    vendor_id=item.vendor_id,
                    order_id=order.id,
                    order_item_id=item.id,
                    order_type=order_type,
                    estimated_production_days=estimated_production_days,
                    scheduled_pickup_date=scheduled_at,
                    admin_notes=(
                        "Made-to-order pickup remains unscheduled until staff or vendor confirms production readiness."
                        if order_type == OrderType.MADE_TO_ORDER
                        else None
                    ),
                    pickup_address=vendor.business_address,
                    pickup_contact_phone=vendor.business_phone,
                    status=PickupStatus.SCHEDULED,
                )
            )
    for vendor_id in vendors:
        if vendor_id not in existing_notifications:
            vendor_items = [item for item in order.items if item.vendor_id == vendor_id]
            session.add(
                VendorNotification(
                    vendor_id=vendor_id,
                    notification_type="order_placed",
                    title=f"New Order #{order.order_number}",
                    message=f"You have received a verified order with {len(vendor_items)} item(s).",
                    order_id=order.id,
                    data={
                        "order_number": order.order_number,
                        "currency": order.currency,
                    },
                    email_sent=False,
                )
            )
    await session.flush()
