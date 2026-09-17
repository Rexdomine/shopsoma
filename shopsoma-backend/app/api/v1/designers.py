"""Public designers API endpoints"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import exists, func, or_, select

from app.core.database import get_db
from app.models.category import Category
from app.models.product import ModerationStatus, Product, ProductStatus
from app.models.user import User
from app.models.vendor import Vendor
from app.schemas.vendor import DesignerResponse, FeaturedStorefrontVendorResponse

router = APIRouter(prefix="/designers", tags=["Designers"])


@router.get("", response_model=List[DesignerResponse])
async def list_designers(db: AsyncSession = Depends(get_db)):
    """List approved designers for public storefront browsing."""
    result = await db.execute(
        select(Vendor)
        .join(User, Vendor.user_id == User.id)
        .where(
            Vendor.approved.is_(True),
            Vendor.is_onboarding.is_(False),
            Vendor.store_active.is_(True),
            Vendor.store_deleted_at.is_(None),
            User.is_active.is_(True),
        )
        .order_by(Vendor.created_at.desc())
    )
    return result.scalars().all()


@router.get("/featured", response_model=List[FeaturedStorefrontVendorResponse])
async def list_featured_storefront_vendors(
    category: str,
    db: AsyncSession = Depends(get_db),
):
    """Return only safe, admin-curated vendors eligible for a public storefront."""
    normalized_category = category.strip().lower()
    if normalized_category not in {"men", "women"}:
        return []

    primary_category = await db.scalar(
        select(Category).where(
            func.lower(Category.name) == normalized_category,
            Category.parent_id.is_(None),
            Category.is_active.is_(True),
        )
    )
    if primary_category is None:
        return []

    category_filter = or_(
        Product.category_id == primary_category.id,
        Product.category.has(Category.parent_id == primary_category.id),
    )
    eligible_product = exists(
        select(Product.id).where(
            Product.vendor_id == Vendor.id,
            Product.status == ProductStatus.ACTIVE,
            Product.moderation_status == ModerationStatus.APPROVED,
            category_filter,
        )
    )
    product_count = (
        select(func.count(Product.id))
        .where(
            Product.vendor_id == Vendor.id,
            Product.status == ProductStatus.ACTIVE,
            Product.moderation_status == ModerationStatus.APPROVED,
            category_filter,
        )
        .correlate(Vendor)
        .scalar_subquery()
    )
    result = await db.execute(
        select(Vendor.id, Vendor.business_name, Vendor.featured_storefront_image_url, product_count.label("product_count"))
        .join(User, Vendor.user_id == User.id)
        .where(
            Vendor.is_featured_storefront.is_(True),
            Vendor.approved.is_(True),
            Vendor.is_onboarding.is_(False),
            Vendor.store_active.is_(True),
            Vendor.store_deleted_at.is_(None),
            User.is_active.is_(True),
            Vendor.featured_storefront_image_url.is_not(None),
            Vendor.featured_storefront_image_url != "",
            eligible_product,
        )
        .order_by(Vendor.updated_at.desc(), Vendor.id.asc())
    )
    return [
        FeaturedStorefrontVendorResponse(
            id=row.id,
            business_name=row.business_name,
            featured_storefront_image_url=row.featured_storefront_image_url,
            product_count=row.product_count,
        )
        for row in result.all()
    ]
