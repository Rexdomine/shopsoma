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
from app.services.shipbubble_service import get_shipbubble_service

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


async def _get_shipbubble_rates(
    calc_data: ShippingCalculationRequest,
    db: AsyncSession
) -> ShippingCalculationResponse:
    """Get shipping rates from ShipBubble API"""
    service = get_shipbubble_service()

    # Get address if provided
    address = None
    if hasattr(calc_data, 'address_id') and calc_data.address_id:
        addr_query = select(Address).where(Address.id == calc_data.address_id)
        addr_result = await db.execute(addr_query)
        address = addr_result.scalar_one_or_none()

    # For ShipBubble, we need to create addresses first
    # Use default vendor address (first address in system) for sender
    vendor_address_query = select(Address).limit(1)
    vendor_result = await db.execute(vendor_address_query)
    vendor_address = vendor_result.scalar_one_or_none()

    if not vendor_address and not address:
        logger.warning("[ShipBubble] No addresses found, cannot fetch rates")
        return None

    # Create sender address in ShipBubble
    sender_address_str = (
        f"{vendor_address.address_line1}, {vendor_address.address_line2 or ''}"
        if vendor_address
        else "123 Store St"
    ).strip().rstrip(',')

    sender_code = await service.create_address(
        name="Shopsoma Store",
        phone="+2348000000000",  # Default phone
        email="store@shopsoma.com",
        address=sender_address_str,
        city=vendor_address.city if vendor_address else "Lagos",
        state=vendor_address.state if vendor_address else "Lagos",
        country="Nigeria",
        postal_code=vendor_address.postal_code if vendor_address else "100001"
    )

    # Create receiver address in ShipBubble
    receiver_address_str = (
        f"{address.address_line1}, {address.address_line2 or ''}"
        if address
        else "456 Customer Ave"
    ).strip().rstrip(',')

    receiver_code = await service.create_address(
        name=address.full_name if address else "Customer",
        phone=address.phone_number if address else "+2348000000001",
        email="customer@example.com",
        address=receiver_address_str,
        city=address.city if address else calc_data.state,
        state=address.state if address else calc_data.state,
        country=calc_data.country,
        postal_code=address.postal_code if address else "100002"
    )

    # Calculate pickup date (tomorrow)
    pickup_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Get rates from ShipBubble
    rates = await service.get_shipping_rates(
        sender_address_code=sender_code,
        receiver_address_code=receiver_code,
        pickup_date=pickup_date,
        category_id=1,  # Fashion/Clothing
        package_items=[
            {
                "name": "Order Items",
                "description": "Clothing items",
                "unit_weight": 0.5,  # 0.5 kg default weight
                "unit_amount": float(calc_data.order_value),
                "quantity": 1
            }
        ],
        package_dimension={
            "length": 30,   # cm
            "width": 25,    # cm
            "height": 10    # cm
        },
        service_type="pickup"
    )

    if not rates:
        return None

    # Convert ShipBubble rates to our ShippingRate format
    available_rates = []
    for rate in rates:
        # Create temporary ShippingRate object
        shipping_rate = ShippingRate(
            name=f"{rate['courier']} - {rate.get('description', 'Delivery')}",
            description=f"Estimated delivery: {rate['estimated_days']} days",
            base_rate=Decimal(str(rate['price'])),
            country=calc_data.country,
            state=calc_data.state,
            min_delivery_days=rate['estimated_days'],
            max_delivery_days=rate['estimated_days'],
            is_active=True,
            is_default=False,
            priority=len(available_rates) + 1
        )
        available_rates.append(shipping_rate)

    if not available_rates:
        return None

    # First rate is recommended (lowest price)
    available_rates[0].is_default = True

    return ShippingCalculationResponse(
        available_rates=available_rates,
        recommended_rate=available_rates[0]
    )


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
