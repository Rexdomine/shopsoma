"""Durable bookkeeping for product-image storage cleanup retries."""

import logging
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import ProductImageStorageCleanup

logger = logging.getLogger(__name__)


async def record_storage_cleanup(
    db: AsyncSession,
    storage_keys: Sequence[str],
    *,
    reason: str,
    product_id: Optional[UUID] = None,
    image_id: Optional[UUID] = None,
) -> None:
    """Persist failed/unresolved keys so a later reconciler can retry them."""
    keys = list(dict.fromkeys(key for key in storage_keys if key))
    if not keys:
        return
    try:
        db.add(ProductImageStorageCleanup(
            product_id=product_id,
            image_id=image_id,
            storage_keys=keys,
            reason=reason,
        ))
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Failed to persist product-image storage cleanup record", extra={"storage_keys": keys})