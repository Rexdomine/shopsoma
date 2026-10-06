"""
Transaction-neutral variation persistence, in-place synchronization, and validation.
Preserves stable Variation.id and SizeStock.id entities across product updates.
"""
from decimal import Decimal
from typing import Any, List, Optional, Sequence
import uuid
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import (
    Product,
    ProductImage,
    ProductStatus,
    ProductType,
    SizeEnum,
    SizeStock,
    Variation,
)
from app.models.stock_payment_persistence import coordinate_catalog_write
from app.schemas.product import (
    is_color_variation_type,
    normalize_color_value,
    validate_variation_inventory_shape,
)
from app.services.product_image_storage import lock_and_validate_variation_image_urls
from app.services.product_moderation import mark_product_content_pending


def normalize_size_enum(value: Any) -> SizeEnum:
    """Normalize input string or enum into a canonical SizeEnum value, rejecting invalid sizes."""
    if isinstance(value, SizeEnum):
        return value
    val = str(value).strip() if value is not None else ""
    if val.upper() in ("ONE_SIZE", "ONE SIZE", "ONE/SIZE"):
        return SizeEnum.ONE_SIZE
    try:
        return SizeEnum(val)
    except ValueError as exc:
        allowed = ", ".join(e.value for e in SizeEnum)
        raise ValueError(f"Invalid size '{val}'. Allowed sizes are: {allowed}") from exc


def validate_variation_data_list(
    variations: Sequence[Any],
    variants: Optional[Sequence[Any]] = None,
) -> None:
    """Shared comprehensive validation for variation payloads."""
    variation_list = list(variations or [])
    if not variation_list:
        return

    # 1. Reject duplicate labels across variations
    titles: List[str] = []
    for variation in variation_list:
        title = getattr(variation, "title", None)
        if title is None and isinstance(variation, dict):
            title = variation.get("title")
        if title:
            norm_title = normalize_color_value(title)
            if norm_title in titles:
                raise ValueError("Variation titles must be unique after normalization")
            titles.append(norm_title)

    # 2. Per-variation field validations (prices, nested sizes, duplicate sizes, negative stock)
    for variation in variation_list:
        # Check prices
        price = getattr(variation, "price", None)
        sale_price = getattr(variation, "sale_price", None)
        if isinstance(variation, dict):
            if "price" in variation and price is None:
                price = variation.get("price")
            if "sale_price" in variation and sale_price is None:
                sale_price = variation.get("sale_price")

        if price is not None:
            price_dec = Decimal(str(price))
            if price_dec <= 0:
                raise ValueError("Price must be greater than 0")
            if price_dec > Decimal("999999.99"):
                raise ValueError("Price cannot exceed 999,999.99")

        if sale_price is not None:
            sale_price_dec = Decimal(str(sale_price))
            if sale_price_dec <= 0:
                raise ValueError("Sale price must be greater than 0")
            if sale_price_dec > Decimal("999999.99"):
                raise ValueError("Sale price cannot exceed 999,999.99")
            if price is not None and sale_price_dec >= Decimal(str(price)):
                raise ValueError("Sale price must be less than regular price")

        # Check nested sizes
        nested_sizes = (
            getattr(variation, "sizes", None)
            if hasattr(variation, "sizes")
            else getattr(variation, "size_stocks", None)
        )
        if nested_sizes is None and isinstance(variation, dict):
            nested_sizes = variation.get("sizes") or variation.get("size_stocks")

        if nested_sizes:
            seen_sizes = set()
            for s in nested_sizes:
                size_val = getattr(s, "size", None)
                stock_val = getattr(s, "stock", None)
                if isinstance(s, dict):
                    if size_val is None:
                        size_val = s.get("size")
                    if stock_val is None:
                        stock_val = s.get("stock")

                # Validate size enum
                enum_size = normalize_size_enum(size_val)
                if enum_size in seen_sizes:
                    raise ValueError("Duplicate size options are not allowed within the same variation")
                seen_sizes.add(enum_size)

                # Validate stock non-negative
                if stock_val is not None:
                    stock_int = int(stock_val)
                    if stock_int < 0:
                        raise ValueError("Stock quantity cannot be negative")

    # 3. Shape validation (including color-size matrix incompatibility)
    validate_variation_inventory_shape(variation_list, variants)


async def sync_product_variations(
    db: AsyncSession,
    product: Product,
    variations_data: list,
    *,
    inherited_price_update: bool = False,
    is_admin: bool = False,
) -> List[Variation]:
    """
    Synchronize variations for a product in-place, preserving stable IDs.

    - Matches variations by explicit id (if provided) or normalized title.
    - Updates matched variations and nested size stocks in-place without generating new IDs.
    - Only creates new variations if not matching existing ones.
    - Only deletes variations explicitly removed.
    - Validates image ownership, duplicate labels, valid sizes, and matrix rules.
    - Moderation-safe: vendor updates trigger mark_product_content_pending.
    """
    try:
        validate_variation_data_list(variations_data, product.variants)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["body", "variations"],
                    "msg": str(exc),
                    "type": "value_error",
                }
            ],
        ) from exc

    # Validate image ownership
    variation_image_urls = [
        image_url
        for v in variations_data
        for image_url in (
            (getattr(v, "images", None) if hasattr(v, "images") else v.get("images")) or []
            if isinstance(v, (dict, object))
            else []
        )
    ]
    if variation_image_urls:
        try:
            await coordinate_catalog_write(db, product_ids=[product.id], lock_only=True)
            await lock_and_validate_variation_image_urls(
                db, variation_image_urls, product_id=product.id
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    existing_by_id = {v.id: v for v in product.variations}
    existing_by_title = {normalize_color_value(v.title): v for v in product.variations}

    touched_ids = set()
    variations_to_sync: List[Variation] = []

    for v_item in variations_data:
        v_dict = v_item if isinstance(v_item, dict) else v_item.model_dump()
        v_id = v_dict.get("id")
        if v_id is not None:
            if isinstance(v_id, str):
                v_id = UUID(v_id)
            if v_id in existing_by_id:
                target = existing_by_id[v_id]
            else:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Variation {v_id} not found on this product",
                )
        else:
            norm_title = normalize_color_value(v_dict["title"])
            if norm_title in existing_by_title and existing_by_title[norm_title].id not in touched_ids:
                target = existing_by_title[norm_title]
            else:
                target = None

        # Price inheritance resolution
        inherits_price = v_dict.get("inherits_price")
        inherits_sale_price = v_dict.get("inherits_sale_price")
        var_price = v_dict.get("price")
        var_sale_price = v_dict.get("sale_price")
        if inherited_price_update and inherits_price is True:
            var_price = product.compare_at_price
        if inherited_price_update and inherits_sale_price is True:
            var_sale_price = (
                product.base_price if product.compare_at_price is not None else None
            )

        if target is not None:
            # Update target in-place preserving its primary key ID
            target.title = v_dict["title"]
            target.type = v_dict.get("type", "color")
            target.color_hex = v_dict.get("color_hex")
            target.price = var_price
            target.sale_price = var_sale_price
            target.inherits_price = inherits_price
            target.inherits_sale_price = inherits_sale_price
            target.images = v_dict.get("images", [])
            target.is_active = v_dict.get("is_active", True)

            # In-place update of nested size_stocks
            sizes_data = v_dict.get("sizes")
            if sizes_data is not None:
                existing_sizes = {s.size: s for s in target.size_stocks}
                handled_sizes = set()
                for s_item in sizes_data:
                    s_dict = s_item if isinstance(s_item, dict) else s_item.model_dump()
                    enum_size = normalize_size_enum(s_dict["size"])
                    stock_qty = s_dict.get("stock", 0)
                    if enum_size in existing_sizes:
                        s_obj = existing_sizes[enum_size]
                        s_obj.stock = stock_qty
                        handled_sizes.add(enum_size)
                    else:
                        new_s = SizeStock(
                            variation_id=target.id,
                            size=enum_size,
                            stock=stock_qty,
                        )
                        db.add(new_s)
                        target.size_stocks.append(new_s)
                        handled_sizes.add(enum_size)

                for old_size, old_s in list(existing_sizes.items()):
                    if old_size not in handled_sizes:
                        await db.delete(old_s)
                        target.size_stocks.remove(old_s)

            touched_ids.add(target.id)
            variations_to_sync.append(target)
        else:
            # Create new variation
            new_var_id = uuid.uuid4()
            size_stocks_list = []
            if "sizes" in v_dict and v_dict["sizes"] is not None:
                for s_item in v_dict["sizes"]:
                    s_dict = s_item if isinstance(s_item, dict) else s_item.model_dump()
                    size_stock = SizeStock(
                        id=uuid.uuid4(),
                        variation_id=new_var_id,
                        size=normalize_size_enum(s_dict["size"]),
                        stock=s_dict.get("stock", 0),
                    )
                    size_stocks_list.append(size_stock)

            new_variation = Variation(
                id=new_var_id,
                product_id=product.id,
                title=v_dict["title"],
                type=v_dict.get("type", "color"),
                color_hex=v_dict.get("color_hex"),
                price=var_price,
                sale_price=var_sale_price,
                inherits_price=inherits_price,
                inherits_sale_price=inherits_sale_price,
                images=v_dict.get("images", []),
                is_active=v_dict.get("is_active", True),
                size_stocks=size_stocks_list,
            )
            db.add(new_variation)
            product.variations.append(new_variation)
            touched_ids.add(new_var_id)
            variations_to_sync.append(new_variation)

    # Delete variations that were removed from the product
    for existing_variation in list(product.variations):
        if existing_variation.id not in touched_ids:
            await db.delete(existing_variation)
            product.variations.remove(existing_variation)

    if not is_admin:
        await mark_product_content_pending(db=db, product_id=product.id)

    return variations_to_sync


async def update_single_variation(
    db: AsyncSession,
    product: Product,
    variation_id: UUID,
    variation_data: Any,
    *,
    is_admin: bool = False,
) -> Variation:
    """
    Update a single selected variation in-place.
    Untouched variations and the product gallery are guaranteed to remain untouched.
    """
    target = next((v for v in product.variations if v.id == variation_id), None)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variation not found on this product",
        )

    v_dict = variation_data if isinstance(variation_data, dict) else variation_data.model_dump(exclude_unset=True)

    # Validate against other variations on this product
    other_variations = [v for v in product.variations if v.id != variation_id]
    candidate_title = v_dict.get("title", target.title)
    if candidate_title:
        norm_title = normalize_color_value(candidate_title)
        for other in other_variations:
            if normalize_color_value(other.title) == norm_title:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Variation titles must be unique after normalization",
                )

    # Validate single variation payload
    try:
        synthetic_list = other_variations + [
            {
                "title": candidate_title,
                "type": v_dict.get("type", target.type),
                "price": v_dict.get("price", target.price),
                "sale_price": v_dict.get("sale_price", target.sale_price),
                "is_active": v_dict.get("is_active", target.is_active),
                "sizes": v_dict.get("sizes", [
                    {"size": s.size.value if hasattr(s.size, "value") else str(s.size), "stock": s.stock}
                    for s in target.size_stocks
                ]),
            }
        ]
        validate_variation_data_list(synthetic_list, product.variants)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=[
                {
                    "loc": ["body", "variations"],
                    "msg": str(exc),
                    "type": "value_error",
                }
            ],
        ) from exc

    # Scoped image ownership check
    if "images" in v_dict and v_dict["images"]:
        try:
            await coordinate_catalog_write(db, product_ids=[product.id], lock_only=True)
            await lock_and_validate_variation_image_urls(
                db, v_dict["images"], product_id=product.id
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # In-place field updates
    for field in ("title", "type", "color_hex", "price", "sale_price", "inherits_price", "inherits_sale_price", "images", "is_active"):
        if field in v_dict:
            setattr(target, field, v_dict[field])

    # Nested sizes update
    if "sizes" in v_dict and v_dict["sizes"] is not None:
        existing_sizes = {s.size: s for s in target.size_stocks}
        handled_sizes = set()
        for s_item in v_dict["sizes"]:
            s_dict = s_item if isinstance(s_item, dict) else s_item.model_dump()
            enum_size = normalize_size_enum(s_dict["size"])
            stock_qty = s_dict.get("stock", 0)
            if enum_size in existing_sizes:
                s_obj = existing_sizes[enum_size]
                s_obj.stock = stock_qty
                handled_sizes.add(enum_size)
            else:
                new_s = SizeStock(
                    variation_id=target.id,
                    size=enum_size,
                    stock=stock_qty,
                )
                db.add(new_s)
                target.size_stocks.append(new_s)
                handled_sizes.add(enum_size)

        for old_size, old_s in list(existing_sizes.items()):
            if old_size not in handled_sizes:
                await db.delete(old_s)
                target.size_stocks.remove(old_s)

    if not is_admin:
        await mark_product_content_pending(db=db, product_id=product.id)

    await db.commit()
    reloaded_result = await db.execute(
        select(Variation)
        .options(selectinload(Variation.size_stocks))
        .where(Variation.id == target.id)
    )
    return reloaded_result.scalar_one()


async def delete_single_variation(
    db: AsyncSession,
    product: Product,
    variation_id: UUID,
    *,
    is_admin: bool = False,
) -> None:
    """Delete a single variation without altering untouched variations or product gallery."""
    target = next((v for v in product.variations if v.id == variation_id), None)
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Variation not found on this product",
        )

    await db.delete(target)
    product.variations.remove(target)

    if not is_admin:
        await mark_product_content_pending(db=db, product_id=product.id)

    await db.commit()
