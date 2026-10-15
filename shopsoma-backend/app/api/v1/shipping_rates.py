"""Shipping rate configuration endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, text
from uuid import UUID
from decimal import Decimal
from datetime import datetime, timedelta
import logging

from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.shipping_rate import ShippingRate
from app.services.shipbubble_service import get_shipbubble_service
from app.services.shipping.provider_settings import require_manual_order_pricing
from app.services.shipping.manual_rates import manual_rates_query
from app.models.address import Address
from app.schemas.shipping_rate import (
    ShippingRateCreate,
    ShippingRateUpdate,
    ShippingRateResponse,
    ShippingRateListResponse,
    ShippingCalculationRequest,
    ShippingCalculationResponse,
)
from app.api.dependencies import get_current_active_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipping-rates", tags=["Shipping Rates"])


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Dependency to require admin role"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


@router.post("", response_model=ShippingRateResponse, status_code=status.HTTP_201_CREATED)
async def create_shipping_rate(
    rate_data: ShippingRateCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new shipping rate (Admin only)

    - **name**: Rate name (e.g., "Standard Shipping", "Express Delivery")
    - **description**: Description with estimated delivery time
    - **base_rate**: Base shipping cost
    - **country**: Target country (default: Nigeria)
    - **state**: Specific state or null for all states
    - **min_order_value**: Minimum order value (for free shipping thresholds)
    - **max_order_value**: Maximum order value
    - **min_delivery_days**: Minimum delivery days
    - **max_delivery_days**: Maximum delivery days
    - **is_active**: Active status
    - **is_default**: Default rate
    - **priority**: Priority (lower number = higher priority)
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(736401, 2)"))
    # If setting as default, unset other defaults
    if rate_data.is_default:
        await db.execute(
            update(ShippingRate).values(is_default=False)
        )

    new_rate = ShippingRate(**rate_data.model_dump())
    db.add(new_rate)
    await db.commit()
    await db.refresh(new_rate)

    return new_rate


@router.get("", response_model=ShippingRateListResponse)
async def list_shipping_rates(
    active_only: bool = Query(False, description="Return only active rates"),
    country: str = Query(None, description="Filter by country"),
    state: str = Query(None, description="Filter by state"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all shipping rates (optionally filtered)
    """
    query = select(ShippingRate)

    # Apply filters
    conditions = []
    if active_only:
        conditions.append(ShippingRate.is_active == True)
    if country:
        conditions.append(ShippingRate.country == country)
    if state:
        conditions.append(or_(ShippingRate.state == state, ShippingRate.state == None))

    if conditions:
        query = query.where(and_(*conditions))

    query = query.order_by(ShippingRate.priority.asc(), ShippingRate.created_at.desc())

    result = await db.execute(query)
    rates = result.scalars().all()

    return ShippingRateListResponse(
        shipping_rates=rates,
        total=len(rates)
    )


@router.get("/{rate_id}", response_model=ShippingRateResponse)
async def get_shipping_rate(
    rate_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific shipping rate by ID
    """
    query = select(ShippingRate).where(ShippingRate.id == rate_id)
    result = await db.execute(query)
    rate = result.scalar_one_or_none()

    if not rate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipping rate not found"
        )

    return rate


@router.put("/{rate_id}", response_model=ShippingRateResponse)
async def update_shipping_rate(
    rate_id: UUID,
    rate_data: ShippingRateUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a shipping rate (Admin only)
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(736401, 2)"))
    # Get existing rate
    query = select(ShippingRate).where(ShippingRate.id == rate_id)
    result = await db.execute(query)
    rate = result.scalar_one_or_none()

    if not rate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipping rate not found"
        )

    # Update rate fields
    update_data = rate_data.model_dump(exclude_unset=True)
    merged = {column.name: getattr(rate, column.name) for column in ShippingRate.__table__.columns}
    merged.update(update_data)
    # Validate the merged state, not only the partial PATCH payload.
    try:
        normalized = ShippingRateCreate(**{k: merged[k] for k in ShippingRateCreate.model_fields if k in merged})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if normalized.is_default:
        await db.execute(update(ShippingRate).where(ShippingRate.id != rate_id).values(is_default=False))
    for field, value in normalized.model_dump().items():
        setattr(rate, field, value)

    await db.commit()
    await db.refresh(rate)

    return rate


@router.delete("/{rate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shipping_rate(
    rate_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a shipping rate (Admin only)
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(736401, 2)"))
    query = select(ShippingRate).where(ShippingRate.id == rate_id)
    result = await db.execute(query)
    rate = result.scalar_one_or_none()

    if not rate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipping rate not found"
        )

    # Rates may be referenced by immutable checkout snapshots; deactivate
    # instead of deleting historical configuration.
    rate.is_active = False
    rate.is_default = False
    await db.commit()
    return None


@router.post("/calculate", response_model=ShippingCalculationResponse)
async def calculate_shipping(
    calc_data: ShippingCalculationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Calculate available shipping rates for an order

    Returns all matching rates sorted by priority, with a recommended rate.
    Preview saved manual rates; unavailable provider modes fail closed.

    - **country**: Delivery country
    - **state**: Delivery state
    - **order_value**: Order subtotal
    """
    # Preserve preliminary manual pricing before partial-cohort classification.
    await require_manual_order_pricing(db)
    return await _get_local_rates(calc_data, db)


async def _get_local_rates(
    calc_data: ShippingCalculationRequest,
    db: AsyncSession
) -> ShippingCalculationResponse:
    """Get shipping rates from local database"""
    query = manual_rates_query(calc_data.country, calc_data.state).where(
        or_(ShippingRate.min_order_value.is_(None), ShippingRate.min_order_value <= calc_data.order_value),
        or_(ShippingRate.max_order_value.is_(None), ShippingRate.max_order_value >= calc_data.order_value),
    )
    available_rates = list((await db.scalars(query)).all())

    if not available_rates:
        # Check if shipping rates table is empty (e.g. freshly initialized local database).
        # If so, auto-seed default shipping rates and re-query.
        from sqlalchemy import func
        total_rates = await db.scalar(select(func.count(ShippingRate.id)))
        if total_rates == 0:
            try:
                from seed_shipping_rates import ensure_default_shipping_rates
                if await ensure_default_shipping_rates(db):
                    available_rates = list((await db.scalars(query)).all())
            except Exception as e:
                logger.warning(f"Failed to auto-seed shipping rates: {e}")

    if not available_rates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": f"No shipping rates configured for {calc_data.state}, {calc_data.country}",
                "error_code": "NO_SHIPPING_RATES",
                "suggestion": "Please contact support or try a different delivery location",
                "debug_info": {
                    "country": calc_data.country,
                    "state": calc_data.state,
                    "order_value": float(calc_data.order_value)
                }
            }
        )

    # The recommended rate is the default one, or the first (highest priority)
    recommended = next((r for r in available_rates if r.is_default), available_rates[0])

    return ShippingCalculationResponse(
        available_rates=available_rates,
        recommended_rate=recommended
    )


@router.post("/{rate_id}/set-default", response_model=ShippingRateResponse)
async def set_default_rate(
    rate_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Set a shipping rate as the default (Admin only)
    """
    await db.execute(text("SELECT pg_advisory_xact_lock(736401, 2)"))
    # Get rate
    query = select(ShippingRate).where(ShippingRate.id == rate_id)
    result = await db.execute(query)
    rate = result.scalar_one_or_none()

    if not rate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shipping rate not found"
        )

    if not rate.is_active:
        raise HTTPException(status_code=422, detail="Only an active rate can be the default")
    # Unset other defaults
    await db.execute(
        update(ShippingRate)
        .where(ShippingRate.id != rate_id)
        .values(is_default=False)
    )

    # Set this as default
    rate.is_default = True
    await db.commit()
    await db.refresh(rate)

    return rate
