"""Durable bookkeeping for product-image storage cleanup retries."""

import logging
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import ProductImage, ProductImageStorageCleanup

logger = logging.getLogger(__name__)


async def lock_and_validate_storage_keys(db: AsyncSession, storage_keys: Sequence[str]) -> None:
    """Serialize ownership checks and reject keys owned by any image."""
    keys = sorted(set(key for key in storage_keys if key))
    for key in keys:
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})
    for key in keys:
        owned = await db.scalar(
            select(ProductImage.id).where(ProductImage.storage_keys.contains([key])).limit(1)
        )
        if owned is not None:
            raise ValueError("Image storage key is already associated with a product image")


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