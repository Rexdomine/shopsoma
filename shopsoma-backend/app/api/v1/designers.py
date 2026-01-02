"""Public designers API endpoints"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.vendor import Vendor
from app.schemas.vendor import DesignerResponse

router = APIRouter(prefix="/designers", tags=["Designers"])


@router.get("", response_model=List[DesignerResponse])
async def list_designers(db: AsyncSession = Depends(get_db)):
    """List approved designers for public storefront browsing."""
    result = await db.execute(
        select(Vendor)
        .where(Vendor.approved.is_(True))
        .order_by(Vendor.created_at.desc())
    )
    return result.scalars().all()
