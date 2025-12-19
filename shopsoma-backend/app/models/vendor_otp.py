"""Vendor OTP model for account activation"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from datetime import datetime, timedelta, timezone

from app.core.base import Base


class VendorOTP(Base):
    """Vendor OTP model for activation"""
    __tablename__ = "vendor_otps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(String(255), nullable=False, index=True)

    # Hashed OTP code (never store plain text)
    code_hash = Column(String(255), nullable=False)

    # Expiration (default 15 minutes from creation)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Attempt tracking for security
    attempts = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=5, nullable=False)

    # Status tracking
    is_used = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    vendor = relationship("Vendor", back_populates="otps")

    def is_expired(self) -> bool:
        """Check if OTP is expired"""
        return datetime.now(timezone.utc) > self.expires_at

    def is_locked(self) -> bool:
        """Check if OTP is locked due to too many attempts"""
        return self.attempts >= self.max_attempts

    def can_verify(self) -> bool:
        """Check if OTP can be verified"""
        return not self.is_used and not self.is_expired() and not self.is_locked()

    def __repr__(self):
        return f"<VendorOTP {self.id} for {self.email}>"
