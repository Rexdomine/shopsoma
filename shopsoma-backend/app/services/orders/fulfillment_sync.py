"""Monotonic carrier fulfillment transitions and vendor item/pickup lifecycle sync."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import FulfillmentStatus, Order, OrderItem
from app.models.vendor_pickup import PickupStatus, VendorPickup
from app.services.orders.made_to_order_readiness import (
    is_made_to_order_item,
    is_picked_up,
    is_pickup_scheduled,
)

# Monotonic forward progression ranks for active fulfillment stages.
FORWARD_FULFILLMENT_RANK: dict[FulfillmentStatus, int] = {
    FulfillmentStatus.ORDER_RECEIVED: 0,
    FulfillmentStatus.PREPARING_FOR_PICKUP: 1,
    FulfillmentStatus.PICKUP_SCHEDULED: 2,
    FulfillmentStatus.PICKED_UP: 3,
    FulfillmentStatus.IN_TRANSIT: 4,
    FulfillmentStatus.OUT_FOR_DELIVERY: 5,
    FulfillmentStatus.DELIVERED: 6,
}

TERMINAL_FULFILLMENT_STATUSES: frozenset[FulfillmentStatus] = frozenset(
    {
        FulfillmentStatus.DELIVERED,
        FulfillmentStatus.RETURNED,
        FulfillmentStatus.CANCELLED,
    }
)


def can_apply_carrier_status_transition(
    current: FulfillmentStatus,
    target: FulfillmentStatus,
    *,
    is_webhook: bool = False,
) -> bool:
    """Return True only when a carrier poll/webhook transition moves forward safely.

    Prevents stale carrier statuses (e.g. ShipBubble remaining at ``confirmed`` ->
    ``pickup_scheduled`` after manual hub/admin delivery) from regressing an order
    backwards into a pending vendor state.
    """
    if target == current:
        return False

    if current in (FulfillmentStatus.CANCELLED, FulfillmentStatus.RETURNED):
        return False

    if current == FulfillmentStatus.DELIVERED:
        # Polling must never overwrite a delivered order; only an explicit post-delivery
        # return webhook can transition DELIVERED -> RETURNED.
        return bool(is_webhook and target == FulfillmentStatus.RETURNED)

    if current == FulfillmentStatus.DELIVERY_FAILED:
        return target in {
            FulfillmentStatus.OUT_FOR_DELIVERY,
            FulfillmentStatus.DELIVERED,
            FulfillmentStatus.RETURNED,
            FulfillmentStatus.CANCELLED,
        }

    if target in {
        FulfillmentStatus.DELIVERY_FAILED,
        FulfillmentStatus.RETURNED,
        FulfillmentStatus.CANCELLED,
    }:
        return True

    current_rank = FORWARD_FULFILLMENT_RANK.get(current)
    target_rank = FORWARD_FULFILLMENT_RANK.get(target)
    if current_rank is None or target_rank is None:
        return False

    return target_rank > current_rank


def _pickup_implied_fulfillment_status(
    item: OrderItem,
    pickup: Optional[VendorPickup],
) -> Optional[FulfillmentStatus]:
    if pickup is None:
        return None

    if pickup.status == PickupStatus.CANCELLED:
        return FulfillmentStatus.CANCELLED
    if pickup.status == PickupStatus.COMPLETED:
        return FulfillmentStatus.DELIVERED
    if pickup.status == PickupStatus.SHIPPED_TO_CUSTOMER:
        return FulfillmentStatus.IN_TRANSIT
    if is_picked_up(pickup):
        return FulfillmentStatus.PICKED_UP

    mto_unready = is_made_to_order_item(item) and pickup.ready_for_pickup_at is None
    if not mto_unready and is_pickup_scheduled(pickup):
        return FulfillmentStatus.PICKUP_SCHEDULED
    if pickup.ready_for_pickup_at is not None:
        return FulfillmentStatus.PREPARING_FOR_PICKUP
    return None


def resolve_effective_item_fulfillment_status(
    item: OrderItem,
    order: Optional[Order],
    pickup: Optional[VendorPickup] = None,
) -> FulfillmentStatus:
    """Resolve the authoritative item fulfillment status for vendor and admin views.

    Note: ``domestic_checkout_v1`` paid orders keep ``order_items`` immutable in SQL
    because ``trg_order_items_checkout_completion`` enforces ``active`` reservations
    while paid reservations are ``consumed``. Deriving from ``Order`` + ``VendorPickup``
    ensures item-level badges reflect delivery and pickup progress accurately.
    """
    item_status = item.fulfillment_status or FulfillmentStatus.ORDER_RECEIVED
    if item_status == FulfillmentStatus.CANCELLED:
        return FulfillmentStatus.CANCELLED

    if order is None:
        return item_status

    order_status = order.fulfillment_status or FulfillmentStatus.ORDER_RECEIVED
    if order_status in {
        FulfillmentStatus.DELIVERED,
        FulfillmentStatus.DELIVERY_FAILED,
        FulfillmentStatus.RETURNED,
        FulfillmentStatus.CANCELLED,
    }:
        return order_status

    best_status = item_status
    best_rank = FORWARD_FULFILLMENT_RANK.get(best_status, 0)

    pickup_status = _pickup_implied_fulfillment_status(item, pickup)
    if pickup_status == FulfillmentStatus.CANCELLED:
        return FulfillmentStatus.CANCELLED
    if pickup_status is not None:
        pickup_rank = FORWARD_FULFILLMENT_RANK.get(pickup_status, 0)
        if pickup_rank > best_rank:
            best_status = pickup_status
            best_rank = pickup_rank

    mto_unready = (
        is_made_to_order_item(item)
        and (pickup is None or (pickup.ready_for_pickup_at is None and not is_picked_up(pickup)))
    )
    order_is_customer_outbound = order_status in {
        FulfillmentStatus.IN_TRANSIT,
        FulfillmentStatus.OUT_FOR_DELIVERY,
    }
    if order_is_customer_outbound or not mto_unready:
        order_rank = FORWARD_FULFILLMENT_RANK.get(order_status, 0)
        if order_rank > best_rank:
            best_status = order_status
            best_rank = order_rank

    return best_status


async def sync_vendor_items_and_pickups_for_order_status(
    db: AsyncSession,
    *,
    order: Order,
    new_status: FulfillmentStatus,
    now_utc: Optional[datetime] = None,
) -> None:
    """Keep VendorPickup and (when mutable) OrderItem statuses aligned with Order status."""
    effective_now = now_utc or datetime.now(timezone.utc)

    pickups = (
        await db.scalars(select(VendorPickup).where(VendorPickup.order_id == order.id))
    ).all()
    for pickup in pickups:
        if new_status == FulfillmentStatus.DELIVERED:
            if pickup.status != PickupStatus.CANCELLED:
                pickup.status = PickupStatus.COMPLETED
                if pickup.completed_at is None:
                    pickup.completed_at = effective_now
                db.add(pickup)
        elif new_status in (
            FulfillmentStatus.IN_TRANSIT,
            FulfillmentStatus.OUT_FOR_DELIVERY,
        ):
            if (
                pickup.status not in (PickupStatus.COMPLETED, PickupStatus.CANCELLED, PickupStatus.SHIPPED_TO_CUSTOMER)
                and is_picked_up(pickup)
            ):
                pickup.status = PickupStatus.SHIPPED_TO_CUSTOMER
                db.add(pickup)
        elif new_status == FulfillmentStatus.CANCELLED:
            if pickup.status not in (PickupStatus.COMPLETED, PickupStatus.CANCELLED):
                pickup.status = PickupStatus.CANCELLED
                if pickup.cancelled_at is None:
                    pickup.cancelled_at = effective_now
                db.add(pickup)

    # Avoid mutating order_items on domestic_checkout_v1 orders with completed checkout
    # prerequisites because trg_order_items_checkout_completion enforces active
    # stock_reservations whereas paid orders have consumed reservations.
    can_mutate_order_items = (
        getattr(order, "workflow_cohort", None) != "domestic_checkout_v1"
        or getattr(order, "checkout_prerequisites_completed_at", None) is None
    )
    if not can_mutate_order_items:
        return

    items = (
        await db.scalars(select(OrderItem).where(OrderItem.order_id == order.id))
    ).all()
    pickup_by_item = {p.order_item_id: p for p in pickups}
    for item in items:
        if item.fulfillment_status == FulfillmentStatus.CANCELLED:
            continue
        target_item_status = resolve_effective_item_fulfillment_status(
            item,
            order,
            pickup_by_item.get(item.id),
        )
        if item.fulfillment_status != target_item_status:
            item.fulfillment_status = target_item_status
            db.add(item)
