"""Vendor model"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Numeric, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.base import Base


class KYCStatus(str, enum.Enum):
    """KYC verification status"""
    PENDING = "pending"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class Vendor(Base):
    """Vendor model"""
    __tablename__ = "vendors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    # Business Information
    business_name = Column(String(255), nullable=False)
    business_description = Column(Text, nullable=True)
    business_address = Column(Text, nullable=True)
    business_phone = Column(String(20), nullable=True)

    # KYC Information
    kyc_status = Column(SQLEnum(KYCStatus), default=KYCStatus.PENDING, nullable=False, index=True)
    kyc_document_type = Column(String(50), nullable=True)
    kyc_document_url = Column(Text, nullable=True)
    kyc_submitted_at = Column(DateTime(timezone=True), nullable=True)
    kyc_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    kyc_reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    kyc_rejection_reason = Column(Text, nullable=True)

    # Bank Information
    bank_name = Column(String(100), nullable=True)
    bank_account_number = Column(String(50), nullable=True)
    bank_account_name = Column(String(255), nullable=True)

    # Platform Settings
    commission_rate = Column(Numeric(5, 2), default=12.5, nullable=False)
    approved = Column(Boolean, default=False, nullable=False, index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    # Metrics
    total_products = Column(Integer, default=0, nullable=False)
    total_orders = Column(Integer, default=0, nullable=False)
    total_revenue = Column(Numeric(12, 2), default=0.00, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="vendor", foreign_keys=[user_id])
    products = relationship("Product", back_populates="vendor", cascade="all, delete-orphan")
    order_items = relationship("OrderItem", back_populates="vendor")
    payouts = relationship("Payout", back_populates="vendor")

    def __repr__(self):
        return f"<Vendor {self.business_name}>"
