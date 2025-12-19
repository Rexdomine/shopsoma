"""Settings API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
import logging

from app.core.database import get_db
from app.models.setting import Setting
from app.models.app_setting import AppSetting
from app.models.user import User
from app.schemas.setting import (
    SettingResponse,
    SettingUpdate,
    ExchangeRateUpdate,
    ExchangeRateResponse
)
from app.schemas.app_setting import (
    ShippingProviderSettings,
    ShippingProviderSettingsUpdate,
    AppSettingResponse,
)
from app.api.dependencies import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/public/exchange-rate", response_model=ExchangeRateResponse)
async def get_public_exchange_rate(db: AsyncSession = Depends(get_db)):
    """
    Get current exchange rate (public endpoint)

    This endpoint is accessible without authentication for frontend initialization.
    """
    result = await db.execute(
        select(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
    )
    setting = result.scalar_one_or_none()

    if not setting:
        # Return default if not found
        return ExchangeRateResponse(
            rate=833.0,
            updated_at=None
        )

    try:
        rate = float(setting.value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Invalid exchange rate format in database"
        )

    return ExchangeRateResponse(
        rate=rate,
        updated_at=setting.updated_at
    )


@router.get("/admin", response_model=List[SettingResponse])
async def get_all_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get all settings (admin only)

    Requires admin authentication.
    """
    result = await db.execute(select(Setting).order_by(Setting.key))
    settings = result.scalars().all()

    return [
        SettingResponse(
            id=str(setting.id),
            key=setting.key,
            value=setting.value,
            description=setting.description,
            created_at=setting.created_at,
            updated_at=setting.updated_at
        )
        for setting in settings
    ]


@router.patch("/admin/exchange-rate", response_model=ExchangeRateResponse)
async def update_exchange_rate(
    update_data: ExchangeRateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Update exchange rate (admin only)

    Updates the USD to NGN exchange rate.
    Requires admin authentication.
    """
    result = await db.execute(
        select(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
    )
    setting = result.scalar_one_or_none()

    if not setting:
        # Create if doesn't exist
        setting = Setting(
            key="exchange_rate_usd_to_ngn",
            value=str(update_data.rate),
            description="Exchange rate from USD to NGN (1 USD = X NGN)"
        )
        db.add(setting)
    else:
        setting.value = str(update_data.rate)

    await db.commit()
    await db.refresh(setting)

    return ExchangeRateResponse(
        rate=update_data.rate,
        updated_at=setting.updated_at
    )


@router.patch("/admin/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    update_data: SettingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Update a setting by key (admin only)

    Generic endpoint for updating any setting.
    Requires admin authentication.
    """
    result = await db.execute(
        select(Setting).where(Setting.key == key)
    )
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Setting with key '{key}' not found"
        )

    setting.value = update_data.value
    await db.commit()
    await db.refresh(setting)

    return SettingResponse(
        id=str(setting.id),
        key=setting.key,
        value=setting.value,
        description=setting.description,
        created_at=setting.created_at,
        updated_at=setting.updated_at
    )


# ============================================================================
# SHIPBUBBLE SETTINGS ENDPOINTS
# ============================================================================

async def get_app_setting_value(db: AsyncSession, key: str, default: str = "") -> str:
    """Helper to get app setting value by key"""
    query = select(AppSetting).where(AppSetting.key == key)
    result = await db.execute(query)
    setting = result.scalar_one_or_none()
    return setting.value if setting else default


async def update_app_setting_value(db: AsyncSession, key: str, value: str) -> None:
    """Helper to update app setting value by key"""
    query = select(AppSetting).where(AppSetting.key == key)
    result = await db.execute(query)
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = value
    else:
        # Create if doesn't exist
        new_setting = AppSetting(
            key=key,
            value=value,
            value_type="boolean" if value in ["true", "false"] else "string"
        )
        db.add(new_setting)

    await db.commit()


@router.get("/shipping-provider", response_model=ShippingProviderSettings)
async def get_shipping_provider_settings(
    db: AsyncSession = Depends(get_db)
):
    """
    Get shipping provider settings (public endpoint)

    Returns whether ShipBubble is enabled for shipping rates.
    """
    use_shipbubble_str = await get_app_setting_value(db, "shipping_use_shipbubble", "false")
    use_shipbubble = use_shipbubble_str.lower() == "true"

    logger.info(f"[Settings] ShipBubble enabled: {use_shipbubble}")

    return ShippingProviderSettings(use_shipbubble=use_shipbubble)


@router.put("/shipping-provider", response_model=ShippingProviderSettings)
async def update_shipping_provider_settings(
    settings: ShippingProviderSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Update shipping provider settings (Admin only)

    Toggle between ShipBubble and local shipping rates.
    """
    value_str = "true" if settings.use_shipbubble else "false"
    await update_app_setting_value(db, "shipping_use_shipbubble", value_str)

    logger.info(f"[Settings] Admin {current_user.email} updated ShipBubble to: {settings.use_shipbubble}")

    return ShippingProviderSettings(use_shipbubble=settings.use_shipbubble)


@router.get("/app-settings", response_model=List[AppSettingResponse])
async def get_all_app_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """
    Get all app settings (Admin only)

    Returns all application configuration settings.
    """
    query = select(AppSetting).order_by(AppSetting.key)
    result = await db.execute(query)
    settings = result.scalars().all()

    return settings
