"""Transaction-neutral product graph construction shared by create and Duplicate."""

from uuid import UUID
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.models.category import Category

from app.models.product import (
    Product, ProductVariant, ProductImage, ProductStatus, ProductType,
    ModerationStatus, Variation, SizeStock, SizeEnum,
)
from app.schemas.product import ProductCreate
from app.services.product_image_storage import lock_and_validate_variation_image_urls


PRODUCT_RELATIONSHIPS = (
    selectinload(Product.variants),
    selectinload(Product.variations).selectinload(Variation.size_stocks),
    selectinload(Product.images),
    selectinload(Product.vendor),
    selectinload(Product.category).selectinload(Category.parent),
    selectinload(Product.collection),
)


async def build_product_graph(
    db: AsyncSession, product_data: ProductCreate, vendor_id: UUID,
    *, product_id: UUID | None = None,
) -> Product:
    """Build and flush, leaving commit/rollback and image provenance to the caller."""
    # Create product
    product = Product(
        id=product_id,
        vendor_id=vendor_id,
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
        weight_kg=product_data.weight_kg,
        length_cm=product_data.length_cm,
        width_cm=product_data.width_cm,
        height_cm=product_data.height_cm,
        meta_title=product_data.meta_title,
        meta_description=product_data.meta_description,
        size_guide=product_data.size_guide.model_dump() if product_data.size_guide else None,
        moderation_status=ModerationStatus.PENDING,
    )

    db.add(product)
    await db.flush()  # Get product ID

    # Add variations if provided (new system)
    if product_data.variations:
        variation_image_urls = [
            image_url
            for variation_data in product_data.variations
            for image_url in (variation_data.images or [])
        ]
        try:
            await lock_and_validate_variation_image_urls(
                db, variation_image_urls,
                new_image_urls=[image.image_url for image in product_data.images or []],
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        for variation_data in product_data.variations:
            variation = Variation(
                product_id=product.id,
                title=variation_data.title,
                type=variation_data.type,
                color_hex=variation_data.color_hex,
                price=variation_data.price,
                sale_price=variation_data.sale_price,
                inherits_price=variation_data.inherits_price,
                inherits_sale_price=variation_data.inherits_sale_price,
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
            explicit_inventory = bool(
                {"stock", "is_available"} & variant_data.model_fields_set
            )
            inherits_stock = (
                product.product_type == ProductType.SINGLE
                and not product_data.variations
                and variant_data.size is None
                and variant_data.color is None
                and not explicit_inventory
            )
            variant = ProductVariant(
                product_id=product.id,
                size=variant_data.size,
                inherits_price=False,
                # A generic legacy row on a single product is the compatibility
                # projection of product.total_stock, not an independent axis.
                inherits_stock=inherits_stock,
                color=variant_data.color,
                color_hex=variant_data.color_hex,
                price=variant_data.price,
                stock=(
                    (0 if product.made_to_order else int(product.total_stock or 0))
                    if inherits_stock
                    else variant_data.stock
                ),
                sku=variant_data.sku,
                is_available=(
                    (True if product.made_to_order else int(product.total_stock or 0) > 0)
                    if inherits_stock
                    else variant_data.is_available
                ),
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
                storage_keys=image_data.storage_keys,
            )
            db.add(image)

    return product
