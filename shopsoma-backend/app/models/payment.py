"""Payment and Payout models"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Text, Date, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.database import Base


class PaymentGateway(str, enum.Enum):
    """Payment gateway enum"""
    STRIPE = "stripe"
    PAYSTACK = "paystack"


class TransactionStatus(str, enum.Enum):
    """Transaction status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PayoutStatus(str, enum.Enum):
    """Payout status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Payment(Base):
    """Payment transaction model"""
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Payment Details
    payment_gateway = Column(SQLEnum(PaymentGateway), nullable=False)
    transaction_id = Column(String(255), unique=True, nullable=True, index=True)
    payment_method = Column(String(50), nullable=True)  # card, bank_transfer

    # Amount
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="NGN", nullable=False)

    # Status
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False, index=True)

    # Gateway Response
    gateway_response = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="payments")

    def __repr__(self):
        return f"<Payment {self.transaction_id} - {self.amount} {self.currency}>"


class Payout(Base):
    """Vendor payout model"""
    __tablename__ = "payouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Payout Details
    payout_period_start = Column(Date, nullable=False)
    payout_period_end = Column(Date, nullable=False)

    # Amounts
    total_sales = Column(Numeric(12, 2), nullable=False)
    commission_amount = Column(Numeric(12, 2), nullable=False)
    payout_amount = Column(Numeric(12, 2), nullable=False)

    # Status
    status = Column(SQLEnum(PayoutStatus), default=PayoutStatus.PENDING, nullable=False, index=True)

    # Processing
    processed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    payment_reference = Column(String(100), nullable=True)

    # Notes
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    vendor = relationship("Vendor", back_populates="payouts")
    processor = relationship("User", foreign_keys=[processed_by])

    def __repr__(self):
        return f"<Payout {self.vendor_id} - {self.payout_amount}>"
