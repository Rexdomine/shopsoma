"""Promo code endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal

from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.promo_code import PromoCode, DiscountType
from app.schemas.promo_code import (
    PromoCodeCreate,
    PromoCodeUpdate,
    PromoCodeResponse,
    PromoCodeListResponse,
    PromoCodeValidateRequest,
    PromoCodeValidateResponse,
)
from app.api.dependencies import get_current_active_user

router = APIRouter(prefix="/promo-codes", tags=["Promo Codes"])


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Dependency to require admin role"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


@router.post("/validate", response_model=PromoCodeValidateResponse)
async def validate_promo_code(
    validate_data: PromoCodeValidateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Validate a promo code and calculate discount

    - **code**: Promo code to validate
    - **order_subtotal**: Order subtotal amount

    Returns validation status and calculated discount if valid.
    """
    # Get promo code
    query = select(PromoCode).where(
        and_(
            PromoCode.code == validate_data.code.upper(),
            PromoCode.is_active == True
        )
    )

    result = await db.execute(query)
    promo = result.scalar_one_or_none()

    if not promo:
        return PromoCodeValidateResponse(
            valid=False,
            message=f"Promo code '{validate_data.code}' not found"
        )

    # Check validity period
    now = datetime.now(timezone.utc)
    if now < promo.valid_from:
        return PromoCodeValidateResponse(
            valid=False,
            message=f"Promo code not yet valid. Valid from {promo.valid_from.strftime('%Y-%m-%d')}"
        )

    if now > promo.valid_until:
        return PromoCodeValidateResponse(
            valid=False,
            message=f"Promo code expired on {promo.valid_until.strftime('%Y-%m-%d')}"
        )

    # Check usage limit
    if promo.usage_limit and promo.usage_count >= promo.usage_limit:
        return PromoCodeValidateResponse(
            valid=False,
            message="Promo code usage limit reached"
        )

    # Check minimum purchase amount
    if promo.min_purchase_amount and validate_data.order_subtotal < promo.min_purchase_amount:
        return PromoCodeValidateResponse(
            valid=False,
            message=f"Minimum purchase amount of ₦{promo.min_purchase_amount:,.2f} required"
        )

    # Calculate discount
    discount_amount = Decimal("0.00")

    if promo.discount_type == DiscountType.PERCENTAGE:
        discount_amount = (validate_data.order_subtotal * promo.discount_value) / Decimal("100")

        # Apply max discount cap if specified
        if promo.max_discount_amount and discount_amount > promo.max_discount_amount:
            discount_amount = promo.max_discount_amount

    elif promo.discount_type == DiscountType.FIXED_AMOUNT:
        discount_amount = promo.discount_value

        # Don't exceed order subtotal
        if discount_amount > validate_data.order_subtotal:
            discount_amount = validate_data.order_subtotal

    return PromoCodeValidateResponse(
        valid=True,
        code=promo.code,
        discount_type=promo.discount_type,
        discount_value=promo.discount_value,
        discount_amount=discount_amount,
        message=f"₦{discount_amount:,.2f} discount applied"
    )


@router.post("", response_model=PromoCodeResponse, status_code=status.HTTP_201_CREATED)
async def create_promo_code(
    promo_data: PromoCodeCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new promo code (Admin only)
    """
    # Check if code already exists
    existing = await db.execute(
        select(PromoCode).where(PromoCode.code == promo_data.code.upper())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Promo code '{promo_data.code}' already exists"
        )

    # Validate dates
    if promo_data.valid_from >= promo_data.valid_until:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="valid_until must be after valid_from"
        )

    new_promo = PromoCode(
        **promo_data.model_dump(),
        code=promo_data.code.upper()
    )

    db.add(new_promo)
    await db.commit()
    await db.refresh(new_promo)

    return new_promo


@router.get("", response_model=PromoCodeListResponse)
async def list_promo_codes(
    active_only: bool = False,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all promo codes (Admin only)
    """
    query = select(PromoCode)

    if active_only:
        query = query.where(PromoCode.is_active == True)

    query = query.order_by(PromoCode.created_at.desc())

    result = await db.execute(query)
    promo_codes = result.scalars().all()

    return PromoCodeListResponse(
        promo_codes=promo_codes,
        total=len(promo_codes)
    )


@router.get("/{promo_id}", response_model=PromoCodeResponse)
async def get_promo_code(
    promo_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific promo code (Admin only)
    """
    query = select(PromoCode).where(PromoCode.id == promo_id)
    result = await db.execute(query)
    promo = result.scalar_one_or_none()

    if not promo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promo code not found"
        )

    return promo


@router.put("/{promo_id}", response_model=PromoCodeResponse)
async def update_promo_code(
    promo_id: UUID,
    promo_data: PromoCodeUpdate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a promo code (Admin only)
    """
    query = select(PromoCode).where(PromoCode.id == promo_id)
    result = await db.execute(query)
    promo = result.scalar_one_or_none()

    if not promo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promo code not found"
        )

    # Update fields
    update_data = promo_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "code" and value:
            value = value.upper()
        setattr(promo, field, value)

    await db.commit()
    await db.refresh(promo)

    return promo


@router.delete("/{promo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_promo_code(
    promo_id: UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a promo code (Admin only)
    """
    query = select(PromoCode).where(PromoCode.id == promo_id)
    result = await db.execute(query)
    promo = result.scalar_one_or_none()

    if not promo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promo code not found"
        )

    await db.delete(promo)
    await db.commit()

    return None
