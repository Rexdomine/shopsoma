"""User model"""
from sqlalchemy import Column, String, Boolean, DateTime, Date, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.base import Base


class UserRole(str, enum.Enum):
    """User role enum"""
    CUSTOMER = "customer"
    VENDOR = "vendor"
    ADMIN = "admin"


class User(Base):
    """User model"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=True)  # Nullable for magic link
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(50), nullable=True)
    role = Column(SQLEnum(UserRole), default=UserRole.CUSTOMER, nullable=False, index=True)

    email_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    is_guest_created = Column(Boolean, default=False, nullable=False)
    profile_image_url = Column(String, nullable=True)

    # Payment gateway customer IDs
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    paystack_customer_code = Column(String(255), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    vendor = relationship("Vendor", back_populates="user", uselist=False, cascade="all, delete-orphan", foreign_keys="[Vendor.user_id]")
    orders = relationship("Order", back_populates="customer", foreign_keys="[Order.customer_id]")
    addresses = relationship("Address", back_populates="user", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="customer", cascade="all, delete-orphan", foreign_keys="[Review.customer_id]")
    returns = relationship("Return", back_populates="customer", foreign_keys="[Return.customer_id]")
    cart_items = relationship("CartItem", back_populates="user", cascade="all, delete-orphan")
    wishlists = relationship("Wishlist", back_populates="user", cascade="all, delete-orphan")
    preference = relationship("ManagePreference", back_populates="user", uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"
