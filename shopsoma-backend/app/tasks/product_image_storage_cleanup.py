"""Reconcile durable product-image storage cleanup records."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select

from app.core.database import AsyncSessionLocal, engine
from app.models.product import ProductImageStorageCleanup
from app.services.image_service import image_service

logger = logging.getLogger(__name__)


CLAIM_LEASE = timedelta(minutes=5)


async def reconcile_product_image_storage_cleanups(*, session_factory=AsyncSessionLocal, limit: int = 100):
    """Claim bounded work durably, then delete externally without DB row locks."""
    resolved = remaining = 0
    claimed_at = datetime.now(timezone.utc)
    lease_cutoff = claimed_at - CLAIM_LEASE
    claimed_rows: list[tuple[object, list[str]]] = []

    async with session_factory() as session:
        rows = list((await session.scalars(
            select(ProductImageStorageCleanup)
            .where(
                ProductImageStorageCleanup.resolved_at.is_(None),
                or_(
                    ProductImageStorageCleanup.claimed_at.is_(None),
                    ProductImageStorageCleanup.claimed_at < lease_cutoff,
                ),
            )
            .order_by(
                func.coalesce(
                    ProductImageStorageCleanup.last_attempted_at,
                    ProductImageStorageCleanup.created_at,
                ),
                ProductImageStorageCleanup.id,
            )
            .with_for_update(skip_locked=True).limit(limit)
        )).all())
        for row in rows:
            row.claimed_at = claimed_at
            row.last_attempted_at = claimed_at
            claimed_rows.append((row.id, list(row.storage_keys)))
        await session.commit()

    for row_id, storage_keys in claimed_rows:
        failed_keys = storage_keys
        try:
            result = await image_service.delete_images(storage_keys)
            failed_keys = result.get("failed_keys", storage_keys) if isinstance(result, dict) else storage_keys
        except Exception:
            logger.exception(
                "Product image storage cleanup retry failed",
                extra={"cleanup_id": str(row_id), "storage_keys": storage_keys},
            )

        async with session_factory() as session:
            row = await session.get(ProductImageStorageCleanup, row_id, with_for_update=True)
            if row is None or row.resolved_at is not None or row.claimed_at != claimed_at:
                # A recovered/competing worker owns the terminal outcome; do not overwrite it.
                remaining += 1
                continue
            if not failed_keys:
                row.resolved_at = datetime.now(timezone.utc)
                row.claimed_at = None
                resolved += 1
            else:
                row.last_attempted_at = datetime.now(timezone.utc)
                row.claimed_at = None
                remaining += 1
            try:
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "Product image cleanup result bookkeeping failed",
                    extra={"cleanup_id": str(row_id), "storage_keys": storage_keys},
                )
                remaining += 1
                if not failed_keys:
                    resolved -= 1
    return {"resolved": resolved, "remaining": remaining}


def reconcile_product_image_storage_cleanup() -> dict[str, int]:
    try:
        return asyncio.run(reconcile_product_image_storage_cleanups())
    finally:
        asyncio.run(engine.dispose())
