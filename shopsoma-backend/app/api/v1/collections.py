"""
Collections API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import selectinload
from typing import List, Optional
import uuid
import re

from app.core.database import get_db
from app.models.collection import Collection
from app.models.product import Product, ProductStatus
from app.models.user import User
from app.schemas.collection import (
    CollectionCreate,
    CollectionUpdate,
    CollectionResponse,
    CollectionSummaryResponse,
    CollectionDetailResponse,
    CollectionProductsResponse,
    CollectionProductSummary,
    CollectionProductAssignRequest,
)
from app.api.dependencies import get_current_user
from app.models.vendor_pickup import VendorNotification

router = APIRouter(prefix="/collections", tags=["collections"])


def create_slug(name: str) -> str:
    """Create a URL-friendly slug from collection name"""
    slug = name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')


@router.get("", response_model=List[CollectionSummaryResponse])
async def get_collections(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_inactive: bool = Query(False)
):
    """
    Get all collections for the current vendor.

    - Only returns collections belonging to the current vendor
    - If include_inactive is False: only returns active collections
    """
    # Get vendor_id for current user
    from app.models.vendor import Vendor
    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    query = select(Collection).where(Collection.vendor_id == vendor.id)

    if not include_inactive:
        query = query.where(Collection.is_active == True)

    query = query.order_by(Collection.created_at.desc())

    result = await db.execute(query)
    collections = result.scalars().all()

    summaries: List[CollectionSummaryResponse] = []
    for collection in collections:
        count_result = await db.execute(
            select(func.count(Product.id)).where(
                and_(
                    Product.vendor_id == vendor.id,
                    Product.collection_id == collection.id,
                    Product.status != ProductStatus.ARCHIVED
                )
            )
        )
        products_available = count_result.scalar() or 0

        product_result = await db.execute(
            select(Product)
            .options(selectinload(Product.images))
            .where(
                and_(
                    Product.vendor_id == vendor.id,
                    Product.collection_id == collection.id,
                    Product.status != ProductStatus.ARCHIVED
                )
            )
            .order_by(Product.created_at.desc())
            .limit(3)
        )
        products = product_result.scalars().all()
        thumbnails: list[str] = []
        for product in products:
            image = next((img for img in product.images if img.is_primary), None)
            if not image and product.images:
                image = product.images[0]
            if image:
                thumbnails.append(image.thumbnail_url or image.image_url)

        summaries.append(
            CollectionSummaryResponse(
                id=collection.id,
                vendor_id=collection.vendor_id,
                name=collection.name,
                description=collection.description,
                banner_image_url=collection.banner_image_url,
                slug=collection.slug,
                is_active=collection.is_active,
                created_at=collection.created_at,
                updated_at=collection.updated_at,
                products_available=products_available,
                thumbnails=thumbnails,
            )
        )

    return summaries


@router.post("", response_model=CollectionResponse, status_code=201)
async def create_collection(
    collection_data: CollectionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new collection for the current vendor"""
    # Get vendor_id for current user
    from app.models.vendor import Vendor
    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    # Create slug from name
    slug = create_slug(collection_data.name)

    # Check if collection with same name already exists for this vendor
    existing = await db.execute(
        select(Collection).where(
            Collection.vendor_id == vendor.id,
            Collection.slug == slug
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Collection with name '{collection_data.name}' already exists"
        )

    # Create new collection
    collection = Collection(
        id=uuid.uuid4(),
        vendor_id=vendor.id,
        name=collection_data.name,
        slug=slug,
        description=collection_data.description,
        banner_image_url=collection_data.banner_image_url,
        is_active=True
    )

    db.add(collection)
    await db.commit()
    await db.refresh(collection)

    notification = VendorNotification(
        vendor_id=vendor.id,
        notification_type="collection_created",
        title="Collection created",
        message="Your collection is live. Add a banner image and manage products to complete it.",
        data={"collection_id": str(collection.id)},
    )
    db.add(notification)
    await db.commit()

    return collection


@router.get("/{collection_id}", response_model=CollectionDetailResponse)
async def get_collection(
    collection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a single collection by ID"""
    # Get vendor_id for current user
    from app.models.vendor import Vendor
    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    result = await db.execute(
        select(Collection).where(
            Collection.id == uuid.UUID(collection_id),
            Collection.vendor_id == vendor.id
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    count_result = await db.execute(
        select(func.count(Product.id)).where(
            and_(
                Product.vendor_id == vendor.id,
                Product.collection_id == collection.id,
                Product.status != ProductStatus.ARCHIVED
            )
        )
    )
    products_available = count_result.scalar() or 0

    product_result = await db.execute(
        select(Product)
        .options(selectinload(Product.images))
        .where(
            and_(
                Product.vendor_id == vendor.id,
                Product.collection_id == collection.id,
                Product.status != ProductStatus.ARCHIVED
            )
        )
        .order_by(Product.created_at.desc())
        .limit(3)
    )
    products = product_result.scalars().all()
    thumbnails: list[str] = []
    for product in products:
        image = next((img for img in product.images if img.is_primary), None)
        if not image and product.images:
            image = product.images[0]
        if image:
            thumbnails.append(image.thumbnail_url or image.image_url)

    return CollectionDetailResponse(
        id=collection.id,
        vendor_id=collection.vendor_id,
        name=collection.name,
        description=collection.description,
        banner_image_url=collection.banner_image_url,
        slug=collection.slug,
        is_active=collection.is_active,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        products_available=products_available,
        thumbnails=thumbnails,
    )


@router.patch("/{collection_id}", response_model=CollectionResponse)
async def update_collection(
    collection_id: str,
    collection_data: CollectionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a collection"""
    # Get vendor_id for current user
    from app.models.vendor import Vendor
    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    result = await db.execute(
        select(Collection).where(
            Collection.id == uuid.UUID(collection_id),
            Collection.vendor_id == vendor.id
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    # Update fields
    if collection_data.name is not None:
        collection.name = collection_data.name
        collection.slug = create_slug(collection_data.name)
    if collection_data.description is not None:
        collection.description = collection_data.description
    if collection_data.banner_image_url is not None:
        collection.banner_image_url = collection_data.banner_image_url
    if collection_data.is_active is not None:
        collection.is_active = collection_data.is_active

    await db.commit()
    await db.refresh(collection)

    return collection


@router.get("/{collection_id}/products", response_model=CollectionProductsResponse)
async def list_collection_products(
    collection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=255),
):
    """List products assigned to a collection"""
    from app.models.vendor import Vendor

    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    collection_result = await db.execute(
        select(Collection).where(
            Collection.id == uuid.UUID(collection_id),
            Collection.vendor_id == vendor.id
        )
    )
    collection = collection_result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    query = select(Product).options(
        selectinload(Product.images),
        selectinload(Product.collection),
    ).where(
        and_(
            Product.vendor_id == vendor.id,
            Product.collection_id == collection.id,
            Product.status != ProductStatus.ARCHIVED
        )
    )
    if search:
        query = query.where(Product.title.ilike(f"%{search}%"))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Product.created_at.desc()).offset(offset).limit(page_size)
    )
    products = result.scalars().all()

    items: list[CollectionProductSummary] = []
    for product in products:
        image = next((img for img in product.images if img.is_primary), None)
        if not image and product.images:
            image = product.images[0]
        items.append(
            CollectionProductSummary(
                id=product.id,
                title=product.title,
                status=product.status.value if hasattr(product.status, "value") else str(product.status),
                base_price=float(product.base_price),
                total_stock=product.total_stock or 0,
                created_at=product.created_at,
                image_url=(image.thumbnail_url or image.image_url) if image else None,
                collection_name=product.collection_name,
            )
        )

    return CollectionProductsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{collection_id}/available-products", response_model=CollectionProductsResponse)
async def list_available_collection_products(
    collection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=255),
):
    """List vendor products not assigned to this collection"""
    from app.models.vendor import Vendor

    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    collection_uuid = uuid.UUID(collection_id)
    query = select(Product).options(
        selectinload(Product.images),
        selectinload(Product.collection),
    ).where(
        and_(
            Product.vendor_id == vendor.id,
            Product.status != ProductStatus.ARCHIVED,
            or_(Product.collection_id.is_(None), Product.collection_id != collection_uuid)
        )
    )
    if search:
        query = query.where(Product.title.ilike(f"%{search}%"))

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    result = await db.execute(
        query.order_by(Product.created_at.desc()).offset(offset).limit(page_size)
    )
    products = result.scalars().all()

    items: list[CollectionProductSummary] = []
    for product in products:
        image = next((img for img in product.images if img.is_primary), None)
        if not image and product.images:
            image = product.images[0]
        items.append(
            CollectionProductSummary(
                id=product.id,
                title=product.title,
                status=product.status.value if hasattr(product.status, "value") else str(product.status),
                base_price=float(product.base_price),
                total_stock=product.total_stock or 0,
                created_at=product.created_at,
                image_url=(image.thumbnail_url or image.image_url) if image else None,
                collection_name=product.collection_name,
            )
        )

    return CollectionProductsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/{collection_id}/products", status_code=status.HTTP_200_OK)
async def add_products_to_collection(
    collection_id: str,
    payload: CollectionProductAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add products to a collection"""
    from app.models.vendor import Vendor

    product_ids = payload.product_ids
    if not product_ids:
        raise HTTPException(status_code=400, detail="product_ids is required.")

    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    collection_result = await db.execute(
        select(Collection).where(
            Collection.id == uuid.UUID(collection_id),
            Collection.vendor_id == vendor.id
        )
    )
    collection = collection_result.scalar_one_or_none()
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    result = await db.execute(
        select(Product).where(
            and_(
                Product.vendor_id == vendor.id,
                Product.id.in_(product_ids)
            )
        )
    )
    products = result.scalars().all()

    for product in products:
        product.collection_id = collection.id

    await db.commit()

    return {"updated_count": len(products)}


@router.delete("/{collection_id}/products/{product_id}", status_code=status.HTTP_200_OK)
async def remove_product_from_collection(
    collection_id: str,
    product_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a product from a collection"""
    from app.models.vendor import Vendor

    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    product_result = await db.execute(
        select(Product).where(
            and_(
                Product.id == uuid.UUID(product_id),
                Product.vendor_id == vendor.id,
                Product.collection_id == uuid.UUID(collection_id)
            )
        )
    )
    product = product_result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found in collection")

    product.collection_id = None
    await db.commit()

    return {"removed": True}


@router.delete("/{collection_id}", status_code=204)
async def delete_collection(
    collection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a collection"""
    # Get vendor_id for current user
    from app.models.vendor import Vendor
    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    result = await db.execute(
        select(Collection).where(
            Collection.id == uuid.UUID(collection_id),
            Collection.vendor_id == vendor.id
        )
    )
    collection = result.scalar_one_or_none()

    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    await db.delete(collection)
    await db.commit()

    return None
