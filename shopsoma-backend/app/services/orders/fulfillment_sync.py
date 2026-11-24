"""Monotonic carrier fulfillment transitions and vendor item/pickup lifecycle sync."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import FulfillmentStatus, Order, OrderItem
from app.models.vendor_pickup import PickupStatus, VendorPickup
from app.services.orders.made_to_order_readiness import (
    is_made_to_order_item,
    is_picked_up,
    is_pickup_scheduled,
    pickups_by_order_item,
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


def is_backward_admin_status_transition(
    current: FulfillmentStatus,
    target: FulfillmentStatus,
) -> bool:
    """Return True when an admin status change moves backwards or exits a terminal state."""
    if target == current:
        return False

    if current in (FulfillmentStatus.CANCELLED, FulfillmentStatus.RETURNED):
        return True

    if current == FulfillmentStatus.DELIVERED:
        return target != FulfillmentStatus.RETURNED

    if current == FulfillmentStatus.DELIVERY_FAILED:
        return target in {
            FulfillmentStatus.ORDER_RECEIVED,
            FulfillmentStatus.PREPARING_FOR_PICKUP,
            FulfillmentStatus.PICKUP_SCHEDULED,
            FulfillmentStatus.PICKED_UP,
            FulfillmentStatus.IN_TRANSIT,
        }

    if target in {
        FulfillmentStatus.DELIVERY_FAILED,
        FulfillmentStatus.RETURNED,
        FulfillmentStatus.CANCELLED,
    }:
        return False

    current_rank = FORWARD_FULFILLMENT_RANK.get(current)
    target_rank = FORWARD_FULFILLMENT_RANK.get(target)
    if current_rank is None or target_rank is None:
        return False

    return target_rank < current_rank


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
    explicitly_scheduled = pickup.pickup_window_start is not None or (
        pickup.ready_for_pickup_at is not None and is_pickup_scheduled(pickup)
    )
    if not mto_unready and explicitly_scheduled:
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
    allow_backward: bool = False,
) -> None:
    """Keep VendorPickup and OrderItem statuses aligned with Order status."""
    effective_now = now_utc or datetime.now(timezone.utc)
    if order.fulfillment_status != new_status:
        order.fulfillment_status = new_status

    pickups = (
        await db.scalars(select(VendorPickup).where(VendorPickup.order_id == order.id))
    ).all()
    for pickup in pickups:
        if new_status == FulfillmentStatus.DELIVERED:
            if pickup.status != PickupStatus.CANCELLED:
                if pickup.actual_pickup_date is None:
                    pickup.actual_pickup_date = effective_now
                pickup.status = PickupStatus.COMPLETED
                if pickup.completed_at is None:
                    pickup.completed_at = effective_now
                db.add(pickup)
        elif new_status in (
            FulfillmentStatus.IN_TRANSIT,
            FulfillmentStatus.OUT_FOR_DELIVERY,
            FulfillmentStatus.DELIVERY_FAILED,
        ):
            if pickup.status != PickupStatus.CANCELLED:
                if pickup.actual_pickup_date is None:
                    pickup.actual_pickup_date = effective_now
                if pickup.status not in (
                    PickupStatus.COMPLETED,
                    PickupStatus.SHIPPED_TO_CUSTOMER,
                ) or (allow_backward and pickup.status == PickupStatus.COMPLETED):
                    pickup.status = PickupStatus.SHIPPED_TO_CUSTOMER
                    if allow_backward:
                        pickup.completed_at = None
                db.add(pickup)
        elif new_status == FulfillmentStatus.PICKED_UP:
            if pickup.status != PickupStatus.CANCELLED:
                if pickup.actual_pickup_date is None:
                    pickup.actual_pickup_date = effective_now
                if pickup.status == PickupStatus.SCHEDULED or (
                    allow_backward
                    and pickup.status
                    in (
                        PickupStatus.DELIVERED_TO_QC,
                        PickupStatus.QC_APPROVED,
                        PickupStatus.QC_REJECTED,
                        PickupStatus.SHIPPED_TO_CUSTOMER,
                        PickupStatus.COMPLETED,
                    )
                ):
                    pickup.status = PickupStatus.IN_TRANSIT
                    if allow_backward:
                        pickup.completed_at = None
                db.add(pickup)
        elif allow_backward and new_status in (
            FulfillmentStatus.ORDER_RECEIVED,
            FulfillmentStatus.PREPARING_FOR_PICKUP,
            FulfillmentStatus.PICKUP_SCHEDULED,
        ):
            if pickup.status != PickupStatus.CANCELLED:
                pickup.status = PickupStatus.SCHEDULED
                pickup.actual_pickup_date = None
                pickup.completed_at = None
                db.add(pickup)
        elif new_status == FulfillmentStatus.CANCELLED:
            if pickup.status != PickupStatus.CANCELLED and (
                pickup.status != PickupStatus.COMPLETED or allow_backward
            ):
                pickup.status = PickupStatus.CANCELLED
                if allow_backward:
                    pickup.completed_at = None
                if pickup.cancelled_at is None:
                    pickup.cancelled_at = effective_now
                db.add(pickup)

    items = (
        await db.scalars(
            select(OrderItem)
            .options(selectinload(OrderItem.product))
            .where(OrderItem.order_id == order.id)
        )
    ).all()
    pickup_by_item = pickups_by_order_item(pickups)
    for item in items:
        if item.fulfillment_status == FulfillmentStatus.CANCELLED and not (
            allow_backward and new_status != FulfillmentStatus.CANCELLED
        ):
            continue
        item_for_eval = (
            SimpleNamespace(
                fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
                inventory_policy=item.inventory_policy,
                product=item.__dict__.get("product"),
            )
            if allow_backward
            else item
        )
        target_item_status = resolve_effective_item_fulfillment_status(
            item_for_eval,
            order,
            pickup_by_item.get(item.id),
        )
        if item.fulfillment_status != target_item_status:
            item.fulfillment_status = target_item_status
            db.add(item)
