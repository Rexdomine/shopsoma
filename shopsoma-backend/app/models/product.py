"""Product models"""

from sqlalchemy import (
    Column,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    Enum as SQLEnum,
    UniqueConstraint,
    inspect,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.orm.attributes import NO_VALUE
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


class ProductType(str, enum.Enum):
    """Product type enum"""

    SINGLE = "single"  # Single product with base color/size
    VARIABLE = "variable"  # Variable product with variations


class Product(Base):
    """Product model"""

    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    collection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Product Information
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sku = Column(String(100), unique=True, nullable=True, index=True)

    # Pricing
    base_price = Column(Numeric(10, 2), nullable=False)
    compare_at_price = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="NGN", nullable=False)  # NGN or USD

    # Inventory (for products without variants)
    total_stock = Column(Integer, default=0, nullable=False)

    # Status
    status = Column(
        SQLEnum(ProductStatus), default=ProductStatus.DRAFT, nullable=False, index=True
    )
    is_featured = Column(Boolean, default=False, nullable=False)
    product_type = Column(
        SQLEnum(ProductType), default=ProductType.SINGLE, nullable=False, index=True
    )

    # Made to Order
    made_to_order = Column(Boolean, default=False, nullable=False)
    made_to_order_timeline = Column(
        String(255), nullable=True
    )  # e.g., "Ships in 2-3 weeks"

    # Product Details
    care_instructions = Column(Text, nullable=True)
    fabric_composition = Column(Text, nullable=True)

    # Shipping parcel facts supplied by the vendor and used for DHL rating.
    weight_kg = Column(Numeric(10, 3), nullable=True)
    length_cm = Column(Numeric(10, 3), nullable=True)
    width_cm = Column(Numeric(10, 3), nullable=True)
    height_cm = Column(Numeric(10, 3), nullable=True)

    # SEO
    meta_title = Column(String(255), nullable=True)
    meta_description = Column(Text, nullable=True)
    size_guide = Column(JSONB, nullable=True)

    # Metrics
    views_count = Column(Integer, default=0, nullable=False)
    orders_count = Column(Integer, default=0, nullable=False)

    # Moderation
    moderation_status = Column(
        SQLEnum(ModerationStatus), default=ModerationStatus.PENDING, nullable=False
    )
    moderated_at = Column(DateTime(timezone=True), nullable=True)
    moderated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    moderation_notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    vendor = relationship("Vendor", back_populates="products")
    category = relationship("Category", back_populates="products")
    collection = relationship("Collection", back_populates="products")
    variants = relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan"
    )
    variations = relationship(
        "Variation", back_populates="product", cascade="all, delete-orphan"
    )
    images = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.display_order",
    )
    order_items = relationship(
        "OrderItem", back_populates="product", foreign_keys="OrderItem.product_id"
    )
    reviews = relationship(
        "Review", back_populates="product", cascade="all, delete-orphan"
    )

    @property
    def vendor_name(self):
        """Expose the vendor's business name for API responses."""
        if self.vendor:
            return self.vendor.business_name
        return None

    @property
    def category_name(self):
        """Expose the category name for API responses."""
        if self.category:
            return self.category.name
        return None

    @property
    def collection_name(self):
        """Expose the collection name for API responses."""
        if self.collection:
            return self.collection.name
        return None

    @property
    def category_parent_name(self):
        """Expose the parent category name for API responses."""
        if not self.category:
            return None

        parent_attr = inspect(self.category).attrs.parent
        if parent_attr.loaded_value is NO_VALUE:
            return None

        parent = parent_attr.loaded_value
        if parent:
            return parent.name
        return None

    def __repr__(self):
        return f"<Product {self.title}>"


class ProductVariant(Base):
    """Product variant model (size, color variations)"""

    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("product_id", "size", "color", name="uq_product_variant"),
        UniqueConstraint("product_id", "id", name="uq_product_variants_product_id_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    product = relationship("Product", back_populates="variants")
    order_items = relationship("OrderItem", back_populates="variant")

    def __repr__(self):
        return f"<ProductVariant {self.product_id} - {self.size}/{self.color}>"


class ProductImage(Base):
    """Product image model"""

    __tablename__ = "product_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    image_url = Column(Text, nullable=False)
    thumbnail_url = Column(Text, nullable=True)
    alt_text = Column(String(255), nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    product = relationship("Product", back_populates="images")

    def __repr__(self):
        return f"<ProductImage {self.product_id}>"


class SizeEnum(str, enum.Enum):
    """Size enum"""

    XXS = "XXS"
    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"
    XXL = "XXL"
    XXXL = "XXXL"


class Variation(Base):
    """Product variation model (e.g., different colors)"""

    __tablename__ = "variations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Variation details
    title = Column(String(100), nullable=False)  # e.g., "Black", "Red Print"
    type = Column(String(50), default="color", nullable=False)  # e.g., "color"
    color_hex = Column(String(7), nullable=True)  # e.g., "#000000"

    # Pricing (optional override of product base price)
    price = Column(Numeric(10, 2), nullable=True)  # if null → use product.base_price
    sale_price = Column(
        Numeric(10, 2), nullable=True
    )  # if null → use product.base_sale_price

    # Images for this variation (stored as JSON array)
    images = Column(JSONB, nullable=True, default=list)  # ["url1", "url2", ...]

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    product = relationship("Product", back_populates="variations")
    size_stocks = relationship(
        "SizeStock", back_populates="variation", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Variation {self.title}>"


class SizeStock(Base):
    """Size stock for a specific variation"""

    __tablename__ = "size_stocks"
    __table_args__ = (
        UniqueConstraint("variation_id", "size", name="uq_variation_size"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("variations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Size and stock
    size = Column(SQLEnum(SizeEnum), nullable=False)
    stock = Column(Integer, default=0, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    variation = relationship("Variation", back_populates="size_stocks")

    def __repr__(self):
        return f"<SizeStock {self.size} - {self.stock}>"
