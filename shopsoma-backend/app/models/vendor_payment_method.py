"""Vendor Payment Method model"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.core.base import Base


class VendorPaymentMethod(Base):
    """Model for vendor payment methods (bank accounts)"""
    __tablename__ = "vendor_payment_methods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)

    # Bank account details
    account_type = Column(String(50), nullable=True)  # Checking or Savings
    bank_name = Column(String(100), nullable=False)
    account_number = Column(String(50), nullable=False)
    account_holder = Column(String(255), nullable=False)

    # TIN (optional, can be shared across methods or specific)
    tin = Column(String(50), nullable=True)

    # Default flag - only one per vendor should be true
    is_default = Column(Boolean, default=False, nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    vendor = relationship("Vendor", back_populates="payment_methods")

    def __repr__(self):
        return f"<VendorPaymentMethod {self.bank_name} (****{self.account_number[-4:]})>"

    def to_dict(self):
        """Convert to dictionary with masked account number"""
        return {
            "id": str(self.id),
            "vendor_id": str(self.vendor_id),
            "account_type": self.account_type,
            "bank_name": self.bank_name,
            "account_number": self.account_number,
            "masked_account": f"****{self.account_number[-4:]}",
            "account_holder": self.account_holder,
            "tin": self.tin,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
