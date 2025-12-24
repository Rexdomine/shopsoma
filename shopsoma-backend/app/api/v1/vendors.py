"""Vendor API endpoints"""
from typing import List, Optional
from datetime import datetime, date, time, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc, exists
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.core.database import get_db
from app.api.dependencies import (
    get_current_user, get_vendor_profile, get_approved_vendor,
    get_kyc_submitted_vendor, get_current_admin
)
from app.models import (
    Vendor, User, VendorAsset, VendorPickup, VendorNotification,
    Order, OrderItem, Product, Payout, Wishlist
)
from app.models.vendor import KYCStatus
from app.schemas.vendor import (
    VendorOnboardingRequest, VendorResponse, VendorProfileUpdate,
    VendorKYCSubmission, VendorAssetCreate, VendorAssetResponse,
    VendorAssetUpdate, VendorPickupResponse, VendorPickupCreate,
    VendorPickupUpdate, VendorNotificationResponse, VendorNotificationMarkRead,
    VendorOrderResponse, VendorOrderItemResponse, VendorOrderItemUpdate, VendorPayoutResponse,
    VendorDashboardResponse, VendorDashboardMetrics, VendorPayoutSummary,
    VendorProductPerformance, VendorBrandInfoUpdate, VendorPayoutInfoUpdate,
    VendorEarningsSummary, VendorPayoutRequest,
    VendorAnalyticsSummary, VendorAnalyticsChartResponse, VendorAnalyticsStats
)

router = APIRouter(prefix="/vendor", tags=["Vendors"])


# ==================== VENDOR ONBOARDING & PROFILE ====================

@router.post("/onboard", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor_profile(
    vendor_data: VendorOnboardingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create vendor profile (onboarding)
    """
    # Check if user already has a vendor profile
    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    existing_vendor = result.scalar_one_or_none()

    if existing_vendor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a vendor profile"
        )

    # Create vendor
    vendor = Vendor(
        user_id=current_user.id,
        business_name=vendor_data.business_name,
        business_description=vendor_data.business_description,
        business_address=vendor_data.business_address,
        business_phone=vendor_data.business_phone,
        bank_name=vendor_data.bank_name,
        bank_account_number=vendor_data.bank_account_number,
        bank_account_name=vendor_data.bank_account_name,
        kyc_status=KYCStatus.PENDING,
        approved=False,
        commission_rate=12.5  # Default 12.5%
    )

    db.add(vendor)

    # Update user role to vendor
    current_user.role = "vendor"

    await db.commit()
    await db.refresh(vendor)

    return vendor


@router.get("/profile", response_model=VendorResponse)
async def get_vendor_profile_endpoint(
    vendor: Vendor = Depends(get_vendor_profile)
):
    """Get current vendor profile"""
    return vendor


@router.put("/profile", response_model=VendorResponse)
async def update_vendor_profile_endpoint(
    update_data: VendorProfileUpdate,
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """Update vendor profile"""
    update_dict = update_data.model_dump(exclude_unset=True)

    for field, value in update_dict.items():
        setattr(vendor, field, value)

    await db.commit()
    await db.refresh(vendor)

    return vendor


@router.put("/onboarding/brand-info", response_model=VendorResponse)
async def save_brand_info(
    brand_info: VendorBrandInfoUpdate,
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Save brand info during onboarding.
    Marks brand_info_completed as true if all required fields are filled.
    """
    from datetime import datetime

    # Update vendor with brand info
    vendor.business_phone = brand_info.business_phone
    vendor.business_description = brand_info.business_description
    vendor.business_address = brand_info.shipping_address
    vendor.logo_url = brand_info.logo_url
    vendor.returning_address = brand_info.returning_address
    vendor.open_days = brand_info.open_days
    vendor.open_hour = brand_info.open_hour
    vendor.close_hour = brand_info.close_hour

    # Mark brand info as completed
    vendor.brand_info_completed = True

    # Check if onboarding is complete (both brand and payout info)
    if vendor.brand_info_completed and vendor.payout_info_completed:
        vendor.is_onboarding = False
        vendor.onboarding_completed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(vendor)

    return vendor


@router.put("/onboarding/payout-info", response_model=VendorResponse)
async def save_payout_info(
    payout_info: VendorPayoutInfoUpdate,
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Save payout info during onboarding.
    Marks payout_info_completed as true if all required fields are filled.
    """
    from datetime import datetime

    # Update vendor with payout info
    vendor.bank_name = payout_info.bank_name
    vendor.bank_account_number = payout_info.account_number
    vendor.bank_account_name = payout_info.account_holder

    # Mark payout info as completed
    vendor.payout_info_completed = True

    # Check if onboarding is complete (both brand and payout info)
    if vendor.brand_info_completed and vendor.payout_info_completed:
        vendor.is_onboarding = False
        vendor.onboarding_completed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(vendor)

    return vendor


@router.post("/kyc/submit", response_model=VendorResponse)
async def submit_kyc_documents(
    kyc_data: VendorKYCSubmission,
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """Submit KYC documents"""
    from datetime import datetime

    vendor.kyc_document_type = kyc_data.kyc_document_type
    vendor.kyc_document_url = kyc_data.kyc_document_url
    vendor.kyc_status = KYCStatus.SUBMITTED
    vendor.kyc_submitted_at = datetime.utcnow()

    await db.commit()
    await db.refresh(vendor)

    return vendor


# ==================== VENDOR ASSETS ====================

@router.post("/assets", response_model=VendorAssetResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor_asset(
    asset_data: VendorAssetCreate,
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """Upload vendor asset (logo, banner, size chart)"""
    asset = VendorAsset(
        vendor_id=vendor.id,
        **asset_data.model_dump()
    )

    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    return asset


@router.get("/assets", response_model=List[VendorAssetResponse])
async def list_vendor_assets(
    asset_type: Optional[str] = Query(None, description="Filter by asset type: logo, banner, size_chart"),
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """List vendor assets"""
    query = select(VendorAsset).where(VendorAsset.vendor_id == vendor.id)

    if asset_type:
        query = query.where(VendorAsset.asset_type == asset_type)

    query = query.order_by(VendorAsset.display_order)

    result = await db.execute(query)
    assets = result.scalars().all()

    return assets


@router.get("/assets/{asset_id}", response_model=VendorAssetResponse)
async def get_vendor_asset(
    asset_id: UUID,
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """Get specific vendor asset"""
    result = await db.execute(
        select(VendorAsset).where(
            and_(
                VendorAsset.id == asset_id,
                VendorAsset.vendor_id == vendor.id
            )
        )
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )

    return asset


@router.put("/assets/{asset_id}", response_model=VendorAssetResponse)
async def update_vendor_asset(
    asset_id: UUID,
    update_data: VendorAssetUpdate,
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """Update vendor asset"""
    result = await db.execute(
        select(VendorAsset).where(
            and_(
                VendorAsset.id == asset_id,
                VendorAsset.vendor_id == vendor.id
            )
        )
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(asset, field, value)

    await db.commit()
    await db.refresh(asset)

    return asset


@router.delete("/assets/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_vendor_asset(
    asset_id: UUID,
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """Delete vendor asset"""
    result = await db.execute(
        select(VendorAsset).where(
            and_(
                VendorAsset.id == asset_id,
                VendorAsset.vendor_id == vendor.id
            )
        )
    )
    asset = result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )

    await db.delete(asset)
    await db.commit()


# ==================== VENDOR ORDERS ====================

@router.get("/orders", response_model=dict)
async def list_vendor_orders(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by fulfillment status"),
    search: Optional[str] = Query(None, description="Search orders by order number or customer name"),
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    List orders containing vendor's products
    """
    print(f"[list_vendor_orders] ENDPOINT REACHED - Vendor: {vendor.business_name}, Page: {page}, Search: '{search}'")

    # Base query - get distinct orders that have vendor's items
    query = select(Order).join(OrderItem).where(
        OrderItem.vendor_id == vendor.id
    ).distinct()

    # Filter by status
    if status_filter:
        query = query.where(Order.fulfillment_status == status_filter)

    # Search by order number or customer name
    if search:
        query = query.join(Order.customer).where(
            or_(
                Order.order_number.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(
        select(Order.id).join(OrderItem).where(
            OrderItem.vendor_id == vendor.id
        ).distinct().subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(desc(Order.created_at)).offset(offset).limit(page_size)

    # Execute with relationships loaded
    query = query.options(
        selectinload(Order.items),
        selectinload(Order.customer),
        selectinload(Order.shipping_address)
    )

    result = await db.execute(query)
    orders = result.scalars().all()

    # Filter items to only show vendor's items
    orders_data = []
    for order in orders:
        vendor_items = [item for item in order.items if item.vendor_id == vendor.id]

        # Serialize order items to dictionaries
        serialized_items = []
        for item in vendor_items:
            serialized_items.append({
                "id": str(item.id),
                "order_id": str(item.order_id),
                "product_id": str(item.product_id),
                "product_title": item.product_title,
                "variant_details": item.variant_details,
                "unit_price": float(item.unit_price),
                "quantity": item.quantity,
                "subtotal": float(item.subtotal),
                "commission_rate": float(item.commission_rate),
                "commission_amount": float(item.commission_amount),
                "vendor_payout": float(item.vendor_payout),
                "fulfillment_status": item.fulfillment_status.value,
                "created_at": item.created_at.isoformat(),
            })

        orders_data.append({
            "id": str(order.id),
            "order_number": order.order_number,
            "items": serialized_items,
            "customer_name": order.customer.full_name if order.customer else "Unknown",
            "customer_email": order.customer.email if order.customer else "Unknown",
            "shipping_address": {
                "address_line1": order.shipping_address.address_line1 if order.shipping_address else None,
                "city": order.shipping_address.city if order.shipping_address else None,
                "state": order.shipping_address.state if order.shipping_address else None,
                "country": order.shipping_address.country if order.shipping_address else None,
            } if order.shipping_address else None,
            "payment_status": order.payment_status.value,
            "fulfillment_status": order.fulfillment_status.value,
            "created_at": order.created_at.isoformat(),
            "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None
        })

    return {
        "orders": orders_data,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/orders/{order_id}", response_model=dict)
async def get_vendor_order(
    order_id: UUID,
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get specific order details (only vendor's items) with pickup/shipping information"""
    # Get order with product images
    result = await db.execute(
        select(Order).where(Order.id == order_id).options(
            selectinload(Order.items).selectinload(OrderItem.pickup),
            selectinload(Order.items).selectinload(OrderItem.product).selectinload(Product.images),
            selectinload(Order.customer),
            selectinload(Order.shipping_address)
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    # Check if vendor has items in this order
    vendor_items = [item for item in order.items if item.vendor_id == vendor.id]

    if not vendor_items:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this order"
        )

    # Serialize order items to dictionaries with pickup information
    serialized_items = []
    for item in vendor_items:
        # Serialize pickup information if available
        pickup_data = None
        if item.pickup:
            pickup_data = {
                "id": str(item.pickup.id),
                "order_type": item.pickup.order_type.value,
                "scheduled_pickup_date": item.pickup.scheduled_pickup_date.isoformat() if item.pickup.scheduled_pickup_date else None,
                "actual_pickup_date": item.pickup.actual_pickup_date.isoformat() if item.pickup.actual_pickup_date else None,
                "pickup_window_start": item.pickup.pickup_window_start.isoformat() if item.pickup.pickup_window_start else None,
                "pickup_window_end": item.pickup.pickup_window_end.isoformat() if item.pickup.pickup_window_end else None,
                "pickup_address": item.pickup.pickup_address,
                "courier_name": item.pickup.courier_name,
                "rider_id": item.pickup.rider_id,
                "logistics_partner": item.pickup.logistics_partner,
                "tracking_number": item.pickup.tracking_number,
                "status": item.pickup.status.value,
                "qc_center_arrival_date": item.pickup.qc_center_arrival_date.isoformat() if item.pickup.qc_center_arrival_date else None,
                "qc_approved_date": item.pickup.qc_approved_date.isoformat() if item.pickup.qc_approved_date else None,
                "qc_notes": item.pickup.qc_notes,
                "vendor_notes": item.pickup.vendor_notes,
                "created_at": item.pickup.created_at.isoformat() if item.pickup.created_at else None,
                "completed_at": item.pickup.completed_at.isoformat() if item.pickup.completed_at else None,
            }

        # Get product image (prefer thumbnail, fallback to primary image)
        product_image_url = None
        if item.product and item.product.images:
            # Try to find primary image first
            primary_image = next((img for img in item.product.images if img.is_primary), None)
            if primary_image:
                product_image_url = primary_image.thumbnail_url or primary_image.image_url
            # If no primary, use first image
            elif item.product.images:
                first_image = item.product.images[0]
                product_image_url = first_image.thumbnail_url or first_image.image_url

        serialized_items.append({
            "id": str(item.id),
            "order_id": str(item.order_id),
            "product_id": str(item.product_id),
            "product_title": item.product_title,
            "variant_details": item.variant_details,
            "unit_price": float(item.unit_price),
            "quantity": item.quantity,
            "subtotal": float(item.subtotal),
            "commission_rate": float(item.commission_rate),
            "commission_amount": float(item.commission_amount),
            "vendor_payout": float(item.vendor_payout),
            "fulfillment_status": item.fulfillment_status.value,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "pickup": pickup_data,
            "product_image_url": product_image_url,
        })

    return {
        "id": str(order.id),
        "order_number": order.order_number,
        "items": serialized_items,
        "vendor_business_name": vendor.business_name,
        "customer_name": order.customer.full_name if order.customer else "Unknown",
        "customer_email": order.customer.email if order.customer else "Unknown",
        "shipping_address": {
            "address_line1": order.shipping_address.address_line1 if order.shipping_address else None,
            "address_line2": order.shipping_address.address_line2 if order.shipping_address else None,
            "city": order.shipping_address.city if order.shipping_address else None,
            "state": order.shipping_address.state if order.shipping_address else None,
            "postal_code": order.shipping_address.postal_code if order.shipping_address else None,
            "country": order.shipping_address.country if order.shipping_address else None,
        } if order.shipping_address else None,
        "payment_status": order.payment_status.value,
        "fulfillment_status": order.fulfillment_status.value,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
        "customer_notes": order.customer_notes
    }


# NOTE: Vendors cannot update fulfillment status - only admin can do this
# Fulfillment status is managed by Shopsoma logistics team through admin panel


# ==================== VENDOR PICKUPS ====================

@router.get("/pickups", response_model=dict)
async def list_vendor_pickups(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by pickup status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """List vendor pickups"""
    query = select(VendorPickup).where(VendorPickup.vendor_id == vendor.id)

    if status_filter:
        query = query.where(VendorPickup.status == status_filter)

    # Get total count
    count_query = select(func.count()).select_from(
        select(VendorPickup.id).where(VendorPickup.vendor_id == vendor.id)
    )
    if status_filter:
        count_query = select(func.count()).where(
            and_(VendorPickup.vendor_id == vendor.id, VendorPickup.status == status_filter)
        )

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(desc(VendorPickup.created_at)).offset(offset).limit(page_size)

    result = await db.execute(query)
    pickups = result.scalars().all()

    return {
        "pickups": pickups,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/pickups/{pickup_id}", response_model=VendorPickupResponse)
async def get_vendor_pickup(
    pickup_id: UUID,
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get specific pickup details"""
    result = await db.execute(
        select(VendorPickup).where(
            and_(
                VendorPickup.id == pickup_id,
                VendorPickup.vendor_id == vendor.id
            )
        )
    )
    pickup = result.scalar_one_or_none()

    if not pickup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pickup not found"
        )

    return pickup


@router.put("/pickups/{pickup_id}", response_model=VendorPickupResponse)
async def update_vendor_pickup(
    pickup_id: UUID,
    update_data: VendorPickupUpdate,
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Update pickup information (vendor notes, contact info)"""
    result = await db.execute(
        select(VendorPickup).where(
            and_(
                VendorPickup.id == pickup_id,
                VendorPickup.vendor_id == vendor.id
            )
        )
    )
    pickup = result.scalar_one_or_none()

    if not pickup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pickup not found"
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(pickup, field, value)

    await db.commit()
    await db.refresh(pickup)

    return pickup


# ==================== VENDOR NOTIFICATIONS ====================

@router.get("/notifications", response_model=dict)
async def list_vendor_notifications(
    unread_only: bool = Query(False, description="Show only unread notifications"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """List vendor notifications"""
    query = select(VendorNotification).where(VendorNotification.vendor_id == vendor.id)

    if unread_only:
        query = query.where(VendorNotification.is_read == False)

    # Get total count
    count_query = select(func.count()).where(VendorNotification.vendor_id == vendor.id)
    if unread_only:
        count_query = count_query.where(VendorNotification.is_read == False)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(desc(VendorNotification.created_at)).offset(offset).limit(page_size)

    result = await db.execute(query)
    notifications = result.scalars().all()

    return {
        "notifications": notifications,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/notifications/unread-count", response_model=dict)
async def get_unread_notification_count(
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """Get count of unread notifications"""
    result = await db.execute(
        select(func.count()).where(
            and_(
                VendorNotification.vendor_id == vendor.id,
                VendorNotification.is_read == False
            )
        )
    )
    count = result.scalar() or 0

    return {"unread_count": count}


@router.post("/notifications/mark-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notifications_read(
    data: VendorNotificationMarkRead,
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """Mark notifications as read"""
    from datetime import datetime

    await db.execute(
        VendorNotification.__table__.update().where(
            and_(
                VendorNotification.vendor_id == vendor.id,
                VendorNotification.id.in_(data.notification_ids)
            )
        ).values(
            is_read=True,
            read_at=datetime.utcnow()
        )
    )

    await db.commit()


# ==================== VENDOR FINANCIALS ====================
def _parse_date(value: Optional[str], label: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {label}. Use YYYY-MM-DD."
        ) from exc


def _build_date_range(start_date: Optional[str], end_date: Optional[str]):
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")

    if start and end and start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be on or before end_date."
        )

    start_dt = datetime.combine(start, time.min) if start else None
    end_dt = datetime.combine(end, time.max) if end else None
    return start, end, start_dt, end_dt


def _resolve_date_range(
    start_date: Optional[str],
    end_date: Optional[str],
    default_days: int = 365
):
    start, end, start_dt, end_dt = _build_date_range(start_date, end_date)
    if not end_dt:
        end_dt = datetime.utcnow()
        end = end_dt.date()
    if not start_dt:
        start_dt = end_dt - timedelta(days=default_days)
        start = start_dt.date()
    return start, end, start_dt, end_dt


@router.get("/earnings/summary", response_model=VendorEarningsSummary)
async def get_vendor_earnings_summary(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor earnings summary"""
    from decimal import Decimal
    from datetime import timedelta
    from app.models.order import PaymentStatus
    from app.models.payment import PayoutStatus

    start, end, start_dt, end_dt = _build_date_range(start_date, end_date)
    previous_start_dt = None
    previous_end_dt = None
    if start_dt and end_dt:
        period_days = (end_dt.date() - start_dt.date()).days + 1
        previous_end_dt = start_dt - timedelta(days=1)
        previous_start_dt = previous_end_dt - timedelta(days=period_days - 1)

    payout_expr = func.coalesce(
        OrderItem.vendor_payout,
        OrderItem.subtotal - func.coalesce(OrderItem.commission_amount, 0)
    )
    delivered_filters = [
        OrderItem.vendor_id == vendor.id,
        Order.payment_status == PaymentStatus.PAID,
        or_(
            OrderItem.fulfillment_status == FulfillmentStatus.DELIVERED,
            Order.fulfillment_status == FulfillmentStatus.DELIVERED,
        ),
        Order.delivered_at.isnot(None),
    ]
    if start_dt:
        delivered_filters.append(Order.delivered_at >= start_dt)
    if end_dt:
        delivered_filters.append(Order.delivered_at <= end_dt)

    current_result = await db.execute(
        select(func.sum(payout_expr)).join(Order).where(and_(*delivered_filters))
    )
    current_earnings = current_result.scalar() or Decimal("0.00")

    expenses_result = await db.execute(
        select(func.sum(OrderItem.commission_amount)).join(Order).where(and_(*delivered_filters))
    )
    expenses = expenses_result.scalar() or Decimal("0.00")

    current_prev = None
    expenses_prev = None
    if previous_start_dt and previous_end_dt:
        prev_filters = [
            OrderItem.vendor_id == vendor.id,
            Order.payment_status == PaymentStatus.PAID,
            or_(
                OrderItem.fulfillment_status == FulfillmentStatus.DELIVERED,
                Order.fulfillment_status == FulfillmentStatus.DELIVERED,
            ),
            Order.delivered_at.isnot(None),
            Order.delivered_at >= previous_start_dt,
            Order.delivered_at <= previous_end_dt,
        ]
        prev_current_result = await db.execute(
            select(func.sum(payout_expr)).join(Order).where(and_(*prev_filters))
        )
        current_prev = prev_current_result.scalar() or Decimal("0.00")
        prev_expenses_result = await db.execute(
            select(func.sum(OrderItem.commission_amount)).join(Order).where(and_(*prev_filters))
        )
        expenses_prev = prev_expenses_result.scalar() or Decimal("0.00")

    projected_filters = [
        OrderItem.vendor_id == vendor.id,
        Order.payment_status == PaymentStatus.PAID,
        Order.delivered_at.is_(None),
    ]
    if start_dt:
        projected_filters.append(Order.created_at >= start_dt)
    if end_dt:
        projected_filters.append(Order.created_at <= end_dt)

    projected_result = await db.execute(
        select(func.sum(payout_expr)).join(Order).where(and_(*projected_filters))
    )
    projected_earnings = projected_result.scalar() or Decimal("0.00")

    projected_prev = None
    if previous_start_dt and previous_end_dt:
        prev_projected_filters = [
            OrderItem.vendor_id == vendor.id,
            Order.payment_status == PaymentStatus.PAID,
            Order.delivered_at.is_(None),
            Order.created_at >= previous_start_dt,
            Order.created_at <= previous_end_dt,
        ]
        prev_projected_result = await db.execute(
            select(func.sum(payout_expr)).join(Order).where(and_(*prev_projected_filters))
        )
        projected_prev = prev_projected_result.scalar() or Decimal("0.00")

    def pct_change(current: Decimal, previous: Optional[Decimal]) -> Optional[float]:
        if previous is None or previous == 0:
            return None
        return float(((current - previous) / previous) * 100)

    return VendorEarningsSummary(
        current_earnings=float(current_earnings),
        projected_earnings=float(projected_earnings),
        expenses=float(expenses),
        current_earnings_change_pct=pct_change(current_earnings, current_prev),
        projected_earnings_change_pct=pct_change(projected_earnings, projected_prev),
        expenses_change_pct=pct_change(expenses, expenses_prev),
        start_date=start,
        end_date=end
    )


@router.get("/earnings/items", response_model=dict)
async def get_vendor_earnings_items(
    view: str = Query("products", description="View mode: products or orders"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search by product title or order number"),
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor earnings items by products or orders"""
    from decimal import Decimal
    from app.models.order import PaymentStatus

    if view not in {"products", "orders"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="view must be either 'products' or 'orders'."
        )

    _, _, start_dt, end_dt = _build_date_range(start_date, end_date)
    hold_days = await _get_payout_hold_days(db)
    today = datetime.utcnow().date()

    payout_expr = func.coalesce(
        OrderItem.vendor_payout,
        OrderItem.subtotal - func.coalesce(OrderItem.commission_amount, 0)
    )
    delivered_filters = [
        OrderItem.vendor_id == vendor.id,
        Order.payment_status == PaymentStatus.PAID,
        or_(
            OrderItem.fulfillment_status == FulfillmentStatus.DELIVERED,
            Order.fulfillment_status == FulfillmentStatus.DELIVERED,
        ),
        Order.delivered_at.isnot(None),
    ]
    if start_dt:
        delivered_filters.append(Order.delivered_at >= start_dt)
    if end_dt:
        delivered_filters.append(Order.delivered_at <= end_dt)

    completed_payouts_result = await db.execute(
        select(func.sum(Payout.payout_amount)).where(
            and_(
                Payout.vendor_id == vendor.id,
                Payout.status == PayoutStatus.COMPLETED
            )
        )
    )
    completed_payouts = completed_payouts_result.scalar() or Decimal("0.00")

    if view == "products":
        payout_value = payout_expr.label("payout_value")
        cumulative_payout = func.sum(payout_expr).over(
            order_by=[Order.delivered_at.asc(), OrderItem.id.asc()]
        ).label("cumulative_payout")
        query = select(
            OrderItem,
            Order.order_number,
            Order.delivered_at,
            Order.fulfillment_status,
            payout_value,
            cumulative_payout
        ).join(Order).where(
            and_(*delivered_filters)
        )

        if search:
            query = query.where(
                or_(
                    Order.order_number.ilike(f"%{search}%"),
                    OrderItem.product_title.ilike(f"%{search}%")
                )
            )

        count_base = select(OrderItem.id).join(Order).where(and_(*delivered_filters))
        if search:
            count_base = count_base.where(
                or_(
                    Order.order_number.ilike(f"%{search}%"),
                    OrderItem.product_title.ilike(f"%{search}%")
                )
            )
        count_result = await db.execute(
            select(func.count()).select_from(count_base.subquery())
        )
        total = count_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.options(
            selectinload(OrderItem.product).selectinload(Product.images)
        ).order_by(desc(Order.delivered_at)).offset(offset).limit(page_size)

        result = await db.execute(query)
        rows = result.all()

        items = []
        for item, order_number, delivered_at, fulfillment_status, payout_amount, cumulative_amount in rows:
            product_image_url = None
            if item.product and item.product.images:
                primary_image = next((img for img in item.product.images if img.is_primary), None)
                if primary_image:
                    product_image_url = primary_image.thumbnail_url or primary_image.image_url
                else:
                    first_image = item.product.images[0]
                    product_image_url = first_image.thumbnail_url or first_image.image_url

            payout_status = "paid_out" if cumulative_amount and cumulative_amount <= completed_payouts else "available"
            withdraw_available_at = None
            withdraw_days_left = None
            withdraw_available = False
            if delivered_at:
                withdraw_available_at = delivered_at + timedelta(days=hold_days)
                withdraw_days_left = max(0, (withdraw_available_at.date() - today).days)
                withdraw_available = withdraw_days_left == 0
            items.append({
                "id": str(item.id),
                "order_id": str(item.order_id),
                "product_id": str(item.product_id),
                "order_number": order_number,
                "product_title": item.product_title,
                "product_image_url": product_image_url,
                "unit_price": float(item.unit_price),
                "quantity": item.quantity,
                "commission_amount": float(item.commission_amount),
                "vendor_payout": float(payout_amount or item.vendor_payout or 0),
                "payout_status": payout_status,
                "status": fulfillment_status.value if hasattr(fulfillment_status, "value") else str(fulfillment_status),
                "delivered_at": delivered_at.isoformat() if delivered_at else None,
                "withdraw_available": withdraw_available,
                "withdraw_days_left": withdraw_days_left,
                "withdraw_available_at": withdraw_available_at.isoformat() if withdraw_available_at else None,
            })

        return {
            "view": "products",
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }

    orders_query = select(Order).join(OrderItem).where(and_(*delivered_filters)).distinct()
    if search:
        orders_query = orders_query.where(
            or_(
                Order.order_number.ilike(f"%{search}%"),
                OrderItem.product_title.ilike(f"%{search}%")
            )
        )

    count_query = select(func.count()).select_from(
        select(Order.id).join(OrderItem).where(and_(*delivered_filters)).where(
            or_(
                Order.order_number.ilike(f"%{search}%"),
                OrderItem.product_title.ilike(f"%{search}%")
            )
        ).distinct().subquery() if search else
        select(Order.id).join(OrderItem).where(and_(*delivered_filters)).distinct().subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    orders_query = orders_query.order_by(desc(Order.delivered_at)).offset(offset).limit(page_size)
    orders_query = orders_query.options(selectinload(Order.items))

    result = await db.execute(orders_query)
    orders = result.scalars().all()

    order_payout_status = {}
    if orders:
        cumulative_items = select(
            OrderItem.id.label("item_id"),
            OrderItem.order_id.label("order_id"),
            func.sum(payout_expr).over(
                order_by=[Order.delivered_at.asc(), OrderItem.id.asc()]
            ).label("cumulative_payout")
        ).join(Order).where(and_(*delivered_filters)).subquery()

        paid_out_counts = select(
            cumulative_items.c.order_id,
            func.count().label("paid_out_count")
        ).where(
            cumulative_items.c.cumulative_payout <= completed_payouts
        ).group_by(cumulative_items.c.order_id).subquery()

        total_counts = select(
            OrderItem.order_id.label("order_id"),
            func.count().label("total_count")
        ).join(Order).where(and_(*delivered_filters)).group_by(OrderItem.order_id).subquery()

        payout_status_result = await db.execute(
            select(
                total_counts.c.order_id,
                total_counts.c.total_count,
                func.coalesce(paid_out_counts.c.paid_out_count, 0).label("paid_out_count")
            ).outerjoin(
                paid_out_counts,
                paid_out_counts.c.order_id == total_counts.c.order_id
            )
        )

        for row in payout_status_result:
            order_id = row.order_id
            order_payout_status[str(order_id)] = (
                "paid_out" if row.paid_out_count >= row.total_count else "available"
            )

    items = []
    for order in orders:
        vendor_items = [item for item in order.items if item.vendor_id == vendor.id]
        total_quantity = sum(item.quantity for item in vendor_items)
        total_commission = sum((item.commission_amount or Decimal("0.00")) for item in vendor_items)
        total_payout = sum((item.vendor_payout or Decimal("0.00")) for item in vendor_items)
        withdraw_available_at = None
        withdraw_days_left = None
        withdraw_available = False
        if order.delivered_at:
            withdraw_available_at = order.delivered_at + timedelta(days=hold_days)
            withdraw_days_left = max(0, (withdraw_available_at.date() - today).days)
            withdraw_available = withdraw_days_left == 0
        items.append({
            "id": str(order.id),
            "order_number": order.order_number,
            "items": [item.product_title for item in vendor_items],
            "total_quantity": total_quantity,
            "total_commission": float(total_commission),
            "total_payout": float(total_payout),
            "status": order.fulfillment_status.value,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "payout_status": order_payout_status.get(str(order.id)),
            "withdraw_available": withdraw_available,
            "withdraw_days_left": withdraw_days_left,
            "withdraw_available_at": withdraw_available_at.isoformat() if withdraw_available_at else None,
        })

    return {
        "view": "orders",
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/analytics/summary", response_model=VendorAnalyticsSummary)
async def get_vendor_analytics_summary(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor analytics revenue summary"""
    from decimal import Decimal

    start, end, start_dt, end_dt = _resolve_date_range(start_date, end_date)
    period_days = (end_dt.date() - start_dt.date()).days + 1

    base_filters = [
        OrderItem.vendor_id == vendor.id,
        Order.payment_status == PaymentStatus.PAID,
        Order.created_at >= start_dt,
        Order.created_at <= end_dt,
    ]

    totals_result = await db.execute(
        select(
            func.sum(OrderItem.subtotal),
            func.sum(OrderItem.commission_amount)
        ).join(Order).where(and_(*base_filters))
    )
    total_revenue, total_commission = totals_result.one()
    total_revenue = total_revenue or Decimal("0.00")
    total_commission = total_commission or Decimal("0.00")

    commission_rate_pct = None
    if total_revenue > 0:
        commission_rate_pct = float((total_commission / total_revenue) * 100)

    previous_end_dt = start_dt - timedelta(days=1)
    previous_start_dt = previous_end_dt - timedelta(days=period_days - 1)
    prev_result = await db.execute(
        select(func.sum(OrderItem.subtotal))
        .join(Order)
        .where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.payment_status == PaymentStatus.PAID,
                Order.created_at >= previous_start_dt,
                Order.created_at <= previous_end_dt,
            )
        )
    )
    prev_revenue = prev_result.scalar() or Decimal("0.00")

    revenue_change_pct = None
    if prev_revenue > 0:
        revenue_change_pct = float(((total_revenue - prev_revenue) / prev_revenue) * 100)

    return VendorAnalyticsSummary(
        total_revenue=float(total_revenue),
        revenue_change_pct=revenue_change_pct,
        commission_rate_pct=commission_rate_pct,
        start_date=start,
        end_date=end
    )


@router.get("/analytics/chart", response_model=VendorAnalyticsChartResponse)
async def get_vendor_analytics_chart(
    range: str = Query("1Y", description="Chart range: 1D, 7D, 1M, 1Y"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor analytics chart data"""
    allowed_ranges = {"1D", "7D", "1M", "1Y"}
    if range not in allowed_ranges:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="range must be one of 1D, 7D, 1M, 1Y."
        )

    if start_date or end_date:
        _, _, start_dt, end_dt = _build_date_range(start_date, end_date)
        if not start_dt or not end_dt:
            start_dt = datetime.utcnow() - timedelta(days=365)
            end_dt = datetime.utcnow()
    else:
        end_dt = datetime.utcnow()
        if range == "1D":
            start_dt = end_dt - timedelta(days=1)
        elif range == "7D":
            start_dt = end_dt - timedelta(days=7)
        elif range == "1M":
            start_dt = end_dt - timedelta(days=30)
        else:
            start_dt = end_dt - timedelta(days=365)

    query = select(
        Order.created_at,
        OrderItem.subtotal,
        OrderItem.commission_amount
    ).join(Order).where(
        and_(
            OrderItem.vendor_id == vendor.id,
            Order.payment_status == PaymentStatus.PAID,
            Order.created_at >= start_dt,
            Order.created_at <= end_dt,
        )
    )
    result = await db.execute(query)
    rows = result.all()

    def bucket_key(value: datetime) -> datetime:
        if range == "1D":
            return value.replace(minute=0, second=0, microsecond=0)
        if range in {"7D", "1M"}:
            return datetime(value.year, value.month, value.day)
        return datetime(value.year, value.month, 1)

    buckets: dict[datetime, dict] = {}
    for created_at, subtotal, commission_amount in rows:
        key = bucket_key(created_at)
        if key not in buckets:
            buckets[key] = {"revenue": 0.0, "expenses": 0.0}
        buckets[key]["revenue"] += float(subtotal or 0)
        buckets[key]["expenses"] += float(commission_amount or 0)

    points = []
    cursor = bucket_key(start_dt)
    if range == "1D":
        step = timedelta(hours=1)
        while cursor <= end_dt:
            data = buckets.get(cursor, {"revenue": 0.0, "expenses": 0.0})
            points.append({
                "timestamp": cursor,
                "revenue": data["revenue"],
                "expenses": data["expenses"],
            })
            cursor += step
    elif range in {"7D", "1M"}:
        step = timedelta(days=1)
        while cursor <= end_dt:
            data = buckets.get(cursor, {"revenue": 0.0, "expenses": 0.0})
            points.append({
                "timestamp": cursor,
                "revenue": data["revenue"],
                "expenses": data["expenses"],
            })
            cursor += step
    else:
        while cursor <= end_dt:
            data = buckets.get(cursor, {"revenue": 0.0, "expenses": 0.0})
            points.append({
                "timestamp": cursor,
                "revenue": data["revenue"],
                "expenses": data["expenses"],
            })
            next_month = (cursor.month % 12) + 1
            next_year = cursor.year + (1 if cursor.month == 12 else 0)
            cursor = datetime(next_year, next_month, 1)

    return VendorAnalyticsChartResponse(
        range=range,
        start_date=start_dt,
        end_date=end_dt,
        points=points
    )


@router.get("/analytics/stats", response_model=VendorAnalyticsStats)
async def get_vendor_analytics_stats(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor analytics stats"""
    start, end, start_dt, end_dt = _resolve_date_range(start_date, end_date)

    order_filters = [
        OrderItem.vendor_id == vendor.id,
        Order.payment_status == PaymentStatus.PAID,
        Order.created_at >= start_dt,
        Order.created_at <= end_dt,
    ]

    products_sold_result = await db.execute(
        select(func.sum(OrderItem.quantity)).join(Order).where(and_(*order_filters))
    )
    total_products_sold = products_sold_result.scalar() or 0

    wishlist_filters = [Product.vendor_id == vendor.id]
    if start_dt:
        wishlist_filters.append(Wishlist.created_at >= start_dt)
    if end_dt:
        wishlist_filters.append(Wishlist.created_at <= end_dt)

    wishlist_result = await db.execute(
        select(func.count(Wishlist.id)).join(Product).where(and_(*wishlist_filters))
    )
    wishlisted_products = wishlist_result.scalar() or 0

    range_customers = (
        select(Order.customer_id)
        .join(OrderItem)
        .where(and_(*order_filters))
        .distinct()
        .subquery()
    )

    prior_customers = (
        select(Order.customer_id)
        .join(OrderItem)
        .where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.payment_status == PaymentStatus.PAID,
                Order.created_at < start_dt,
            )
        )
        .distinct()
        .subquery()
    )

    returning_result = await db.execute(
        select(func.count())
        .select_from(range_customers)
        .where(range_customers.c.customer_id.in_(select(prior_customers.c.customer_id)))
    )
    returning_customers = returning_result.scalar() or 0

    new_result = await db.execute(
        select(func.count())
        .select_from(range_customers)
        .where(~range_customers.c.customer_id.in_(select(prior_customers.c.customer_id)))
    )
    new_customers = new_result.scalar() or 0

    return VendorAnalyticsStats(
        total_products_sold=total_products_sold,
        wishlisted_products=wishlisted_products,
        returning_customers=returning_customers,
        new_customers=new_customers
    )
@router.get("/payouts", response_model=dict)
async def list_vendor_payouts(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """List vendor payouts"""
    query = select(Payout).where(Payout.vendor_id == vendor.id)

    # Get total count
    count_result = await db.execute(
        select(func.count()).where(Payout.vendor_id == vendor.id)
    )
    total = count_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(desc(Payout.created_at)).offset(offset).limit(page_size)

    result = await db.execute(query)
    payouts = result.scalars().all()

    return {
        "payouts": payouts,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/payouts/summary", response_model=VendorPayoutSummary)
async def get_payout_summary(
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor payout summary"""
    from datetime import datetime
    from decimal import Decimal
    from app.models.order import PaymentStatus, FulfillmentStatus

    # Pending amount (completed but not yet paid out)
    pending_result = await db.execute(
        select(func.sum(OrderItem.vendor_payout)).join(Order).where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.payment_status == PaymentStatus.PAID,
                Order.fulfillment_status == FulfillmentStatus.DELIVERED
            )
        )
    )
    pending_from_orders = pending_result.scalar() or Decimal("0.00")

    # Subtract completed payouts
    completed_payouts_result = await db.execute(
        select(func.sum(Payout.payout_amount)).where(
            and_(
                Payout.vendor_id == vendor.id,
                Payout.status == "COMPLETED"
            )
        )
    )
    completed_payouts = completed_payouts_result.scalar() or Decimal("0.00")

    pending_amount = max(pending_from_orders - completed_payouts, Decimal("0.00"))

    # Last payout
    last_payout_result = await db.execute(
        select(Payout).where(
            and_(
                Payout.vendor_id == vendor.id,
                Payout.status == "COMPLETED"
            )
        ).order_by(desc(Payout.processed_at)).limit(1)
    )
    last_payout = last_payout_result.scalar_one_or_none()

    # Current month sales
    current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    current_month_result = await db.execute(
        select(func.sum(OrderItem.subtotal)).join(Order).where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.payment_status == PaymentStatus.PAID,
                Order.created_at >= current_month_start
            )
        )
    )
    current_month_sales = current_month_result.scalar() or Decimal("0.00")

    return VendorPayoutSummary(
        pending_amount=pending_amount,
        last_payout_amount=last_payout.payout_amount if last_payout else Decimal("0.00"),
        last_payout_date=last_payout.payout_period_end if last_payout else None,
        total_earnings=completed_payouts,
        current_month_sales=current_month_sales
    )


# ==================== VENDOR DASHBOARD ====================

@router.get("/dashboard/metrics", response_model=VendorDashboardMetrics)
async def get_dashboard_metrics(
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor dashboard metrics"""
    from datetime import datetime
    from decimal import Decimal
    from app.models.product import ProductStatus, ModerationStatus
    from app.models.order import PaymentStatus, FulfillmentStatus
    from app.models.vendor_pickup import PickupStatus

    # Products metrics
    total_products_result = await db.execute(
        select(func.count()).where(Product.vendor_id == vendor.id)
    )
    total_products = total_products_result.scalar() or 0

    active_products_result = await db.execute(
        select(func.count()).where(
            and_(
                Product.vendor_id == vendor.id,
                Product.status == ProductStatus.ACTIVE
            )
        )
    )
    active_products = active_products_result.scalar() or 0

    pending_approval_result = await db.execute(
        select(func.count()).where(
            and_(
                Product.vendor_id == vendor.id,
                Product.moderation_status == ModerationStatus.PENDING
            )
        )
    )
    pending_approval = pending_approval_result.scalar() or 0

    # Orders metrics
    total_orders_result = await db.execute(
        select(func.count(func.distinct(OrderItem.order_id))).where(
            OrderItem.vendor_id == vendor.id
        )
    )
    total_orders = total_orders_result.scalar() or 0

    pending_orders_result = await db.execute(
        select(func.count(func.distinct(OrderItem.order_id))).join(Order).where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.fulfillment_status == FulfillmentStatus.ORDER_RECEIVED
            )
        )
    )
    pending_orders = pending_orders_result.scalar() or 0

    in_progress_orders_result = await db.execute(
        select(func.count(func.distinct(OrderItem.order_id))).join(Order).where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.fulfillment_status == FulfillmentStatus.PREPARING_FOR_PICKUP
            )
        )
    )
    in_progress_orders = in_progress_orders_result.scalar() or 0

    completed_orders_result = await db.execute(
        select(func.count(func.distinct(OrderItem.order_id))).join(Order).where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.fulfillment_status == FulfillmentStatus.DELIVERED
            )
        )
    )
    completed_orders = completed_orders_result.scalar() or 0

    # Revenue metrics
    total_revenue = vendor.total_revenue

    current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    current_month_revenue_result = await db.execute(
        select(func.sum(OrderItem.vendor_payout)).join(Order).where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.payment_status == PaymentStatus.PAID,
                Order.created_at >= current_month_start
            )
        )
    )
    current_month_revenue = current_month_revenue_result.scalar() or Decimal("0.00")

    # Pending payout
    pending_payout_result = await db.execute(
        select(func.sum(OrderItem.vendor_payout)).join(Order).where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.payment_status == PaymentStatus.PAID,
                Order.fulfillment_status == FulfillmentStatus.DELIVERED
            )
        )
    )
    pending_from_orders = pending_payout_result.scalar() or Decimal("0.00")

    completed_payouts_result = await db.execute(
        select(func.sum(Payout.payout_amount)).where(
            and_(
                Payout.vendor_id == vendor.id,
                Payout.status == "COMPLETED"
            )
        )
    )
    completed_payouts = completed_payouts_result.scalar() or Decimal("0.00")

    pending_payout = max(pending_from_orders - completed_payouts, Decimal("0.00"))

    # Pickups metrics
    scheduled_pickups_result = await db.execute(
        select(func.count()).where(
            and_(
                VendorPickup.vendor_id == vendor.id,
                VendorPickup.status == PickupStatus.SCHEDULED
            )
        )
    )
    scheduled_pickups = scheduled_pickups_result.scalar() or 0

    # Notifications
    unread_notifications_result = await db.execute(
        select(func.count()).where(
            and_(
                VendorNotification.vendor_id == vendor.id,
                VendorNotification.is_read == False
            )
        )
    )
    unread_notifications = unread_notifications_result.scalar() or 0

    return VendorDashboardMetrics(
        total_products=total_products,
        active_products=active_products,
        pending_approval_products=pending_approval,
        total_orders=total_orders,
        pending_orders=pending_orders,
        in_progress_orders=in_progress_orders,
        completed_orders=completed_orders,
        total_revenue=total_revenue,
        current_month_revenue=current_month_revenue,
        pending_payout=pending_payout,
        scheduled_pickups=scheduled_pickups,
        pending_pickups=scheduled_pickups,
        unread_notifications=unread_notifications
    )


@router.post("/store/pause", response_model=VendorResponse)
async def pause_store(
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Temporarily pause the vendor's store.
    This will make the store inactive and hide all products from customers.
    """
    from datetime import datetime

    # Check if store is already paused
    if not vendor.store_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Store is already paused"
        )

    # Pause the store
    vendor.store_active = False
    vendor.store_paused_at = datetime.utcnow()

    await db.commit()
    await db.refresh(vendor)

    return vendor


@router.post("/store/activate", response_model=VendorResponse)
async def activate_store(
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Reactivate a paused store.
    This will make the store active again and show all products to customers.
    """
    # Check if store is already active
    if vendor.store_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Store is already active"
        )

    # Check if store is deleted
    if vendor.store_deleted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot activate a deleted store"
        )

    # Activate the store
    vendor.store_active = True
    vendor.store_paused_at = None

    await db.commit()
    await db.refresh(vendor)

    return vendor


@router.delete("/store", response_model=VendorResponse)
async def delete_store(
    vendor: Vendor = Depends(get_vendor_profile),
    db: AsyncSession = Depends(get_db)
):
    """
    Soft delete the vendor's store.
    This marks the store as deleted but keeps all data in the database.
    Store can potentially be restored by contacting support.
    """
    from datetime import datetime

    # Check if store is already deleted
    if vendor.store_deleted_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Store is already deleted"
        )

    # Soft delete the store
    vendor.store_active = False
    vendor.store_deleted_at = datetime.utcnow()

    await db.commit()
    await db.refresh(vendor)

    return vendor
