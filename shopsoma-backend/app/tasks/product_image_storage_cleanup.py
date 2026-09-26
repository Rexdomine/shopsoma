"""Reconcile durable product-image storage cleanup records."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal, engine
from app.models.product import ProductImageStorageCleanup
from app.services.image_service import image_service


async def reconcile_product_image_storage_cleanups(*, session_factory=AsyncSessionLocal, limit: int = 100):
    resolved = remaining = 0
    async with session_factory() as session:
        rows = list((await session.scalars(
            select(ProductImageStorageCleanup)
            .where(ProductImageStorageCleanup.resolved_at.is_(None))
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
            try:
                result = await image_service.delete_images(list(row.storage_keys))
                failed = result.get("failed_keys", []) if isinstance(result, dict) else list(row.storage_keys)
                if not failed:
                    row.resolved_at = datetime.now(timezone.utc)
                    resolved += 1
                else:
                    row.last_attempted_at = datetime.now(timezone.utc)
                    remaining += 1
            except Exception:
                row.last_attempted_at = datetime.now(timezone.utc)
                remaining += 1
        await session.commit()
    return {"resolved": resolved, "remaining": remaining}


def reconcile_product_image_storage_cleanup() -> dict[str, int]:
    try:
        return asyncio.run(reconcile_product_image_storage_cleanups())
    finally:
        asyncio.run(engine.dispose())
