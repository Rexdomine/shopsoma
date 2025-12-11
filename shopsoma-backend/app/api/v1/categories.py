"""
Categories API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import uuid

from app.core.database import get_db
from app.models.category import Category
from app.schemas.category import CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=List[CategoryResponse])
async def get_categories(
    db: AsyncSession = Depends(get_db),
    parent_id: Optional[str] = None,
    include_inactive: bool = False
):
    """
    Get all categories, optionally filtered by parent_id.

    - If parent_id is None: returns root categories (primary categories like Men, Women, Beauty)
    - If parent_id is provided: returns subcategories of that parent
    - If include_inactive is False: only returns active categories
    """
    query = select(Category)

    if parent_id:
        # Get subcategories of specific parent
        query = query.where(Category.parent_id == uuid.UUID(parent_id))
    else:
        # Get root categories (no parent)
        query = query.where(Category.parent_id.is_(None))

    if not include_inactive:
        query = query.where(Category.is_active == True)

    query = query.order_by(Category.display_order, Category.name)

    result = await db.execute(query)
    categories = result.scalars().all()

    return categories


@router.get("/all", response_model=List[CategoryResponse])
async def get_all_categories(
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = False
):
    """
    Get all categories in a flat list (useful for product forms).
    """
    query = select(Category)

    if not include_inactive:
        query = query.where(Category.is_active == True)

    query = query.order_by(Category.parent_id.nulls_first(), Category.display_order, Category.name)

    result = await db.execute(query)
    categories = result.scalars().all()

    return categories


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get a single category by ID"""
    result = await db.execute(
        select(Category).where(Category.id == uuid.UUID(category_id))
    )
    category = result.scalar_one_or_none()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    return category
