"""Shipping rate model"""
from sqlalchemy import Column, String, DateTime, Numeric, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.core.base import Base


class ShippingRate(Base):
    """Configurable shipping rate model"""
    __tablename__ = "shipping_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Rate Details
    name = Column(String(100), nullable=False)  # e.g., "Standard Shipping", "Express Delivery"
    description = Column(String(500), nullable=True)  # e.g., "2-4 business days"

    # Pricing
    base_rate = Column(Numeric(10, 2), nullable=False)  # Base shipping cost

    # Geographic Restrictions
    country = Column(String(100), default="Nigeria", nullable=False)
    state = Column(String(100), nullable=True)  # Null means all states

    # Conditions
    min_order_value = Column(Numeric(10, 2), default=0.00, nullable=True)  # Free shipping threshold
    max_order_value = Column(Numeric(10, 2), nullable=True)  # Maximum order value for this rate

    # Delivery Time
    min_delivery_days = Column(Integer, default=2, nullable=False)
    max_delivery_days = Column(Integer, default=5, nullable=False)

    # Status
    is_active = Column(Boolean, default=True, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)

    # Priority (lower number = higher priority when multiple rates match)
    priority = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<ShippingRate {self.name} - ₦{self.base_rate}>"
