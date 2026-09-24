"""Shared atomic product moderation transition."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import ModerationStatus, Product, ProductStatus
from app.models.stock_payment_persistence import coordinate_catalog_write


async def transition_product_moderation(
    *,
    db: AsyncSession,
    product_id: UUID,
    admin_id: UUID,
    target_status: ModerationStatus,
    moderation_notes: Optional[str],
    expected_updated_at: datetime,
):
    """Atomically allow exactly one pending product moderation transition."""
    if target_status is ModerationStatus.PENDING:
        raise HTTPException(status_code=422, detail="A moderation decision must be approved or rejected")

    now = datetime.now(timezone.utc)
    await coordinate_catalog_write(db, product_ids=[product_id])
    locked_status = await db.scalar(
        select(Product.status).where(Product.id == product_id).with_for_update()
    )
    if locked_status is None:
        raise HTTPException(status_code=404, detail="Product not found")

    values = {
        "moderation_status": target_status,
        "moderated_at": now,
        "moderated_by": admin_id,
        "moderation_notes": moderation_notes,
        "status": (
            ProductStatus.ACTIVE
            if target_status is ModerationStatus.APPROVED and locked_status is ProductStatus.DRAFT
            else locked_status
            if target_status is ModerationStatus.APPROVED
            else ProductStatus.DRAFT
        ),
    }
    result = await db.execute(
        update(Product)
        .where(
            Product.id == product_id,
            Product.moderation_status == ModerationStatus.PENDING,
            Product.updated_at == expected_updated_at,
        )
        .values(**values)
        .returning(
            Product.id,
            Product.title,
            Product.status,
            Product.moderation_status,
            Product.moderated_at,
            Product.moderated_by,
        )
    )
    transitioned = result.mappings().one_or_none()
    if transitioned is None:
        exists = await db.scalar(select(Product.id).where(Product.id == product_id))
        if exists is None:
            raise HTTPException(status_code=404, detail="Product not found")
        raise HTTPException(status_code=409, detail="Product moderation has already been decided or the product changed")
    await db.commit()
    return transitioned
