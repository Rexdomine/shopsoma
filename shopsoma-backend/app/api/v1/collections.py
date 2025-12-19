"""
Collections API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import uuid
import re

from app.core.database import get_db
from app.models.collection import Collection
from app.models.user import User
from app.schemas.collection import CollectionCreate, CollectionUpdate, CollectionResponse
from app.api.dependencies import get_current_user

router = APIRouter(prefix="/collections", tags=["collections"])


def create_slug(name: str) -> str:
    """Create a URL-friendly slug from collection name"""
    slug = name.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')


@router.get("", response_model=List[CollectionResponse])
async def get_collections(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_inactive: bool = False
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

    return collections


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
        is_active=True
    )

    db.add(collection)
    await db.commit()
    await db.refresh(collection)

    return collection


@router.get("/{collection_id}", response_model=CollectionResponse)
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

    return collection


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
    if collection_data.is_active is not None:
        collection.is_active = collection_data.is_active

    await db.commit()
    await db.refresh(collection)

    return collection


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
