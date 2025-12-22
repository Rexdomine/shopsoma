"""Vendor API endpoints"""
from typing import List, Optional
import logging
from datetime import datetime, date, time, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import selectinload
from uuid import UUID

from app.core.database import get_db
from app.core.config import settings
from app.api.dependencies import (
    get_current_user, get_vendor_profile, get_approved_vendor,
    get_kyc_submitted_vendor, get_current_admin
)
from app.models import (
    Vendor, User, VendorAsset, VendorPickup, VendorNotification,
    Order, OrderItem, Product, Payout, VendorPaymentMethod
)
from app.models.app_setting import AppSetting
from app.models.vendor import KYCStatus
from app.models.order import PaymentStatus, FulfillmentStatus
from app.models.payment import PayoutStatus
from app.models.user import UserRole
from app.schemas.vendor import (
    VendorOnboardingRequest, VendorResponse, VendorProfileUpdate,
    VendorKYCSubmission, VendorAssetCreate, VendorAssetResponse,
    VendorAssetUpdate, VendorPickupResponse, VendorPickupCreate,
    VendorPickupUpdate, VendorNotificationResponse, VendorNotificationMarkRead,
    VendorOrderResponse, VendorOrderItemResponse, VendorOrderItemUpdate, VendorPayoutResponse,
    VendorDashboardResponse, VendorDashboardMetrics, VendorPayoutSummary,
    VendorProductPerformance, VendorBrandInfoUpdate, VendorPayoutInfoUpdate,
    VendorEarningsSummary, VendorPayoutRequest
)
from app.schemas.product import ProductResponse
from app.models.product import ProductStatus, Variation
from app.services.email_service import email_service

router = APIRouter(prefix="/vendor", tags=["Vendors"])
logger = logging.getLogger(__name__)


async def _get_payout_hold_days(db: AsyncSession) -> int:
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == "payout_hold_days")
    )
    setting = result.scalar_one_or_none()
    hold_days = settings.PAYOUT_HOLD_DAYS
    if setting and setting.value is not None:
        try:
            hold_days = int(setting.value)
        except ValueError:
            hold_days = settings.PAYOUT_HOLD_DAYS
    return max(hold_days, 0)


async def _build_admin_recipients(db: AsyncSession) -> List[dict]:
    result = await db.execute(
        select(User).where(User.role == UserRole.ADMIN)
    )
    admin_users = result.scalars().all()
    recipients = [
        {"email": user.email, "name": user.full_name or "Admin"}
        for user in admin_users
        if user.email
    ]
    if settings.ADMIN_EMAIL and all(
        recipient["email"] != settings.ADMIN_EMAIL for recipient in recipients
    ):
        recipients.append({"email": settings.ADMIN_EMAIL, "name": "Admin"})
    return recipients


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

@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_vendor_product(
    product_id: UUID,
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor product details"""
    product_query = (
        select(Product)
        .options(
            selectinload(Product.variants),
            selectinload(Product.variations).selectinload(Variation.size_stocks),
            selectinload(Product.images),
            selectinload(Product.category),
            selectinload(Product.collection),
        )
        .where(
            and_(
                Product.id == product_id,
                Product.vendor_id == vendor.id,
                Product.status != ProductStatus.ARCHIVED
            )
        )
    )

    result = await db.execute(product_query)
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    return product

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
    from app.models.order import PaymentStatus, FulfillmentStatus

    start, end, start_dt, end_dt = _build_date_range(start_date, end_date)
    previous_start_dt = None
    previous_end_dt = None
    if start_dt and end_dt:
        period_days = (end_dt.date() - start_dt.date()).days + 1
        previous_end_dt = start_dt - timedelta(days=1)
        previous_start_dt = previous_end_dt - timedelta(days=period_days - 1)

    delivered_filters = [
        OrderItem.vendor_id == vendor.id,
        Order.payment_status == PaymentStatus.PAID,
        Order.fulfillment_status == FulfillmentStatus.DELIVERED,
        Order.delivered_at.isnot(None),
    ]
    if start_dt:
        delivered_filters.append(Order.delivered_at >= start_dt)
    if end_dt:
        delivered_filters.append(Order.delivered_at <= end_dt)

    current_result = await db.execute(
        select(func.sum(OrderItem.vendor_payout)).join(Order).where(and_(*delivered_filters))
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
            Order.fulfillment_status == FulfillmentStatus.DELIVERED,
            Order.delivered_at.isnot(None),
            Order.delivered_at >= previous_start_dt,
            Order.delivered_at <= previous_end_dt,
        ]
        prev_current_result = await db.execute(
            select(func.sum(OrderItem.vendor_payout)).join(Order).where(and_(*prev_filters))
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
        select(func.sum(OrderItem.vendor_payout)).join(Order).where(and_(*projected_filters))
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
            select(func.sum(OrderItem.vendor_payout)).join(Order).where(and_(*prev_projected_filters))
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
    from app.models.order import PaymentStatus, FulfillmentStatus

    if view not in {"products", "orders"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="view must be either 'products' or 'orders'."
        )

    _, _, start_dt, end_dt = _build_date_range(start_date, end_date)

    delivered_filters = [
        OrderItem.vendor_id == vendor.id,
        Order.payment_status == PaymentStatus.PAID,
        Order.fulfillment_status == FulfillmentStatus.DELIVERED,
        Order.delivered_at.isnot(None),
    ]
    if start_dt:
        delivered_filters.append(Order.delivered_at >= start_dt)
    if end_dt:
        delivered_filters.append(Order.delivered_at <= end_dt)

    if view == "products":
        query = select(OrderItem, Order.order_number, Order.delivered_at, Order.fulfillment_status).join(Order).where(
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
        for item, order_number, delivered_at, fulfillment_status in rows:
            product_image_url = None
            if item.product and item.product.images:
                primary_image = next((img for img in item.product.images if img.is_primary), None)
                if primary_image:
                    product_image_url = primary_image.thumbnail_url or primary_image.image_url
                else:
                    first_image = item.product.images[0]
                    product_image_url = first_image.thumbnail_url or first_image.image_url

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
                "vendor_payout": float(item.vendor_payout),
                "status": fulfillment_status.value if hasattr(fulfillment_status, "value") else str(fulfillment_status),
                "delivered_at": delivered_at.isoformat() if delivered_at else None,
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

    items = []
    for order in orders:
        vendor_items = [item for item in order.items if item.vendor_id == vendor.id]
        total_quantity = sum(item.quantity for item in vendor_items)
        total_commission = sum((item.commission_amount or Decimal("0.00")) for item in vendor_items)
        total_payout = sum((item.vendor_payout or Decimal("0.00")) for item in vendor_items)
        items.append({
            "id": str(order.id),
            "order_number": order.order_number,
            "items": [item.product_title for item in vendor_items],
            "total_quantity": total_quantity,
            "total_commission": float(total_commission),
            "total_payout": float(total_payout),
            "status": order.fulfillment_status.value,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
        })

    return {
        "view": "orders",
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }
@router.get("/payouts", response_model=dict)
async def list_vendor_payouts(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by payout status"),
    search: Optional[str] = Query(None, description="Search by payment reference or notes"),
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """List vendor payouts"""
    _, _, start_dt, end_dt = _build_date_range(start_date, end_date)

    query = select(Payout).where(Payout.vendor_id == vendor.id)
    if status_filter:
        query = query.where(Payout.status == status_filter)
    if start_dt:
        query = query.where(Payout.created_at >= start_dt)
    if end_dt:
        query = query.where(Payout.created_at <= end_dt)
    if search:
        query = query.where(
            or_(
                Payout.payment_reference.ilike(f"%{search}%"),
                Payout.notes.ilike(f"%{search}%")
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(
        query.order_by(None).subquery()
    )
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Pagination
    offset = (page - 1) * page_size
    query = query.order_by(desc(Payout.created_at)).offset(offset).limit(page_size)

    result = await db.execute(query)
    payouts = result.scalars().all()

    return {
        "payouts": [
            {
                "id": str(payout.id),
                "vendor_id": str(payout.vendor_id),
                "payout_period_start": payout.payout_period_start.isoformat(),
                "payout_period_end": payout.payout_period_end.isoformat(),
                "total_sales": float(payout.total_sales),
                "commission_amount": float(payout.commission_amount),
                "payout_amount": float(payout.payout_amount),
                "status": payout.status.value,
                "processed_at": payout.processed_at.isoformat() if payout.processed_at else None,
                "payment_reference": payout.payment_reference,
                "notes": payout.notes,
                "created_at": payout.created_at.isoformat() if payout.created_at else None,
            }
            for payout in payouts
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }


@router.get("/payouts/{payout_id}", response_model=VendorPayoutResponse)
async def get_vendor_payout(
    payout_id: UUID,
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db),
):
    """Get a vendor payout detail."""
    result = await db.execute(
        select(Payout).where(
            and_(
                Payout.id == payout_id,
                Payout.vendor_id == vendor.id,
            )
        )
    )
    payout = result.scalar_one_or_none()
    if not payout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payout not found")
    return payout


@router.post("/payouts/request", response_model=VendorPayoutResponse, status_code=status.HTTP_201_CREATED)
async def request_vendor_payout(
    payout_request: VendorPayoutRequest,
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """Request a vendor payout"""
    from decimal import Decimal

    selected_method = None
    if payout_request.payment_method_id:
        method_result = await db.execute(
            select(VendorPaymentMethod).where(
                and_(
                    VendorPaymentMethod.id == payout_request.payment_method_id,
                    VendorPaymentMethod.vendor_id == vendor.id
                )
            )
        )
        selected_method = method_result.scalar_one_or_none()
        if not selected_method:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected payment method not found."
            )
    else:
        methods_result = await db.execute(
            select(VendorPaymentMethod)
            .where(VendorPaymentMethod.vendor_id == vendor.id)
            .order_by(VendorPaymentMethod.is_default.desc(), VendorPaymentMethod.created_at.desc())
        )
        selected_method = methods_result.scalars().first()

    if not selected_method and (not vendor.bank_name or not vendor.bank_account_number or not vendor.bank_account_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bank payout information is incomplete."
        )

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

    completed_payouts_result = await db.execute(
        select(func.sum(Payout.payout_amount)).where(
            and_(
                Payout.vendor_id == vendor.id,
                Payout.status == PayoutStatus.COMPLETED
            )
        )
    )
    completed_payouts = completed_payouts_result.scalar() or Decimal("0.00")

    pending_amount = max(pending_from_orders - completed_payouts, Decimal("0.00"))

    existing_result = await db.execute(
        select(Payout).where(
            and_(
                Payout.vendor_id == vendor.id,
                Payout.status.in_([PayoutStatus.PENDING, PayoutStatus.PROCESSING])
            )
        )
    )
    existing_payout = existing_result.scalar_one_or_none()
    if existing_payout:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You already have a pending withdrawal request."
        )

    hold_days = await _get_payout_hold_days(db)
    cutoff_date = datetime.utcnow() - timedelta(days=hold_days)
    available_result = await db.execute(
        select(func.sum(OrderItem.vendor_payout)).join(Order).where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.payment_status == PaymentStatus.PAID,
                Order.fulfillment_status == FulfillmentStatus.DELIVERED,
                Order.delivered_at.isnot(None),
                Order.delivered_at <= cutoff_date
            )
        )
    )
    available_from_orders = available_result.scalar() or Decimal("0.00")
    available_payout = max(available_from_orders - completed_payouts, Decimal("0.00"))

    request_amount = payout_request.amount
    if available_payout == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No available payout balance."
        )

    if request_amount > available_payout:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requested amount exceeds available payout balance."
        )

    totals_result = await db.execute(
        select(
            func.sum(OrderItem.subtotal),
            func.sum(OrderItem.commission_amount),
            func.min(Order.delivered_at),
            func.max(Order.delivered_at),
        ).join(Order).where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.payment_status == PaymentStatus.PAID,
                Order.fulfillment_status == FulfillmentStatus.DELIVERED,
                Order.delivered_at.isnot(None)
            )
        )
    )
    total_sales, commission_amount, earliest_delivered, latest_delivered = totals_result.one()
    total_sales = total_sales or Decimal("0.00")
    commission_amount = commission_amount or Decimal("0.00")

    ratio = Decimal("0.00")
    if available_payout > 0:
        ratio = (request_amount / available_payout).quantize(Decimal("0.0001"))

    payout_total_sales = (total_sales * ratio).quantize(Decimal("0.01"))
    payout_commission = (commission_amount * ratio).quantize(Decimal("0.01"))

    payout_notes = "Vendor requested payout"
    if selected_method:
        payout_notes = (
            f"Vendor requested payout via {selected_method.bank_name} "
            f"(****{selected_method.account_number[-4:]})"
        )

    payout = Payout(
        vendor_id=vendor.id,
        payout_period_start=earliest_delivered.date() if earliest_delivered else datetime.utcnow().date(),
        payout_period_end=latest_delivered.date() if latest_delivered else datetime.utcnow().date(),
        total_sales=payout_total_sales,
        commission_amount=payout_commission,
        payout_amount=request_amount,
        status=PayoutStatus.PENDING,
        notes=payout_notes,
    )

    db.add(payout)
    await db.commit()
    await db.refresh(payout)

    try:
        vendor_user_result = await db.execute(
            select(User).where(User.id == vendor.user_id)
        )
        vendor_user = vendor_user_result.scalar_one_or_none()
        payout_method = payout_notes.replace("Vendor requested payout via ", "")
        admin_recipients = await _build_admin_recipients(db)

        async def _send_payout_request_emails():
            try:
                if vendor_user and vendor_user.email:
                    await email_service.send_vendor_payout_request_email(
                        email=vendor_user.email,
                        name=vendor.business_name,
                        payout_amount=float(payout.payout_amount),
                        requested_at=payout.created_at,
                        payout_method=payout_method,
                        hold_days=hold_days,
                    )
                await email_service.send_admin_payout_request_email(
                    recipients=admin_recipients,
                    vendor_name=vendor.business_name,
                    vendor_email=vendor_user.email if vendor_user else "",
                    payout_amount=float(payout.payout_amount),
                    requested_at=payout.created_at,
                    payout_id=str(payout.id),
                )
            except Exception:
                logger.exception(
                    "[Vendor Payout] Failed to send payout request emails for vendor_id=%s",
                    vendor.id
                )

        if background_tasks is not None:
            background_tasks.add_task(_send_payout_request_emails)
        else:
            await _send_payout_request_emails()
    except Exception:
        logger.exception("[Vendor Payout] Failed to queue payout request emails for vendor_id=%s", vendor.id)

    return payout


@router.get("/payouts/summary", response_model=VendorPayoutSummary)
async def get_payout_summary(
    vendor: Vendor = Depends(get_approved_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Get vendor payout summary"""
    from datetime import datetime, timedelta
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

    hold_days = await _get_payout_hold_days(db)
    cutoff_date = datetime.utcnow() - timedelta(days=hold_days)
    available_result = await db.execute(
        select(func.sum(OrderItem.vendor_payout)).join(Order).where(
            and_(
                OrderItem.vendor_id == vendor.id,
                Order.payment_status == PaymentStatus.PAID,
                Order.fulfillment_status == FulfillmentStatus.DELIVERED,
                Order.delivered_at.isnot(None),
                Order.delivered_at <= cutoff_date
            )
        )
    )
    available_from_orders = available_result.scalar() or Decimal("0.00")
    available_payout = max(available_from_orders - completed_payouts, Decimal("0.00"))

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
        available_payout=available_payout,
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
