"""Manage preference endpoints"""
from datetime import datetime
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.dependencies import get_current_active_user
from app.core.database import get_db
from app.models.user import User
from app.models.manage_preference import ManagePreference
from app.models.category import Category
from app.models.vendor import Vendor
from app.schemas.preference import (
    PreferenceResponse,
    PreferenceUpdate,
    PreferenceOptionsResponse,
    PreferenceCategoryOption,
    PreferenceDesignerOption,
)

router = APIRouter(prefix="/preferences", tags=["Preferences"])


@router.get("", response_model=PreferenceResponse)
async def get_preferences(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ManagePreference).where(ManagePreference.user_id == current_user.id))
    preference = result.scalar_one_or_none()
    if not preference:
        return PreferenceResponse()
    return preference


@router.get("/options", response_model=PreferenceOptionsResponse)
async def get_preference_options(
    _current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return available designer and category options sourced from the database."""
    category_result = await db.execute(
        select(Category.id, Category.name, Category.slug)
        .where(Category.is_active.is_(True))
        .order_by(Category.name.asc())
    )
    categories = [
        PreferenceCategoryOption(id=row.id, name=row.name, slug=row.slug)
        for row in category_result.all()
    ]

    designer_result = await db.execute(
        select(Vendor.id, Vendor.business_name)
        .where(Vendor.approved.is_(True))
        .order_by(Vendor.business_name.asc())
    )
    designers = [
        PreferenceDesignerOption(id=row.id, name=row.business_name)
        for row in designer_result.all()
        if row.business_name
    ]

    return PreferenceOptionsResponse(categories=categories, designers=designers)


@router.put("", response_model=PreferenceResponse, status_code=status.HTTP_200_OK)
async def update_preferences(
    payload: PreferenceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ManagePreference).where(ManagePreference.user_id == current_user.id))
    preference = result.scalar_one_or_none()

    if preference:
        preference.interest = payload.interest
        preference.preferred_language = payload.preferred_language
        preference.preferred_currency = payload.preferred_currency
        preference.favorite_designers = payload.favorite_designers or []
        preference.favorite_categories = payload.favorite_categories or []
        preference.updated_at = datetime.utcnow()
    else:
        preference = ManagePreference(
            user_id=current_user.id,
            interest=payload.interest,
            preferred_language=payload.preferred_language,
            preferred_currency=payload.preferred_currency,
            favorite_designers=payload.favorite_designers or [],
            favorite_categories=payload.favorite_categories or [],
        )
        db.add(preference)

    await db.commit()
    await db.refresh(preference)
    return preference
