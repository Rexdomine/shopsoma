"""Made-to-order readiness and per-item pickup rules.

Readiness is tracked per order item on the existing ``VendorPickup`` row (one per
``OrderItem``), never on the parent ``Order``. This keeps a multi-vendor customer
order grouped while letting each vendor's made-to-order item become ready and be
collected independently.

Lifecycle surfaced to vendor/admin UIs (derived, not stored):

    being_prepared -> ready_for_pickup -> pickup_scheduled -> picked_up
                                   (cancelled at any point)

Only the vendor-owned ``being_prepared -> ready_for_pickup`` transition is
performed here; scheduling and pickup progress remain admin-only through the
existing admin pickup endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
from app.models.vendor import Vendor
from app.models.vendor_pickup import OrderType, PickupStatus, VendorPickup


MADE_TO_ORDER_POLICY = "made_to_order"


class ReadinessState:
    """String constants for the derived per-item readiness/pickup state."""

    BEING_PREPARED = "being_prepared"
    READY_FOR_PICKUP = "ready_for_pickup"
    PICKUP_SCHEDULED = "pickup_scheduled"
    PICKED_UP = "picked_up"
    CANCELLED = "cancelled"


# Pickup statuses that prove the item has already left the vendor.
_PICKED_UP_STATUSES = frozenset(
    {
        PickupStatus.IN_TRANSIT,
        PickupStatus.DELIVERED_TO_QC,
        PickupStatus.QC_APPROVED,
        PickupStatus.QC_REJECTED,
        PickupStatus.SHIPPED_TO_CUSTOMER,
        PickupStatus.COMPLETED,
    }
)

# Admin pickup fields that schedule or progress a physical collection.
_SCHEDULING_FIELDS = (
    "scheduled_pickup_date",
    "pickup_window_start",
    "pickup_window_end",
    "actual_pickup_date",
)


class ReadinessError(Exception):
    """Domain error carrying the HTTP status the API layer should return."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass
class MarkReadyResult:
    order: Order
    item: OrderItem
    pickup: VendorPickup
    transitioned: bool


def is_made_to_order_item(item: OrderItem) -> bool:
    """Use the checkout snapshot first; fall back to the product flag for legacy rows.

    ``OrderItem.inventory_policy`` is the order-time snapshot of
    ``Product.made_to_order``. Legacy rows created before the snapshot existed have
    ``NULL`` and fall back to the (already loaded) product configuration. The
    relationship is read from ``__dict__`` so this never triggers an async lazy load.
    """
    if item.inventory_policy is not None:
        return item.inventory_policy == MADE_TO_ORDER_POLICY
    product = item.__dict__.get("product")
    return bool(getattr(product, "made_to_order", False))


def select_item_pickup(pickups: Iterable[VendorPickup]) -> Optional[VendorPickup]:
    """Return the canonical (earliest created) pickup row for one order item."""
    rows = [pickup for pickup in pickups if pickup is not None]
    if not rows:
        return None
    return min(
        rows,
        key=lambda pickup: (
            pickup.created_at or datetime.max.replace(tzinfo=timezone.utc),
            str(pickup.id),
        ),
    )


def pickups_by_order_item(pickups: Iterable[VendorPickup]) -> dict:
    grouped: dict = {}
    for pickup in pickups:
        grouped.setdefault(pickup.order_item_id, []).append(pickup)
    return {item_id: select_item_pickup(rows) for item_id, rows in grouped.items()}


def is_pickup_scheduled(pickup: Optional[VendorPickup]) -> bool:
    return bool(
        pickup is not None
        and (pickup.scheduled_pickup_date is not None or pickup.pickup_window_start is not None)
    )


def is_picked_up(pickup: Optional[VendorPickup]) -> bool:
    return bool(
        pickup is not None
        and (pickup.actual_pickup_date is not None or pickup.status in _PICKED_UP_STATUSES)
    )


def derive_readiness_state(
    *,
    made_to_order: bool,
    pickup: Optional[VendorPickup],
    item_cancelled: bool = False,
) -> Optional[str]:
    """Derive the per-item state; ``None`` for non-made-to-order items that haven't transitioned."""
    if not made_to_order:
        if pickup is None or pickup.ready_for_pickup_at is None:
            return None
        if item_cancelled or pickup.status == PickupStatus.CANCELLED:
            return ReadinessState.CANCELLED
        if is_picked_up(pickup):
            return ReadinessState.PICKED_UP
        if is_pickup_scheduled(pickup):
            return ReadinessState.PICKUP_SCHEDULED
        return ReadinessState.READY_FOR_PICKUP

    if item_cancelled or (pickup is not None and pickup.status == PickupStatus.CANCELLED):
        return ReadinessState.CANCELLED
    if is_picked_up(pickup):
        return ReadinessState.PICKED_UP
    if pickup is None or pickup.ready_for_pickup_at is None:
        return ReadinessState.BEING_PREPARED
    if is_pickup_scheduled(pickup):
        return ReadinessState.PICKUP_SCHEDULED
    return ReadinessState.READY_FOR_PICKUP


def readiness_fields(item: OrderItem, pickup: Optional[VendorPickup]) -> dict:
    """Common serialized readiness fields shared by vendor and admin responses."""
    made_to_order = is_made_to_order_item(item)
    return {
        "made_to_order": made_to_order,
        "ready_for_pickup_at": pickup.ready_for_pickup_at if pickup else None,
        "readiness_state": derive_readiness_state(
            made_to_order=made_to_order,
            pickup=pickup,
            item_cancelled=item.fulfillment_status == FulfillmentStatus.CANCELLED,
        ),
    }


async def mark_item_ready_for_pickup(
    db: AsyncSession,
    *,
    vendor: Vendor,
    order_id: UUID,
    order_item_id: UUID,
    actor_user_id: Optional[UUID],
) -> MarkReadyResult:
    """Idempotently mark one vendor-owned item (MTO or RTW) ready for pickup.

    The order item row is locked ``FOR UPDATE`` so concurrent/duplicate requests
    serialize; only the first request observes the not-ready -> ready transition
    (``transitioned=True``) and therefore only it should trigger notifications.
    Commits the transaction.
    """
    item = await db.scalar(
        select(OrderItem)
        .options(selectinload(OrderItem.product))
        .where(OrderItem.id == order_item_id, OrderItem.order_id == order_id)
        .with_for_update(of=OrderItem)
    )
    if item is None:
        raise ReadinessError(404, "Order item not found")
    if item.vendor_id != vendor.id:
        raise ReadinessError(403, "You don't have access to this order item")

    order = await db.scalar(
        select(Order).options(selectinload(Order.customer)).where(Order.id == order_id)
    )
    if order is None:
        raise ReadinessError(404, "Order not found")
    status_str = (
        order.payment_status.value
        if hasattr(order.payment_status, "value")
        else str(order.payment_status or "")
    )
    if status_str.upper() != "PAID":
        raise ReadinessError(409, "Order has not been paid yet")
    if (
        order.fulfillment_status == FulfillmentStatus.CANCELLED
        or item.fulfillment_status == FulfillmentStatus.CANCELLED
    ):
        raise ReadinessError(409, "Cancelled items cannot be marked ready for pickup")

    is_mto = is_made_to_order_item(item)

    pickups = (
        await db.scalars(
            select(VendorPickup).where(VendorPickup.order_item_id == item.id)
        )
    ).all()
    pickup = select_item_pickup(pickups)
    if pickup is None:
        # Orders created before vendor work was provisioned (or whose provisioning
        # was skipped) get the same pickup row the order flows would have created.
        pickup = VendorPickup(
            vendor_id=item.vendor_id,
            order_id=order.id,
            order_item_id=item.id,
            order_type=OrderType.MADE_TO_ORDER if is_mto else OrderType.RTW,
            scheduled_pickup_date=None,
            pickup_address=vendor.business_address,
            pickup_contact_phone=vendor.business_phone,
            status=PickupStatus.SCHEDULED,
        )
        db.add(pickup)
    elif pickup.status == PickupStatus.CANCELLED:
        raise ReadinessError(409, "This pickup has been cancelled")

    transitioned = False
    if pickup.ready_for_pickup_at is None and not is_picked_up(pickup):
        pickup.ready_for_pickup_at = datetime.now(timezone.utc)
        pickup.ready_for_pickup_marked_by = actor_user_id
        if is_mto and pickup.order_type != OrderType.MADE_TO_ORDER:
            pickup.order_type = OrderType.MADE_TO_ORDER
        elif not is_mto and pickup.order_type != OrderType.RTW:
            pickup.order_type = OrderType.RTW
        transitioned = True

    await db.commit()
    await db.refresh(pickup)
    return MarkReadyResult(order=order, item=item, pickup=pickup, transitioned=transitioned)


def ensure_admin_pickup_update_allowed(
    *,
    made_to_order: bool,
    pickup: VendorPickup,
    update,
) -> None:
    """Guard admin pickup writes for made-to-order items and validate windows.

    A made-to-order item cannot be scheduled or progressed until its vendor has
    marked it ready. Notes, courier metadata and cancellation remain allowed.
    """
    start = update.pickup_window_start or pickup.pickup_window_start
    end = update.pickup_window_end or pickup.pickup_window_end
    if (update.pickup_window_start or update.pickup_window_end) and start and end:
        if _as_aware(end) < _as_aware(start):
            raise ReadinessError(400, "Pickup window end must be after the start")

    if not made_to_order or pickup.ready_for_pickup_at is not None:
        return
    schedules = any(getattr(update, field, None) is not None for field in _SCHEDULING_FIELDS)
    progresses = update.pickup_status is not None and update.pickup_status not in (
        PickupStatus.SCHEDULED,
        PickupStatus.CANCELLED,
    )
    if schedules or progresses:
        raise ReadinessError(
            409,
            "This made-to-order item is not ready yet. Pickup can be scheduled once "
            "the vendor marks it ready for Shopsoma pickup.",
        )


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


from app.services.orders.production_tracking import (
    add_working_days,
    count_working_days_between,
    get_production_tracking,
    is_working_day,
    parse_production_days,
)
