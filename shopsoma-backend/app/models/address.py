"""Address model"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.database import Base


class AddressType(str, enum.Enum):
    """Address type enum"""
    SHIPPING = "shipping"
    BILLING = "billing"


class Address(Base):
    """Customer address model"""
    __tablename__ = "addresses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Address Type
    address_type = Column(SQLEnum(AddressType), default=AddressType.SHIPPING, nullable=False)

    # Address Details
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=False)
    address_line1 = Column(String(255), nullable=False)
    address_line2 = Column(String(255), nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), default="Nigeria", nullable=False)

    # Flags
    is_default = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="addresses")

    def __repr__(self):
        return f"<Address {self.full_name} - {self.city}>"
