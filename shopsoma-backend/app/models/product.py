"""Product models"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Numeric, Text, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.base import Base


class ProductStatus(str, enum.Enum):
    """Product status enum"""
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class ModerationStatus(str, enum.Enum):
    """Product moderation status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Product(Base):
    """Product model"""
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)

    # Product Information
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sku = Column(String(100), unique=True, nullable=True, index=True)

    # Pricing
    base_price = Column(Numeric(10, 2), nullable=False)
    compare_at_price = Column(Numeric(10, 2), nullable=True)

    # Inventory (for products without variants)
    total_stock = Column(Integer, default=0, nullable=False)

    # Status
    status = Column(SQLEnum(ProductStatus), default=ProductStatus.DRAFT, nullable=False, index=True)
    is_featured = Column(Boolean, default=False, nullable=False)

    # SEO
    meta_title = Column(String(255), nullable=True)
    meta_description = Column(Text, nullable=True)
    size_guide = Column(JSONB, nullable=True)

    # Metrics
    views_count = Column(Integer, default=0, nullable=False)
    orders_count = Column(Integer, default=0, nullable=False)

    # Moderation
    moderation_status = Column(SQLEnum(ModerationStatus), default=ModerationStatus.PENDING, nullable=False)
    moderated_at = Column(DateTime(timezone=True), nullable=True)
    moderated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    moderation_notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    vendor = relationship("Vendor", back_populates="products")
    category = relationship("Category", back_populates="products")
    variants = relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan", order_by="ProductImage.display_order")
    order_items = relationship("OrderItem", back_populates="product")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")

    @property
    def vendor_name(self):
        """Expose the vendor's business name for API responses."""
        if self.vendor:
            return self.vendor.business_name
        return None

    def __repr__(self):
        return f"<Product {self.title}>"


class ProductVariant(Base):
    """Product variant model (size, color variations)"""
    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint('product_id', 'size', 'color', name='uq_product_variant'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)

    # Variant Attributes
    size = Column(String(50), nullable=True)
    color = Column(String(50), nullable=True)
    color_hex = Column(String(7), nullable=True)  # #FFFFFF

    # Pricing & Stock
    price = Column(Numeric(10, 2), nullable=False)
    stock = Column(Integer, default=0, nullable=False, index=True)
    sku = Column(String(100), unique=True, nullable=True, index=True)

    # Status
    is_available = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    product = relationship("Product", back_populates="variants")
    order_items = relationship("OrderItem", back_populates="variant")

    def __repr__(self):
        return f"<ProductVariant {self.product_id} - {self.size}/{self.color}>"


class ProductImage(Base):
    """Product image model"""
    __tablename__ = "product_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)

    image_url = Column(Text, nullable=False)
    thumbnail_url = Column(Text, nullable=True)
    alt_text = Column(String(255), nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    product = relationship("Product", back_populates="images")

    def __repr__(self):
        return f"<ProductImage {self.product_id}>"
