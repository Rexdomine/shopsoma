"""
User profile and management endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm import selectinload
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from uuid import UUID
from datetime import date

from app.core.database import get_db
from app.core.security import verify_password, get_password_hash
from app.models.user import User
from app.models.address import Address
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.returns import Return, ReturnStatus
from app.schemas.auth import UserResponse
from app.schemas.address import AddressResponse, AddressCreate, AddressUpdate
from app.schemas.order import OrderResponse
from app.schemas.returns import ReturnCreateRequest, ReturnResponse, ReturnUpdateRequest
from app.api.dependencies import get_current_active_user
import uuid

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
        .where(Order.customer_id == current_user.id)
        .order_by(Order.created_at.desc())
        .limit(page_size)
        .offset(offset)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images)
        )
    )
    orders = result.scalars().all()

    for order in orders:
        for item in order.items:
            if item.product and item.product.images:
                primary_image = next((img for img in item.product.images if img.is_primary), None)
                if not primary_image and item.product.images:
                    primary_image = item.product.images[0]
                item.product_image_url = primary_image.image_url if primary_image else None
            else:
                item.product_image_url = None

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
        select(Order)
        .where(
            Order.id == order_id,
            Order.customer_id == current_user.id
        )
        .options(
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images)
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    for item in order.items:
        if item.product and item.product.images:
            primary_image = next((img for img in item.product.images if img.is_primary), None)
            if not primary_image and item.product.images:
                primary_image = item.product.images[0]
            item.product_image_url = primary_image.image_url if primary_image else None
        else:
            item.product_image_url = None

    return order


@router.get("/me/returns", response_model=List[ReturnResponse])
async def get_user_returns(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Return)
        .where(Return.customer_id == current_user.id)
        .order_by(Return.created_at.desc())
        .options(
            selectinload(Return.order),
            selectinload(Return.order_item).selectinload(OrderItem.product).selectinload(Product.images),
        )
    )
    returns = result.scalars().all()

    response = []
    for ret in returns:
        order_item = ret.order_item
        product_image_url = None
        if order_item and order_item.product and order_item.product.images:
            primary_image = next((img for img in order_item.product.images if img.is_primary), None)
            if not primary_image and order_item.product.images:
                primary_image = order_item.product.images[0]
            product_image_url = primary_image.image_url if primary_image else None

        response.append(
            ReturnResponse(
                id=ret.id,
                return_number=ret.return_number,
                status=ret.status.value,
                reason=ret.reason,
                description=ret.description,
                opened=(ret.request_details or {}).get("opened"),
                return_action=(ret.request_details or {}).get("return_action"),
                rejection_reason=ret.rejection_reason,
                created_at=ret.created_at,
                order_id=ret.order_id,
                order_number=ret.order.order_number if ret.order else None,
                order_date=ret.order.created_at if ret.order else None,
                product_title=order_item.product_title if order_item else None,
                quantity=order_item.quantity if order_item else None,
                amount=float(order_item.subtotal) if order_item else None,
                product_image_url=product_image_url,
            )
        )

    return response


@router.get("/me/returns/{return_id}", response_model=ReturnResponse)
async def get_user_return(
    return_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Return)
        .where(Return.id == return_id, Return.customer_id == current_user.id)
        .options(
            selectinload(Return.order),
            selectinload(Return.order_item).selectinload(OrderItem.product).selectinload(Product.images),
        )
    )
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return not found")

    order_item = ret.order_item
    product_image_url = None
    if order_item and order_item.product and order_item.product.images:
        primary_image = next((img for img in order_item.product.images if img.is_primary), None)
        if not primary_image and order_item.product.images:
            primary_image = order_item.product.images[0]
        product_image_url = primary_image.image_url if primary_image else None

    return ReturnResponse(
        id=ret.id,
        return_number=ret.return_number,
        status=ret.status.value,
        reason=ret.reason,
        description=ret.description,
        opened=(ret.request_details or {}).get("opened"),
        return_action=(ret.request_details or {}).get("return_action"),
        rejection_reason=ret.rejection_reason,
        created_at=ret.created_at,
        order_id=ret.order_id,
        order_number=ret.order.order_number if ret.order else None,
        order_date=ret.order.created_at if ret.order else None,
        product_title=order_item.product_title if order_item else None,
        quantity=order_item.quantity if order_item else None,
        amount=float(order_item.subtotal) if order_item else None,
        product_image_url=product_image_url,
    )


@router.post("/me/returns", response_model=ReturnResponse, status_code=status.HTTP_201_CREATED)
async def create_user_return(
    payload: ReturnCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    order_result = await db.execute(
        select(Order)
        .where(Order.id == payload.order_id, Order.customer_id == current_user.id)
        .options(
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images)
        )
    )
    order = order_result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order_item = next((item for item in order.items if item.id == payload.order_item_id), None)
    if not order_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order item not found")

    return_number = f"RET-{uuid.uuid4().hex[:8].upper()}"
    existing = await db.execute(select(Return).where(Return.return_number == return_number))
    while existing.scalar_one_or_none() is not None:
        return_number = f"RET-{uuid.uuid4().hex[:8].upper()}"
        existing = await db.execute(select(Return).where(Return.return_number == return_number))

    new_return = Return(
        return_number=return_number,
        order_id=order.id,
        customer_id=current_user.id,
        order_item_id=order_item.id,
        reason=payload.reason,
        description=payload.description,
        request_details={
            "opened": payload.opened,
            "return_action": payload.return_action,
        },
        status=ReturnStatus.REQUESTED,
    )
    db.add(new_return)
    await db.commit()
    await db.refresh(new_return)

    product_image_url = None
    if order_item.product and order_item.product.images:
        primary_image = next((img for img in order_item.product.images if img.is_primary), None)
        if not primary_image and order_item.product.images:
            primary_image = order_item.product.images[0]
        product_image_url = primary_image.image_url if primary_image else None

    return ReturnResponse(
        id=new_return.id,
        return_number=new_return.return_number,
        status=new_return.status.value,
        reason=new_return.reason,
        description=new_return.description,
        opened=(new_return.request_details or {}).get("opened"),
        return_action=(new_return.request_details or {}).get("return_action"),
        rejection_reason=new_return.rejection_reason,
        created_at=new_return.created_at,
        order_id=order.id,
        order_number=order.order_number,
        order_date=order.created_at,
        product_title=order_item.product_title,
        quantity=order_item.quantity,
        amount=float(order_item.subtotal),
        product_image_url=product_image_url,
    )


@router.patch("/me/returns/{return_id}", response_model=ReturnResponse)
async def update_user_return(
    return_id: UUID,
    payload: ReturnUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Return)
        .where(Return.id == return_id, Return.customer_id == current_user.id)
        .options(
            selectinload(Return.order),
            selectinload(Return.order_item).selectinload(OrderItem.product).selectinload(Product.images),
        )
    )
    ret = result.scalar_one_or_none()
    if not ret:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return not found")

    if ret.status != ReturnStatus.REQUESTED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Return request can no longer be edited")

    if payload.reason is not None:
        ret.reason = payload.reason
    if payload.description is not None:
        ret.description = payload.description

    details = ret.request_details or {}
    if payload.opened is not None:
        details["opened"] = payload.opened
    if payload.return_action is not None:
        details["return_action"] = payload.return_action
    ret.request_details = details

    await db.commit()
    await db.refresh(ret)

    order_item = ret.order_item
    product_image_url = None
    if order_item and order_item.product and order_item.product.images:
        primary_image = next((img for img in order_item.product.images if img.is_primary), None)
        if not primary_image and order_item.product.images:
            primary_image = order_item.product.images[0]
        product_image_url = primary_image.image_url if primary_image else None

    return ReturnResponse(
        id=ret.id,
        return_number=ret.return_number,
        status=ret.status.value,
        reason=ret.reason,
        description=ret.description,
        opened=(ret.request_details or {}).get("opened"),
        return_action=(ret.request_details or {}).get("return_action"),
        created_at=ret.created_at,
        order_id=ret.order_id,
        order_number=ret.order.order_number if ret.order else None,
        order_date=ret.order.created_at if ret.order else None,
        product_title=order_item.product_title if order_item else None,
        quantity=order_item.quantity if order_item else None,
        amount=float(order_item.subtotal) if order_item else None,
        product_image_url=product_image_url,
    )
