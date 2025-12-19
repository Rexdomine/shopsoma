"""
User profile and management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import date

from app.core.database import get_db
from app.core.security import verify_password, get_password_hash
from app.models.user import User
from app.models.address import Address
from app.models.order import Order
from app.schemas.auth import UserResponse
from app.schemas.address import AddressResponse, AddressCreate, AddressUpdate
from app.schemas.order import OrderResponse
from app.api.dependencies import get_current_active_user

router = APIRouter(prefix="/users", tags=["Users"])


class UpdateProfileData(BaseModel):
    """Schema for updating user profile"""
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone_number: Optional[str] = Field(None, max_length=20)
    date_of_birth: Optional[date] = None
    gender: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None


class ChangePasswordData(BaseModel):
    """Schema for changing password"""
    current_password: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "OldPass123",
                "new_password": "NewSecurePass456"
            }
        }


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_active_user)
):
    """
    Get current user profile

    Returns the authenticated user's profile information.
    """
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_profile(
    profile_data: UpdateProfileData,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update current user profile

    - **full_name**: User's full name (optional)
    - **phone_number**: Phone number (optional)
    - **date_of_birth**: Date of birth (optional)
    - **gender**: Gender (optional)
    - **email**: Email address (optional)
    """
    # Check if email is being changed and if it's already taken
    if profile_data.email and profile_data.email != current_user.email:
        result = await db.execute(
            select(User).where(User.email == profile_data.email)
        )
        existing_user = result.scalar_one_or_none()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already in use"
            )
        current_user.email = profile_data.email

    # Update fields if provided
    update_data = profile_data.model_dump(exclude_unset=True, exclude={'email'})
    for field, value in update_data.items():
        setattr(current_user, field, value)

    await db.commit()
    await db.refresh(current_user)

    return current_user


@router.post("/me/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    password_data: ChangePasswordData,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Change user password

    Requires current password for verification.
    New password must meet security requirements:
    - At least 8 characters
    - Contains at least one letter
    - Contains at least one number
    """
    # Verify current password
    if not current_user.hashed_password or not verify_password(
        password_data.current_password, current_user.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )

    # Validate new password strength
    if len(password_data.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long"
        )
    if not any(char.isdigit() for char in password_data.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must contain at least one number"
        )
    if not any(char.isalpha() for char in password_data.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must contain at least one letter"
        )

    # Update password
    current_user.hashed_password = get_password_hash(password_data.new_password)
    await db.commit()

    return {"message": "Password changed successfully"}


@router.get("/me/addresses", response_model=List[AddressResponse])
async def get_user_addresses(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all addresses for the current user

    Returns a list of all saved addresses for the authenticated user.
    """
    result = await db.execute(
        select(Address)
        .where(Address.user_id == current_user.id)
        .order_by(Address.is_default.desc(), Address.created_at.desc())
    )
    addresses = result.scalars().all()
    return addresses


@router.post("/me/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
async def create_address(
    address_data: AddressCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new address for the current user

    If this is set as the default address, all other addresses will be set to non-default.
    Also updates the user's phone number if they don't have one.
    """
    # If this is the default address, unset all other defaults
    if address_data.is_default:
        result = await db.execute(
            select(Address).where(
                Address.user_id == current_user.id,
                Address.is_default == True
            )
        )
        existing_defaults = result.scalars().all()
        for addr in existing_defaults:
            addr.is_default = False

    # Update user's phone number if they don't have one
    if not current_user.phone_number and address_data.phone_number:
        current_user.phone_number = address_data.phone_number

    # Create new address
    new_address = Address(
        user_id=current_user.id,
        full_name=address_data.full_name,
        phone_number=address_data.phone_number,
        address_line1=address_data.address_line1,
        address_line2=address_data.address_line2,
        city=address_data.city,
        state=address_data.state,
        postal_code=address_data.postal_code,
        country=address_data.country,
        address_type=address_data.address_type,
        is_default=address_data.is_default,
    )

    db.add(new_address)
    await db.commit()
    await db.refresh(new_address)

    return new_address


@router.put("/me/addresses/{address_id}", response_model=AddressResponse)
async def update_address(
    address_id: UUID,
    address_data: AddressUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an existing address

    Only the address owner can update their addresses.
    If setting as default, all other addresses will be set to non-default.
    """
    # Get the address and verify ownership
    result = await db.execute(
        select(Address).where(
            Address.id == address_id,
            Address.user_id == current_user.id
        )
    )
    address = result.scalar_one_or_none()

    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )

    # If setting as default, unset all other defaults
    if address_data.is_default:
        result = await db.execute(
            select(Address).where(
                Address.user_id == current_user.id,
                Address.is_default == True,
                Address.id != address_id
            )
        )
        existing_defaults = result.scalars().all()
        for addr in existing_defaults:
            addr.is_default = False

    # Update fields if provided
    update_data = address_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(address, field, value)

    await db.commit()
    await db.refresh(address)

    return address


@router.delete("/me/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete an address

    Only the address owner can delete their addresses.
    Cannot delete the default address if other addresses exist.
    """
    # Get the address and verify ownership
    result = await db.execute(
        select(Address).where(
            Address.id == address_id,
            Address.user_id == current_user.id
        )
    )
    address = result.scalar_one_or_none()

    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )

    # Check if this is the default address
    if address.is_default:
        # Count other addresses
        count_result = await db.execute(
            select(Address).where(
                Address.user_id == current_user.id,
                Address.id != address_id
            )
        )
        other_addresses = count_result.scalars().all()

        if other_addresses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete default address. Please set another address as default first."
            )

    await db.delete(address)
    await db.commit()

    return None


@router.get("/me/orders", response_model=List[OrderResponse])
async def get_user_orders(
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all orders for the current user

    Returns a paginated list of orders for the authenticated user.

    - **page**: Page number (default: 1)
    - **page_size**: Items per page (default: 10)
    """
    # Calculate offset
    offset = (page - 1) * page_size

    # Get orders with pagination
    result = await db.execute(
        select(Order)
        .where(Order.user_id == current_user.id)
        .order_by(Order.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    orders = result.scalars().all()

    return orders


@router.get("/me/orders/{order_id}", response_model=OrderResponse)
async def get_user_order(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific order by ID

    Only the order owner can view their order details.
    """
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.id
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    return order
