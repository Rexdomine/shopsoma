"""Public designers API endpoints"""
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.category import Category
from app.models.product import ModerationStatus, Product, ProductStatus
from app.models.user import User
from app.models.vendor import Vendor
from app.models.vendor_asset import VendorAsset
from app.schemas.vendor import (
    DesignerCategoryResponse,
    DesignerResponse,
    FeaturedStorefrontVendorResponse,
)

router = APIRouter(prefix="/designers", tags=["Designers"])


def _public_designer_criteria():
    """Eligibility criteria for a vendor to appear as a public designer."""
    return (
        Vendor.approved.is_(True),
        Vendor.is_onboarding.is_(False),
        Vendor.store_active.is_(True),
        Vendor.store_deleted_at.is_(None),
        User.is_active.is_(True),
    )


def _clean_url(value: Optional[str]) -> Optional[str]:
    if not value or not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _extract_product_image_url(product: Product) -> Optional[str]:
    """Extract the best available image URL from a published product."""
    images = sorted(
        list(product.images or []),
        key=lambda img: (
            not bool(getattr(img, "is_primary", False)),
            int(getattr(img, "display_order", 0) or 0),
        ),
    )
    for image in images:
        candidate = _clean_url(getattr(image, "image_url", None)) or _clean_url(
            getattr(image, "thumbnail_url", None)
        )
        if candidate:
            return candidate

    variations = sorted(
        [v for v in (product.variations or []) if getattr(v, "is_active", True)],
        key=lambda v: int(getattr(v, "display_order", 0) or 0),
    )
    for variation in variations:
        raw_images = getattr(variation, "images", None) or []
        if isinstance(raw_images, list):
            for raw_url in raw_images:
                candidate = _clean_url(raw_url)
                if candidate:
                    return candidate

    return None


async def _hydrate_designers(
    db: AsyncSession,
    vendors: List[Vendor],
) -> List[DesignerResponse]:
    """Hydrate public DesignerResponse payloads using only approved/published data."""
    if not vendors:
        return []

    vendor_ids = [vendor.id for vendor in vendors]

    assets_result = await db.execute(
        select(VendorAsset)
        .where(
            VendorAsset.vendor_id.in_(vendor_ids),
            VendorAsset.is_active.is_(True),
            VendorAsset.asset_type.in_(["banner", "logo"]),
        )
        .order_by(
            VendorAsset.display_order.asc(),
            VendorAsset.created_at.desc(),
        )
    )
    banner_by_vendor: Dict[UUID, str] = {}
    logo_asset_by_vendor: Dict[UUID, str] = {}
    for asset in assets_result.scalars().all():
        file_url = _clean_url(asset.file_url)
        if not file_url:
            continue
        if asset.asset_type == "banner" and asset.vendor_id not in banner_by_vendor:
            banner_by_vendor[asset.vendor_id] = file_url
        elif asset.asset_type == "logo" and asset.vendor_id not in logo_asset_by_vendor:
            logo_asset_by_vendor[asset.vendor_id] = file_url

    products_result = await db.execute(
        select(Product)
        .options(
            selectinload(Product.images),
            selectinload(Product.variations),
            selectinload(Product.category),
        )
        .where(
            Product.vendor_id.in_(vendor_ids),
            Product.status == ProductStatus.ACTIVE,
            Product.moderation_status == ModerationStatus.APPROVED,
        )
        .order_by(
            Product.is_featured.desc(),
            Product.created_at.desc(),
        )
    )
    published_products_by_vendor: Dict[UUID, List[Product]] = {
        vendor_id: [] for vendor_id in vendor_ids
    }
    for product in products_result.scalars().all():
        published_products_by_vendor.setdefault(product.vendor_id, []).append(product)

    responses: List[DesignerResponse] = []
    for vendor in vendors:
        published_products = published_products_by_vendor.get(vendor.id, [])
        published_product_image: Optional[str] = None
        categories_by_id: Dict[UUID, Category] = {}

        for product in published_products:
            if published_product_image is None:
                published_product_image = _extract_product_image_url(product)
            category = getattr(product, "category", None)
            if category is not None and getattr(category, "is_active", True):
                categories_by_id[category.id] = category

        sorted_categories = sorted(
            categories_by_id.values(),
            key=lambda cat: (int(getattr(cat, "display_order", 0) or 0), (cat.name or "").lower()),
        )

        featured_image = _clean_url(vendor.featured_storefront_image_url)
        banner_image = banner_by_vendor.get(vendor.id)
        resolved_logo = _clean_url(vendor.logo_url) or logo_asset_by_vendor.get(vendor.id)

        campaign_image = (
            featured_image
            or banner_image
            or published_product_image
            or resolved_logo
        )
        best_image = (
            featured_image
            or banner_image
            or published_product_image
            or resolved_logo
        )

        responses.append(
            DesignerResponse(
                id=vendor.id,
                business_name=vendor.business_name,
                business_description=vendor.business_description,
                logo_url=resolved_logo,
                featured_storefront_image_url=featured_image,
                is_featured_storefront=bool(vendor.is_featured_storefront),
                image_url=best_image,
                campaign_image_url=campaign_image,
                total_products=vendor.total_products or 0,
                published_products_count=len(published_products),
                total_orders=vendor.total_orders or 0,
                categories=[
                    DesignerCategoryResponse.model_validate(cat)
                    for cat in sorted_categories
                ],
                created_at=vendor.created_at,
            )
        )

    return responses


@router.get("", response_model=List[DesignerResponse])
async def list_designers(
    search: Optional[str] = Query(None, description="Search designers by business name"),
    letter: Optional[str] = Query(None, description="Filter designers by starting letter (A-Z)"),
    db: AsyncSession = Depends(get_db),
):
    """List active, approved designers for public directory browsing."""
    query = (
        select(Vendor)
        .join(User, Vendor.user_id == User.id)
        .where(*_public_designer_criteria())
    )

    if search and search.strip():
        query = query.where(Vendor.business_name.ilike(f"%{search.strip()}%"))

    if letter and letter.strip():
        normalized_letter = letter.strip().upper()
        if len(normalized_letter) == 1 and normalized_letter.isalpha():
            query = query.where(
                func.upper(func.substr(func.trim(Vendor.business_name), 1, 1))
                == normalized_letter
            )

    query = query.order_by(
        func.lower(Vendor.business_name).asc(),
        Vendor.created_at.desc(),
    )

    result = await db.execute(query)
    vendors = list(result.scalars().all())
    return await _hydrate_designers(db, vendors)


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
            *_public_designer_criteria(),
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


@router.get("/{designer_id}", response_model=DesignerResponse)
async def get_designer(
    designer_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single active, approved designer for their public storefront."""
    result = await db.execute(
        select(Vendor)
        .join(User, Vendor.user_id == User.id)
        .where(
            Vendor.id == designer_id,
            *_public_designer_criteria(),
        )
    )
    vendor = result.scalar_one_or_none()
    if vendor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Designer not found",
        )

    hydrated = await _hydrate_designers(db, [vendor])
    return hydrated[0]
