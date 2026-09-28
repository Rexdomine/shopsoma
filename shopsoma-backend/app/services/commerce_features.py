"""Persisted storefront gates, separate from historical financial truth."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.app_setting import AppSetting
from app.schemas.app_setting import CommerceFeatures


async def get_commerce_features(db: AsyncSession) -> CommerceFeatures:
    keys = tuple(CommerceFeatures.model_fields)
    rows = (await db.execute(select(AppSetting).where(AppSetting.key.in_(keys)))).scalars().all()
    values = {row.key: row.value == "true" for row in rows}
    return CommerceFeatures(**values)


async def shopping_currency(db: AsyncSession, requested: str) -> str:
    if requested == "USD" and not (await get_commerce_features(db)).usd_switching_enabled:
        return "NGN"
    return requested
