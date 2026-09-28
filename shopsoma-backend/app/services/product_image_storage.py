"""Durable bookkeeping for product-image storage cleanup retries."""

import logging
from typing import Optional, Sequence
from uuid import UUID
from urllib.parse import unquote, urlparse
from posixpath import normpath

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import ProductImage, ProductImageStorageCleanup, ProductImageUpload, Variation
from app.models.vendor import Vendor
from app.services.image_service import image_service

logger = logging.getLogger(__name__)


def _is_featured_storefront_image(featured_url: str | None, storage_key: str) -> bool:
    """Match a persisted featured-image URL to its exact storage key."""
    if not featured_url:
        return False

    storage_prefix = image_service._get_public_url("").rstrip("/") + "/"
    if featured_url.startswith(storage_prefix):
        return featured_url.removeprefix(storage_prefix) == storage_key

    path = urlparse(featured_url).path.lstrip("/")
    if path.startswith("uploads/"):
        path = path[len("uploads/"):]
    return path == storage_key


async def clear_featured_storefront_references(
    db: AsyncSession, storage_keys: Sequence[str]
) -> int:
    """Clear vendor storefront references before deleting backing objects."""
    keys = [key for key in storage_keys if key]
    if not keys:
        return 0
    vendors = list(
        (
            await db.scalars(
                select(Vendor).where(Vendor.featured_storefront_image_url.is_not(None))
            )
        ).all()
    )
    cleared = 0
    for vendor in vendors:
        if any(_is_featured_storefront_image(vendor.featured_storefront_image_url, key) for key in keys):
            vendor.featured_storefront_image_url = None
            cleared += 1
    return cleared


async def clear_variation_image_references(
    db: AsyncSession,
    product_id: UUID,
    storage_keys: Sequence[str],
    image_url: str | None = None,
) -> int:
    """Remove deleted product-image URLs from this product's variation galleries."""
    keys = {key for key in storage_keys if key}
    if image_url:
        legacy_key = storage_key_from_public_url(image_url)
        if legacy_key:
            keys.add(legacy_key)
    if not keys:
        return 0
    variations = list(
        (
            await db.scalars(
                select(Variation).where(Variation.product_id == product_id)
            )
        ).all()
    )
    cleared = 0
    for variation in variations:
        images = list(variation.images or [])
        remaining = [
            image_url
            for image_url in images
            if storage_key_from_public_url(image_url) not in keys
        ]
        if remaining != images:
            variation.images = remaining
            cleared += len(images) - len(remaining)
    return cleared


def storage_key_from_public_url(featured_url: str | None) -> str | None:
    """Return the storage key represented by a local or production public URL."""
    if not featured_url:
        return None
    storage_prefix = image_service._get_public_url("").rstrip("/") + "/"
    path = unquote(urlparse(featured_url).path)
    if featured_url.startswith(storage_prefix):
        path = path.removeprefix(unquote(urlparse(storage_prefix).path))
    path = normpath(path).lstrip("/")
    if path.startswith("uploads/"):
        path = path[len("uploads/"):]
    return path if path and path != "." else None


async def lock_and_validate_featured_storefront_key(
    db: AsyncSession, featured_url: str | None
) -> None:
    """Reserve a featured key and reject it while cleanup still owns it."""
    key = storage_key_from_public_url(featured_url)
    if not key:
        return
    await lock_storage_keys(db, [key])
    pending_cleanup = await db.scalar(
        select(ProductImageStorageCleanup.id).where(
            ProductImageStorageCleanup.resolved_at.is_(None),
            ProductImageStorageCleanup.storage_keys.contains([key]),
        ).limit(1)
    )
    if pending_cleanup is not None:
        raise ValueError("Image storage key is reserved for pending cleanup")


async def lock_storage_keys(db: AsyncSession, storage_keys: Sequence[str]) -> list[str]:
    """Acquire transaction-scoped locks in canonical order for exact storage identities."""
    keys = sorted(set(key for key in storage_keys if key))
    for key in keys:
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})
    return keys


async def lock_and_validate_storage_keys(db: AsyncSession, storage_keys: Sequence[str]) -> None:
    """Serialize ownership checks and reject keys owned by any image."""
    keys = await lock_storage_keys(db, storage_keys)
    for key in keys:
        owned = await db.scalar(
            select(ProductImage.id).where(ProductImage.storage_keys.contains([key])).limit(1)
        )
        if owned is not None:
            raise ValueError("Image storage key is already associated with a product image")
        consumed_cleanup = await db.scalar(
            select(ProductImageStorageCleanup.id)
            .where(ProductImageStorageCleanup.storage_keys.contains([key]))
            .limit(1)
        )
        if consumed_cleanup is not None:
            raise ValueError("Image storage key was previously consumed and cannot be reused")


async def record_image_upload(db: AsyncSession, uploaded: dict) -> None:
    """Persist the upload response before allowing clients to associate its keys."""
    db.add(
        ProductImageUpload(
            image_url=uploaded["original"],
            thumbnail_url=uploaded.get("thumbnail"),
            storage_keys=list(uploaded.get("_storage_keys") or []),
        )
    )
    try:
        await db.commit()
    except Exception:
        # A lost commit acknowledgement must not trigger deletion of an upload
        # whose identity may already be durable. The client receives no success.
        await db.rollback()
        raise


async def validate_image_upload(
    db: AsyncSession,
    image_url: str,
    thumbnail_url: str | None,
    storage_keys: Sequence[str] | None,
) -> None:
    """Bind association URLs and the complete key set to one server-issued upload."""
    if not storage_keys:
        # Keep external legacy image support, but do not allow omission of keys
        # to turn an owned upload into an unprotected legacy reference.
        for url in (image_url, thumbnail_url):
            key = storage_key_from_public_url(url) or ""
            parts = key.split("/")
            if parts[0] == "vendors":
                raise ValueError(
                    "Uploaded product images require their server-issued storage keys"
                )
            if key:
                await lock_storage_keys(db, [key])
                owned = await db.scalar(
                    select(ProductImage.id)
                    .where(ProductImage.storage_keys.contains([key]))
                    .limit(1)
                )
                consumed = await db.scalar(
                    select(ProductImageStorageCleanup.id)
                    .where(ProductImageStorageCleanup.storage_keys.contains([key]))
                    .limit(1)
                )
                upload = await db.get(ProductImageUpload, url)
                if owned is not None or consumed is not None or upload is not None:
                    raise ValueError(
                        "Uploaded product images require their server-issued storage keys"
                    )
        return
    upload = await db.get(ProductImageUpload, image_url)
    if (
        upload is None
        or set(storage_keys) != set(upload.storage_keys)
        or thumbnail_url not in (None, image_url, upload.thumbnail_url)
    ):
        raise ValueError(
            "Image URL, thumbnail and storage keys must match the same upload"
        )


async def lock_and_validate_variation_image_urls(
    db: AsyncSession,
    image_urls: Sequence[str | None],
    *,
    product_id: UUID | None = None,
    new_image_urls: Sequence[str] = (),
) -> None:
    """Require a same-product image and reject keys consumed by cleanup."""
    urls = {url for url in image_urls if url}
    if not urls:
        return
    allowed_urls = set(new_image_urls)
    if product_id is not None:
        allowed_urls.update(
            (
                await db.scalars(
                    select(ProductImage.image_url).where(
                        ProductImage.product_id == product_id
                    )
                )
            ).all()
        )
    if not urls.issubset(allowed_urls):
        raise ValueError("Variation images must belong to this product")
    keys = {key for url in urls if (key := storage_key_from_public_url(url))}
    await lock_storage_keys(db, list(keys))
    for key in keys:
        pending_cleanup = await db.scalar(
            select(ProductImageStorageCleanup.id)
            .where(
                ProductImageStorageCleanup.storage_keys.contains([key]),
            )
            .limit(1)
        )
        if pending_cleanup is not None:
            raise ValueError(
                "Image storage key was previously consumed and cannot be reused"
            )


async def record_storage_cleanup(
    db: AsyncSession,
    storage_keys: Sequence[str],
    *,
    reason: str,
    product_id: Optional[UUID] = None,
    image_id: Optional[UUID] = None,
    commit: bool = True,
) -> Optional[ProductImageStorageCleanup]:
    """Persist exact keys for retry and return the durable record when created."""
    keys = list(dict.fromkeys(key for key in storage_keys if key))
    if not keys:
        return None
    try:
        cleanup = ProductImageStorageCleanup(
            product_id=product_id,
            image_id=image_id,
            storage_keys=keys,
            reason=reason,
        )
        db.add(cleanup)
        if commit:
            await db.commit()
        return cleanup
    except Exception:
        await db.rollback()
        logger.exception("Failed to persist product-image storage cleanup record", extra={"storage_keys": keys})
        raise
