"""Vendor service layer"""
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
from uuid import UUID

from app.models import (
    Vendor, User, VendorAsset, VendorPickup, VendorNotification,
    Order, OrderItem, Product, ProductVariant, Payout, Payment
)
from app.models.vendor import KYCStatus
from app.models.vendor_pickup import PickupStatus, OrderType
from app.models.order import FulfillmentStatus, PaymentStatus
from app.models.product import ProductStatus, ModerationStatus
from app.schemas.vendor import (
    VendorOnboardingRequest, VendorKYCSubmission, VendorProfileUpdate,
    VendorAssetCreate, VendorPickupCreate, VendorDashboardMetrics,
    VendorPayoutSummary
)
from app.services.commission import DEFAULT_COMMISSION_RATE


class VendorService:
    """Service for vendor operations"""

    @staticmethod
    def create_vendor(db: Session, user_id: UUID, vendor_data: VendorOnboardingRequest) -> Vendor:
        """Create a new vendor profile"""
        # Check if user already has a vendor profile
        existing_vendor = db.query(Vendor).filter(Vendor.user_id == user_id).first()
        if existing_vendor:
            raise ValueError("User already has a vendor profile")

        # Create vendor
        vendor = Vendor(
            user_id=user_id,
            business_name=vendor_data.business_name,
            business_description=vendor_data.business_description,
            business_address=vendor_data.business_address,
            business_phone=vendor_data.business_phone,
            bank_name=vendor_data.bank_name,
            bank_account_number=vendor_data.bank_account_number,
            bank_account_name=vendor_data.bank_account_name,
            kyc_status=KYCStatus.PENDING,
            approved=False,
            commission_rate=DEFAULT_COMMISSION_RATE
        )

        db.add(vendor)
        db.commit()
        db.refresh(vendor)

        # Update user role to vendor
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.role = "vendor"
            db.commit()

        return vendor

    @staticmethod
    def get_vendor_by_user_id(db: Session, user_id: UUID) -> Optional[Vendor]:
        """Get vendor by user ID"""
        return db.query(Vendor).filter(Vendor.user_id == user_id).first()

    @staticmethod
    def get_vendor_by_id(db: Session, vendor_id: UUID) -> Optional[Vendor]:
        """Get vendor by ID"""
        return db.query(Vendor).filter(Vendor.id == vendor_id).first()

    @staticmethod
    def update_vendor_profile(db: Session, vendor_id: UUID, update_data: VendorProfileUpdate) -> Vendor:
        """Update vendor profile"""
        vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not vendor:
            raise ValueError("Vendor not found")

        # Update fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(vendor, field, value)

        db.commit()
        db.refresh(vendor)
        return vendor

    @staticmethod
    def submit_kyc(db: Session, vendor_id: UUID, kyc_data: VendorKYCSubmission) -> Vendor:
        """Submit KYC documents"""
        vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not vendor:
            raise ValueError("Vendor not found")

        vendor.kyc_document_type = kyc_data.kyc_document_type
        vendor.kyc_document_url = kyc_data.kyc_document_url
        vendor.kyc_status = KYCStatus.SUBMITTED
        vendor.kyc_submitted_at = datetime.utcnow()

        db.commit()
        db.refresh(vendor)
        return vendor

    # ==================== VENDOR ASSETS ====================

    @staticmethod
    def create_vendor_asset(db: Session, vendor_id: UUID, asset_data: VendorAssetCreate) -> VendorAsset:
        """Create vendor asset (logo, banner, size chart)"""
        asset = VendorAsset(
            vendor_id=vendor_id,
            **asset_data.model_dump()
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset

    @staticmethod
    def get_vendor_assets(db: Session, vendor_id: UUID, asset_type: Optional[str] = None) -> List[VendorAsset]:
        """Get vendor assets"""
        query = db.query(VendorAsset).filter(VendorAsset.vendor_id == vendor_id)
        if asset_type:
            query = query.filter(VendorAsset.asset_type == asset_type)
        return query.order_by(VendorAsset.display_order).all()

    @staticmethod
    def delete_vendor_asset(db: Session, vendor_id: UUID, asset_id: UUID) -> bool:
        """Delete vendor asset"""
        asset = db.query(VendorAsset).filter(
            VendorAsset.id == asset_id,
            VendorAsset.vendor_id == vendor_id
        ).first()

        if not asset:
            return False

        db.delete(asset)
        db.commit()
        return True

    # ==================== VENDOR ORDERS ====================

    @staticmethod
    def get_vendor_orders(
        db: Session,
        vendor_id: UUID,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[List[Order], int]:
        """Get vendor orders"""
        # Base query - get orders that have items from this vendor
        query = db.query(Order).join(OrderItem).filter(
            OrderItem.vendor_id == vendor_id
        ).distinct()

        # Filter by status
        if status:
            query = query.filter(Order.fulfillment_status == status)

        # Get total count
        total = query.count()

        # Pagination
        offset = (page - 1) * page_size
        orders = query.order_by(desc(Order.created_at)).offset(offset).limit(page_size).all()

        return orders, total

    @staticmethod
    def get_vendor_order_items(db: Session, vendor_id: UUID, order_id: UUID) -> List[OrderItem]:
        """Get vendor's items from a specific order"""
        return db.query(OrderItem).filter(
            OrderItem.vendor_id == vendor_id,
            OrderItem.order_id == order_id
        ).all()

    # ==================== VENDOR PICKUPS ====================

    @staticmethod
    def create_pickup(db: Session, vendor_id: UUID, pickup_data: VendorPickupCreate) -> VendorPickup:
        """Create pickup schedule"""
        # Get order item
        order_item = db.query(OrderItem).filter(
            OrderItem.id == pickup_data.order_item_id,
            OrderItem.vendor_id == vendor_id
        ).first()

        if not order_item:
            raise ValueError("Order item not found or does not belong to vendor")

        # Calculate scheduled pickup date based on order type
        if pickup_data.order_type == "RTW":
            # RTW: 24-48 hours
            scheduled_date = datetime.utcnow() + timedelta(hours=48)
        elif pickup_data.order_type == "MADE_TO_ORDER" and pickup_data.estimated_production_days:
            # Made to order: use estimated production days
            scheduled_date = datetime.utcnow() + timedelta(days=pickup_data.estimated_production_days)
        else:
            # Default: 48 hours
            scheduled_date = datetime.utcnow() + timedelta(hours=48)

        pickup = VendorPickup(
            vendor_id=vendor_id,
            order_id=order_item.order_id,
            order_item_id=order_item.id,
            order_type=pickup_data.order_type,
            estimated_production_days=pickup_data.estimated_production_days,
            scheduled_pickup_date=scheduled_date,
            pickup_address=pickup_data.pickup_address,
            pickup_contact_name=pickup_data.pickup_contact_name,
            pickup_contact_phone=pickup_data.pickup_contact_phone,
            vendor_notes=pickup_data.vendor_notes,
            status=PickupStatus.SCHEDULED
        )

        db.add(pickup)
        db.commit()
        db.refresh(pickup)
        return pickup

    @staticmethod
    def get_vendor_pickups(
        db: Session,
        vendor_id: UUID,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[List[VendorPickup], int]:
        """Get vendor pickups"""
        query = db.query(VendorPickup).filter(VendorPickup.vendor_id == vendor_id)

        if status:
            query = query.filter(VendorPickup.status == status)

        total = query.count()
        offset = (page - 1) * page_size
        pickups = query.order_by(desc(VendorPickup.created_at)).offset(offset).limit(page_size).all()

        return pickups, total

    # ==================== VENDOR NOTIFICATIONS ====================

    @staticmethod
    def create_notification(
        db: Session,
        vendor_id: UUID,
        notification_type: str,
        title: str,
        message: str,
        order_id: Optional[UUID] = None,
        pickup_id: Optional[UUID] = None,
        payout_id: Optional[UUID] = None,
        data: Optional[dict] = None
    ) -> VendorNotification:
        """Create vendor notification"""
        notification = VendorNotification(
            vendor_id=vendor_id,
            notification_type=notification_type,
            title=title,
            message=message,
            order_id=order_id,
            pickup_id=pickup_id,
            payout_id=payout_id,
            data=data
        )

        db.add(notification)
        db.commit()
        db.refresh(notification)
        return notification

    @staticmethod
    def get_vendor_notifications(
        db: Session,
        vendor_id: UUID,
        unread_only: bool = False,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[List[VendorNotification], int]:
        """Get vendor notifications"""
        query = db.query(VendorNotification).filter(VendorNotification.vendor_id == vendor_id)

        if unread_only:
            query = query.filter(VendorNotification.is_read == False)

        total = query.count()
        offset = (page - 1) * page_size
        notifications = query.order_by(desc(VendorNotification.created_at)).offset(offset).limit(page_size).all()

        return notifications, total

    @staticmethod
    def mark_notifications_read(db: Session, vendor_id: UUID, notification_ids: List[UUID]) -> int:
        """Mark notifications as read"""
        result = db.query(VendorNotification).filter(
            VendorNotification.vendor_id == vendor_id,
            VendorNotification.id.in_(notification_ids)
        ).update({
            "is_read": True,
            "read_at": datetime.utcnow()
        }, synchronize_session=False)

        db.commit()
        return result

    # ==================== VENDOR DASHBOARD METRICS ====================

    @staticmethod
    def get_dashboard_metrics(db: Session, vendor_id: UUID) -> VendorDashboardMetrics:
        """Get vendor dashboard metrics"""
        vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
        if not vendor:
            raise ValueError("Vendor not found")

        # Products metrics
        total_products = db.query(func.count(Product.id)).filter(Product.vendor_id == vendor_id).scalar() or 0
        active_products = db.query(func.count(Product.id)).filter(
            Product.vendor_id == vendor_id,
            Product.status == ProductStatus.ACTIVE
        ).scalar() or 0
        pending_approval = db.query(func.count(Product.id)).filter(
            Product.vendor_id == vendor_id,
            Product.moderation_status == ModerationStatus.PENDING
        ).scalar() or 0

        # Orders metrics
        total_orders = db.query(func.count(func.distinct(OrderItem.order_id))).filter(
            OrderItem.vendor_id == vendor_id
        ).scalar() or 0

        pending_orders = db.query(func.count(func.distinct(OrderItem.order_id))).join(Order).filter(
            OrderItem.vendor_id == vendor_id,
            Order.fulfillment_status == FulfillmentStatus.PENDING
        ).scalar() or 0

        in_progress_orders = db.query(func.count(func.distinct(OrderItem.order_id))).join(Order).filter(
            OrderItem.vendor_id == vendor_id,
            Order.fulfillment_status == FulfillmentStatus.PROCESSING
        ).scalar() or 0

        completed_orders = db.query(func.count(func.distinct(OrderItem.order_id))).join(Order).filter(
            OrderItem.vendor_id == vendor_id,
            Order.fulfillment_status == FulfillmentStatus.DELIVERED
        ).scalar() or 0

        # Revenue metrics
        total_revenue = vendor.total_revenue

        # Current month revenue
        current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_month_revenue = db.query(func.sum(OrderItem.vendor_payout)).join(Order).filter(
            OrderItem.vendor_id == vendor_id,
            Order.payment_status == PaymentStatus.PAID,
            Order.created_at >= current_month_start
        ).scalar() or Decimal("0.00")

        # Pending payout (completed orders not yet paid out)
        pending_payout = db.query(func.sum(OrderItem.vendor_payout)).join(Order).filter(
            OrderItem.vendor_id == vendor_id,
            Order.payment_status == PaymentStatus.PAID,
            Order.fulfillment_status == FulfillmentStatus.DELIVERED
        ).scalar() or Decimal("0.00")

        # Subtract already paid out amounts
        total_payouts = db.query(func.sum(Payout.payout_amount)).filter(
            Payout.vendor_id == vendor_id,
            Payout.status == "COMPLETED"
        ).scalar() or Decimal("0.00")

        pending_payout -= total_payouts
        if pending_payout < 0:
            pending_payout = Decimal("0.00")

        # Pickups metrics
        scheduled_pickups = db.query(func.count(VendorPickup.id)).filter(
            VendorPickup.vendor_id == vendor_id,
            VendorPickup.status == PickupStatus.SCHEDULED
        ).scalar() or 0

        pending_pickups = scheduled_pickups

        # Notifications
        unread_notifications = db.query(func.count(VendorNotification.id)).filter(
            VendorNotification.vendor_id == vendor_id,
            VendorNotification.is_read == False
        ).scalar() or 0

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
            pending_pickups=pending_pickups,
            unread_notifications=unread_notifications
        )

    @staticmethod
    def get_payout_summary(db: Session, vendor_id: UUID) -> VendorPayoutSummary:
        """Get vendor payout summary"""
        # Pending amount (not yet paid out)
        pending_amount = db.query(func.sum(OrderItem.vendor_payout)).join(Order).filter(
            OrderItem.vendor_id == vendor_id,
            Order.payment_status == PaymentStatus.PAID,
            Order.fulfillment_status == FulfillmentStatus.DELIVERED
        ).scalar() or Decimal("0.00")

        # Subtract completed payouts
        completed_payouts = db.query(func.sum(Payout.payout_amount)).filter(
            Payout.vendor_id == vendor_id,
            Payout.status == "COMPLETED"
        ).scalar() or Decimal("0.00")

        pending_amount -= completed_payouts
        if pending_amount < 0:
            pending_amount = Decimal("0.00")

        # Last payout
        last_payout = db.query(Payout).filter(
            Payout.vendor_id == vendor_id,
            Payout.status == "COMPLETED"
        ).order_by(desc(Payout.processed_at)).first()

        last_payout_amount = last_payout.payout_amount if last_payout else Decimal("0.00")
        last_payout_date = last_payout.payout_period_end if last_payout else None

        # Total earnings (all completed payouts)
        total_earnings = completed_payouts

        # Current month sales
        current_month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        current_month_sales = db.query(func.sum(OrderItem.subtotal)).join(Order).filter(
            OrderItem.vendor_id == vendor_id,
            Order.payment_status == PaymentStatus.PAID,
            Order.created_at >= current_month_start
        ).scalar() or Decimal("0.00")

        return VendorPayoutSummary(
            pending_amount=pending_amount,
            last_payout_amount=last_payout_amount,
            last_payout_date=last_payout_date,
            total_earnings=total_earnings,
            current_month_sales=current_month_sales
        )
