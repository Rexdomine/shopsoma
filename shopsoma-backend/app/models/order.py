"""Order models"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Numeric, Text, Date, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.base import Base


class PaymentStatus(str, enum.Enum):
    """Payment status enum"""
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"


class FulfillmentStatus(str, enum.Enum):
    """Fulfillment status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class Order(Base):
    """Customer order model"""
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Address Information
    shipping_address_id = Column(UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=True)
    billing_address_id = Column(UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=True)

    # Pricing
    subtotal = Column(Numeric(10, 2), nullable=False)
    shipping_cost = Column(Numeric(10, 2), default=0.00, nullable=False)
    tax_amount = Column(Numeric(10, 2), default=0.00, nullable=False)
    discount_amount = Column(Numeric(10, 2), default=0.00, nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)

    # Status
    payment_status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False, index=True)
    fulfillment_status = Column(SQLEnum(FulfillmentStatus), default=FulfillmentStatus.PENDING, nullable=False, index=True)

    # Delivery
    delivery_provider = Column(String(50), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    estimated_delivery_date = Column(Date, nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    # Notes
    customer_notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Relationships
    customer = relationship("User", back_populates="orders", foreign_keys=[customer_id])
    shipping_address = relationship("Address", foreign_keys=[shipping_address_id])
    billing_address = relationship("Address", foreign_keys=[billing_address_id])
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="order")
    returns = relationship("Return", back_populates="order")
    pickups = relationship("VendorPickup", back_populates="order")

    def __repr__(self):
        return f"<Order {self.order_number}>"


class OrderItem(Base):
    """Order item model"""
    __tablename__ = "order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="RESTRICT"), nullable=False, index=True)
    variant_id = Column(UUID(as_uuid=True), ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Product Snapshot (at time of order)
    product_title = Column(String(255), nullable=False)
    variant_details = Column(JSONB, nullable=True)  # {size: "M", color: "Blue"}

    # Pricing
    unit_price = Column(Numeric(10, 2), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    # Vendor Commission
    commission_rate = Column(Numeric(5, 2), nullable=False)
    commission_amount = Column(Numeric(10, 2), nullable=False)
    vendor_payout = Column(Numeric(10, 2), nullable=False)

    # Fulfillment
    fulfillment_status = Column(SQLEnum(FulfillmentStatus), default=FulfillmentStatus.PENDING, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")
    variant = relationship("ProductVariant", back_populates="order_items")
    vendor = relationship("Vendor", back_populates="order_items")
    pickup = relationship("VendorPickup", back_populates="order_item", uselist=False)

    def __repr__(self):
        return f"<OrderItem {self.product_title} x{self.quantity}>"
