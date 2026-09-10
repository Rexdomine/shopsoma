"""Milestone 3 pre-payment checkout-estimate endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError

from app.api.dependencies import get_optional_user
from app.core.database import get_db
from app.models.checkout_shipping_estimate import CheckoutShippingEstimate
from app.models.user import User
from app.schemas.checkout_shipping_estimate import CheckoutEstimateResponse
from app.services.checkout.capabilities import authorize_checkout_actor
from app.services.checkout.estimates import (
    create_estimate,
    estimate_payload,
    load_checkout_order,
)
from app.services.checkout.reservations import select_estimate_option

router = APIRouter(
    prefix="/orders/{order_id}/checkout-estimates", tags=["Checkout estimates"]
)


def _idempotency_key(value: Optional[str]) -> str:
    if (
        not value
        or len(value) > 200
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        raise HTTPException(status_code=422, detail="valid X-Idempotency-Key required")
    return value


async def _checkout_actor(db, order, current_user, capability):
    return await authorize_checkout_actor(
        db,
        order=order,
        current_user=current_user,
        token=capability,
    )


@router.post(
    "", response_model=CheckoutEstimateResponse, status_code=status.HTTP_201_CREATED
)
async def create_checkout_estimate(
    order_id: UUID,
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    capability: Optional[str] = Header(None, alias="X-ShopSoma-Checkout-Capability"),
    current_user: Optional[User] = Depends(get_optional_user),
    db=Depends(get_db),
):
    # DHL rating must not hold aggregate locks across the provider await;
    # create_estimate acquires the post-provider lock before persistence.
    order = await load_checkout_order(db, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="checkout not available")
    actor_type, actor_id = await _checkout_actor(db, order, current_user, capability)
    estimate = await create_estimate(
        db,
        order=order,
        actor_type=actor_type,
        actor_id=actor_id,
        idempotency_key=_idempotency_key(idempotency_key),
    )
    await db.commit()
    order = await load_checkout_order(db, order_id)
    estimate = await db.get(CheckoutShippingEstimate, estimate.id)
    return await estimate_payload(db, order=order, estimate=estimate)


@router.get("", response_model=list[CheckoutEstimateResponse])
async def list_checkout_estimates(
    order_id: UUID,
    capability: Optional[str] = Header(None, alias="X-ShopSoma-Checkout-Capability"),
    current_user: Optional[User] = Depends(get_optional_user),
    db=Depends(get_db),
):
    order = await load_checkout_order(db, order_id, for_update=True)
    if not order:
        raise HTTPException(status_code=404, detail="checkout not available")
    await _checkout_actor(db, order, current_user, capability)
    estimates = (
        (
            await db.execute(
                select(CheckoutShippingEstimate)
                .where(CheckoutShippingEstimate.order_id == order.id)
                .order_by(CheckoutShippingEstimate.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [await estimate_payload(db, order=order, estimate=row) for row in estimates]


@router.get("/{estimate_id}", response_model=CheckoutEstimateResponse)
async def get_checkout_estimate(
    order_id: UUID,
    estimate_id: UUID,
    capability: Optional[str] = Header(None, alias="X-ShopSoma-Checkout-Capability"),
    current_user: Optional[User] = Depends(get_optional_user),
    db=Depends(get_db),
):
    order = await load_checkout_order(db, order_id, for_update=True)
    if not order:
        raise HTTPException(status_code=404, detail="checkout not available")
    await _checkout_actor(db, order, current_user, capability)
    estimate = await db.get(CheckoutShippingEstimate, estimate_id)
    if not estimate or estimate.order_id != order.id:
        raise HTTPException(status_code=404, detail="checkout not available")
    return await estimate_payload(db, order=order, estimate=estimate)


@router.post(
    "/{estimate_id}/options/{option_id}/select",
    response_model=CheckoutEstimateResponse,
)
async def select_checkout_estimate_option(
    order_id: UUID,
    estimate_id: UUID,
    option_id: UUID,
    idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
    capability: Optional[str] = Header(None, alias="X-ShopSoma-Checkout-Capability"),
    current_user: Optional[User] = Depends(get_optional_user),
    db=Depends(get_db),
):
    order = await load_checkout_order(db, order_id, for_update=True)
    if not order:
        raise HTTPException(status_code=404, detail="checkout not available")
    actor_type, actor_id = await _checkout_actor(db, order, current_user, capability)
    try:
        await select_estimate_option(
            db,
            order=order,
            estimate_id=estimate_id,
            option_id=option_id,
            actor_type=actor_type,
            actor_id=actor_id,
            idempotency_key=_idempotency_key(idempotency_key),
        )
        await db.commit()
    except DBAPIError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) in {"40001", "40P01"}:
            raise HTTPException(
                status_code=503, detail="checkout concurrency retry exhausted"
            ) from exc
        raise
    order = await load_checkout_order(db, order_id)
    estimate = await db.get(CheckoutShippingEstimate, estimate_id)
    return await estimate_payload(db, order=order, estimate=estimate)
