"""
Product Pydantic schemas for request/response validation
"""
from typing import Optional, List
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


def effective_variation_price(
    price: Optional[Decimal],
    sale_price: Optional[Decimal],
    fallback: Decimal,
) -> Decimal:
    """Return the effective purchasable price for a variation."""
    regular_price = price if price is not None else fallback
    if sale_price is not None and sale_price > 0 and sale_price < regular_price:
        return sale_price
    return regular_price


def normalize_color_value(value: Optional[str]) -> str:
    """Normalize color labels for matching legacy variants to variations."""
    return (value or "").strip().casefold()


COLOR_VARIATION_TYPES = {"color", "solid", "multi", "none"}


def is_color_variation_type(value: str) -> bool:
    """Treat every non-size variation type as a color axis."""
    return value.casefold() != "size"


def validate_variation_inventory_shape(
    variations: Optional[List["VariationCreate"]],
    variants: Optional[List["ProductVariantCreate"]] = None,
) -> None:
    """Reject variation combinations without one canonical inventory source."""
    all_variations = list(variations or [])
    size_variation_labels = [
        normalize_color_value(variation.title)
        for variation in all_variations
        if variation.type.casefold() == "size"
    ]
    if len(size_variation_labels) != len(set(size_variation_labels)):
        raise ValueError("Size variation labels must be unique after normalization")

    active_variations = [variation for variation in all_variations if variation.is_active]
    color_variations = [
        variation
        for variation in active_variations
        if is_color_variation_type(variation.type)
    ]
    size_variations = [
        variation
        for variation in active_variations
        if variation.type.casefold() == "size"
    ]

    legacy_variants = list(variants or [])
    legacy_color_variants = [
        variant for variant in legacy_variants if getattr(variant, "color", None) is not None
    ]
    if (color_variations or legacy_color_variants) and size_variations:
        raise ValueError(
            "Color and size variations cannot be combined until a "
            "color-size inventory matrix is supported"
        )

    size_stock_labels = {
        normalize_color_value(getattr(size, "size", None))
        for variation in active_variations
        for size in (
            (
                getattr(variation, "sizes", None)
                if getattr(variation, "sizes", None) is not None
                else getattr(variation, "size_stocks", [])
            )
            or []
        )
    }
    if any(
        normalize_color_value(variant.size) in size_stock_labels
        for variant in legacy_variants
        if variant.size is not None
    ):
        raise ValueError(
            "Legacy variants cannot duplicate size variation inventory; "
            "use one canonical stock source per size"
        )

    has_color_backed_size_stocks = any(
        is_color_variation_type(variation.type)
        and bool(
            (
                getattr(variation, "sizes", None)
                if getattr(variation, "sizes", None) is not None
                else getattr(variation, "size_stocks", [])
            )
            or []
        )
        for variation in active_variations
    )
    if has_color_backed_size_stocks and legacy_variants:
        raise ValueError(
            "Legacy variants cannot coexist with color variation size stock; "
            "use variation-backed inventory as the sole stock source"
        )

def unique_variations_by_color(variations: List["VariationResponse"]) -> dict[str, "VariationResponse"]:
    """Index only unambiguous variation colors, avoiding collision-dependent pricing."""
    indexed: dict[str, VariationResponse] = {}
    collisions: set[str] = set()
    for variation in variations:
        if not variation.is_active or not is_color_variation_type(variation.type):
            continue
        key = normalize_color_value(variation.title)
        if not key or key in collisions:
            continue
        if key in indexed:
            del indexed[key]
            collisions.add(key)
            continue
        indexed[key] = variation
    return indexed


def unique_variations_by_size(variations: List["VariationResponse"]) -> dict[str, "VariationResponse"]:
    """Index only unambiguous size variation labels."""
    indexed: dict[str, VariationResponse] = {}
    collisions: set[str] = set()
    for variation in variations:
        if not variation.is_active or variation.type.casefold() != "size":
            continue
        key = normalize_color_value(variation.title)
        if not key or key in collisions:
            continue
        if key in indexed:
            del indexed[key]
            collisions.add(key)
            continue
        indexed[key] = variation
    return indexed


# ============================================================================
# Product Image Schemas
# ============================================================================

class SizeGuideRow(BaseModel):
    """Row entry for size conversion"""
    label: str = Field(..., min_length=1, max_length=50)
    standard: Optional[str] = Field(None, max_length=50)
    measurement: Optional[str] = Field(None, max_length=100)


class SizeGuide(BaseModel):
    """Size guide schema"""
    title: Optional[str] = Field(None, max_length=100)
    subtitle: Optional[str] = Field(None, max_length=255)
    gender: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=500)
    rows: List[SizeGuideRow] = Field(default_factory=list)


class ProductImageBase(BaseModel):
    """Base product image schema"""
    image_url: str = Field(..., min_length=1, max_length=2048, description="Image URL")
    thumbnail_url: Optional[str] = Field(None, max_length=2048, description="Thumbnail URL")
    alt_text: Optional[str] = Field(None, max_length=255, description="Alternative text for accessibility")
    display_order: int = Field(default=0, ge=0, description="Display order (0 = first)")
    is_primary: bool = Field(default=False, description="Primary product image")


class ProductImageCreate(ProductImageBase):
    """Schema for creating product image"""
    pass


class ProductImageUpdate(BaseModel):
    """Schema for updating product image"""
    image_url: Optional[str] = Field(None, min_length=1, max_length=2048)
    thumbnail_url: Optional[str] = Field(None, max_length=2048)
    alt_text: Optional[str] = Field(None, max_length=255)
    display_order: Optional[int] = Field(None, ge=0)
    is_primary: Optional[bool] = None


class ProductImageResponse(ProductImageBase):
    """Schema for product image response"""
    id: UUID
    product_id: UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Size Stock Schemas
# ============================================================================

class SizeStockBase(BaseModel):
    """Base size stock schema

    Supports three sizing systems:
    - US Sizing: Letter sizes (XXS, XS, S, M, L, XL, XXL, XXXL)
    - UK Sizing: Numeric sizes (4, 6, 8, 10, 12, 14, 16, 18, 20, 22)
    - EU Sizing: Numeric sizes (32, 34, 36, 38, 40, 42, 44, 46, 48, 50)
    """
    size: str = Field(
        ...,
        pattern="^(XXS|XS|S|M|L|XL|XXL|XXXL|4|6|8|10|12|14|16|18|20|22|32|34|36|38|40|42|44|46|48|50)$",
        description="Size (US/UK/EU sizing)"
    )
    stock: int = Field(default=0, ge=0, description="Stock quantity")


class SizeStockCreate(SizeStockBase):
    """Schema for creating size stock"""
    pass


class SizeStockUpdate(BaseModel):
    """Schema for updating size stock"""
    stock: Optional[int] = Field(None, ge=0)


class SizeStockResponse(SizeStockBase):
    """Schema for size stock response"""
    id: UUID
    variation_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Variation Schemas
# ============================================================================

class VariationBase(BaseModel):
    """Base variation schema"""
    title: str = Field(..., min_length=1, max_length=100, description="Variation title (e.g., 'Black', 'Red Print')")
    type: str = Field(default="color", max_length=50, description="Variation type (e.g., 'color')")
    color_hex: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$", description="Color hex code")
    price: Optional[Decimal] = Field(None, gt=0, decimal_places=2, description="Price override (if null, uses product base_price)")
    sale_price: Optional[Decimal] = Field(None, gt=0, decimal_places=2, description="Sale price override")
    images: List[str] = Field(default_factory=list, description="Image URLs for this variation")
    is_active: bool = Field(default=True, description="Variation active status")

    @field_validator("price", "sale_price")
    @classmethod
    def validate_price(cls, v):
        """Validate price"""
        if v is not None:
            if v <= 0:
                raise ValueError("Price must be greater than 0")
            if v > 999999.99:
                raise ValueError("Price cannot exceed 999,999.99")
            return round(v, 2)
        return v


class VariationCreate(VariationBase):
    """Schema for creating variation"""
    sizes: List[SizeStockCreate] = Field(default_factory=list, description="Optional size stock array")


class VariationUpdate(BaseModel):
    """Schema for updating variation"""
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    type: Optional[str] = Field(None, max_length=50)
    color_hex: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    sale_price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    images: Optional[List[str]] = None
    is_active: Optional[bool] = None
    sizes: Optional[List[SizeStockCreate]] = None  # For sync operations

    @field_validator("price", "sale_price")
    @classmethod
    def validate_price(cls, v):
        """Validate price"""
        if v is not None:
            if v <= 0:
                raise ValueError("Price must be greater than 0")
            if v > 999999.99:
                raise ValueError("Price cannot exceed 999,999.99")
            return round(v, 2)
        return v


class VariationResponse(VariationBase):
    """Schema for variation response"""
    id: UUID
    product_id: UUID
    created_at: datetime
    updated_at: datetime
    size_stocks: List[SizeStockResponse] = []

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("size_stocks", mode="before")
    @classmethod
    def ensure_list(cls, v):
        """Ensure size_stocks is always a list"""
        if v is None:
            return []
        return v


# ============================================================================
# Product Variant Schemas
# ============================================================================

class ProductVariantBase(BaseModel):
    """Base product variant schema"""
    size: Optional[str] = Field(None, max_length=50, description="Size (XS, S, M, L, XL, etc.)")
    color: Optional[str] = Field(None, max_length=50, description="Color name")
    color_hex: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$", description="Color hex code")
    price: Decimal = Field(..., gt=0, decimal_places=2, description="Variant price")
    stock: int = Field(default=0, ge=0, description="Stock quantity")
    sku: Optional[str] = Field(None, max_length=100, description="Stock Keeping Unit")
    is_available: bool = Field(default=True, description="Variant availability")

    @field_validator("price")
    @classmethod
    def validate_price(cls, v):
        """Validate price is positive and has max 2 decimal places"""
        if v <= 0:
            raise ValueError("Price must be greater than 0")
        if v > 999999.99:
            raise ValueError("Price cannot exceed 999,999.99")
        return round(v, 2)


class ProductVariantCreate(ProductVariantBase):
    """Schema for creating product variant"""
    pass


class ProductVariantUpdate(BaseModel):
    """Schema for updating product variant"""
    size: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=50)
    color_hex: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    stock: Optional[int] = Field(None, ge=0)
    sku: Optional[str] = Field(None, max_length=100)
    is_available: Optional[bool] = None

    @field_validator("price")
    @classmethod
    def validate_price(cls, v):
        """Validate price"""
        if v is not None:
            if v <= 0:
                raise ValueError("Price must be greater than 0")
            if v > 999999.99:
                raise ValueError("Price cannot exceed 999,999.99")
            return round(v, 2)
        return v


class ProductVariantResponse(ProductVariantBase):
    """Schema for product variant response"""
    id: UUID
    product_id: UUID
    compare_at_price: Optional[Decimal] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Product Schemas
# ============================================================================

class ProductBase(BaseModel):
    """Base product schema"""
    title: str = Field(..., min_length=3, max_length=255, description="Product title")
    description: Optional[str] = Field(None, max_length=5000, description="Product description")
    category_id: Optional[UUID] = Field(None, description="Category UUID")
    collection_id: Optional[UUID] = Field(None, description="Collection UUID")
    sku: Optional[str] = Field(None, max_length=100, description="Stock Keeping Unit")
    base_price: Decimal = Field(..., gt=0, decimal_places=2, description="Base price")
    compare_at_price: Optional[Decimal] = Field(None, gt=0, decimal_places=2, description="Compare at price (original price)")
    currency: str = Field(default="NGN", pattern="^(NGN|USD)$", description="Currency code: NGN or USD")
    total_stock: int = Field(default=0, ge=0, description="Total stock (for products without variants)")
    status: str = Field(default="draft", pattern="^(draft|active|inactive|archived)$", description="Product status")
    is_featured: bool = Field(default=False, description="Featured product")
    product_type: str = Field(default="single", pattern="^(single|variable)$", description="Product type: single or variable")
    made_to_order: bool = Field(default=False, description="Product is made to order")
    made_to_order_timeline: Optional[str] = Field(None, max_length=255, description="Made to order timeline (e.g., 'Ships in 2-3 weeks')")
    care_instructions: Optional[str] = Field(None, max_length=5000, description="Product care instructions")
    fabric_composition: Optional[str] = Field(None, max_length=5000, description="Fabric/material composition")
    weight_kg: Optional[Decimal] = Field(None, ge=Decimal("0.001"), le=9999999.999, description="Packed product weight in kilograms")
    length_cm: Optional[Decimal] = Field(None, ge=Decimal("0.001"), le=9999999.999, description="Packed product length in centimeters")
    width_cm: Optional[Decimal] = Field(None, ge=Decimal("0.001"), le=9999999.999, description="Packed product width in centimeters")
    height_cm: Optional[Decimal] = Field(None, ge=Decimal("0.001"), le=9999999.999, description="Packed product height in centimeters")
    meta_title: Optional[str] = Field(None, max_length=255, description="SEO meta title")
    meta_description: Optional[str] = Field(None, max_length=500, description="SEO meta description")
    size_guide: Optional[SizeGuide] = Field(default=None, description="Optional size guide information")

    @field_validator("base_price", "compare_at_price")
    @classmethod
    def validate_price(cls, v):
        """Validate price is positive and has max 2 decimal places"""
        if v is not None:
            if v <= 0:
                raise ValueError("Price must be greater than 0")
            if v > 999999.99:
                raise ValueError("Price cannot exceed 999,999.99")
            return round(v, 2)
        return v

    @field_validator("compare_at_price")
    @classmethod
    def validate_compare_price(cls, v, info):
        """Validate compare_at_price (original price) is greater than or equal to base_price (sale price)

        E-commerce standard:
        - base_price: Current selling price (what customer pays)
        - compare_at_price: Original/MSRP price for comparison (shown crossed out)
        - compare_at_price should be >= base_price to show savings
        """
        if v is not None and "base_price" in info.data:
            base_price = info.data["base_price"]
            if v < base_price:
                raise ValueError(
                    f"Compare at price (${v}) must be greater than or equal to base price (${base_price}). "
                    "Compare at price is the original price shown for comparison."
                )
        return v


class ProductCreate(ProductBase):
    """Schema for creating product"""
    # Nested creation
    variants: Optional[List[ProductVariantCreate]] = Field(default=None, description="Product variants (legacy)")
    variations: Optional[List[VariationCreate]] = Field(default=None, description="Product variations (color/style variations with sizes)")
    images: Optional[List[ProductImageCreate]] = Field(default=None, max_length=10, description="Product images (max 10)")

    @field_validator("images")
    @classmethod
    def validate_images(cls, v):
        """Validate at least one primary image"""
        if v and len(v) > 0:
            primary_count = sum(1 for img in v if img.is_primary)
            if primary_count == 0:
                # Set first image as primary
                v[0].is_primary = True
            elif primary_count > 1:
                raise ValueError("Only one image can be marked as primary")
        return v

    @model_validator(mode="after")
    def validate_made_to_order(self) -> "ProductCreate":
        """Made-to-order products should rely on timeline, not stock."""
        if self.made_to_order:
            if not self.made_to_order_timeline or not self.made_to_order_timeline.strip():
                raise ValueError("Made-to-order products require a production timeline")
            self.total_stock = 0
        return self

    @model_validator(mode="after")
    def validate_variation_inventory_shape(self) -> "ProductCreate":
        """Reject combinations that cannot represent one canonical stock source."""
        validate_variation_inventory_shape(self.variations, self.variants)
        return self


class ProductUpdate(BaseModel):
    """Schema for updating product"""
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = Field(None, max_length=5000)
    category_id: Optional[UUID] = None
    sku: Optional[str] = Field(None, max_length=100)
    base_price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    compare_at_price: Optional[Decimal] = Field(None, gt=0, decimal_places=2)
    currency: Optional[str] = Field(None, pattern="^(NGN|USD)$")
    total_stock: Optional[int] = Field(None, ge=0)
    status: Optional[str] = Field(None, pattern="^(draft|active|inactive|archived)$")
    is_featured: Optional[bool] = None
    product_type: Optional[str] = Field(None, pattern="^(single|variable)$")
    made_to_order: Optional[bool] = None
    made_to_order_timeline: Optional[str] = Field(None, max_length=255)
    care_instructions: Optional[str] = Field(None, max_length=5000)
    fabric_composition: Optional[str] = Field(None, max_length=5000)
    weight_kg: Optional[Decimal] = Field(None, ge=Decimal("0.001"), le=9999999.999)
    length_cm: Optional[Decimal] = Field(None, ge=Decimal("0.001"), le=9999999.999)
    width_cm: Optional[Decimal] = Field(None, ge=Decimal("0.001"), le=9999999.999)
    height_cm: Optional[Decimal] = Field(None, ge=Decimal("0.001"), le=9999999.999)
    meta_title: Optional[str] = Field(None, max_length=255)
    meta_description: Optional[str] = Field(None, max_length=500)
    size_guide: Optional[SizeGuide] = None
    variations: Optional[List[VariationCreate]] = None  # For sync operations

    @field_validator("base_price", "compare_at_price")
    @classmethod
    def validate_price(cls, v):
        """Validate price"""
        if v is not None:
            if v <= 0:
                raise ValueError("Price must be greater than 0")
            if v > 999999.99:
                raise ValueError("Price cannot exceed 999,999.99")
            return round(v, 2)
        return v

    @model_validator(mode="after")
    def validate_made_to_order(self) -> "ProductUpdate":
        """Keep made-to-order updates internally consistent."""
        if self.made_to_order is True:
            if not self.made_to_order_timeline or not self.made_to_order_timeline.strip():
                raise ValueError("Made-to-order products require a production timeline")
            self.total_stock = 0
        validate_variation_inventory_shape(self.variations)
        return self


class ProductResponse(ProductBase):
    """Schema for product response"""
    id: UUID
    vendor_id: UUID
    vendor_name: Optional[str] = None
    category_name: Optional[str] = None
    category_parent_name: Optional[str] = None
    collection_name: Optional[str] = None
    moderation_status: str
    moderation_notes: Optional[str] = None
    views_count: int
    orders_count: int
    created_at: datetime
    updated_at: datetime

    # Nested relationships
    variants: List[ProductVariantResponse] = []
    variations: List[VariationResponse] = []
    images: List[ProductImageResponse] = []

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def generate_variants_from_variations(self) -> "ProductResponse":
        """
        Auto-generate variants from variations for consistent frontend consumption.

        If product has variations (vendor-uploaded products), explode them into variants.
        This allows frontend to use a single data structure (variants) regardless of
        whether product was created via admin (variants) or vendor (variations).
        """
        # If product already has variants, preserve them but merge matching
        # variation pricing so persisted legacy variants expose the same
        # effective and compare-at prices as vendor variation responses.
        if self.variants:
            if self.variations:
                variations_by_title = unique_variations_by_color(self.variations)
                variations_by_size = unique_variations_by_size(self.variations)
                color_variations = [
                    variation
                    for variation in self.variations
                    if is_color_variation_type(variation.type) and variation.is_active
                ]
                size_variant_color = (
                    color_variations[0].title if len(color_variations) == 1 else None
                )
                size_variant_color_hex = (
                    color_variations[0].color_hex if len(color_variations) == 1 else None
                )
                for variant in self.variants:
                    variation = None
                    if variant.color is not None:
                        variation = variations_by_title.get(normalize_color_value(variant.color))
                    if variation is None and variant.size is not None:
                        variation = variations_by_size.get(normalize_color_value(variant.size))
                    if variation is None:
                        continue
                    if variation.price is None and variation.sale_price is None:
                        continue

                    variant_price = effective_variation_price(
                        variation.price, variation.sale_price, self.base_price
                    )
                    regular_price = (
                        variation.price if variation.price is not None else self.base_price
                    )
                    variant.price = variant_price
                    variant.compare_at_price = (
                        regular_price if variant_price < regular_price else None
                    )

                existing_inventory = {
                    (
                        normalize_color_value(variant.size),
                        normalize_color_value(variant.color),
                    )
                    for variant in self.variants
                    if variant.size is not None
                }
                for variation in self.variations:
                    if not variation.is_active or not variation.size_stocks:
                        continue
                    variant_price = effective_variation_price(
                        variation.price, variation.sale_price, self.base_price
                    )
                    regular_price = (
                        variation.price if variation.price is not None else self.base_price
                    )
                    compare_at_price = (
                        regular_price if variant_price < regular_price else None
                    )
                    variation_color = (
                        size_variant_color
                        if not is_color_variation_type(variation.type)
                        else variation.title
                    )
                    for size_stock in variation.size_stocks:
                        size = getattr(size_stock.size, "value", str(size_stock.size))
                        inventory_key = (
                            normalize_color_value(size),
                            normalize_color_value(variation_color),
                        )
                        if inventory_key in existing_inventory:
                            continue
                        self.variants.append(
                            ProductVariantResponse.model_validate(
                                {
                                    "id": size_stock.id,
                                    "product_id": self.id,
                                    "size": size,
                                    "color": variation_color,
                                    "color_hex": (
                                        size_variant_color_hex
                                        if not is_color_variation_type(variation.type)
                                        else variation.color_hex
                                    ),
                                    "price": variant_price,
                                    "compare_at_price": compare_at_price,
                                    "stock": size_stock.stock,
                                    "sku": None,
                                    "is_available": bool(variation.is_active)
                                    and size_stock.stock > 0,
                                    "created_at": variation.created_at,
                                    "updated_at": variation.updated_at,
                                }
                            )
                        )
                        existing_inventory.add(inventory_key)
            return self

        # If product has variations (vendor-created), generate variants
        if self.variations:
            generated_variants = []

            for variation in self.variations:
                if not variation.is_active:
                    continue
                # Normalize variation pricing to the legacy variant contract:
                # `price` is the effective purchase price and `compare_at_price`
                # retains the regular price when a valid sale is configured.
                variant_price = effective_variation_price(
                    variation.price, variation.sale_price, self.base_price
                )
                regular_price = (
                    variation.price if variation.price is not None else self.base_price
                )
                has_valid_sale = variant_price < regular_price
                compare_at_price = regular_price if has_valid_sale else None

                # If variation has no size_stocks, create one variant with no size
                if not variation.size_stocks:
                    # Build variant dict with only the fields that exist in ProductVariantResponse
                    variant_dict = {
                        "id": variation.id,
                        "product_id": self.id,
                        "size": None,
                        "color": None if variation.type.casefold() == "size" else variation.title,
                        "color_hex": variation.color_hex,
                        "price": variant_price,
                        "compare_at_price": compare_at_price,
                        "stock": 0,
                        "sku": None,
                        "is_available": bool(variation.is_active),
                        "created_at": variation.created_at,
                        "updated_at": variation.updated_at,
                    }
                    generated_variants.append(ProductVariantResponse.model_validate(variant_dict))
                else:
                    # Create one variant per size in size_stocks
                    for size_stock in variation.size_stocks:
                        variant_dict = {
                            "id": size_stock.id,
                            "product_id": self.id,
                            "size": size_stock.size,
                            "color": None if variation.type.casefold() == "size" else variation.title,
                            "color_hex": variation.color_hex,
                            "price": variant_price,
                            "compare_at_price": compare_at_price,
                            "stock": size_stock.stock,
                            "sku": None,
                            "is_available": bool(variation.is_active) and size_stock.stock > 0,
                            "created_at": variation.created_at,
                            "updated_at": variation.updated_at,
                        }
                        generated_variants.append(ProductVariantResponse.model_validate(variant_dict))

            # Replace empty variants list with generated ones
            self.variants = generated_variants

        return self


class ProductListResponse(BaseModel):
    """Schema for product list with pagination"""
    products: List[ProductResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ProductSearchParams(BaseModel):
    """Schema for product search parameters"""
    search: Optional[str] = Field(None, max_length=255, description="Search in title and description")
    category_id: Optional[UUID] = Field(None, description="Filter by category")
    vendor_id: Optional[UUID] = Field(None, description="Filter by vendor")
    status: Optional[str] = Field(None, pattern="^(draft|active|inactive|archived)$", description="Filter by status")
    min_price: Optional[Decimal] = Field(None, ge=0, description="Minimum price")
    max_price: Optional[Decimal] = Field(None, ge=0, description="Maximum price")
    is_featured: Optional[bool] = Field(None, description="Filter featured products")
    in_stock: Optional[bool] = Field(None, description="Filter in-stock products")
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")
    sort_by: str = Field(default="created_at", pattern="^(created_at|title|base_price|orders_count|views_count)$")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$")


# ============================================================================
# Admin Moderation Schemas
# ============================================================================

class ProductModerationUpdate(BaseModel):
    """Schema for admin product moderation"""
    moderation_status: str = Field(..., pattern="^(pending|approved|rejected)$")
    moderation_notes: Optional[str] = Field(None, max_length=1000)


class ProductApprovalRequest(BaseModel):
    """Schema for approving a product"""
    notes: Optional[str] = Field(None, max_length=500, description="Optional approval notes")


class ProductRejectionRequest(BaseModel):
    """Schema for rejecting a product"""
    reason: str = Field(..., min_length=10, max_length=1000, description="Rejection reason (required)")
    notes: Optional[str] = Field(None, max_length=500, description="Additional notes")


class ProductFeatureUpdate(BaseModel):
    """Schema for toggling a product's featured status"""
    is_featured: bool = Field(..., description="Whether the product is featured")
