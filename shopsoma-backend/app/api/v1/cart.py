from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import Optional
from datetime import datetime
import uuid

from app.core.database import get_db
from app.models.cart import CartItem, Coupon
from app.models.product import Product
from app.schemas.cart import (
    CartItemCreate,
    CartItemUpdate,
    CartItemResponse,
    CartResponse,
    CartSummary,
    ApplyCouponRequest,
    ApplyCouponResponse,
)
from app.api.dependencies import get_optional_user
from app.models.user import User

router = APIRouter(prefix="/cart", tags=["cart"])

# Pricing configuration
TAX_RATE = 0.075  # 7.5% VAT
SHIPPING_FEE = 2000  # ₦2,000
FREE_SHIPPING_THRESHOLD = 50000  # ₦50,000


def calculate_cart_summary(items: list[CartItem], discount: float = 0) -> CartSummary:
    """Calculate cart summary with tax and shipping"""
    subtotal = sum(item.price * item.quantity for item in items)

    # Calculate shipping
    shipping = 0 if subtotal >= FREE_SHIPPING_THRESHOLD else SHIPPING_FEE

    # Calculate tax on (subtotal - discount)
    taxable_amount = max(0, subtotal - discount)
    tax = round(taxable_amount * TAX_RATE, 2)

    # Calculate total
    total = round(subtotal + shipping + tax - discount, 2)

    # Count items
    item_count = sum(item.quantity for item in items)

    return CartSummary(
        subtotal=subtotal,
        shipping=shipping,
        tax=tax,
        discount=discount,
        total=total,
        item_count=item_count
    )


async def get_user_or_session_id(
    current_user: Optional[User],
    session_id: Optional[str] = Header(None, alias="X-Session-ID")
) -> tuple[Optional[str], Optional[str]]:
    """Get user_id or session_id for cart identification"""
    user_id = str(current_user.id) if current_user else None

    if not user_id and not session_id:
        # Generate new session ID for guest users
        session_id = str(uuid.uuid4())

    return user_id, session_id


@router.get("", response_model=CartResponse)
async def get_cart(
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """Get user's cart"""
    user_id, sess_id = await get_user_or_session_id(current_user, session_id)

    # Query cart items
    query = select(CartItem)
    if user_id:
        query = query.where(CartItem.user_id == user_id)
    else:
        query = query.where(CartItem.session_id == sess_id)

    result = await db.execute(query)
    items = result.scalars().all()

    summary = calculate_cart_summary(items)

    return CartResponse(
        items=[CartItemResponse(**item.to_dict()) for item in items],
        summary=summary,
        last_updated=datetime.utcnow()
    )


@router.post("/items", response_model=CartItemResponse)
async def add_to_cart(
    item_data: CartItemCreate,
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """Add item to cart"""
    user_id, sess_id = await get_user_or_session_id(current_user, session_id)

    # Verify product exists
    product_result = await db.execute(
        select(Product).where(Product.id == item_data.product_id)
    )
    product = product_result.scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Get variant price
    variant = next(
        (v for v in product.variants if v.get("id") == item_data.variant_id),
        None
    )

    if not variant:
        raise HTTPException(status_code=404, detail="Product variant not found")

    price = variant.get("price", product.base_price)

    # Check if item already exists
    cart_item_id = f"{item_data.product_id}_{item_data.variant_id}"
    existing_query = select(CartItem).where(CartItem.id == cart_item_id)

    if user_id:
        existing_query = existing_query.where(CartItem.user_id == user_id)
    else:
        existing_query = existing_query.where(CartItem.session_id == sess_id)

    result = await db.execute(existing_query)
    existing_item = result.scalar_one_or_none()

    if existing_item:
        # Update quantity
        existing_item.quantity += item_data.quantity
        existing_item.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(existing_item)
        return CartItemResponse(**existing_item.to_dict())

    # Create new cart item
    cart_item = CartItem(
        id=cart_item_id,
        user_id=user_id,
        session_id=sess_id if not user_id else None,
        product_id=item_data.product_id,
        variant_id=item_data.variant_id,
        quantity=item_data.quantity,
        price=price
    )

    db.add(cart_item)
    await db.commit()
    await db.refresh(cart_item)

    return CartItemResponse(**cart_item.to_dict())


@router.patch("/items/{item_id}", response_model=CartItemResponse)
async def update_cart_item(
    item_id: str,
    update_data: CartItemUpdate,
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """Update cart item quantity"""
    user_id, sess_id = await get_user_or_session_id(current_user, session_id)

    # Find cart item
    query = select(CartItem).where(CartItem.id == item_id)
    if user_id:
        query = query.where(CartItem.user_id == user_id)
    else:
        query = query.where(CartItem.session_id == sess_id)

    result = await db.execute(query)
    cart_item = result.scalar_one_or_none()

    if not cart_item:
        raise HTTPException(status_code=404, detail="Cart item not found")

    cart_item.quantity = update_data.quantity
    cart_item.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(cart_item)

    return CartItemResponse(**cart_item.to_dict())


@router.delete("/items/{item_id}")
async def remove_from_cart(
    item_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """Remove item from cart"""
    user_id, sess_id = await get_user_or_session_id(current_user, session_id)

    # Delete cart item
    query = delete(CartItem).where(CartItem.id == item_id)
    if user_id:
        query = query.where(CartItem.user_id == user_id)
    else:
        query = query.where(CartItem.session_id == sess_id)

    result = await db.execute(query)
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Cart item not found")

    return {"status": "success", "message": "Item removed from cart"}


@router.delete("")
async def clear_cart(
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """Clear all items from cart"""
    user_id, sess_id = await get_user_or_session_id(current_user, session_id)

    query = delete(CartItem)
    if user_id:
        query = query.where(CartItem.user_id == user_id)
    else:
        query = query.where(CartItem.session_id == sess_id)

    await db.execute(query)
    await db.commit()

    return {"status": "success", "message": "Cart cleared"}


@router.post("/apply-coupon", response_model=ApplyCouponResponse)
async def apply_coupon(
    coupon_data: ApplyCouponRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """Apply coupon code to cart"""
    # Get cart
    user_id, sess_id = await get_user_or_session_id(current_user, session_id)

    query = select(CartItem)
    if user_id:
        query = query.where(CartItem.user_id == user_id)
    else:
        query = query.where(CartItem.session_id == sess_id)

    result = await db.execute(query)
    items = result.scalars().all()

    if not items:
        raise HTTPException(status_code=400, detail="Cart is empty")

    # Find coupon
    coupon_result = await db.execute(
        select(Coupon).where(
            Coupon.code == coupon_data.code.upper(),
            Coupon.is_active == 1
        )
    )
    coupon = coupon_result.scalar_one_or_none()

    if not coupon:
        return ApplyCouponResponse(
            is_valid=False,
            discount_amount=0,
            discount_type="fixed",
            message="Invalid coupon code"
        )

    # Check validity dates
    now = datetime.utcnow()
    if now < coupon.valid_from or now > coupon.valid_until:
        return ApplyCouponResponse(
            is_valid=False,
            discount_amount=0,
            discount_type=coupon.discount_type,
            message="Coupon has expired"
        )

    # Check usage limit
    if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
        return ApplyCouponResponse(
            is_valid=False,
            discount_amount=0,
            discount_type=coupon.discount_type,
            message="Coupon usage limit reached"
        )

    # Calculate subtotal
    subtotal = sum(item.price * item.quantity for item in items)

    # Check minimum purchase
    if coupon.min_purchase and subtotal < coupon.min_purchase:
        return ApplyCouponResponse(
            is_valid=False,
            discount_amount=0,
            discount_type=coupon.discount_type,
            message=f"Minimum purchase of ₦{coupon.min_purchase:,.0f} required"
        )

    # Calculate discount
    discount_amount = 0
    if coupon.discount_type == "percentage":
        discount_amount = subtotal * (coupon.discount_value / 100)
        if coupon.max_discount:
            discount_amount = min(discount_amount, coupon.max_discount)
    else:
        discount_amount = coupon.discount_value

    discount_amount = round(discount_amount, 2)

    # Calculate new cart summary
    summary = calculate_cart_summary(items, discount_amount)

    return ApplyCouponResponse(
        is_valid=True,
        discount_amount=discount_amount,
        discount_type=coupon.discount_type,
        message=f"Coupon applied: {coupon.discount_type == 'percentage' and f'{coupon.discount_value}% off' or f'₦{coupon.discount_value:,.0f} off'}",
        cart=CartResponse(
            items=[CartItemResponse(**item.to_dict()) for item in items],
            summary=summary,
            last_updated=datetime.utcnow()
        )
    )
