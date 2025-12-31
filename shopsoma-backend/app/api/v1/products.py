"""
Product CRUD API endpoints
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.api.dependencies import get_current_user, get_current_vendor, get_current_admin, get_optional_user
from app.models.user import User
from app.models.category import Category
from app.models.product import Product, ProductVariant, ProductImage, ProductStatus, ProductType, ModerationStatus, Variation, SizeStock, SizeEnum
from app.models.vendor import Vendor
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductListResponse,
    ProductSearchParams,
    ProductVariantCreate,
    ProductVariantUpdate,
    ProductVariantResponse,
    ProductImageCreate,
    ProductImageUpdate,
    ProductImageResponse,
    ProductModerationUpdate,
    VariationCreate,
    VariationUpdate,
    VariationResponse,
    SizeStockCreate,
    SizeStockResponse,
)

router = APIRouter(prefix="/products", tags=["products"])

PRODUCT_RELATIONSHIPS = (
    selectinload(Product.variants),
    selectinload(Product.variations).selectinload(Variation.size_stocks),
    selectinload(Product.images),
    selectinload(Product.vendor),
    selectinload(Product.category).selectinload(Category.parent),
    selectinload(Product.collection),
)

# ============================================================================
# Product CRUD Endpoints
# ============================================================================

@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    product_data: ProductCreate,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new product (vendors only)

    - **title**: Product title (required, 3-255 chars)
    - **description**: Product description
    - **base_price**: Base price (required, > 0)
    - **category_id**: Category UUID
    - **variants**: Optional list of variants
    - **images**: Optional list of images (max 10)
    """
    # Get vendor record
    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor profile not found"
        )

    if not vendor.approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor account not approved yet"
        )

    # Create product
    product = Product(
        vendor_id=vendor.id,
        title=product_data.title,
        description=product_data.description,
        category_id=product_data.category_id,
        collection_id=product_data.collection_id,
        sku=product_data.sku,
        base_price=product_data.base_price,
        compare_at_price=product_data.compare_at_price,
        currency=product_data.currency,
        total_stock=product_data.total_stock,
        status=ProductStatus(product_data.status),
        is_featured=product_data.is_featured,
        product_type=ProductType(product_data.product_type),
        made_to_order=product_data.made_to_order,
        made_to_order_timeline=product_data.made_to_order_timeline,
        care_instructions=product_data.care_instructions,
        fabric_composition=product_data.fabric_composition,
        meta_title=product_data.meta_title,
        meta_description=product_data.meta_description,
        size_guide=product_data.size_guide.model_dump() if product_data.size_guide else None,
        moderation_status=ModerationStatus.PENDING,
    )

    db.add(product)
    await db.flush()  # Get product ID

    # Add variations if provided (new system)
    if product_data.variations:
        for variation_data in product_data.variations:
            variation = Variation(
                product_id=product.id,
                title=variation_data.title,
                type=variation_data.type,
                color_hex=variation_data.color_hex,
                price=variation_data.price,
                sale_price=variation_data.sale_price,
                images=variation_data.images,
                is_active=variation_data.is_active,
            )
            db.add(variation)
            await db.flush()  # Get variation ID

            # Add size stocks for this variation
            for size_data in variation_data.sizes:
                size_stock = SizeStock(
                    variation_id=variation.id,
                    size=SizeEnum(size_data.size),
                    stock=size_data.stock,
                )
                db.add(size_stock)

    # Add variants if provided (legacy system - backward compatibility)
    if product_data.variants:
        for variant_data in product_data.variants:
            variant = ProductVariant(
                product_id=product.id,
                size=variant_data.size,
                color=variant_data.color,
                color_hex=variant_data.color_hex,
                price=variant_data.price,
                stock=variant_data.stock,
                sku=variant_data.sku,
                is_available=variant_data.is_available,
            )
            db.add(variant)

    # Add images if provided
    if product_data.images:
        for idx, image_data in enumerate(product_data.images):
            image = ProductImage(
                product_id=product.id,
                image_url=image_data.image_url,
                thumbnail_url=image_data.thumbnail_url,
                alt_text=image_data.alt_text,
                display_order=image_data.display_order if image_data.display_order is not None else idx,
                is_primary=image_data.is_primary,
            )
            db.add(image)

    await db.commit()
    await db.refresh(product)

    # Fetch with relationships
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product.id)
    )
    product = result.scalar_one()

    return product


@router.get("", response_model=ProductListResponse)
async def list_products(
    search: Optional[str] = Query(None, max_length=255),
    category_id: Optional[UUID] = None,
    vendor_id: Optional[UUID] = None,
    status: Optional[str] = Query(None, pattern="^(draft|active|inactive|archived)$"),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    is_featured: Optional[bool] = None,
    in_stock: Optional[bool] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="created_at", pattern="^(created_at|title|base_price|orders_count|views_count)$"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    List products with filters and pagination

    - Public endpoint (shows only active/approved products to non-vendors)
    - Vendors can see their own products regardless of status
    - Admins can see all products
    """
    # Build query
    query = select(Product).options(*PRODUCT_RELATIONSHIPS)

    # Apply filters
    filters = []

    # Non-vendors can only see active, approved products
    if not current_user or current_user.role == "customer":
        filters.append(Product.status == ProductStatus.ACTIVE)
        filters.append(Product.moderation_status == ModerationStatus.APPROVED)
    elif current_user.role == "vendor":
        # Vendors see only their own products (excluding archived/deleted)
        result = await db.execute(
            select(Vendor.id).where(Vendor.user_id == current_user.id)
        )
        vendor_id_result = result.scalar_one_or_none()
        if vendor_id_result:
            filters.append(Product.vendor_id == vendor_id_result)
            # Exclude archived products (soft-deleted)
            filters.append(Product.status != ProductStatus.ARCHIVED)

    # Search
    if search:
        search_filter = or_(
            Product.title.ilike(f"%{search}%"),
            Product.description.ilike(f"%{search}%")
        )
        filters.append(search_filter)

    # Category filter
    if category_id:
        filters.append(
            or_(
                Product.category_id == category_id,
                Product.category.has(Category.parent_id == category_id),
            )
        )

    # Vendor filter
    if vendor_id and (not current_user or current_user.role == "admin"):
        filters.append(Product.vendor_id == vendor_id)

    # Status filter
    if status:
        filters.append(Product.status == ProductStatus(status))

    # Price range
    if min_price is not None:
        filters.append(Product.base_price >= min_price)
    if max_price is not None:
        filters.append(Product.base_price <= max_price)

    # Featured
    if is_featured is not None:
        filters.append(Product.is_featured == is_featured)

    # In stock
    if in_stock:
        filters.append(Product.total_stock > 0)

    # Apply all filters
    if filters:
        query = query.where(and_(*filters))

    # Count total
    count_query = select(func.count()).select_from(Product)
    if filters:
        count_query = count_query.where(and_(*filters))

    result = await db.execute(count_query)
    total = result.scalar()

    # Sorting
    sort_column = getattr(Product, sort_by)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    products = result.scalars().all()

    total_pages = (total + page_size - 1) // page_size

    return ProductListResponse(
        products=products,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get a single product by ID

    - Public endpoint (only active/approved products for non-vendors)
    - Vendors can view their own products
    - Admins can view all products
    """
    query = select(Product).options(*PRODUCT_RELATIONSHIPS).where(Product.id == product_id)

    result = await db.execute(query)
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Permission check
    if not current_user or current_user.role == "customer":
        if product.status != ProductStatus.ACTIVE or product.moderation_status != ModerationStatus.APPROVED:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
    elif current_user.role == "vendor":
        # Check if product belongs to vendor
        result = await db.execute(
            select(Vendor.id).where(Vendor.user_id == current_user.id)
        )
        vendor_id = result.scalar_one_or_none()

        if product.vendor_id != vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view this product"
            )

    # Increment views
    product.views_count += 1
    await db.commit()

    # Reload with relationships to avoid lazy loading issues
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one()

    return product


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    product_data: ProductUpdate,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Update a product (vendors only - own products)

    - Vendors can only update their own products
    - Cannot update moderation status (admin only)
    """
    # Get vendor
    result = await db.execute(
        select(Vendor.id).where(Vendor.user_id == current_user.id)
    )
    vendor_id = result.scalar_one_or_none()

    if not vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor profile not found"
        )

    # Get product
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Check ownership
    if product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this product"
        )

    # Update fields
    update_data = product_data.model_dump(exclude_unset=True)

    # Handle variations separately for sync logic
    variations_data = update_data.pop("variations", None)

    for field, value in update_data.items():
        if field == "status":
            setattr(product, field, ProductStatus(value))
        elif field == "size_guide":
            setattr(product, field, value.model_dump() if value is not None else None)
        else:
            setattr(product, field, value)

    # Sync variations if provided
    if variations_data is not None:
        # Delete all existing variations (cascade will delete size_stocks)
        await db.execute(
            select(Variation).where(Variation.product_id == product_id)
        )
        for existing_variation in product.variations:
            await db.delete(existing_variation)

        # Create new variations
        for variation_data in variations_data:
            variation = Variation(
                product_id=product.id,
                title=variation_data["title"],
                type=variation_data.get("type", "color"),
                color_hex=variation_data.get("color_hex"),
                price=variation_data.get("price"),
                sale_price=variation_data.get("sale_price"),
                images=variation_data.get("images", []),
                is_active=variation_data.get("is_active", True),
            )
            db.add(variation)
            await db.flush()  # Get variation ID

            # Add size stocks for this variation
            if "sizes" in variation_data:
                for size_data in variation_data["sizes"]:
                    size_stock = SizeStock(
                        variation_id=variation.id,
                        size=SizeEnum(size_data["size"]),
                        stock=size_data.get("stock", 0),
                    )
                    db.add(size_stock)

    # Reset moderation if content changed
    if any(field in update_data for field in ["title", "description"]):
        product.moderation_status = ModerationStatus.PENDING

    await db.commit()

    # Reload with relationships to avoid lazy loading issues
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one()

    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: UUID,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a product (vendors only - own products)

    - Soft delete (sets status to archived)
    - Vendors can only delete their own products
    """
    # Get vendor
    result = await db.execute(
        select(Vendor.id).where(Vendor.user_id == current_user.id)
    )
    vendor_id = result.scalar_one_or_none()

    if not vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vendor profile not found"
        )

    # Get product
    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Check ownership
    if product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this product"
        )

    # Soft delete
    product.status = ProductStatus.ARCHIVED
    # Ensure archived products no longer count toward collection totals
    product.collection_id = None
    await db.commit()


# ============================================================================
# Product Variant Endpoints
# ============================================================================

@router.post("/{product_id}/variants", response_model=ProductVariantResponse, status_code=status.HTTP_201_CREATED)
async def create_variant(
    product_id: UUID,
    variant_data: ProductVariantCreate,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Create a product variant"""
    # Check product ownership
    result = await db.execute(
        select(Vendor.id).where(Vendor.user_id == current_user.id)
    )
    vendor_id = result.scalar_one_or_none()

    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Create variant
    variant = ProductVariant(
        product_id=product_id,
        **variant_data.model_dump()
    )
    db.add(variant)
    await db.commit()
    await db.refresh(variant)

    return variant


@router.put("/{product_id}/variants/{variant_id}", response_model=ProductVariantResponse)
async def update_variant(
    product_id: UUID,
    variant_id: UUID,
    variant_data: ProductVariantUpdate,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Update a product variant"""
    # Check ownership
    result = await db.execute(
        select(Vendor.id).where(Vendor.user_id == current_user.id)
    )
    vendor_id = result.scalar_one_or_none()

    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Get variant
    result = await db.execute(
        select(ProductVariant).where(
            and_(ProductVariant.id == variant_id, ProductVariant.product_id == product_id)
        )
    )
    variant = result.scalar_one_or_none()

    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found"
        )

    # Update
    update_data = variant_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(variant, field, value)

    await db.commit()
    await db.refresh(variant)

    return variant


@router.delete("/{product_id}/variants/{variant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_variant(
    product_id: UUID,
    variant_id: UUID,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Delete a product variant"""
    # Check ownership
    result = await db.execute(
        select(Vendor.id).where(Vendor.user_id == current_user.id)
    )
    vendor_id = result.scalar_one_or_none()

    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Get and delete variant
    result = await db.execute(
        select(ProductVariant).where(
            and_(ProductVariant.id == variant_id, ProductVariant.product_id == product_id)
        )
    )
    variant = result.scalar_one_or_none()

    if not variant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variant not found"
        )

    await db.delete(variant)
    await db.commit()


# ============================================================================
# Product Image Endpoints
# ============================================================================

@router.post("/{product_id}/images", response_model=ProductImageResponse, status_code=status.HTTP_201_CREATED)
async def create_image(
    product_id: UUID,
    image_data: ProductImageCreate,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Add a product image"""
    # Check ownership
    result = await db.execute(
        select(Vendor.id).where(Vendor.user_id == current_user.id)
    )
    vendor_id = result.scalar_one_or_none()

    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Create image
    image = ProductImage(
        product_id=product_id,
        **image_data.model_dump()
    )
    db.add(image)
    await db.commit()
    await db.refresh(image)

    return image


@router.delete("/{product_id}/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_image(
    product_id: UUID,
    image_id: UUID,
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
):
    """Delete a product image"""
    # Check ownership
    result = await db.execute(
        select(Vendor.id).where(Vendor.user_id == current_user.id)
    )
    vendor_id = result.scalar_one_or_none()

    result = await db.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product or product.vendor_id != vendor_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Get and delete image
    result = await db.execute(
        select(ProductImage).where(
            and_(ProductImage.id == image_id, ProductImage.product_id == product_id)
        )
    )
    image = result.scalar_one_or_none()

    if not image:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found"
        )

    await db.delete(image)
    await db.commit()


# ============================================================================
# Admin Moderation Endpoints
# ============================================================================

@router.patch("/{product_id}/moderation", response_model=ProductResponse)
async def moderate_product(
    product_id: UUID,
    moderation_data: ProductModerationUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    Moderate a product (admins only)

    - Approve, reject, or mark as pending
    - Add moderation notes
    """
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found"
        )

    # Update moderation
    product.moderation_status = ModerationStatus(moderation_data.moderation_status)
    product.moderation_notes = moderation_data.moderation_notes
    product.moderated_by = current_user.id
    product.moderated_at = func.now()

    await db.commit()

    # Reload with relationships to avoid lazy loading issues
    result = await db.execute(
        select(Product)
        .options(*PRODUCT_RELATIONSHIPS)
        .where(Product.id == product_id)
    )
    product = result.scalar_one()

    return product
