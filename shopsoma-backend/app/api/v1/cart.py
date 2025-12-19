from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from typing import Optional
from datetime import datetime
import uuid

from app.core.database import get_db
from app.models.cart import CartItem, Coupon
from app.models.product import Product, Variation, SizeStock
from app.schemas.cart import (
    CartItemCreate,
    CartItemUpdate,
    CartItemResponse,
    CartResponse,
    CartSummary,
    ApplyCouponRequest,
    ApplyCouponResponse,
)
from app.schemas.product import ProductResponse, ProductVariantResponse
from app.api.dependencies import get_optional_user
from app.models.user import User

router = APIRouter(prefix="/cart", tags=["cart"])

# Pricing configuration
TAX_RATE = 0.075  # 7.5% VAT
SHIPPING_FEE = 2000  # ₦2,000
FREE_SHIPPING_THRESHOLD = 50000  # ₦50,000

CART_ITEM_LOAD_OPTIONS = [
    selectinload(CartItem.product).selectinload(Product.images),
    selectinload(CartItem.product).selectinload(Product.variants),
    selectinload(CartItem.product).selectinload(Product.variations).selectinload(Variation.size_stocks),
    selectinload(CartItem.product).selectinload(Product.vendor),
    selectinload(CartItem.product).selectinload(Product.category),
]


def resolve_variant_response(
    product: Optional[Product],
    variant_id: Optional[str],
) -> Optional[ProductVariantResponse]:
    """Return a ProductVariantResponse from either variants or variations.

    Vendors create products using variations/size_stocks instead of legacy variants.
    This helper normalizes both shapes so cart responses always have a populated
    variant when a valid ID is provided.
    """
    if not product or not variant_id:
        return None

    # First, look for a legacy variant match
    for variant in product.variants or []:
        if str(variant.id) == str(variant_id):
            return ProductVariantResponse.model_validate(variant)

    # Fallback to vendor variations/size stocks
    for variation in product.variations or []:
        base_price = variation.price if variation.price is not None else product.base_price

        if str(variation.id) == str(variant_id):
            return ProductVariantResponse.model_validate({
                "id": variation.id,
                "product_id": product.id,
                "size": None,
                "color": variation.title,
                "color_hex": variation.color_hex,
                "price": base_price,
                "stock": 0,
                "sku": None,
                "is_available": bool(variation.is_active),
                "created_at": variation.created_at,
                "updated_at": variation.updated_at,
            })

        for size_stock in variation.size_stocks or []:
            if str(size_stock.id) == str(variant_id):
                return ProductVariantResponse.model_validate({
                    "id": size_stock.id,
                    "product_id": product.id,
                    "size": getattr(size_stock.size, "value", str(size_stock.size)),
                    "color": variation.title,
                    "color_hex": variation.color_hex,
                    "price": base_price,
                    "stock": size_stock.stock,
                    "sku": None,
                    "is_available": bool(variation.is_active) and size_stock.stock > 0,
                    "created_at": variation.created_at,
                    "updated_at": variation.updated_at,
                })

    return None


def cast_uuid(value: Optional[str]) -> Optional[uuid.UUID]:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def serialize_cart_item(cart_item: CartItem) -> CartItemResponse:
    product = cart_item.product
    variant_response = resolve_variant_response(product, str(cart_item.variant_id))
    product_response = ProductResponse.model_validate(product) if product else None

    return CartItemResponse(
        id=str(cart_item.id),
        product_id=str(cart_item.product_id),
        variant_id=str(cart_item.variant_id),
        quantity=cart_item.quantity,
        user_id=str(cart_item.user_id) if cart_item.user_id else None,
        session_id=cart_item.session_id,
        price=cart_item.price,
        subtotal=cart_item.price * cart_item.quantity,
        created_at=cart_item.created_at,
        updated_at=cart_item.updated_at,
        product=product_response,
        variant=variant_response
    )


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

    print(f"[Cart API] get_user_or_session_id: user_id={user_id}, received session_id={session_id}")

    if not user_id and not session_id:
        # Generate new session ID for guest users
        session_id = str(uuid.uuid4())
        print(f"[Cart API] get_user_or_session_id: WARNING - No session_id provided, generated new one: {session_id}")

    return user_id, session_id


async def fetch_cart_item_with_relations(
    db: AsyncSession,
    item_id: str,
) -> Optional[CartItem]:
    item_uuid = cast_uuid(item_id)
    if not item_uuid:
        return None
    query = select(CartItem).options(*CART_ITEM_LOAD_OPTIONS).where(CartItem.id == item_uuid)
    result = await db.execute(query)
    return result.scalar_one_or_none()


@router.get("", response_model=CartResponse)
async def get_cart(
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """Get user's cart"""
    user_id, sess_id = await get_user_or_session_id(current_user, session_id)
    user_uuid = cast_uuid(user_id)

    # Query cart items
    query = select(CartItem).options(*CART_ITEM_LOAD_OPTIONS)
    if user_uuid:
        query = query.where(CartItem.user_id == user_uuid)
    else:
        query = query.where(CartItem.session_id == sess_id)

    result = await db.execute(query)
    items = result.scalars().all()
    print(f"[Cart API] get_cart user={user_uuid} session={sess_id} items={len(items)}")

    summary = calculate_cart_summary(items)

    return CartResponse(
        items=[serialize_cart_item(item) for item in items],
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
    try:
        user_id, sess_id = await get_user_or_session_id(current_user, session_id)
        user_uuid = cast_uuid(user_id)
        print(f"[Cart API] add_to_cart: Using user_id={user_uuid}, session_id={sess_id}")

        # Verify product exists
        product_result = await db.execute(
            select(Product)
            .options(
                selectinload(Product.variants),
                selectinload(Product.variations).selectinload(Variation.size_stocks),
            )
            .where(Product.id == item_data.product_id)
        )
        product = product_result.scalar_one_or_none()

        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Get variant price
        # Handle products without variants (variant_id format: "default-{product_id}")
        variant_id_str = str(item_data.variant_id or "")
        print(
            f"[Cart API] add_to_cart: variant_id_str={variant_id_str}, product.variants count={len(product.variants) if product.variants else 0}, "
            f"variations count={len(product.variations) if product.variations else 0}"
        )

        if variant_id_str.startswith("default-"):
            # Product has no variants, use base price
            if not product.variants or len(product.variants) == 0:
                variant = None
                price = float(product.base_price)
                # For products without variants, set variant_id to None in DB
                item_data.variant_id = None
                print(f"[Cart API] add_to_cart: Using default variant, price={price}")
            else:
                raise HTTPException(status_code=404, detail="Product variant not found")
        else:
            variant_response = resolve_variant_response(product, item_data.variant_id)

            if not variant_response:
                raise HTTPException(status_code=404, detail="Product variant not found")

            price = float(getattr(variant_response, "price", product.base_price))

        # Check if item already exists (by product_id + variant_id + user/session)
        existing_query = select(CartItem).where(
            CartItem.product_id == item_data.product_id,
            CartItem.variant_id == item_data.variant_id
        )

        if user_uuid:
            existing_query = existing_query.where(CartItem.user_id == user_uuid)
        else:
            existing_query = existing_query.where(CartItem.session_id == sess_id)

        result = await db.execute(existing_query)
        existing_item = result.scalar_one_or_none()

        if existing_item:
            # Update quantity
            existing_item.quantity += item_data.quantity
            existing_item.updated_at = datetime.utcnow()
            await db.commit()
            refreshed_item = await fetch_cart_item_with_relations(db, str(existing_item.id))
            print(f"[Cart API] add_to_cart existing id={existing_item.id} qty={existing_item.quantity} user={user_uuid}")
            return serialize_cart_item(refreshed_item or existing_item)

        # Create new cart item with auto-generated UUID
        cart_item = CartItem(
            user_id=user_uuid,
            session_id=sess_id if not user_uuid else None,
            product_id=item_data.product_id,
            variant_id=item_data.variant_id,
            quantity=item_data.quantity,
            price=price
        )

        db.add(cart_item)
        await db.commit()
        await db.refresh(cart_item)

        cart_with_relations = await fetch_cart_item_with_relations(db, str(cart_item.id))
        print(f"[Cart API] add_to_cart created id={cart_item.id} qty={cart_item.quantity} user={user_uuid} session={cart_item.session_id}")

        return serialize_cart_item(cart_with_relations or cart_item)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Cart API] add_to_cart error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "code": "CART_DB_ERROR",
                "message": "We could not update your cart. Please refresh and try again."
            }
        )


@router.patch("/items/{item_id}", response_model=CartItemResponse)
async def update_cart_item(
    item_id: str,
    update_data: CartItemUpdate,
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """Update cart item quantity"""
    try:
        user_id, sess_id = await get_user_or_session_id(current_user, session_id)
        user_uuid = cast_uuid(user_id)
        item_uuid = cast_uuid(item_id)

        if not item_uuid:
            raise HTTPException(status_code=400, detail="Invalid cart item ID")

        # Find cart item
        query = select(CartItem).where(CartItem.id == item_uuid)
        if user_uuid:
            query = query.where(CartItem.user_id == user_uuid)
        else:
            query = query.where(CartItem.session_id == sess_id)

        result = await db.execute(query)
        cart_item = result.scalar_one_or_none()

        if not cart_item:
            raise HTTPException(status_code=404, detail="Cart item not found")

        cart_item.quantity = update_data.quantity
        cart_item.updated_at = datetime.utcnow()

        await db.commit()

        updated_item = await fetch_cart_item_with_relations(db, str(cart_item.id))
        print(f"[Cart API] update_cart_item id={cart_item.id} qty={cart_item.quantity} user={user_uuid}")

        return serialize_cart_item(updated_item or cart_item)

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Cart API] update_cart_item error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "code": "CART_UPDATE_ERROR",
                "message": "We could not update your cart. Please refresh and try again."
            }
        )


@router.delete("/items/{item_id}")
async def remove_from_cart(
    item_id: str,
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """Remove item from cart"""
    try:
        user_id, sess_id = await get_user_or_session_id(current_user, session_id)
        user_uuid = cast_uuid(user_id)
        item_uuid = cast_uuid(item_id)

        if not item_uuid:
            raise HTTPException(status_code=400, detail="Invalid cart item ID")

        # Delete cart item
        query = delete(CartItem).where(CartItem.id == item_uuid)
        if user_uuid:
            query = query.where(CartItem.user_id == user_uuid)
        else:
            query = query.where(CartItem.session_id == sess_id)

        result = await db.execute(query)
        await db.commit()

        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Cart item not found")

        return {"status": "success", "message": "Item removed from cart"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Cart API] remove_from_cart error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail={
                "success": False,
                "code": "CART_DELETE_ERROR",
                "message": "We could not remove the item from your cart. Please refresh and try again."
            }
        )


@router.delete("")
async def clear_cart(
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """Clear all items from cart"""
    user_id, sess_id = await get_user_or_session_id(current_user, session_id)
    user_uuid = cast_uuid(user_id)

    query = delete(CartItem)
    if user_uuid:
        query = query.where(CartItem.user_id == user_uuid)
    else:
        query = query.where(CartItem.session_id == sess_id)

    await db.execute(query)
    await db.commit()

    return {"status": "success", "message": "Cart cleared"}


@router.post("/merge-guest-cart", response_model=CartResponse)
async def merge_guest_cart(
    current_user: Optional[User] = Depends(get_optional_user),
    session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    Merge guest cart into authenticated user cart.
    Called after login to transfer guest session cart items to the user.
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_uuid = cast_uuid(str(current_user.id))
    print(f"[Cart API] merge_guest_cart: user_id={user_uuid}, session_id={session_id}")

    if not session_id:
        # No guest session to merge, just return user's cart
        print(f"[Cart API] merge_guest_cart: No session_id provided, returning user cart")
        return await get_cart(current_user, session_id, db)

    # Fetch guest cart items (by session_id, user_id must be NULL)
    guest_query = select(CartItem).options(*CART_ITEM_LOAD_OPTIONS).where(
        CartItem.session_id == session_id,
        CartItem.user_id.is_(None)
    )
    guest_result = await db.execute(guest_query)
    guest_items = guest_result.scalars().all()

    print(f"[Cart API] merge_guest_cart: Found {len(guest_items)} guest items for session {session_id}")

    if not guest_items:
        # No guest cart to merge, return user's existing cart
        print(f"[Cart API] merge_guest_cart: No guest items found, fetching user's existing cart")
        user_cart = await get_cart(current_user, session_id, db)
        print(f"[Cart API] merge_guest_cart: Returning user cart with {len(user_cart.items)} items")
        return user_cart

    # Fetch user's existing cart items
    user_query = select(CartItem).where(CartItem.user_id == user_uuid)
    user_result = await db.execute(user_query)
    user_items = user_result.scalars().all()

    # Create a map of user's cart: (product_id, variant_id) -> CartItem
    user_cart_map = {
        (str(item.product_id), str(item.variant_id)): item
        for item in user_items
    }

    # Process each guest cart item
    merged_count = 0
    transferred_count = 0
    guest_item_ids_to_delete = []

    for guest_item in guest_items:
        product_variant_key = (str(guest_item.product_id), str(guest_item.variant_id))

        if product_variant_key in user_cart_map:
            # User already has this item - merge quantities into existing user item
            user_item = user_cart_map[product_variant_key]
            user_item.quantity += guest_item.quantity
            user_item.updated_at = datetime.utcnow()
            merged_count += 1
            # Mark guest item for deletion since we merged its quantity into existing item
            guest_item_ids_to_delete.append(guest_item.id)
            print(f"[Cart API] merge_guest_cart: Merged {guest_item.quantity} into existing item {user_item.id}, new qty={user_item.quantity}")
        else:
            # User doesn't have this item - transfer ownership to user
            guest_item.user_id = user_uuid
            guest_item.session_id = None
            guest_item.updated_at = datetime.utcnow()
            transferred_count += 1
            print(f"[Cart API] merge_guest_cart: Transferred guest item {guest_item.id} to user")

    # Delete only the guest items that were merged (not the ones transferred)
    if guest_item_ids_to_delete:
        await db.execute(
            delete(CartItem).where(CartItem.id.in_(guest_item_ids_to_delete))
        )

    await db.commit()

    print(f"[Cart API] merge_guest_cart: Merged {merged_count} items, transferred {transferred_count} items")

    # Verify the transfer worked
    verify_query = select(CartItem).where(CartItem.user_id == user_uuid)
    verify_result = await db.execute(verify_query)
    final_user_items = verify_result.scalars().all()
    print(f"[Cart API] merge_guest_cart: After commit, user cart has {len(final_user_items)} items")

    # Return the updated user cart
    return await get_cart(current_user, session_id, db)


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
    user_uuid = cast_uuid(user_id)

    query = select(CartItem).options(*CART_ITEM_LOAD_OPTIONS)
    if user_uuid:
        query = query.where(CartItem.user_id == user_uuid)
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
            items=[serialize_cart_item(item) for item in items],
            summary=summary,
            last_updated=datetime.utcnow()
        )
    )
