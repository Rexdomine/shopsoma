"""Promo code endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select
from typing import Optional
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
from app.api.dependencies import get_current_active_user, get_optional_user
from app.services.promo_code_service import evaluate_promo_code

router = APIRouter(prefix="/promo-codes", tags=["Promo Codes"])


def _normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


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
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Validate a promo code and calculate discount

    - **code**: Promo code to validate
    - **order_subtotal**: Order subtotal amount
    - **currency**: Checkout currency (NGN or USD)
    - **customer_email**: Optional customer email for per-user limit checks during guest checkout

    Returns validation status and calculated discount if valid.
    """
    evaluation = await evaluate_promo_code(
        db=db,
        code=validate_data.code,
        subtotal=validate_data.order_subtotal,
        currency=validate_data.currency,
        user_id=current_user.id if current_user else None,
        customer_email=validate_data.customer_email,
    )
    return PromoCodeValidateResponse(
        valid=evaluation.valid,
        code=evaluation.code,
        discount_type=evaluation.discount_type,
        discount_value=evaluation.discount_value,
        discount_amount=evaluation.discount_amount if evaluation.valid else None,
        currency=evaluation.currency,
        message=evaluation.message,
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
    if _normalize_dt(promo_data.valid_from) >= _normalize_dt(promo_data.valid_until):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="valid_until must be after valid_from"
        )

    if promo_data.discount_type == DiscountType.PERCENTAGE and promo_data.discount_value > Decimal("100"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Percentage discount value cannot exceed 100"
        )

    payload = promo_data.model_dump(exclude={"code"})
    new_promo = PromoCode(
        **payload,
        code=promo_data.code.upper()
    )

    db.add(new_promo)
    await db.commit()
    await db.refresh(new_promo)

    return new_promo


@router.get("", response_model=PromoCodeListResponse)
async def list_promo_codes(
    active_only: bool = False,
    search: Optional[str] = Query(None, max_length=100),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    List all promo codes (Admin only)
    """
    query = select(PromoCode)

    if active_only:
        query = query.where(PromoCode.is_active == True)

    if search and search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                PromoCode.code.ilike(pattern),
                PromoCode.description.ilike(pattern),
            )
        )

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

    if "code" in update_data and update_data["code"]:
        normalized_code = update_data["code"].upper()
        existing = await db.execute(
            select(PromoCode).where(
                PromoCode.code == normalized_code,
                PromoCode.id != promo_id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Promo code '{normalized_code}' already exists"
            )
        update_data["code"] = normalized_code

    next_valid_from = update_data.get("valid_from", promo.valid_from)
    next_valid_until = update_data.get("valid_until", promo.valid_until)
    if _normalize_dt(next_valid_from) >= _normalize_dt(next_valid_until):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="valid_until must be after valid_from"
        )

    next_discount_type = update_data.get("discount_type", promo.discount_type)
    next_discount_value = update_data.get("discount_value", promo.discount_value)
    if next_discount_type == DiscountType.PERCENTAGE and Decimal(next_discount_value) > Decimal("100"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Percentage discount value cannot exceed 100"
        )

    for field, value in update_data.items():
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
