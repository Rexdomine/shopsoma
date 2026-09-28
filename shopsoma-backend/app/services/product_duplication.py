"""Vendor duplication with independent storage ownership and one graph commit."""

import asyncio
import logging
from pathlib import PurePosixPath
from time import monotonic
from uuid import UUID, uuid4
from urllib.parse import urlparse

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product, ProductImage, ProductImageStorageCleanup
from app.models.stock_payment_persistence import coordinate_catalog_write
from app.models.vendor import Vendor
from app.schemas.product import ProductCreate, ProductResponse
from app.services.image_service import image_service
from app.services.product_creation import PRODUCT_RELATIONSHIPS, build_product_graph
from app.services.product_image_storage import (
    lock_storage_keys, lock_and_validate_storage_keys, record_storage_cleanup,
    storage_key_from_public_url, validate_image_upload,
)

logger = logging.getLogger(__name__)
_REPAIR = "Source images need repair or re-upload before duplication"
_UNCERTAIN = "Duplication outcome is uncertain. Refresh your product list before trying again."


def _exact_url_key(url: str | None, keys: list[str]) -> str | None:
    if url is None:
        return None
    # Exact configured URL matching, never authority derived from URL parsing.
    for key in keys:
        if url in (f"/uploads/{key}", image_service._get_public_url(key)):
            return key
    raise ValueError(_REPAIR)


def _plan_duplicate(source: Product, vendor_user_id: UUID):
    if len(source.images) > 10:
        raise ValueError(_REPAIR)
    source_keys = []
    mapping = {}
    urls = {}
    images = []
    for image in sorted(source.images, key=lambda row: (row.display_order, str(row.id))):
        keys = list(image.storage_keys or [])
        if len(keys) > 4:
            raise ValueError(_REPAIR)
        for key in keys:
            if (
                not key.startswith(f"vendors/{vendor_user_id}/products/")
                or any(part in ("", ".", "..") for part in key.split("/"))
                or key in mapping
            ):
                raise ValueError(_REPAIR)
            mapping[key] = (
                f"vendors/{vendor_user_id}/products/copies/"
                f"{uuid4().hex}{PurePosixPath(key).suffix}"
            )
        source_keys.extend(keys)
        if keys:
            original_key = _exact_url_key(image.image_url, keys)
            thumbnail_key = _exact_url_key(image.thumbnail_url, keys)
            original_url = image_service.public_url_for_key(mapping[original_key])
            thumbnail_url = (
                image_service.public_url_for_key(mapping[thumbnail_key])
                if thumbnail_key else None
            )
        else:
            # Validation against durable ownership/cleanup follows under locks.
            original_url, thumbnail_url = image.image_url, image.thumbnail_url
        if image.image_url in urls:
            # Multiple owners of a visible original are ambiguous.
            raise ValueError(_REPAIR)
        urls[image.image_url] = original_url
        images.append({
            "image_url": original_url, "thumbnail_url": thumbnail_url,
            "storage_keys": [mapping[key] for key in keys] or None,
            "alt_text": image.alt_text, "display_order": image.display_order,
            "is_primary": image.is_primary,
        })

    variations = []
    for variation in source.variations:
        if any(url not in urls for url in variation.images or []):
            raise ValueError(_REPAIR)
        variations.append({
            **{field: getattr(variation, field) for field in (
                "title", "type", "color_hex", "price", "sale_price",
                "inherits_price", "inherits_sale_price", "is_active",
            )},
            "images": [urls[url] for url in variation.images or []],
            "sizes": [
                {"size": stock.size.value, "stock": 0 if source.made_to_order else stock.stock}
                for stock in variation.size_stocks
            ],
        })
    data = ProductCreate(
        **{field: getattr(source, field) for field in (
            "description", "base_price", "compare_at_price", "currency",
            "category_id", "collection_id", "fabric_composition", "weight_kg",
            "length_cm", "width_cm", "height_cm", "made_to_order",
            "made_to_order_timeline",
        )},
        title=f"{source.title[:248]} (Copy)",
        product_type=source.product_type.value,
        status="draft", is_featured=False, total_stock=0,
        images=images, variations=variations,
    )
    return data, source_keys, mapping


async def _load_product(db, product_id):
    return await db.scalar(
        select(Product).where(Product.id == product_id)
        .options(*PRODUCT_RELATIONSHIPS).execution_options(populate_existing=True)
    )


async def _reserve_cleanup(db, keys, destination_id):
    """A new transaction reserves only exact unowned, never-consumed destinations."""
    await lock_storage_keys(db, keys)
    safe_keys = []
    for key in keys:
        try:
            await lock_and_validate_storage_keys(db, [key])
        except ValueError:
            continue  # Another owner or cleanup ledger is authoritative.
        safe_keys.append(key)
    await record_storage_cleanup(
        db, safe_keys, product_id=destination_id,
        reason="duplicate_compensation",
    )
    # Existing durable cleanup worker owns deletion/retries; never blind-delete.


async def duplicate_vendor_product(
    db: AsyncSession, vendor: Vendor, source_id: UUID
) -> ProductResponse:
    vendor_id, vendor_user_id = vendor.id, vendor.user_id
    # Authorization precedes catalog locking and all storage IO.
    exists = await db.scalar(select(Product.id).where(
        Product.id == source_id, Product.vendor_id == vendor_id,
    ))
    if exists is None:
        raise HTTPException(status_code=404, detail="Product not found")

    destination_id = uuid4()
    attempted = []
    commit_attempted = False
    started = monotonic()
    context = {"source_id": str(source_id), "destination_id": str(destination_id)}
    try:
        await coordinate_catalog_write(
            db, product_ids=[source_id, destination_id], lock_only=True,
        )
        source = await _load_product(db, source_id)
        if source is None or source.vendor_id != vendor_id:
            raise HTTPException(status_code=404, detail="Product not found")
        try:
            data, source_keys, mapping = _plan_duplicate(source, vendor_user_id)
            legacy_keys = [
                storage_key_from_public_url(url)
                for image in source.images if not image.storage_keys
                for url in (image.image_url, image.thumbnail_url) if url
            ]
            await lock_storage_keys(db, [*source_keys, *mapping.values(), *legacy_keys])
            for key in source_keys:
                owners = list((await db.scalars(select(ProductImage.product_id).where(
                    ProductImage.storage_keys.contains([key])
                ))).all())
                consumed = await db.scalar(select(ProductImageStorageCleanup.id).where(
                    ProductImageStorageCleanup.storage_keys.contains([key])
                ).limit(1))
                if owners != [source_id] or consumed is not None:
                    raise ValueError(_REPAIR)
            for image in source.images:
                if not image.storage_keys:
                    # Truly external legacy URLs only. No URL fetching or guessed ownership.
                    if any(url and (
                        urlparse(url).path.startswith("/uploads/")
                        or url.startswith(image_service._get_public_url(""))
                    ) for url in (
                        image.image_url, image.thumbnail_url
                    )):
                        raise ValueError(_REPAIR)
                    await validate_image_upload(db, image.image_url, image.thumbnail_url, None)
            await lock_and_validate_storage_keys(db, list(mapping.values()))
        except (ValueError, ValidationError) as exc:
            raise HTTPException(status_code=409, detail=_REPAIR) from exc

        context["planned_count"] = len(mapping)
        for old_key, new_key in mapping.items():
            # Bound total work without cancelling a thread that may still write.
            if monotonic() - started > 120:
                raise TimeoutError("Duplicate copy budget exhausted")
            attempted.append(new_key)
            await image_service.copy_image_key(old_key, new_key, key_mapping=mapping)

        await build_product_graph(db, data, vendor_id, product_id=destination_id)
        await db.flush()
        product = await _load_product(db, destination_id)
        response = ProductResponse.model_validate(product)
        commit_attempted = True
        await db.commit()
        logger.info("Product duplication completed", extra={
            **context, "attempted_count": len(attempted), "duration_seconds": monotonic() - started,
        })
        return response
    except asyncio.CancelledError:
        # Threaded IO may still finish. Cancellation is not evidence of absence.
        logger.warning("Product duplication cancelled; reconcile retained objects", extra=context)
        raise
    except Exception as exc:
        try:
            await db.rollback()
            if commit_attempted:
                persisted = await _load_product(db, destination_id)
                if persisted is not None:
                    actual = {
                        key for image in persisted.images for key in image.storage_keys or []
                    }
                    if persisted.vendor_id == vendor_id and actual == set(attempted):
                        return ProductResponse.model_validate(persisted)
                    # An unexpected persisted graph must never trigger compensation.
                    raise RuntimeError("Duplicate ownership outcome needs reconciliation")
            await _reserve_cleanup(db, attempted, destination_id)
        except Exception:
            logger.exception("Product duplication requires reconciliation", extra={
                **context, "attempted_count": len(attempted),
            })
            raise HTTPException(status_code=503, detail=_UNCERTAIN) from exc
        if isinstance(exc, HTTPException):
            raise
        logger.exception("Product duplication failed; cleanup reserved", extra=context)
        raise HTTPException(
            status_code=503,
            detail=_UNCERTAIN if commit_attempted else "Could not duplicate product. Please try again later.",
        ) from exc
