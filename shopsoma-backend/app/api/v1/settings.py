"""Settings API endpoints"""
import logging
import os
import shutil
import subprocess
import tempfile
import time
from typing import List
from urllib.parse import urlparse

import anyio
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    PayoutHoldSettings,
    PayoutHoldSettingsUpdate,
    DatabaseSyncResponse,
)
from app.api.dependencies import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])

LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "host.docker.internal"}


def _normalize_sync_db_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def _is_local_database(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() in LOCAL_DB_HOSTS


def _run_db_sync(source_url: str, target_url: str) -> None:
    if not shutil.which("pg_dump"):
        raise RuntimeError("pg_dump is not available on PATH")
    if not shutil.which("pg_restore"):
        raise RuntimeError("pg_restore is not available on PATH")

    temp_file = tempfile.NamedTemporaryFile(suffix=".dump", delete=False)
    temp_path = temp_file.name
    temp_file.close()

    try:
        subprocess.run(
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                temp_path,
                source_url,
            ],
            check=True,
            env=os.environ.copy(),
        )
        subprocess.run(
            [
                "pg_restore",
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-privileges",
                "--dbname",
                target_url,
                temp_path,
            ],
            check=True,
            env=os.environ.copy(),
        )
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


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


@router.get("/admin/payout-hold", response_model=PayoutHoldSettings)
async def get_payout_hold_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Get payout hold settings (Admin only)."""
    from app.core.config import settings as app_settings

    result = await db.execute(
        select(AppSetting).where(AppSetting.key == "payout_hold_days")
    )
    setting = result.scalar_one_or_none()

    if setting and setting.value is not None:
        try:
            hold_days = int(setting.value)
        except ValueError:
            hold_days = app_settings.PAYOUT_HOLD_DAYS
        updated_at = setting.updated_at
    else:
        hold_days = app_settings.PAYOUT_HOLD_DAYS
        updated_at = None

    hold_days = max(hold_days, 0)

    return PayoutHoldSettings(hold_days=hold_days, updated_at=updated_at)


@router.put("/admin/payout-hold", response_model=PayoutHoldSettings)
async def update_payout_hold_settings(
    payload: PayoutHoldSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)
):
    """Update payout hold settings (Admin only)."""
    await update_app_setting_value(db, "payout_hold_days", str(payload.hold_days))

    result = await db.execute(
        select(AppSetting).where(AppSetting.key == "payout_hold_days")
    )
    setting = result.scalar_one_or_none()
    updated_at = setting.updated_at if setting else None

    logger.info(f"[Settings] Admin {current_user.email} updated payout hold days to {payload.hold_days}")

    return PayoutHoldSettings(hold_days=payload.hold_days, updated_at=updated_at)


@router.post("/admin/db-sync", response_model=DatabaseSyncResponse)
async def sync_render_database(
    current_user: User = Depends(require_admin),
):
    """Sync Render database to local database (Admin only, development environments)."""
    from app.core.config import settings as app_settings

    environment = app_settings.ENVIRONMENT.lower()
    if environment not in {"development", "local"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Database sync is only available in local development environments.",
        )

    if not app_settings.RENDER_DATABASE_URL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="RENDER_DATABASE_URL is not configured.",
        )

    if not _is_local_database(app_settings.DATABASE_URL):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target database must be a local database.",
        )

    source_url = _normalize_sync_db_url(app_settings.RENDER_DATABASE_URL)
    target_url = _normalize_sync_db_url(app_settings.DATABASE_URL)

    start_time = time.monotonic()
    try:
        await anyio.to_thread.run_sync(_run_db_sync, source_url, target_url)
    except RuntimeError as exc:
        logger.exception("[Settings] Database sync failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )
    except subprocess.CalledProcessError as exc:
        logger.exception("[Settings] Database sync command failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database sync failed. Check server logs for details.",
        )

    duration = round(time.monotonic() - start_time, 2)
    logger.info(
        "[Settings] Admin %s synced Render DB to local in %ss",
        current_user.email,
        duration,
    )

    return DatabaseSyncResponse(
        status="success",
        message="Render database synced to local database.",
        duration_seconds=duration,
    )
