"""Order management endpoints"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, func
from sqlalchemy.orm import selectinload
from uuid import UUID
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import secrets

from app.core.database import get_db
from app.models.user import User, UserRole
from app.models.order import Order, OrderItem, PaymentStatus, FulfillmentStatus
from app.models.product import Product, ProductVariant, ProductStatus
from app.models.address import Address
from app.models.shipping_rate import ShippingRate
from app.models.vendor import Vendor
from app.schemas.order import (
    OrderCreate,
    OrderUpdate,
    OrderResponse,
    OrderListResponse,
    OrderCancelRequest,
    OrderReviewRequest,
    OrderReviewResponse,
    OrderSummary,
)
from app.api.dependencies import get_current_active_user, get_optional_user
from app.services.email_service import email_service
from app.services.vendor_notification_service import VendorNotificationService
from app.services.account_claim import queue_account_claim_email

router = APIRouter(prefix="/orders", tags=["Orders"])
MIN_ORDER_AMOUNT_NGN = Decimal("60000.00")

# Simple promo code configuration (should eventually move to dedicated table/service)
PROMO_CODES = {
    "WELCOME10": {"type": "percentage", "value": Decimal("0.10")},
    "SAVE5000": {"type": "fixed_amount", "value": Decimal("5000")},
}


def calculate_promo_discount(promo_code: Optional[str], subtotal: Decimal):
    """Calculate promo discount based on configured codes."""
    if not promo_code:
        return Decimal("0.00"), None

    config = PROMO_CODES.get(promo_code.upper())
    if not config:
        return Decimal("0.00"), None

    discount = Decimal("0.00")
    promo_meta = {"code": promo_code.upper()}

    if config["type"] == "percentage":
        discount = (subtotal * config["value"]).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        promo_meta["discount_percent"] = int(config["value"] * 100)
        promo_meta["discount_amount"] = float(discount)
    else:
        discount = config["value"]
        promo_meta["discount_amount"] = float(discount)

    if discount > subtotal:
        discount = subtotal
        promo_meta["discount_amount"] = float(discount)

    return discount, promo_meta

# Tax rate (VAT 7.5% in Nigeria)
TAX_RATE = Decimal("0.075")


def generate_order_number() -> str:
    """Generate a unique order number"""
    timestamp = datetime.now().strftime("%Y%m%d")
    random_part = secrets.token_hex(4).upper()
    return f"SHP-{timestamp}-{random_part}"


async def send_vendor_order_notification(
    vendor_id: str,
    order_number: str,
    product_title: str,
    quantity: int,
    vendor_payout: float,
    scheduled_pickup_date: datetime
):
    """
    Background task to send vendor order notification email
    """
    from app.core.database import get_db_context

    async with get_db_context() as db:
        vendor_notification_service = VendorNotificationService(email_service)
        await vendor_notification_service.send_order_notification(
            db=db,
            vendor_id=vendor_id,
            order_number=order_number,
            product_title=product_title,
            quantity=quantity,
            vendor_payout=vendor_payout,
            scheduled_pickup_date=scheduled_pickup_date
        )


async def calculate_order_totals(
    items_data: list,
    shipping_cost: Decimal,
    discount_amount: Decimal = Decimal("0.00")
) -> dict:
    """Calculate order totals"""
    subtotal = sum(Decimal(str(item.get('subtotal', 0))) for item in items_data)
    tax_amount = (subtotal + shipping_cost) * TAX_RATE
    total_amount = subtotal + shipping_cost + tax_amount - discount_amount

    return {
        "subtotal": subtotal,
        "shipping_cost": shipping_cost,
        "tax_amount": tax_amount,
        "discount_amount": discount_amount,
        "total_amount": total_amount
    }


@router.post("/review", response_model=OrderReviewResponse)
async def review_order(
    review_data: OrderReviewRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Review an order before creation - calculates totals, validates items, finds shipping rate

    Returns order summary with:
    - Item details with pricing
    - Shipping options
    - Tax calculation
    - Total amount
    - Applied promotions (if any)

    Works for both authenticated users and guest checkout.
    For guest checkout, provide guest_address instead of shipping_address_id.
    """
    # Validate shipping address
    shipping_address = None
    guest_shipping_state = None
    guest_shipping_country = None

    if review_data.shipping_address_id:
        # Authenticated user with saved address
        address_query = select(Address).where(Address.id == review_data.shipping_address_id)

        # If user is authenticated, verify address ownership
        if current_user:
            address_query = address_query.where(Address.user_id == current_user.id)

        address_result = await db.execute(address_query)
        shipping_address = address_result.scalar_one_or_none()

        if not shipping_address:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shipping address not found"
            )
    elif review_data.guest_address:
        # Guest checkout with inline address
        guest_shipping_state = review_data.guest_address.state
        guest_shipping_country = review_data.guest_address.country
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either shipping_address_id or guest_address must be provided"
        )

    # Collect and validate items
    items_details = []
    subtotal = Decimal("0.00")

    for item in review_data.items:
        # Get product
        product_query = select(Product).options(
            selectinload(Product.variants),
            selectinload(Product.vendor)
        ).where(Product.id == item.product_id)

        product_result = await db.execute(product_query)
        product = product_result.scalar_one_or_none()

        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {item.product_id} not found"
            )

        if product.status != ProductStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product '{product.title}' is not available"
            )

        # Get variant if specified
        variant = None
        unit_price = product.base_price
        stock = product.total_stock
        variant_details = None

        if item.variant_id:
            variant_query = select(ProductVariant).where(ProductVariant.id == item.variant_id)
            variant_result = await db.execute(variant_query)
            variant = variant_result.scalar_one_or_none()

            if not variant or variant.product_id != product.id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Variant {item.variant_id} not found"
                )

            unit_price = variant.price
            stock = variant.stock
            variant_details = {
                "size": variant.size,
                "color": variant.color,
                "color_hex": variant.color_hex
            }

        # Check stock
        if stock < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for '{product.title}'. Available: {stock}"
            )

        item_subtotal = unit_price * item.quantity
        subtotal += item_subtotal

        items_details.append({
            "product_id": str(product.id),
            "product_title": product.title,
            "variant_id": str(variant.id) if variant else None,
            "variant_details": variant_details,
            "unit_price": float(unit_price),
            "quantity": item.quantity,
            "subtotal": float(item_subtotal),
            "vendor_name": product.vendor.business_name if product.vendor else "Shopsoma"
        })

    # Minimum order enforcement
    if subtotal < MIN_ORDER_AMOUNT_NGN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimum order amount is ₦60,000. Please add more items before checkout."
        )

    # Calculate shipping
    # Use either saved address or guest address for shipping calculation
    shipping_country = shipping_address.country if shipping_address else guest_shipping_country
    shipping_state = shipping_address.state if shipping_address else guest_shipping_state

    shipping_query = select(ShippingRate).where(
        and_(
            ShippingRate.is_active == True,
            ShippingRate.country == shipping_country,
            or_(
                ShippingRate.state == shipping_state,
                ShippingRate.state == None
            )
        )
    ).order_by(ShippingRate.priority.asc())

    shipping_result = await db.execute(shipping_query)
    shipping_rates = shipping_result.scalars().all()

    # Fallback: if no rates match filters but a specific rate was selected, try loading it directly
    if not shipping_rates and review_data.shipping_rate_id:
        direct_rate_query = select(ShippingRate).where(
            and_(
                ShippingRate.id == review_data.shipping_rate_id,
                ShippingRate.is_active == True
            )
        )
        direct_result = await db.execute(direct_rate_query)
        direct_rate = direct_result.scalar_one_or_none()
        if direct_rate:
            shipping_rates = [direct_rate]

    if not shipping_rates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No shipping available for {shipping_state}, {shipping_country}"
        )

    selected_rate = next((r for r in shipping_rates if r.is_default), shipping_rates[0])
    if review_data.shipping_rate_id:
        selected_rate = next((r for r in shipping_rates if r.id == review_data.shipping_rate_id), None) or selected_rate

    shipping_cost = selected_rate.base_rate

    # Calculate discount (if promo code provided)
    discount_amount, applied_promo = calculate_promo_discount(review_data.promo_code, subtotal)

    # Calculate totals
    tax_amount = (subtotal + shipping_cost) * TAX_RATE
    total_amount = subtotal + shipping_cost + tax_amount - discount_amount

    summary = OrderSummary(
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        tax_amount=tax_amount,
        discount_amount=discount_amount,
        total_amount=total_amount,
        items_count=sum(item.quantity for item in review_data.items),
        estimated_delivery_days=selected_rate.max_delivery_days
    )

    return OrderReviewResponse(
        summary=summary,
        items=items_details,
        shipping_rate={
            "id": str(selected_rate.id),
            "name": selected_rate.name,
            "description": selected_rate.description,
            "cost": float(selected_rate.base_rate),
            "min_days": selected_rate.min_delivery_days,
            "max_days": selected_rate.max_delivery_days
        },
        applied_promo=applied_promo
    )


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    order_data: OrderCreate,
    background_tasks: BackgroundTasks,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new order

    - **items**: List of order items (product_id, variant_id, quantity)
    - **shipping_address_id**: Shipping address ID
    - **billing_address_id**: Billing address ID (defaults to shipping)
    - **customer_notes**: Optional notes from customer
    - **promo_code**: Optional promo code

    The order is created with PENDING payment and fulfillment status.
    Works for both authenticated users and guest checkout.
    For guest checkout, provide guest_address and customer_email.
    """
    # Handle shipping address - either from ID or create from guest data
    shipping_address = None
    shipping_address_id = None
    billing_address_id = None
    customer_id_for_order = None

    if order_data.shipping_address_id:
        # Authenticated user with saved address
        shipping_addr_query = select(Address).where(Address.id == order_data.shipping_address_id)

        # If user is authenticated, verify address ownership
        if current_user:
            shipping_addr_query = shipping_addr_query.where(Address.user_id == current_user.id)

        shipping_result = await db.execute(shipping_addr_query)
        shipping_address = shipping_result.scalar_one_or_none()

        if not shipping_address:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shipping address not found"
            )

        shipping_address_id = shipping_address.id
        billing_address_id = order_data.billing_address_id or order_data.shipping_address_id
        customer_id_for_order = current_user.id if current_user else shipping_address.user_id

    elif order_data.guest_address:
        if not order_data.customer_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer email required for guest checkout"
            )

        user_result = await db.execute(
            select(User).where(User.email == order_data.customer_email)
        )
        guest_user = user_result.scalar_one_or_none()

        if not guest_user:
            guest_user = User(
                email=order_data.customer_email,
                full_name=order_data.guest_address.full_name,
                hashed_password=None,
                is_active=True,
                role=UserRole.CUSTOMER,
                is_guest_created=True
            )
            db.add(guest_user)
            await db.flush()
        else:
            if not guest_user.full_name and order_data.guest_address.full_name:
                guest_user.full_name = order_data.guest_address.full_name
            if not guest_user.hashed_password:
                guest_user.is_guest_created = True

        if not guest_user.hashed_password:
            queue_account_claim_email(guest_user, background_tasks)

        guest_addr = Address(
            user_id=guest_user.id,
            **order_data.guest_address.model_dump()
        )
        db.add(guest_addr)
        await db.flush()

        shipping_address = guest_addr
        shipping_address_id = guest_addr.id
        billing_address_id = guest_addr.id
        customer_id_for_order = guest_user.id

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either shipping_address_id or guest_address must be provided"
        )

    # Process and validate items
    order_items = []
    subtotal = Decimal("0.00")

    for item_data in order_data.items:
        # Get product with vendor
        product_query = select(Product).options(
            selectinload(Product.vendor)
        ).where(Product.id == item_data.product_id)

        product_result = await db.execute(product_query)
        product = product_result.scalar_one_or_none()

        if not product or product.status != ProductStatus.ACTIVE:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {item_data.product_id} not available"
            )

        # Get variant if specified
        variant = None
        unit_price = product.base_price
        stock = product.total_stock
        variant_details = None

        if item_data.variant_id:
            variant_query = select(ProductVariant).where(ProductVariant.id == item_data.variant_id)
            variant_result = await db.execute(variant_query)
            variant = variant_result.scalar_one_or_none()

            if not variant:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Variant {item_data.variant_id} not found"
                )

            unit_price = variant.price
            stock = variant.stock
            variant_details = {
                "size": variant.size,
                "color": variant.color,
                "color_hex": variant.color_hex
            }

        # Check stock
        if stock < item_data.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Insufficient stock for '{product.title}'"
            )

        item_subtotal = unit_price * item_data.quantity
        subtotal += item_subtotal

        # Calculate vendor commission (e.g., 15%)
        commission_rate = Decimal("0.15")
        commission_amount = item_subtotal * commission_rate
        vendor_payout = item_subtotal - commission_amount

        order_items.append({
            "product_id": product.id,
            "variant_id": variant.id if variant else None,
            "vendor_id": product.vendor_id,
            "product_title": product.title,
            "variant_details": variant_details,
            "unit_price": unit_price,
            "quantity": item_data.quantity,
            "subtotal": item_subtotal,
            "commission_rate": commission_rate,
            "commission_amount": commission_amount,
            "vendor_payout": vendor_payout
        })

    if subtotal < MIN_ORDER_AMOUNT_NGN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimum order amount is ₦60,000. Please add more items before checkout."
        )

    # Get shipping rate
    shipping_query = select(ShippingRate).where(
        and_(
            ShippingRate.is_active == True,
            ShippingRate.country == shipping_address.country,
            or_(
                ShippingRate.state == shipping_address.state,
                ShippingRate.state == None
            )
        )
    ).order_by(ShippingRate.priority.asc())

    shipping_result = await db.execute(shipping_query)
    shipping_rates = shipping_result.scalars().all()

    if not shipping_rates and order_data.shipping_rate_id:
        direct_rate_query = select(ShippingRate).where(
            and_(
                ShippingRate.id == order_data.shipping_rate_id,
                ShippingRate.is_active == True
            )
        )
        direct_result = await db.execute(direct_rate_query)
        direct_rate = direct_result.scalar_one_or_none()
        if direct_rate:
            shipping_rates = [direct_rate]

    if not shipping_rates:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No shipping available for this location"
        )

    selected_rate = next((r for r in shipping_rates if r.is_default), shipping_rates[0])
    if order_data.shipping_rate_id:
        selected_rate = next((r for r in shipping_rates if r.id == order_data.shipping_rate_id), None) or selected_rate

    shipping_cost = selected_rate.base_rate

    # Calculate discount
    discount_amount, _ = calculate_promo_discount(order_data.promo_code, subtotal)

    # Calculate totals
    tax_amount = (subtotal + shipping_cost) * TAX_RATE
    total_amount = subtotal + shipping_cost + tax_amount - discount_amount

    # Use the customer_id we determined earlier
    if not customer_id_for_order:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to determine customer for order"
        )

    # Create order
    new_order = Order(
        order_number=generate_order_number(),
        customer_id=customer_id_for_order,
        shipping_address_id=shipping_address_id,
        billing_address_id=billing_address_id,
        subtotal=subtotal,
        shipping_cost=shipping_cost,
        tax_amount=tax_amount,
        discount_amount=discount_amount,
        total_amount=total_amount,
        customer_notes=order_data.customer_notes,
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED
    )

    db.add(new_order)
    await db.flush()  # Get order ID

    # Create order items
    created_order_items = []
    for item_dict in order_items:
        order_item = OrderItem(
            order_id=new_order.id,
            **item_dict
        )
        db.add(order_item)
        created_order_items.append(order_item)

    await db.flush()  # Get order item IDs

    # Create vendor pickups and notifications for each order item
    from app.models import VendorPickup, VendorNotification, Vendor
    from app.models.vendor_pickup import OrderType, PickupStatus
    from datetime import datetime, timedelta

    for order_item in created_order_items:
        # Get vendor info
        vendor_result = await db.execute(
            select(Vendor).options(selectinload(Vendor.user)).where(Vendor.id == order_item.vendor_id)
        )
        vendor = vendor_result.scalar_one_or_none()

        if vendor:
            # Determine order type (default to RTW)
            order_type = OrderType.RTW
            estimated_days = None

            # Calculate scheduled pickup date (48 hours for RTW)
            scheduled_date = datetime.utcnow() + timedelta(hours=48)

            # Create vendor pickup
            pickup = VendorPickup(
                vendor_id=vendor.id,
                order_id=new_order.id,
                order_item_id=order_item.id,
                order_type=order_type,
                estimated_production_days=estimated_days,
                scheduled_pickup_date=scheduled_date,
                pickup_address=vendor.business_address,
                pickup_contact_name=vendor.user.full_name if vendor.user else None,
                pickup_contact_phone=vendor.business_phone,
                status=PickupStatus.SCHEDULED
            )
            db.add(pickup)

            # Create vendor notification
            notification = VendorNotification(
                vendor_id=vendor.id,
                notification_type="order_placed",
                title=f"New Order #{new_order.order_number}",
                message=f"You have received a new order for {order_item.product_title}. Pickup scheduled for {scheduled_date.strftime('%B %d, %Y at %I:%M %p')}.",
                order_id=new_order.id,
                data={
                    "order_number": new_order.order_number,
                    "product_title": order_item.product_title,
                    "quantity": order_item.quantity,
                    "vendor_payout": float(order_item.vendor_payout)
                }
            )
            db.add(notification)

            # Queue background task to send vendor notification email
            background_tasks.add_task(
                send_vendor_order_notification,
                str(vendor.id),
                new_order.order_number,
                order_item.product_title,
                order_item.quantity,
                float(order_item.vendor_payout),
                scheduled_date
            )

    # Update stock
    for item_data, item_dict in zip(order_data.items, order_items):
        if item_data.variant_id:
            await db.execute(
                update(ProductVariant)
                .where(ProductVariant.id == item_data.variant_id)
                .values(stock=ProductVariant.stock - item_data.quantity)
            )
        else:
            await db.execute(
                update(Product)
                .where(Product.id == item_data.product_id)
                .values(total_stock=Product.total_stock - item_data.quantity)
            )

    await db.commit()

    # Load order with all relationships
    order_query = select(Order).options(
        selectinload(Order.items),
        selectinload(Order.shipping_address),
        selectinload(Order.billing_address),
        selectinload(Order.customer)
    ).where(Order.id == new_order.id)

    result = await db.execute(order_query)
    loaded_order = result.scalar_one()

    # Send order confirmation email
    try:
        # Prepare items for email
        email_items = []
        for item in loaded_order.items:
            email_items.append({
                'product_name': item.product_title,
                'quantity': item.quantity,
                'price': float(item.unit_price),
                'subtotal': float(item.subtotal),
                'size': item.variant_details.get('size') if item.variant_details else None,
                'color': item.variant_details.get('color') if item.variant_details else None,
            })

        # Prepare shipping address for email
        shipping_addr_dict = {
            'full_name': loaded_order.shipping_address.full_name,
            'address_line_1': loaded_order.shipping_address.address_line1,
            'address_line_2': loaded_order.shipping_address.address_line2,
            'city': loaded_order.shipping_address.city,
            'state': loaded_order.shipping_address.state,
            'postal_code': loaded_order.shipping_address.postal_code,
            'country': loaded_order.shipping_address.country,
            'phone_number': loaded_order.shipping_address.phone_number,
        }

        await email_service.send_order_confirmation_email(
            email=loaded_order.customer.email,
            name=loaded_order.customer.full_name,
            order_number=loaded_order.order_number,
            order_date=loaded_order.created_at,
            items=email_items,
            subtotal=float(loaded_order.subtotal),
            shipping=float(loaded_order.shipping_cost),
            tax=float(loaded_order.tax_amount),
            total=float(loaded_order.total_amount),
            shipping_address=shipping_addr_dict
        )

        # Send admin notification email
        await email_service.send_admin_order_notification(
            order_number=loaded_order.order_number,
            customer_name=loaded_order.customer.full_name,
            customer_email=loaded_order.customer.email,
            order_date=loaded_order.created_at,
            items=email_items,
            subtotal=float(loaded_order.subtotal),
            shipping=float(loaded_order.shipping_cost),
            tax=float(loaded_order.tax_amount),
            total=float(loaded_order.total_amount),
            payment_status=loaded_order.payment_status.value,
            shipping_address=shipping_addr_dict
        )
    except Exception as e:
        # Log error but don't fail order creation if email fails
        print(f"Failed to send order confirmation email for order {loaded_order.order_number}: {e}")

    return loaded_order


@router.get("", response_model=OrderListResponse)
async def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: PaymentStatus = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get orders for the authenticated user
    """
    query = select(Order).where(Order.customer_id == current_user.id)

    if status:
        query = query.where(Order.payment_status == status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    query = query.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    query = query.options(selectinload(Order.items))

    result = await db.execute(query)
    orders = result.scalars().all()

    return OrderListResponse(
        orders=orders,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific order by ID

    Works for both authenticated users and guest checkout.
    Guests can view orders without authentication.
    """
    from app.models.product import ProductImage

    query = select(Order).options(
        selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images),
        selectinload(Order.shipping_address),
        selectinload(Order.billing_address)
    ).where(Order.id == order_id)

    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    # Verify ownership if user is authenticated (unless admin)
    if current_user:
        if current_user.role != UserRole.ADMIN and order.customer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this order"
            )

    # Add product image URLs to order items
    for item in order.items:
        if item.product and item.product.images:
            # Get the primary image or first image
            primary_image = next((img for img in item.product.images if img.is_primary), None)
            if not primary_image and item.product.images:
                primary_image = item.product.images[0]
            item.product_image_url = primary_image.image_url if primary_image else None
        else:
            item.product_image_url = None

    return order


@router.get("/{order_id}/tracking")
async def get_order_tracking(
    order_id: UUID,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get order tracking information

    Returns tracking details including order status, history, and amount.
    Works for both authenticated users and guest checkout.
    """
    query = select(Order).where(Order.id == order_id)
    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    # Verify ownership if user is authenticated (unless admin)
    if current_user:
        if current_user.role != UserRole.ADMIN and order.customer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this order"
            )

    # Generate tracking ID based on order number
    tracking_id = f"GB{order.order_number.replace('-', '')[-8:]}"

    # Map fulfillment status to tracking status (new 7-status system)
    # Matches frontend OrderStatus type in orderService.ts
    status_map = {
        FulfillmentStatus.ORDER_RECEIVED: "order_placed",
        FulfillmentStatus.PREPARING_FOR_PICKUP: "in_transit",
        FulfillmentStatus.PICKUP_SCHEDULED: "in_transit",
        FulfillmentStatus.PICKED_UP: "in_transit",
        FulfillmentStatus.IN_TRANSIT: "in_transit",
        FulfillmentStatus.OUT_FOR_DELIVERY: "out_for_delivery",
        FulfillmentStatus.DELIVERED: "delivered",
        FulfillmentStatus.DELIVERY_FAILED: "delivery_failed",
        FulfillmentStatus.RETURNED: "returned",
        FulfillmentStatus.CANCELLED: "cancelled",
    }

    current_status = status_map.get(order.fulfillment_status, "order_placed")

    # Build history based on order status (new 7-status system)
    history = []

    # Order placed
    if order.created_at:
        history.append({
            "status": "order_placed",
            "description": "Order confirmed by Shopsoma",
            "occurred_at": order.created_at.isoformat()
        })

    # In Transit (consolidates preparing/scheduled/picked_up/in_transit)
    if order.fulfillment_status in [
        FulfillmentStatus.PREPARING_FOR_PICKUP,
        FulfillmentStatus.PICKUP_SCHEDULED,
        FulfillmentStatus.PICKED_UP,
        FulfillmentStatus.IN_TRANSIT
    ]:
        history.append({
            "status": "in_transit",
            "description": "Order is in transit to you",
            "occurred_at": order.updated_at.isoformat()
        })

    # Out for Delivery
    if order.fulfillment_status == FulfillmentStatus.OUT_FOR_DELIVERY:
        history.append({
            "status": "out_for_delivery",
            "description": "Out for delivery to your address",
            "occurred_at": order.updated_at.isoformat()
        })

    # Delivered
    if order.fulfillment_status == FulfillmentStatus.DELIVERED and order.delivered_at:
        history.append({
            "status": "delivered",
            "description": "Package delivered successfully",
            "occurred_at": order.delivered_at.isoformat()
        })

    # Terminal states
    if order.fulfillment_status == FulfillmentStatus.DELIVERY_FAILED:
        history.append({
            "status": "delivery_failed",
            "description": "Delivery attempt failed",
            "occurred_at": order.updated_at.isoformat()
        })

    if order.fulfillment_status == FulfillmentStatus.RETURNED:
        history.append({
            "status": "returned",
            "description": "Order has been returned",
            "occurred_at": order.updated_at.isoformat()
        })

    if order.fulfillment_status == FulfillmentStatus.CANCELLED:
        history.append({
            "status": "cancelled",
            "description": "Order has been cancelled",
            "occurred_at": order.cancelled_at.isoformat() if order.cancelled_at else order.updated_at.isoformat()
        })

    return {
        "order_id": str(order.id),
        "order_number": order.order_number,
        "tracking_id": tracking_id,
        "amount": float(order.total_amount),
        "currency": "NGN",
        "updated_at": order.updated_at.isoformat(),
        "current_status": current_status,
        "history": history
    }


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    cancel_data: OrderCancelRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Cancel an order (only if not yet shipped)
    """
    query = select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    # Verify ownership
    if order.customer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to cancel this order"
        )

    # Check if order can be cancelled
    if order.fulfillment_status in [FulfillmentStatus.PICKED_UP, FulfillmentStatus.IN_TRANSIT, FulfillmentStatus.OUT_FOR_DELIVERY, FulfillmentStatus.DELIVERED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot cancel order that has been shipped or delivered"
        )

    if order.fulfillment_status == FulfillmentStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order is already cancelled"
        )

    # Cancel order
    order.fulfillment_status = FulfillmentStatus.CANCELLED
    order.cancelled_at = datetime.now()
    order.cancellation_reason = cancel_data.cancellation_reason

    # Restore stock
    for item in order.items:
        if item.variant_id:
            await db.execute(
                update(ProductVariant)
                .where(ProductVariant.id == item.variant_id)
                .values(stock=ProductVariant.stock + item.quantity)
            )
        else:
            await db.execute(
                update(Product)
                .where(Product.id == item.product_id)
                .values(total_stock=Product.total_stock + item.quantity)
            )

    await db.commit()
    await db.refresh(order)

    return order
