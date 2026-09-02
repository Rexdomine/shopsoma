"""Admin order management API endpoints"""
from fastapi import APIRouter, Depends, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload
from typing import Optional, List
from uuid import UUID
from datetime import datetime, date, timedelta
from decimal import Decimal
import logging
import csv
import io
import math

from app.api.dependencies import get_db, get_current_admin
from app.core.config import Settings, settings
from app.models.user import User
from app.models.order import Order, OrderItem, PaymentStatus, FulfillmentStatus
from app.models.vendor import Vendor
from app.models.address import Address
from app.models.vendor_pickup import VendorPickup, PickupStatus
from app.models.product import Product
from app.models.payment import Payment
from app.models.setting import Setting
from app.models.package_custody import HubPackage

logger = logging.getLogger(__name__)
from app.services.order_notification_service import OrderNotificationService
from app.services.websocket_manager import get_connection_manager
from app.schemas.admin_order import (
    OrderListItem,
    OrderDetail,
    OrderStats,
    PaginatedOrders,
    OrderStatusUpdate,
    ShippingInfoUpdate,
    PickupStatusUpdate,
    BulkStatusUpdate,
    RefundRequest,
    CancelOrderRequest,
    CustomerInfo,
    VendorInfo,
    AddressInfo,
    OrderItemDetail,
    PickupInfo,
    ReadyPackageInfo,
    ShadowQuoteResult,
)
from app.services.admin_shadow_quote import (
    run_admin_shadow_quote,
    ShadowQuoteConflictError,
    ShadowQuoteError,
)

router = APIRouter(prefix="/admin/orders", tags=["Admin Orders"])


def get_app_settings() -> Settings:
    return settings


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def build_customer_info(customer: User) -> CustomerInfo:
    """Build customer info from user"""
    try:
        # Parse full_name into first_name and last_name
        full_name_parts = (customer.full_name or "").split(" ", 1)
        first_name = full_name_parts[0] if len(full_name_parts) > 0 else None
        last_name = full_name_parts[1] if len(full_name_parts) > 1 else None

        return CustomerInfo(
            id=customer.id,
            first_name=first_name,
            last_name=last_name,
            email=customer.email,
            phone=customer.phone_number,  # User model has phone_number, not phone
        )
    except AttributeError as e:
        # Log detailed error for debugging
        raise ValueError(f"Error building customer info for user {customer.id}: Missing attribute {str(e)}") from e


def build_vendor_info(vendor: Vendor) -> VendorInfo:
    """Build vendor info"""
    try:
        # Get email from vendor.user relationship (if loaded)
        contact_email = None
        if hasattr(vendor, 'user') and vendor.user:
            contact_email = vendor.user.email

        return VendorInfo(
            id=vendor.id,
            business_name=vendor.business_name,
            contact_email=contact_email,
            contact_phone=vendor.business_phone,  # Vendor model has business_phone, not contact_phone
        )
    except AttributeError as e:
        # Log detailed error for debugging
        raise ValueError(f"Error building vendor info for vendor {vendor.id}: Missing attribute {str(e)}") from e


def build_address_info(address: Address) -> AddressInfo:
    """Build address info"""
    try:
        # Combine address_line1 and address_line2 into street_address
        street_address = address.address_line1
        if address.address_line2:
            street_address = f"{address.address_line1}, {address.address_line2}"

        return AddressInfo(
            id=address.id,
            full_name=address.full_name,
            phone=address.phone_number,  # Address model has phone_number, not phone
            street_address=street_address,  # Combine address_line1 and address_line2
            city=address.city,
            state=address.state,
            country=address.country,
            postal_code=address.postal_code or "",  # Handle nullable postal_code
        )
    except AttributeError as e:
        # Log detailed error for debugging
        raise ValueError(f"Error building address info for address {address.id}: Missing attribute {str(e)}") from e


def resolve_order_currency(order: Order) -> str:
    """Prefer the latest payment currency for admin display, then fall back to the order row."""
    payments = list(getattr(order, "payments", []) or [])
    if payments:
        latest_payment = max(
            payments,
            key=lambda payment: payment.created_at or datetime.min,
        )
        if latest_payment.currency:
            return latest_payment.currency.upper()

    return (getattr(order, "currency", None) or "NGN").upper()


def _normalize_currency(currency: Optional[str]) -> str:
    normalized = (currency or "NGN").upper()
    return normalized if normalized in {"NGN", "USD"} else "NGN"


async def _get_usd_to_ngn_rate(db: AsyncSession) -> Decimal:
    result = await db.execute(
        select(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
    )
    rate_setting = result.scalar_one_or_none()
    if not rate_setting:
        return Decimal("833")

    try:
        return Decimal(str(rate_setting.value))
    except (ArithmeticError, ValueError, TypeError):
        return Decimal("833")


def _convert_currency(amount: Decimal, from_currency: str, to_currency: str, usd_to_ngn_rate: Decimal) -> Decimal:
    source = _normalize_currency(from_currency)
    target = _normalize_currency(to_currency)

    if source == target:
        return amount
    if source == "USD" and target == "NGN":
        return (amount * usd_to_ngn_rate).quantize(Decimal("0.01"))
    if source == "NGN" and target == "USD":
        return (amount / usd_to_ngn_rate).quantize(Decimal("0.01"))
    return amount


def _should_use_product_currency_for_legacy_item(item: OrderItem, display_currency: str) -> bool:
    product = getattr(item, "product", None)
    if not product or not getattr(product, "currency", None):
        return False

    product_currency = _normalize_currency(product.currency)
    item_currency = _normalize_currency(getattr(item, "currency", None) or display_currency)
    if product_currency == display_currency or item_currency != display_currency:
        return False

    product_base_price = getattr(product, "base_price", None)
    if product_base_price is None:
        return False

    item_unit_price = Decimal(str(item.unit_price or "0"))
    item_subtotal = Decimal(str(item.subtotal or "0"))
    expected_subtotal = (Decimal(str(product_base_price)) * Decimal(item.quantity or 0)).quantize(Decimal("0.01"))

    return (
        item_unit_price.quantize(Decimal("0.01")) == Decimal(str(product_base_price)).quantize(Decimal("0.01"))
        or item_subtotal.quantize(Decimal("0.01")) == expected_subtotal
    )


def _resolve_admin_item_amounts(item: OrderItem, display_currency: str, usd_to_ngn_rate: Decimal) -> tuple[Decimal, Decimal, str]:
    source_currency = _normalize_currency(getattr(item, "currency", None) or display_currency)

    if _should_use_product_currency_for_legacy_item(item, display_currency):
        source_currency = _normalize_currency(item.product.currency)

    unit_price = _convert_currency(
        Decimal(str(item.unit_price or "0")),
        source_currency,
        display_currency,
        usd_to_ngn_rate,
    )
    subtotal = _convert_currency(
        Decimal(str(item.subtotal or "0")),
        source_currency,
        display_currency,
        usd_to_ngn_rate,
    )
    return unit_price, subtotal, display_currency


def _build_admin_order_item_detail(item: OrderItem, display_currency: str, usd_to_ngn_rate: Decimal) -> OrderItemDetail:
    unit_price, subtotal, item_currency = _resolve_admin_item_amounts(item, display_currency, usd_to_ngn_rate)
    return OrderItemDetail(
        id=item.id,
        product_id=item.product_id,
        product_title=item.product_title,
        product_image_url=(
            next((img.thumbnail_url or img.image_url for img in item.product.images if img.is_primary), None)
            or (item.product.images[0].thumbnail_url or item.product.images[0].image_url if item.product.images else None)
        ) if hasattr(item, 'product') and item.product else None,
        variant_details=item.variant_details,
        unit_price=unit_price,
        currency=item_currency,
        quantity=item.quantity,
        subtotal=subtotal,
        commission_rate=item.commission_rate,
        commission_amount=item.commission_amount,
        vendor_payout=item.vendor_payout,
        fulfillment_status=item.fulfillment_status,
        vendor=build_vendor_info(item.vendor),
    )


# ============================================================================
# ORDER LISTING & STATISTICS
# ============================================================================

@router.get("/stats", response_model=OrderStats)
async def get_order_statistics(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get order statistics for admin dashboard"""

    # Total orders and revenue
    total_query = select(
        func.count(Order.id).label("total_orders"),
        func.coalesce(func.sum(Order.total_amount), 0).label("total_revenue"),
    )
    total_result = await db.execute(total_query)
    total_row = total_result.one()

    # Orders by fulfillment status
    pending_count = await db.scalar(
        select(func.count(Order.id)).where(Order.fulfillment_status == FulfillmentStatus.ORDER_RECEIVED)
    ) or 0

    processing_count = await db.scalar(
        select(func.count(Order.id)).where(Order.fulfillment_status == FulfillmentStatus.PREPARING_FOR_PICKUP)
    ) or 0

    shipped_count = await db.scalar(
        select(func.count(Order.id)).where(Order.fulfillment_status == FulfillmentStatus.IN_TRANSIT)
    ) or 0

    delivered_count = await db.scalar(
        select(func.count(Order.id)).where(Order.fulfillment_status == FulfillmentStatus.DELIVERED)
    ) or 0

    cancelled_count = await db.scalar(
        select(func.count(Order.id)).where(Order.fulfillment_status == FulfillmentStatus.CANCELLED)
    ) or 0

    # Orders by payment status
    pending_payment = await db.scalar(
        select(func.count(Order.id)).where(Order.payment_status == PaymentStatus.PENDING)
    ) or 0

    failed_payment = await db.scalar(
        select(func.count(Order.id)).where(Order.payment_status == PaymentStatus.FAILED)
    ) or 0

    # Today's orders
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_stats = await db.execute(
        select(
            func.count(Order.id).label("orders_today"),
            func.coalesce(func.sum(Order.total_amount), 0).label("revenue_today"),
        ).where(Order.created_at >= today_start)
    )
    today_row = today_stats.one()

    # Average order value
    avg_order_value = Decimal("0.00")
    if total_row.total_orders > 0:
        avg_order_value = total_row.total_revenue / total_row.total_orders

    return OrderStats(
        total_orders=total_row.total_orders,
        total_revenue=total_row.total_revenue,
        pending_orders=pending_count,
        processing_orders=processing_count,
        shipped_orders=shipped_count,
        delivered_orders=delivered_count,
        cancelled_orders=cancelled_count,
        pending_payment=pending_payment,
        failed_payment=failed_payment,
        average_order_value=avg_order_value,
        orders_today=today_row.orders_today,
        revenue_today=today_row.revenue_today,
    )


@router.get("", response_model=PaginatedOrders)
async def list_orders(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by order number, customer name, or email"),
    payment_status: Optional[PaymentStatus] = Query(None, description="Filter by payment status"),
    fulfillment_status: Optional[FulfillmentStatus] = Query(None, description="Filter by fulfillment status"),
    vendor_id: Optional[str] = Query(None, description="Filter by vendor ID"),
    date_from: Optional[date] = Query(None, description="Filter orders from date"),
    date_to: Optional[date] = Query(None, description="Filter orders to date"),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all orders with filters and pagination"""

    # Build base query
    query = select(Order).options(
        selectinload(Order.customer),
        selectinload(Order.items).selectinload(OrderItem.vendor),
        selectinload(Order.payments),
    )

    # Apply filters
    filters = []

    if search:
        # Search by order number, customer name (full_name), or email
        search_term = f"%{search}%"
        filters.append(
            or_(
                Order.order_number.ilike(search_term),
                Order.customer.has(User.email.ilike(search_term)),
                Order.customer.has(User.full_name.ilike(search_term)),  # User model has full_name
            )
        )

    if payment_status:
        filters.append(Order.payment_status == payment_status)

    if fulfillment_status:
        filters.append(Order.fulfillment_status == fulfillment_status)

    if vendor_id:
        # Filter orders that have items from this vendor
        filters.append(Order.items.any(OrderItem.vendor_id == vendor_id))

    if date_from:
        filters.append(Order.created_at >= datetime.combine(date_from, datetime.min.time()))

    if date_to:
        # Include the entire day
        filters.append(Order.created_at <= datetime.combine(date_to, datetime.max.time()))

    if filters:
        query = query.where(and_(*filters))

    # Get total count
    count_query = select(func.count()).select_from(Order)
    if filters:
        count_query = count_query.where(and_(*filters))
    total = await db.scalar(count_query) or 0

    # Apply sorting and pagination
    query = query.order_by(desc(Order.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    result = await db.execute(query)
    orders = result.scalars().unique().all()

    # Build response
    orders_data = []
    for order in orders:
        display_currency = resolve_order_currency(order)
        # Count unique vendors and total items
        vendor_ids = set()
        item_count = 0
        for item in order.items:
            vendor_ids.add(item.vendor_id)
            item_count += item.quantity

        orders_data.append(
            OrderListItem(
                id=order.id,
                order_number=order.order_number,
                customer=build_customer_info(order.customer),
                total_amount=order.total_amount,
                currency=display_currency,
                payment_status=order.payment_status,
                fulfillment_status=order.fulfillment_status,
                created_at=order.created_at,
                vendor_count=len(vendor_ids),
                item_count=item_count,
            )
        )

    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedOrders(
        orders=orders_data,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{order_id}", response_model=OrderDetail)
async def get_order_detail(
    order_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get complete order details"""

    try:
        # Query order with all relationships
        query = select(Order).where(Order.id == order_id).options(
            selectinload(Order.customer),
            selectinload(Order.shipping_address),
            selectinload(Order.billing_address),
            selectinload(Order.items).selectinload(OrderItem.vendor).selectinload(Vendor.user),
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images),
            selectinload(Order.payments),
            selectinload(Order.pickups),
        )

        result = await db.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        # Build response with detailed error tracking
        display_currency = resolve_order_currency(order)
        usd_to_ngn_rate = await _get_usd_to_ngn_rate(db)
        ready_packages = (
            await db.execute(
                select(HubPackage)
                .where(HubPackage.order_id == order.id, HubPackage.state == "ready")
                .order_by(desc(HubPackage.ready_at), desc(HubPackage.created_at))
            )
        ).scalars().all()
        return OrderDetail(
        id=order.id,
        order_number=order.order_number,
        customer=build_customer_info(order.customer),
        shipping_address=build_address_info(order.shipping_address) if order.shipping_address else None,
        billing_address=build_address_info(order.billing_address) if order.billing_address else None,
        currency=display_currency,
        subtotal=order.subtotal,
        shipping_cost=order.shipping_cost,
        tax_amount=order.tax_amount,
        discount_amount=order.discount_amount,
        total_amount=order.total_amount,
        payment_status=order.payment_status,
        fulfillment_status=order.fulfillment_status,
        delivery_provider=order.delivery_provider,
        tracking_number=order.tracking_number,
        estimated_delivery_date=order.estimated_delivery_date,
        delivered_at=order.delivered_at,
        customer_notes=order.customer_notes,
        admin_notes=order.admin_notes,
        created_at=order.created_at,
        updated_at=order.updated_at,
        confirmed_at=order.confirmed_at,
        cancelled_at=order.cancelled_at,
        cancellation_reason=order.cancellation_reason,
        items=[
            _build_admin_order_item_detail(item, display_currency, usd_to_ngn_rate)
            for item in order.items
        ],
        pickups=[
            PickupInfo(
                id=pickup.id,
                status=pickup.status,
                scheduled_pickup_date=pickup.scheduled_pickup_date,
                actual_pickup_date=pickup.actual_pickup_date,
                pickup_window_start=pickup.pickup_window_start,
                pickup_window_end=pickup.pickup_window_end,
                logistics_partner=pickup.logistics_partner,
                courier_name=pickup.courier_name,
                rider_id=pickup.rider_id,
                tracking_number=pickup.tracking_number,
                qc_center_arrival_date=pickup.qc_center_arrival_date,
                qc_approved_date=pickup.qc_approved_date,
                qc_rejected_date=pickup.qc_rejected_date,
                qc_notes=pickup.qc_notes,
                vendor_notes=pickup.vendor_notes,
                admin_notes=pickup.admin_notes,
            )
            for pickup in order.pickups
        ],
        ready_packages=[
            ReadyPackageInfo(
                id=package.id,
                current_version=package.current_version,
                hub_id=package.hub_id,
                ready_at=package.ready_at,
            )
            for package in ready_packages
            if package.ready_at is not None
        ],
    )
    except ValueError as e:
        # Catch our custom ValueError from build_* functions with detailed error info
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error building order details: {str(e)}",
        )
    except AttributeError as e:
        # Catch any unexpected AttributeErrors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model attribute error in order {order_id}: {str(e)}. Please check model mappings.",
        )
    except Exception as e:
        # Catch all other errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error loading order details: {str(e)}",
        )


# ============================================================================
# ORDER UPDATES
# ============================================================================

@router.patch("/{order_id}/status", response_model=OrderDetail)
async def update_order_status(
    order_id: str,
    update_data: OrderStatusUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update order fulfillment status"""

    query = select(Order).where(Order.id == order_id).options(
        selectinload(Order.customer),
        selectinload(Order.shipping_address),
        selectinload(Order.billing_address),
        selectinload(Order.items).selectinload(OrderItem.vendor),
        selectinload(Order.payments),
        selectinload(Order.pickups),
    )

    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    # Store old status for notification
    old_status = order.fulfillment_status
    new_status = update_data.fulfillment_status

    # Update status
    order.fulfillment_status = new_status

    if update_data.admin_notes:
        if order.admin_notes:
            order.admin_notes += f"\n\n[{datetime.now().isoformat()}] {update_data.admin_notes}"
        else:
            order.admin_notes = f"[{datetime.now().isoformat()}] {update_data.admin_notes}"

    # Always refresh delivered_at when status is set to DELIVERED
    if new_status == FulfillmentStatus.DELIVERED:
        order.delivered_at = datetime.now()
        logger.info(
            "[Order Status] order=%s status=%s delivered_at=%s",
            order.order_number,
            new_status.value,
            order.delivered_at.isoformat(),
        )

    # Set cancelled_at timestamp if status is CANCELLED
    if new_status == FulfillmentStatus.CANCELLED and not order.cancelled_at:
        order.cancelled_at = datetime.now()

    # Update vendor pickups with pickup window data if provided
    if new_status == FulfillmentStatus.PICKUP_SCHEDULED and (update_data.pickup_window_start or update_data.pickup_window_end):
        from dateutil import parser

        # Get all pickups for this order
        pickup_query = select(VendorPickup).where(VendorPickup.order_id == order.id)
        pickup_result = await db.execute(pickup_query)
        pickups = pickup_result.scalars().all()

        # Update all pickups with the window data
        for pickup in pickups:
            if update_data.pickup_window_start:
                pickup.pickup_window_start = parser.isoparse(update_data.pickup_window_start)
            if update_data.pickup_window_end:
                pickup.pickup_window_end = parser.isoparse(update_data.pickup_window_end)
            if update_data.courier_name:
                pickup.courier_name = update_data.courier_name
            if update_data.rider_id:
                pickup.rider_id = update_data.rider_id

    await db.commit()
    await db.refresh(order)

    # Send notifications if status changed
    if old_status != new_status:
        notification_service = OrderNotificationService(db)
        try:
            await notification_service.notify_status_change(
                order=order,
                new_status=new_status,
                pickup_details=None  # Can be enhanced to include pickup window if available
            )
        except Exception as e:
            # Log error but don't fail the request
            print(f"Failed to send notifications for order {order.id}: {str(e)}")

        # Broadcast real-time update via WebSocket
        try:
            ws_manager = get_connection_manager()
            broadcast_data = {
                "status": order.status.value if hasattr(order, 'status') else None,
                "fulfillment_status": order.fulfillment_status.value,
                "payment_status": order.payment_status.value,
                "delivery_provider": order.delivery_provider,
                "tracking_number": order.tracking_number,
                "estimated_delivery_date": order.estimated_delivery_date.isoformat() if order.estimated_delivery_date else None,
                "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
                "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
                "updated_at": order.updated_at.isoformat()
            }

            print(f"[WebSocket] ===== BROADCASTING ORDER UPDATE =====")
            print(f"[WebSocket] Order ID: {order.id}")
            print(f"[WebSocket] Fulfillment Status: {order.fulfillment_status.value}")
            print(f"[WebSocket] Active Connections: {ws_manager.get_connection_count(str(order.id))}")
            print(f"[WebSocket] Broadcast Data: {broadcast_data}")

            await ws_manager.send_order_update(
                order_id=str(order.id),
                data=broadcast_data
            )

            print(f"[WebSocket] ✓ Broadcast complete for order {order.id}")
            print(f"[WebSocket] =====================================")
        except Exception as e:
            # Log error but don't fail the request
            print(f"[WebSocket] ✗ Failed to broadcast update for order {order.id}: {str(e)}")
            import traceback
            traceback.print_exc()

    # Return updated order
    return await get_order_detail(str(order.id), admin, db)


@router.patch("/{order_id}/shipping", response_model=OrderDetail)
async def update_shipping_info(
    order_id: str,
    update_data: ShippingInfoUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update shipping information"""

    query = select(Order).where(Order.id == order_id).options(
        selectinload(Order.customer),
        selectinload(Order.shipping_address),
        selectinload(Order.billing_address),
        selectinload(Order.items).selectinload(OrderItem.vendor),
        selectinload(Order.pickups),
    )

    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    # Update shipping fields
    if update_data.delivery_provider is not None:
        order.delivery_provider = update_data.delivery_provider

    if update_data.tracking_number is not None:
        order.tracking_number = update_data.tracking_number

    if update_data.estimated_delivery_date is not None:
        order.estimated_delivery_date = update_data.estimated_delivery_date

    if update_data.admin_notes:
        if order.admin_notes:
            order.admin_notes += f"\n\n[{datetime.now().isoformat()}] {update_data.admin_notes}"
        else:
            order.admin_notes = f"[{datetime.now().isoformat()}] {update_data.admin_notes}"

    await db.commit()
    await db.refresh(order)

    # Return updated order
    return await get_order_detail(str(order.id), admin, db)


@router.patch("/{order_id}/pickup/{pickup_id}", response_model=OrderDetail)
async def update_pickup_status(
    order_id: str,
    pickup_id: str,
    update_data: PickupStatusUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update pickup status and details"""

    # Get pickup
    pickup = await db.get(VendorPickup, pickup_id)

    if not pickup or str(pickup.order_id) != order_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pickup not found for this order",
        )

    # Update status if provided
    if update_data.pickup_status:
        pickup.status = update_data.pickup_status

        # Update timestamps based on status
        if update_data.pickup_status == PickupStatus.IN_TRANSIT and not pickup.actual_pickup_date:
            pickup.actual_pickup_date = datetime.now()
        elif update_data.pickup_status == PickupStatus.DELIVERED_TO_QC and not pickup.qc_center_arrival_date:
            pickup.qc_center_arrival_date = datetime.now()
        elif update_data.pickup_status == PickupStatus.QC_APPROVED and not pickup.qc_approved_date:
            pickup.qc_approved_date = datetime.now()
        elif update_data.pickup_status == PickupStatus.QC_REJECTED and not pickup.qc_rejected_date:
            pickup.qc_rejected_date = datetime.now()
        elif update_data.pickup_status == PickupStatus.COMPLETED and not pickup.completed_at:
            pickup.completed_at = datetime.now()
        elif update_data.pickup_status == PickupStatus.CANCELLED and not pickup.cancelled_at:
            pickup.cancelled_at = datetime.now()

    # Update other fields if provided
    if update_data.scheduled_pickup_date is not None:
        pickup.scheduled_pickup_date = update_data.scheduled_pickup_date

    if update_data.actual_pickup_date is not None:
        pickup.actual_pickup_date = update_data.actual_pickup_date

    if update_data.pickup_window_start is not None:
        pickup.pickup_window_start = update_data.pickup_window_start

    if update_data.pickup_window_end is not None:
        pickup.pickup_window_end = update_data.pickup_window_end

    if update_data.logistics_partner is not None:
        pickup.logistics_partner = update_data.logistics_partner

    if update_data.courier_name is not None:
        pickup.courier_name = update_data.courier_name

    if update_data.rider_id is not None:
        pickup.rider_id = update_data.rider_id

    if update_data.tracking_number is not None:
        pickup.tracking_number = update_data.tracking_number

    if update_data.qc_notes is not None:
        pickup.qc_notes = update_data.qc_notes

    if update_data.admin_notes:
        if pickup.admin_notes:
            pickup.admin_notes += f"\n\n[{datetime.now().isoformat()}] {update_data.admin_notes}"
        else:
            pickup.admin_notes = f"[{datetime.now().isoformat()}] {update_data.admin_notes}"

    await db.commit()

    # Return updated order
    return await get_order_detail(order_id, admin, db)


@router.patch("/bulk/status")
async def bulk_update_status(
    update_data: BulkStatusUpdate,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update order statuses"""

    # Get all orders
    query = select(Order).where(Order.id.in_(update_data.order_ids))
    result = await db.execute(query)
    orders = result.scalars().all()

    if not orders:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No orders found",
        )

    updated_count = 0
    for order in orders:
        previous_status = order.fulfillment_status
        order.fulfillment_status = update_data.fulfillment_status

        if update_data.admin_notes:
            note = f"[{datetime.now().isoformat()}] Bulk update: {update_data.admin_notes}"
            if order.admin_notes:
                order.admin_notes += f"\n\n{note}"
            else:
                order.admin_notes = note

        # Always refresh delivered_at when status is set to DELIVERED
        if update_data.fulfillment_status == FulfillmentStatus.DELIVERED:
            order.delivered_at = datetime.now()
            logger.info(
                "[Order Status] order=%s status=%s delivered_at=%s",
                order.order_number,
                update_data.fulfillment_status.value,
                order.delivered_at.isoformat(),
            )

        updated_count += 1

    await db.commit()

    return {
        "success": True,
        "updated_count": updated_count,
        "message": f"Successfully updated {updated_count} orders",
    }


# ============================================================================
# ORDER ACTIONS
# ============================================================================

@router.post("/{order_id}/shadow-quote", response_model=ShadowQuoteResult)
async def create_shadow_quote(
    order_id: str,
    package_id: str | None = None,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
):
    """Run an admin-only DHL sandbox shadow quote for a ready package."""

    try:
        parsed_order_id = UUID(order_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid order id",
        ) from exc

    if package_id is not None:
        try:
            parsed_package_id = UUID(package_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid package id",
            ) from exc
    else:
        parsed_package_id = None

    if not settings.checkout_capability_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Checkout capability fingerprinting is not configured",
        )

    pepper_version = settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION
    if pepper_version is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Checkout capability fingerprint version is not configured",
        )

    identity_key = settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER.get_secret_value().encode("utf-8")
    identity_key_version = f"checkout-capability-v{pepper_version}"

    try:
        return await run_admin_shadow_quote(
            db=db,
            order_id=parsed_order_id,
            admin=admin,
            settings=settings,
            identity_key=identity_key,
            identity_key_version=identity_key_version,
            ready_package_id=parsed_package_id,
        )
    except ShadowQuoteError as exc:
        detail = str(exc)
        status_code = status.HTTP_400_BAD_REQUEST
        if isinstance(exc, ShadowQuoteConflictError):
            status_code = status.HTTP_409_CONFLICT
        elif detail == "order not found":
            status_code = status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=status_code, detail=detail) from exc


@router.post("/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    cancel_data: CancelOrderRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an order"""

    query = select(Order).where(Order.id == order_id)
    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if order.fulfillment_status == FulfillmentStatus.CANCELLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order is already cancelled",
        )

    # Cancel order
    order.fulfillment_status = FulfillmentStatus.CANCELLED
    order.cancelled_at = datetime.now()
    order.cancellation_reason = cancel_data.cancellation_reason

    # Add admin notes
    note = f"[{datetime.now().isoformat()}] Order cancelled by admin"
    if cancel_data.admin_notes:
        note += f"\nNotes: {cancel_data.admin_notes}"

    if order.admin_notes:
        order.admin_notes += f"\n\n{note}"
    else:
        order.admin_notes = note

    # TODO: Process refund if requested
    # This would integrate with payment gateway

    await db.commit()

    return {
        "success": True,
        "message": "Order cancelled successfully",
        "order_id": str(order.id),
        "order_number": order.order_number,
    }


@router.post("/{order_id}/refund")
async def process_refund(
    order_id: str,
    refund_data: RefundRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Process order refund"""

    query = select(Order).where(Order.id == order_id)
    result = await db.execute(query)
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if order.payment_status != PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only refund paid orders",
        )

    # Calculate refund amount
    refund_amount = refund_data.refund_amount
    if refund_data.refund_type == "full":
        refund_amount = order.total_amount
    elif refund_amount > order.total_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refund amount cannot exceed order total",
        )

    # Update payment status
    order.payment_status = PaymentStatus.REFUNDED

    # Add admin notes
    note = f"[{datetime.now().isoformat()}] Refund processed: {refund_data.refund_type}"
    note += f"\nAmount: {refund_amount}"
    note += f"\nReason: {refund_data.reason}"
    if refund_data.admin_notes:
        note += f"\nAdmin notes: {refund_data.admin_notes}"

    if order.admin_notes:
        order.admin_notes += f"\n\n{note}"
    else:
        order.admin_notes = note

    # TODO: Process actual refund with payment gateway

    await db.commit()

    return {
        "success": True,
        "message": "Refund processed successfully",
        "order_id": str(order.id),
        "order_number": order.order_number,
        "refund_amount": float(refund_amount),
    }


# ============================================================================
# EXPORT
# ============================================================================

@router.get("/export/csv")
async def export_orders_csv(
    payment_status: Optional[PaymentStatus] = Query(None),
    fulfillment_status: Optional[FulfillmentStatus] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export orders to CSV"""

    # Build query
    query = select(Order).options(
        selectinload(Order.customer),
        selectinload(Order.items),
    )

    # Apply filters
    filters = []
    if payment_status:
        filters.append(Order.payment_status == payment_status)
    if fulfillment_status:
        filters.append(Order.fulfillment_status == fulfillment_status)
    if date_from:
        filters.append(Order.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        filters.append(Order.created_at <= datetime.combine(date_to, datetime.max.time()))

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(desc(Order.created_at))

    # Execute query
    result = await db.execute(query)
    orders = result.scalars().unique().all()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "Order Number",
        "Customer Name",
        "Customer Email",
        "Total Amount",
        "Payment Status",
        "Fulfillment Status",
        "Items Count",
        "Created At",
        "Delivered At",
    ])

    # Write data
    for order in orders:
        customer_name = f"{order.customer.first_name or ''} {order.customer.last_name or ''}".strip()
        item_count = sum(item.quantity for item in order.items)

        writer.writerow([
            order.order_number,
            customer_name,
            order.customer.email,
            float(order.total_amount),
            order.payment_status.value,
            order.fulfillment_status.value,
            item_count,
            order.created_at.isoformat(),
            order.delivered_at.isoformat() if order.delivered_at else "",
        ])

    # Return CSV file
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=orders_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        },
    )
