"""Server-owned checkout-estimate creation and snapshot validation."""

from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import aliased, selectinload

from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimate,
    CheckoutShippingEstimateOption,
    CheckoutShippingEstimateSelection,
)
from app.models.address import Address
from app.models.order import Order, OrderItem
from app.models.setting import Setting
from app.models.shipping_rate import ShippingRate

_CENT = Decimal("0.01")
_ESTIMATE_TTL_SECONDS = 1800


def _estimate_expiry_delta(ttl_seconds: int) -> timedelta:
    return timedelta(seconds=ttl_seconds)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def order_snapshot(order: Order) -> tuple[str, str]:
    destination = {
        "address_line1": order.shipping_address.address_line1,
        "address_line2": order.shipping_address.address_line2,
        "city": order.shipping_address.city,
        "country": order.shipping_address.country,
        "postal_code": order.shipping_address.postal_code,
        "state": order.shipping_address.state,
    }
    items = [
        {
            "currency": item.currency,
            "id": str(item.id),
            "inventory_policy": item.inventory_policy,
            "inventory_subject_id": (
                str(item.inventory_subject_id) if item.inventory_subject_id else None
            ),
            "inventory_subject_kind": item.inventory_subject_kind,
            "quantity": item.quantity,
            "subtotal": str(item.subtotal),
            "unit_price": str(item.unit_price),
        }
        for item in sorted(order.items, key=lambda row: str(row.id))
    ]
    return _hash(destination), _hash(
        {
            "currency": order.currency,
            "destination": destination,
            "discount_amount": str(order.discount_amount),
            "items": items,
            "policy": order.workflow_policy_version,
            "subtotal": str(order.subtotal),
        }
    )


async def load_checkout_order(
    db, order_id, *, for_update: bool = False
) -> Order | None:
    if for_update:
        # Canonical checkout lock order starts with the aggregate root, then its
        # destination, then every item in stable UUID order. Callers retain
        # these locks before owner/coordinator/inventory/estimate/option locks.
        order = (
            await db.execute(
                select(Order).where(Order.id == order_id).with_for_update()
            )
        ).scalar_one_or_none()
        if not order:
            return None
        if order.shipping_address_id:
            await db.execute(
                select(Address.id)
                .where(Address.id == order.shipping_address_id)
                .with_for_update()
            )
        await db.execute(
            select(OrderItem.id)
            .where(OrderItem.order_id == order.id)
            .order_by(OrderItem.id)
            .with_for_update()
        )
        return await reload_checkout_order(db, order)

    statement = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.shipping_address))
        .where(Order.id == order_id)
    )
    return (await db.execute(statement)).scalar_one_or_none()


async def reload_checkout_order(db, order: Order) -> Order:
    """Replace cached aggregate state with fresh PostgreSQL row values."""
    db.expire(order, ["shipping_address", "items"])
    return (
        await db.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.shipping_address))
            .where(Order.id == order.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def create_estimate(
    db, *, order: Order, actor_type: str, actor_id: str, idempotency_key: str
):
    if order.workflow_cohort != "domestic_checkout_v1":
        raise HTTPException(status_code=404, detail="checkout not available")
    existing = (
        await db.execute(
            select(CheckoutShippingEstimate).where(
                CheckoutShippingEstimate.customer_id == order.customer_id,
                CheckoutShippingEstimate.source_command == "create_checkout_estimate",
                CheckoutShippingEstimate.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    destination_hash, snapshot_hash = order_snapshot(order)
    fingerprint = _hash({"order_id": str(order.id), "snapshot": snapshot_hash})
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="idempotency conflict")
        return existing

    successor_estimate = aliased(CheckoutShippingEstimate)
    selection = aliased(CheckoutShippingEstimateSelection)
    current_unselected_leaf = (
        await db.execute(
            select(CheckoutShippingEstimate)
            .where(
                CheckoutShippingEstimate.order_id == order.id,
                CheckoutShippingEstimate.customer_id == order.customer_id,
                ~select(successor_estimate.id)
                .where(
                    successor_estimate.supersedes_estimate_id
                    == CheckoutShippingEstimate.id
                )
                .exists(),
                ~select(selection.id)
                .where(selection.estimate_id == CheckoutShippingEstimate.id)
                .exists(),
            )
            .order_by(
                CheckoutShippingEstimate.created_at.desc(),
                CheckoutShippingEstimate.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    usd_to_ngn_rate = None
    if order.currency == "USD":
        rate_setting = await db.scalar(
            select(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
        )
        try:
            usd_to_ngn_rate = Decimal(str(rate_setting.value))
        except (ArithmeticError, ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(
                status_code=503, detail="authoritative exchange rate unavailable"
            ) from exc
        if not usd_to_ngn_rate.is_finite() or usd_to_ngn_rate <= 0:
            raise HTTPException(
                status_code=503, detail="authoritative exchange rate unavailable"
            )

    def ngn_in_order_currency(value) -> Decimal:
        amount = Decimal(value)
        if order.currency == "USD":
            assert usd_to_ngn_rate is not None
            amount /= usd_to_ngn_rate
        return amount.quantize(_CENT, rounding=ROUND_HALF_UP)

    rates = (
        (
            await db.execute(
                select(ShippingRate)
                .where(
                    ShippingRate.is_active.is_(True),
                    ShippingRate.country == order.shipping_address.country,
                    or_(
                        ShippingRate.state == order.shipping_address.state,
                        ShippingRate.state.is_(None),
                    ),
                )
                .order_by(ShippingRate.priority, ShippingRate.id)
            )
        )
        .scalars()
        .all()
    )
    rates = [
        rate
        for rate in rates
        if (
            rate.min_order_value is None
            or ngn_in_order_currency(rate.min_order_value) <= order.subtotal
        )
        and (
            rate.max_order_value is None
            or ngn_in_order_currency(rate.max_order_value) >= order.subtotal
        )
    ]
    if not rates:
        raise HTTPException(status_code=503, detail="no eligible estimate options")
    database_now = await db.scalar(select(text("statement_timestamp()")))
    ttl = _ESTIMATE_TTL_SECONDS
    estimate = CheckoutShippingEstimate(
        order_id=order.id,
        customer_id=order.customer_id,
        supersedes_estimate_id=(
            current_unselected_leaf.id if current_unselected_leaf is not None else None
        ),
        destination_snapshot_hash=destination_hash,
        order_snapshot_hash=snapshot_hash,
        currency=order.currency,
        ttl_seconds=ttl,
        expires_at=database_now + _estimate_expiry_delta(ttl),
        source_kind="static_domestic_rate",
        source_reference="shipping_rates:v1",
        source_command=(
            "refresh_checkout_estimate"
            if current_unselected_leaf is not None
            else "create_checkout_estimate"
        ),
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        schema_version="checkout_estimate_v1",
        created_by_actor_type=actor_type,
        created_by_actor_id=actor_id,
    )
    db.add(estimate)
    await db.flush()
    for rate in rates:
        amount = ngn_in_order_currency(rate.base_rate)
        db.add(
            CheckoutShippingEstimateOption(
                estimate_id=estimate.id,
                option_key=f"static:{rate.id}",
                service_code=f"static-{rate.priority}",
                service_label=rate.name,
                amount=amount,
                currency=order.currency,
                min_delivery_days=rate.min_delivery_days,
                max_delivery_days=rate.max_delivery_days,
                source_rate_id=rate.id,
            )
        )
    await db.flush()
    return estimate


async def estimate_payload(
    db, *, order: Order, estimate: CheckoutShippingEstimate
) -> dict:
    options = (
        (
            await db.execute(
                select(CheckoutShippingEstimateOption)
                .where(CheckoutShippingEstimateOption.estimate_id == estimate.id)
                .order_by(CheckoutShippingEstimateOption.option_key)
            )
        )
        .scalars()
        .all()
    )
    selection = (
        await db.execute(
            select(CheckoutShippingEstimateSelection).where(
                CheckoutShippingEstimateSelection.estimate_id == estimate.id
            )
        )
    ).scalar_one_or_none()
    selected = next(
        (row for row in options if selection and row.id == selection.option_id), None
    )
    return {
        "id": estimate.id,
        "order_id": estimate.order_id,
        "currency": estimate.currency,
        "expires_at": estimate.expires_at,
        "options": options,
        "selected_option": selected,
        "server_payable_total": order.total_amount,
    }
