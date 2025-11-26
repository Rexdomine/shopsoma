"""Address management endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_
from uuid import UUID

from app.core.database import get_db
from app.models.user import User
from app.models.address import Address
from app.schemas.address import (
    AddressCreate,
    AddressUpdate,
    AddressResponse,
    AddressListResponse,
)
from app.api.dependencies import get_current_active_user

router = APIRouter(prefix="/addresses", tags=["Addresses"])


@router.post("", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
async def create_address(
    address_data: AddressCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new address for the authenticated user

    - **full_name**: Full name for delivery
    - **phone_number**: Contact phone number
    - **address_line1**: Street address
    - **address_line2**: Apartment, suite, etc. (optional)
    - **city**: City
    - **state**: State/Province
    - **postal_code**: Postal/ZIP code (optional)
    - **country**: Country (default: Nigeria)
    - **address_type**: shipping or billing
    - **is_default**: Set as default address
    """
    # If this is set as default, unset other default addresses of same type
    if address_data.is_default:
        await db.execute(
            update(Address)
            .where(
                and_(
                    Address.user_id == current_user.id,
                    Address.address_type == address_data.address_type
                )
            )
            .values(is_default=False)
        )

    # Create new address
    new_address = Address(
        user_id=current_user.id,
        **address_data.model_dump()
    )

    db.add(new_address)
    await db.commit()
    await db.refresh(new_address)

    return new_address


@router.get("", response_model=AddressListResponse)
async def list_addresses(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all addresses for the authenticated user
    """
    query = select(Address).where(Address.user_id == current_user.id).order_by(
        Address.is_default.desc(), Address.created_at.desc()
    )

    result = await db.execute(query)
    addresses = result.scalars().all()

    return AddressListResponse(
        addresses=addresses,
        total=len(addresses)
    )


@router.get("/{address_id}", response_model=AddressResponse)
async def get_address(
    address_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific address by ID
    """
    query = select(Address).where(
        and_(
            Address.id == address_id,
            Address.user_id == current_user.id
        )
    )

    result = await db.execute(query)
    address = result.scalar_one_or_none()

    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )

    return address


@router.put("/{address_id}", response_model=AddressResponse)
async def update_address(
    address_id: UUID,
    address_data: AddressUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Update an address
    """
    # Get existing address
    query = select(Address).where(
        and_(
            Address.id == address_id,
            Address.user_id == current_user.id
        )
    )

    result = await db.execute(query)
    address = result.scalar_one_or_none()

    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )

    # If setting as default, unset other defaults of same type
    if address_data.is_default and address_data.is_default != address.is_default:
        address_type = address_data.address_type or address.address_type
        await db.execute(
            update(Address)
            .where(
                and_(
                    Address.user_id == current_user.id,
                    Address.address_type == address_type,
                    Address.id != address_id
                )
            )
            .values(is_default=False)
        )

    # Update address fields
    update_data = address_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(address, field, value)

    await db.commit()
    await db.refresh(address)

    return address


@router.delete("/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete an address
    """
    # Check if address exists and belongs to user
    query = select(Address).where(
        and_(
            Address.id == address_id,
            Address.user_id == current_user.id
        )
    )

    result = await db.execute(query)
    address = result.scalar_one_or_none()

    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )

    # Check if address is being used by any orders
    from app.models.order import Order
    order_check = await db.execute(
        select(Order.id).where(
            or_(
                Order.shipping_address_id == address_id,
                Order.billing_address_id == address_id
            )
        ).limit(1)
    )
    if order_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete address that is associated with existing orders"
        )

    # Delete address
    await db.execute(delete(Address).where(Address.id == address_id))
    await db.commit()

    return None


@router.post("/{address_id}/set-default", response_model=AddressResponse)
async def set_default_address(
    address_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Set an address as the default for its type
    """
    # Get address
    query = select(Address).where(
        and_(
            Address.id == address_id,
            Address.user_id == current_user.id
        )
    )

    result = await db.execute(query)
    address = result.scalar_one_or_none()

    if not address:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Address not found"
        )

    # Unset other defaults of same type
    await db.execute(
        update(Address)
        .where(
            and_(
                Address.user_id == current_user.id,
                Address.address_type == address.address_type,
                Address.id != address_id
            )
        )
        .values(is_default=False)
    )

    # Set this as default
    address.is_default = True
    await db.commit()
    await db.refresh(address)

    return address
