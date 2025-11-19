"""Promo code model"""
from sqlalchemy import Column, String, DateTime, Numeric, Integer, Boolean, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid
import enum

from app.core.base import Base


class DiscountType(str, enum.Enum):
    """Discount type enum"""
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


class PromoCode(Base):
    """Promotional code model"""
    __tablename__ = "promo_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Code Details
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)

    # Discount
    discount_type = Column(SQLEnum(DiscountType), nullable=False)
    discount_value = Column(Numeric(10, 2), nullable=False)  # Percentage or fixed amount

    # Conditions
    min_purchase_amount = Column(Numeric(10, 2), default=0.00, nullable=True)
    max_discount_amount = Column(Numeric(10, 2), nullable=True)  # Cap for percentage discounts

    # Usage Limits
    usage_limit = Column(Integer, nullable=True)  # Total uses allowed (null = unlimited)
    usage_count = Column(Integer, default=0, nullable=False)  # Current usage count
    usage_limit_per_user = Column(Integer, default=1, nullable=False)  # Uses per user

    # Validity Period
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_until = Column(DateTime(timezone=True), nullable=False)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<PromoCode {self.code}>"
