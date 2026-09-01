"""Atomic checkout reservation coverage from frozen order-item truth."""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
import uuid

from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimate,
    CheckoutShippingEstimateOption,
    CheckoutShippingEstimateSelection,
    OrderInventoryCoverage,
)
from app.models.order import FulfillmentStatus, Order, PaymentStatus
from app.models.product import Product, ProductVariant, SizeStock
from app.models.stock_payment_persistence import StockReservation
from app.services.checkout.estimates import order_snapshot, reload_checkout_order

_CENT = Decimal("0.01")
_EFFECTIVE_CLAIM_SQL = text(
    """
    SELECT COALESCE(sum(sr.quantity),0)
    FROM stock_reservations sr
    WHERE sr.inventory_subject_kind=:kind AND sr.inventory_subject_id=:subject_id
      AND sr.state='active'
      AND (
        sr.expires_at > clock_timestamp()
        OR EXISTS (
          SELECT 1 FROM payment_attempt_reservations par
          JOIN payment_attempts pa ON pa.id=par.attempt_id
          WHERE par.reservation_id=sr.id
            AND (
              (
                pa.state IN ('call_started','abandoned_unknown')
                AND pa.authorization_deadline_at>=clock_timestamp()
              )
              OR (pa.state='verified' AND pa.authorization_deadline_at>=clock_timestamp())
            )
        )
      )
    """
)


def _coordinator_keys(
    order: Order, reservations: list[tuple[object, uuid.UUID]], existing_ids
):
    keys = {("order", order.id)}
    for item, reservation_id in reservations:
        keys.add(("reservation", reservation_id))
        keys.add(("product", item.inventory_source_product_id))
        if item.inventory_subject_kind == "product_variant":
            keys.add(("product_variant", item.inventory_subject_id))
        elif item.inventory_subject_kind == "size_stock":
            keys.add(("size_stock", item.inventory_subject_id))
            variation_id = (item.variant_details or {}).get("variation_id")
            if variation_id:
                keys.add(("variation", uuid.UUID(str(variation_id))))
    keys.update(("reservation", value) for value in existing_ids)
    return [
        {"subject_kind": kind, "subject_id": str(subject_id)}
        for kind, subject_id in keys
    ]


async def _lock_and_available(db, item) -> int:
    if item.inventory_subject_kind == "product":
        physical = await db.scalar(
            select(Product.total_stock)
            .where(Product.id == item.inventory_subject_id)
            .with_for_update()
        )
    elif item.inventory_subject_kind == "product_variant":
        physical = await db.scalar(
            select(ProductVariant.stock)
            .where(ProductVariant.id == item.inventory_subject_id)
            .with_for_update()
        )
    else:
        physical = await db.scalar(
            select(SizeStock.stock)
            .where(SizeStock.id == item.inventory_subject_id)
            .with_for_update()
        )
    if physical is None:
        raise HTTPException(status_code=409, detail="inventory subject unavailable")
    claimed = await db.scalar(
        _EFFECTIVE_CLAIM_SQL,
        {"kind": item.inventory_subject_kind, "subject_id": item.inventory_subject_id},
    )
    return int(physical) - int(claimed or 0)


async def release_active_order_reservations(db, *, order: Order) -> None:
    """Release an enforced checkout's logical stock claims without restoring stock."""
    reservation_ids = list(
        await db.scalars(
            select(StockReservation.id)
            .where(
                StockReservation.order_id == order.id,
                StockReservation.state == "active",
            )
            .order_by(StockReservation.id)
        )
    )
    if not reservation_ids:
        return

    items_by_id = {item.id: item for item in order.items}
    reservations = list(
        await db.scalars(
            select(StockReservation)
            .where(StockReservation.id.in_(reservation_ids))
            .order_by(StockReservation.id)
        )
    )
    reservation_pairs = [
        (items_by_id[reservation.order_item_id], reservation.id)
        for reservation in reservations
    ]
    await db.execute(
        text("SELECT coordinate_stock_payment_write(CAST(:keys AS jsonb))"),
        {"keys": json.dumps(_coordinator_keys(order, reservation_pairs, []))},
    )
    locked_reservations = list(
        await db.scalars(
            select(StockReservation)
            .where(StockReservation.id.in_(reservation_ids))
            .order_by(StockReservation.id)
            .with_for_update()
        )
    )
    for reservation in locked_reservations:
        if reservation.state == "active":
            reservation.state = "released"
            reservation.terminal_reason = "checkout_cancelled"
            reservation.row_version += 1
    await db.flush()


async def select_estimate_option(
    db,
    *,
    order: Order,
    estimate_id,
    option_id,
    actor_type: str,
    actor_id: str,
    idempotency_key: str,
):
    existing = (
        await db.execute(
            select(CheckoutShippingEstimateSelection).where(
                CheckoutShippingEstimateSelection.customer_id == order.customer_id,
                CheckoutShippingEstimateSelection.source_command
                == "select_checkout_estimate",
                CheckoutShippingEstimateSelection.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing:
        if existing.estimate_id != estimate_id or existing.option_id != option_id:
            raise HTTPException(status_code=409, detail="idempotency conflict")
        return existing
    if order.checkout_prerequisites_completed_at is not None:
        raise HTTPException(
            status_code=409, detail="checkout prerequisites already completed"
        )

    estimate = await db.get(CheckoutShippingEstimate, estimate_id)
    option = await db.get(CheckoutShippingEstimateOption, option_id)
    destination_hash, snapshot_hash = order_snapshot(order)
    if (
        not estimate
        or not option
        or estimate.order_id != order.id
        or option.estimate_id != estimate.id
        or estimate.destination_snapshot_hash != destination_hash
        or estimate.order_snapshot_hash != snapshot_hash
    ):
        raise HTTPException(status_code=409, detail="stale checkout estimate")

    stock_items = [
        item for item in order.items if item.inventory_policy == "stock_managed"
    ]
    reservation_pairs = [(item, uuid.uuid4()) for item in stock_items]
    subjects = {
        (item.inventory_subject_kind, item.inventory_subject_id) for item in stock_items
    }
    existing_claim_ids = (
        (
            await db.execute(
                select(StockReservation.id).where(
                    StockReservation.state == "active",
                    tuple_(
                        StockReservation.inventory_subject_kind,
                        StockReservation.inventory_subject_id,
                    ).in_(subjects),
                )
            )
        )
        .scalars()
        .all()
        if subjects
        else []
    )
    await db.execute(
        text("SELECT coordinate_stock_payment_write(CAST(:keys AS jsonb))"),
        {
            "keys": json.dumps(
                _coordinator_keys(order, reservation_pairs, existing_claim_ids)
            )
        },
    )

    required = {}
    subject_examples = {}
    for item in stock_items:
        key = (item.inventory_subject_kind, item.inventory_subject_id)
        required[key] = required.get(key, 0) + item.quantity
        subject_examples.setdefault(key, item)
    for key, required_quantity in required.items():
        if await _lock_and_available(db, subject_examples[key]) < required_quantity:
            raise HTTPException(status_code=409, detail="insufficient stock")

    # Coordinator and inventory locks can wait. Re-read immutable quote truth
    # under lock and sample the database clock only after the final lock.
    estimate = (
        await db.execute(
            select(CheckoutShippingEstimate)
            .where(CheckoutShippingEstimate.id == estimate_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    option = (
        await db.execute(
            select(CheckoutShippingEstimateOption)
            .where(CheckoutShippingEstimateOption.id == option_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    # Every potentially waiting lock is now held. Discard ORM relationship
    # cache state, reload authoritative rows, and validate the locked snapshot.
    order = await reload_checkout_order(db, order)
    destination_hash, snapshot_hash = order_snapshot(order)
    database_now = await db.scalar(select(text("clock_timestamp()")))
    if order.payment_status == PaymentStatus.PAID:
        raise HTTPException(status_code=409, detail="paid order cannot select checkout estimate")
    if order.fulfillment_status == FulfillmentStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="cancelled order cannot select checkout estimate")
    if (
        not estimate
        or not option
        or estimate.order_id != order.id
        or option.estimate_id != estimate.id
    ):
        raise HTTPException(status_code=409, detail="expired checkout estimate")
    if (
        estimate.destination_snapshot_hash != destination_hash
        or estimate.order_snapshot_hash != snapshot_hash
    ):
        raise HTTPException(status_code=409, detail="stale checkout estimate")
    if estimate.expires_at <= database_now:
        raise HTTPException(status_code=409, detail="expired checkout estimate")

    selection = CheckoutShippingEstimateSelection(
        estimate_id=estimate.id,
        option_id=option.id,
        order_id=order.id,
        customer_id=order.customer_id,
        selected_by_actor_type=actor_type,
        selected_by_actor_id=actor_id,
        shipping_amount=option.amount,
        currency=option.currency,
        source_command="select_checkout_estimate",
        idempotency_key=idempotency_key,
        selected_at=database_now,
    )
    db.add(selection)
    await db.flush()

    shipping = Decimal(option.amount).quantize(_CENT, rounding=ROUND_HALF_UP)
    tax = ((Decimal(order.subtotal) + shipping) * Decimal("0.075")).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )
    total = (
        Decimal(order.subtotal) + shipping + tax - Decimal(order.discount_amount)
    ).quantize(_CENT, rounding=ROUND_HALF_UP)
    order.shipping_cost = shipping
    order.tax_amount = tax
    order.total_amount = total
    order.checkout_estimate_selection_id = selection.id
    order.checkout_prerequisites_completed_at = database_now
    # M2 freezes payment truth as soon as a reservation exists. Persist totals
    # first; deferred completion validation requires full coverage at commit.
    await db.flush()

    expiry = database_now + timedelta(seconds=1800)
    creation_txid = await db.scalar(select(text("txid_current()")))
    for item, reservation_id in reservation_pairs:
        reservation = StockReservation(
            id=reservation_id,
            order_id=order.id,
            order_item_id=item.id,
            customer_id=order.customer_id,
            workflow_cohort=order.workflow_cohort,
            checkout_estimate_selection_id=selection.id,
            inventory_subject_kind=item.inventory_subject_kind,
            inventory_subject_id=item.inventory_subject_id,
            product_id=item.inventory_source_product_id,
            variant_id=(
                item.inventory_subject_id
                if item.inventory_subject_kind == "product_variant"
                else None
            ),
            size_stock_id=(
                item.inventory_subject_id
                if item.inventory_subject_kind == "size_stock"
                else None
            ),
            quantity=item.quantity,
            unit_price=Decimal(item.unit_price).quantize(_CENT, rounding=ROUND_HALF_UP),
            line_amount=Decimal(item.subtotal).quantize(_CENT, rounding=ROUND_HALF_UP),
            currency=item.currency,
            ttl_seconds=1800,
            expires_at=expiry,
            state="active",
            source_command="select_checkout_estimate",
            idempotency_key=f"{idempotency_key}:{item.id}",
            creation_txid=creation_txid,
        )
        db.add(reservation)
        await db.flush()
        db.add(
            OrderInventoryCoverage(
                order_item_id=item.id,
                order_id=order.id,
                checkout_estimate_selection_id=selection.id,
                inventory_policy=item.inventory_policy,
                reservation_id=reservation.id,
            )
        )
    for item in order.items:
        if item.inventory_policy == "made_to_order":
            db.add(
                OrderInventoryCoverage(
                    order_item_id=item.id,
                    order_id=order.id,
                    checkout_estimate_selection_id=selection.id,
                    inventory_policy=item.inventory_policy,
                    reservation_id=None,
                )
            )

    await db.flush()
    return selection


# Imported late in the module-level expression above to keep SQLAlchemy tuple
# construction adjacent to the only query that needs it.
from sqlalchemy import tuple_  # noqa: E402
