"""Vendor pickup and logistics models"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum as SQLEnum, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.base import Base


class PickupStatus(str, enum.Enum):
    """Pickup status enum"""
    SCHEDULED = "scheduled"
    IN_TRANSIT = "in_transit"
    DELIVERED_TO_QC = "delivered_to_qc"
    QC_APPROVED = "qc_approved"
    QC_REJECTED = "qc_rejected"
    SHIPPED_TO_CUSTOMER = "shipped_to_customer"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class OrderType(str, enum.Enum):
    """Order type for fulfillment timeline"""
    RTW = "rtw"  # Ready-to-wear (24-48 hours)
    MADE_TO_ORDER = "made_to_order"  # Custom timeline
    CUSTOM = "custom"  # Custom/Bespoke orders


class VendorPickup(Base):
    """Vendor pickup scheduling for order fulfillment"""
    __tablename__ = "vendor_pickups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Order Type
    order_type = Column(SQLEnum(OrderType), nullable=False, default=OrderType.RTW)
    estimated_production_days = Column(Integer, nullable=True)  # For made-to-order

    # Pickup Details
    scheduled_pickup_date = Column(DateTime(timezone=True), nullable=True)
    actual_pickup_date = Column(DateTime(timezone=True), nullable=True)
    pickup_address = Column(Text, nullable=True)
    pickup_contact_name = Column(String(255), nullable=True)
    pickup_contact_phone = Column(String(20), nullable=True)

    # Logistics
    logistics_partner = Column(String(100), nullable=True)
    tracking_number = Column(String(100), nullable=True, index=True)
    driver_name = Column(String(255), nullable=True)
    driver_phone = Column(String(20), nullable=True)

    # Status
    status = Column(SQLEnum(PickupStatus), default=PickupStatus.SCHEDULED, nullable=False, index=True)

    # QC Information
    qc_center_arrival_date = Column(DateTime(timezone=True), nullable=True)
    qc_approved_date = Column(DateTime(timezone=True), nullable=True)
    qc_rejected_date = Column(DateTime(timezone=True), nullable=True)
    qc_notes = Column(Text, nullable=True)
    qc_approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Additional Notes
    vendor_notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Relationships
    vendor = relationship("Vendor", back_populates="pickups")
    order = relationship("Order", back_populates="pickups")
    order_item = relationship("OrderItem", back_populates="pickup")
    qc_approver = relationship("User", foreign_keys=[qc_approved_by])

    def __repr__(self):
        return f"<VendorPickup {self.vendor_id} - Order {self.order_id}>"


class VendorNotification(Base):
    """Vendor notification system"""
    __tablename__ = "vendor_notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)

    # Notification Details
    notification_type = Column(String(50), nullable=False, index=True)  # order_placed, pickup_scheduled, payment_processed
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)

    # References
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)
    pickup_id = Column(UUID(as_uuid=True), ForeignKey("vendor_pickups.id", ondelete="SET NULL"), nullable=True)
    payout_id = Column(UUID(as_uuid=True), ForeignKey("payouts.id", ondelete="SET NULL"), nullable=True)

    # Metadata
    data = Column(JSONB, nullable=True)  # Additional context data

    # Status
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    # Email sent
    email_sent = Column(Boolean, default=False, nullable=False)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    vendor = relationship("Vendor", back_populates="notifications")
    order = relationship("Order")
    pickup = relationship("VendorPickup")
    payout = relationship("Payout")

    def __repr__(self):
        return f"<VendorNotification {self.vendor_id} - {self.notification_type}>"
