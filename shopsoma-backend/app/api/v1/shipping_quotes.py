"""Authenticated customer shipping quote endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.customer_shipping_quote import CustomerShippingQuoteResponse
from app.services.shipping.capabilities import domestic_shipping_capabilities
from app.services.shipping.customer_quotes import (
    CustomerShippingQuoteService,
    ShippingQuoteConflict,
    ShippingQuoteNotFound,
    ShippingQuoteUnavailable,
)

router = APIRouter(prefix="/orders", tags=["Shipping Quotes"])


def _service(db: AsyncSession) -> CustomerShippingQuoteService:
    return CustomerShippingQuoteService(
        db,
        capabilities=domestic_shipping_capabilities(settings),
        quote_ttl_seconds=settings.DHL_DOMESTIC_QUOTE_TTL_SECONDS,
    )


def _raise_public(error: Exception) -> None:
    if isinstance(error, ShippingQuoteNotFound):
        raise HTTPException(status_code=404, detail="shipping quote was not found")
    if isinstance(error, ShippingQuoteConflict):
        raise HTTPException(status_code=409, detail=str(error))
    if isinstance(error, ShippingQuoteUnavailable):
        raise HTTPException(status_code=503, detail=str(error))
    if isinstance(error, ValueError):
        raise HTTPException(status_code=422, detail="idempotency key is invalid")
    raise error


@router.get(
    "/{order_id}/shipping-quotes",
    response_model=list[CustomerShippingQuoteResponse],
    response_model_exclude_none=True,
)
async def list_shipping_quotes(
    order_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return await _service(db).list_quotes(
            order_id=order_id, customer_id=current_user.id
        )
    except Exception as error:
        _raise_public(error)


@router.get(
    "/{order_id}/shipping-quotes/{quote_id}",
    response_model=CustomerShippingQuoteResponse,
    response_model_exclude_none=True,
)
async def get_shipping_quote(
    order_id: UUID,
    quote_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        return await _service(db).get_quote(
            order_id=order_id,
            quote_id=quote_id,
            customer_id=current_user.id,
        )
    except Exception as error:
        _raise_public(error)


@router.post(
    "/{order_id}/shipping-quotes",
    response_model=CustomerShippingQuoteResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_shipping_quote(
    order_id: UUID,
    idempotency_key: str = Header(
        ...,
        alias="X-Idempotency-Key",
        min_length=1,
        max_length=200,
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        quote = await _service(db).create_quote(
            order_id=order_id,
            customer_id=current_user.id,
            idempotency_key=idempotency_key,
        )
        await db.commit()
        return quote
    except Exception as error:
        await db.rollback()
        _raise_public(error)


@router.post(
    "/{order_id}/shipping-quotes/{quote_id}/options/{option_id}/select",
    response_model=CustomerShippingQuoteResponse,
    response_model_exclude_none=True,
)
async def select_shipping_quote_option(
    order_id: UUID,
    quote_id: UUID,
    option_id: UUID,
    idempotency_key: str = Header(
        ...,
        alias="X-Idempotency-Key",
        min_length=1,
        max_length=200,
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    try:
        quote = await _service(db).select_option(
            order_id=order_id,
            quote_id=quote_id,
            option_id=option_id,
            customer_id=current_user.id,
            idempotency_key=idempotency_key,
        )
        await db.commit()
        return quote
    except Exception as error:
        await db.rollback()
        _raise_public(error)
