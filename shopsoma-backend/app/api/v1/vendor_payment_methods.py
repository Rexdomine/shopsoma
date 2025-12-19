"""Vendor Payment Methods API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.api.dependencies import get_current_vendor
from app.models import User, Vendor, VendorPaymentMethod

router = APIRouter(prefix="/vendor/payment-methods", tags=["Vendor Payment Methods"])


class PaymentMethodCreate(BaseModel):
    """Request to create a new payment method"""
    account_type: Optional[str] = None
    bank_name: str
    account_number: str
    account_holder: str
    tin: Optional[str] = None
    is_default: bool = False


class PaymentMethodResponse(BaseModel):
    """Payment method response"""
    id: str
    vendor_id: str
    account_type: Optional[str]
    bank_name: str
    account_number: str
    masked_account: str
    account_holder: str
    tin: Optional[str]
    is_default: bool
    created_at: str
    updated_at: str


@router.get("", response_model=List[PaymentMethodResponse])
async def list_payment_methods(
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all payment methods for the current vendor
    """
    # Get vendor
    vendor_result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = vendor_result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )

    # Get all payment methods for this vendor
    result = await db.execute(
        select(VendorPaymentMethod)
        .where(VendorPaymentMethod.vendor_id == vendor.id)
        .order_by(VendorPaymentMethod.created_at.desc())
    )
    payment_methods = result.scalars().all()

    return [PaymentMethodResponse(**pm.to_dict()) for pm in payment_methods]


@router.post("", response_model=PaymentMethodResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_method(
    data: PaymentMethodCreate,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new payment method for the current vendor

    If this is the first payment method or is_default is True,
    it will be set as the default method.
    """
    # Get vendor
    vendor_result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = vendor_result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )

    # Check if this is the first payment method
    existing_count_result = await db.execute(
        select(VendorPaymentMethod)
        .where(VendorPaymentMethod.vendor_id == vendor.id)
    )
    existing_methods = existing_count_result.scalars().all()
    is_first_method = len(existing_methods) == 0

    # If this is the first method OR user explicitly set is_default=True, make it default
    should_be_default = is_first_method or data.is_default

    # If making this default, unset all other defaults
    if should_be_default:
        await db.execute(
            VendorPaymentMethod.__table__.update()
            .where(VendorPaymentMethod.vendor_id == vendor.id)
            .values(is_default=False)
        )

    # Create new payment method
    new_method = VendorPaymentMethod(
        vendor_id=vendor.id,
        account_type=data.account_type,
        bank_name=data.bank_name,
        account_number=data.account_number,
        account_holder=data.account_holder,
        tin=data.tin,
        is_default=should_be_default
    )

    db.add(new_method)
    await db.commit()
    await db.refresh(new_method)

    return PaymentMethodResponse(**new_method.to_dict())


@router.post("/{method_id}/set-default", response_model=PaymentMethodResponse)
async def set_default_payment_method(
    method_id: UUID,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Set a specific payment method as the default for the current vendor

    This will unset all other payment methods as non-default
    """
    # Get vendor
    vendor_result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = vendor_result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )

    # Get the payment method
    method_result = await db.execute(
        select(VendorPaymentMethod)
        .where(
            and_(
                VendorPaymentMethod.id == method_id,
                VendorPaymentMethod.vendor_id == vendor.id
            )
        )
    )
    payment_method = method_result.scalar_one_or_none()

    if not payment_method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found"
        )

    # Unset all defaults for this vendor
    await db.execute(
        VendorPaymentMethod.__table__.update()
        .where(VendorPaymentMethod.vendor_id == vendor.id)
        .values(is_default=False)
    )

    # Set this one as default
    payment_method.is_default = True
    await db.commit()
    await db.refresh(payment_method)

    return PaymentMethodResponse(**payment_method.to_dict())


@router.delete("/{method_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payment_method(
    method_id: UUID,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a payment method

    If the deleted method was the default and other methods exist,
    the most recently created method will become the new default
    """
    # Get vendor
    vendor_result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = vendor_result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vendor profile not found"
        )

    # Get the payment method
    method_result = await db.execute(
        select(VendorPaymentMethod)
        .where(
            and_(
                VendorPaymentMethod.id == method_id,
                VendorPaymentMethod.vendor_id == vendor.id
            )
        )
    )
    payment_method = method_result.scalar_one_or_none()

    if not payment_method:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment method not found"
        )

    was_default = payment_method.is_default

    # Delete the payment method
    await db.delete(payment_method)
    await db.commit()

    # If it was default, set the most recent remaining method as default
    if was_default:
        remaining_result = await db.execute(
            select(VendorPaymentMethod)
            .where(VendorPaymentMethod.vendor_id == vendor.id)
            .order_by(VendorPaymentMethod.created_at.desc())
            .limit(1)
        )
        remaining_method = remaining_result.scalar_one_or_none()

        if remaining_method:
            remaining_method.is_default = True
            await db.commit()

    return None
