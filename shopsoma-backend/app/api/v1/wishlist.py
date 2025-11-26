"""Wishlist endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, and_
from sqlalchemy.orm import selectinload
from uuid import UUID
from datetime import datetime
import uuid

from app.core.database import get_db
from app.api.dependencies import get_current_active_user
from app.models.user import User
from app.models.wishlist import Wishlist
from app.models.product import Product
from app.models.vendor import Vendor
from app.schemas.wishlist import (
    WishlistItemCreate,
    WishlistItemResponse,
    WishlistResponse,
    WishlistCheckResponse,
)

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


@router.get("", response_model=WishlistResponse)
async def get_wishlist(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's wishlist with product details"""
    # Query wishlist items with product and vendor details
    query = (
        select(
            Wishlist,
            Product.id.label("product_db_id"),
            Product.title.label("product_title"),
            Product.base_price.label("product_price"),
            Product.compare_at_price.label("product_sale_price"),
            Product.status.label("status"),
            Vendor.business_name.label("product_vendor_name"),
        )
        .join(Product, Wishlist.product_id == Product.id)
        .join(Vendor, Product.vendor_id == Vendor.id)
        .where(Wishlist.user_id == current_user.id)
        .order_by(Wishlist.created_at.desc())
    )

    result = await db.execute(query)
    rows = result.all()

    # Build response with product details
    items = []
    for row in rows:
        wishlist_item = row[0]

        # Get first product image if available
        image_query = (
            select(Product)
                .options(selectinload(Product.images))
                .where(Product.id == wishlist_item.product_id)
        )
        product_result = await db.execute(image_query)
        product = product_result.scalar_one_or_none()

        product_image = None
        if product and product.images:
            product_image = product.images[0].image_url if product.images else None

        item_response = WishlistItemResponse(
            id=wishlist_item.id,
            user_id=wishlist_item.user_id,
            product_id=wishlist_item.product_id,
            created_at=wishlist_item.created_at,
            product_title=row.product_title,
            product_price=float(row.product_price),
            product_sale_price=float(row.product_sale_price) if row.product_sale_price else None,
            product_image=product_image,
            product_vendor_name=row.product_vendor_name,
            product_slug=str(row.product_db_id),
            is_active=row.status == "active",
        )
        items.append(item_response)

    return WishlistResponse(items=items, total=len(items))


@router.post("", response_model=WishlistItemResponse, status_code=status.HTTP_201_CREATED)
async def add_to_wishlist(
    data: WishlistItemCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a product to wishlist"""
    # Check if product exists
    product_query = select(Product).options(selectinload(Product.images)).where(Product.id == data.product_id)
    product_result = await db.execute(product_query)
    product = product_result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Check if already in wishlist
    existing_query = select(Wishlist).where(
        and_(
            Wishlist.user_id == current_user.id,
            Wishlist.product_id == data.product_id
        )
    )
    existing_result = await db.execute(existing_query)
    existing = existing_result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Product already in wishlist"
        )

    # Create wishlist item
    wishlist_item = Wishlist(
        id=uuid.uuid4(),
        user_id=current_user.id,
        product_id=data.product_id,
        created_at=datetime.utcnow(),
    )

    db.add(wishlist_item)
    await db.commit()
    await db.refresh(wishlist_item)

    # Get product and vendor details for response
    vendor_query = select(Vendor).where(Vendor.id == product.vendor_id)
    vendor_result = await db.execute(vendor_query)
    vendor = vendor_result.scalar_one_or_none()

    product_image = None
    if product.images:
        product_image = product.images[0].image_url if product.images else None

    return WishlistItemResponse(
        id=wishlist_item.id,
        user_id=wishlist_item.user_id,
        product_id=wishlist_item.product_id,
        created_at=wishlist_item.created_at,
        product_title=product.title,
        product_price=float(product.base_price),
        product_sale_price=float(product.compare_at_price) if product.compare_at_price else None,
        product_image=product_image,
        product_vendor_name=vendor.business_name if vendor else "Unknown",
        product_slug=str(product.id),
        is_active=product.status == "active",
    )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_wishlist(
    product_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a product from wishlist"""
    # Find wishlist item
    query = select(Wishlist).where(
        and_(
            Wishlist.user_id == current_user.id,
            Wishlist.product_id == product_id
        )
    )
    result = await db.execute(query)
    wishlist_item = result.scalar_one_or_none()

    if not wishlist_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found in wishlist"
        )

    # Delete wishlist item
    await db.execute(
        delete(Wishlist).where(Wishlist.id == wishlist_item.id)
    )
    await db.commit()


@router.get("/check/{product_id}", response_model=WishlistCheckResponse)
async def check_in_wishlist(
    product_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if a product is in user's wishlist"""
    query = select(Wishlist).where(
        and_(
            Wishlist.user_id == current_user.id,
            Wishlist.product_id == product_id
        )
    )
    result = await db.execute(query)
    wishlist_item = result.scalar_one_or_none()

    if wishlist_item:
        return WishlistCheckResponse(
            in_wishlist=True,
            wishlist_item_id=wishlist_item.id
        )
    else:
        return WishlistCheckResponse(
            in_wishlist=False,
            wishlist_item_id=None
        )
