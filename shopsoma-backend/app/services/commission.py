"""Commission helpers for vendor and order calculations."""
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.models.vendor import Vendor

DEFAULT_COMMISSION_RATE = Decimal("12.5")
COMMISSION_SETTING_KEY = "default_commission_rate"


def normalize_commission_rate(value: Optional[object]) -> Decimal:
    """Return a safe commission percentage, not a fraction."""
    if value is None:
        return DEFAULT_COMMISSION_RATE

    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return DEFAULT_COMMISSION_RATE

    if rate < 0 or rate > 100:
        return DEFAULT_COMMISSION_RATE

    return rate.quantize(Decimal("0.01"))


async def get_default_commission_rate(db: AsyncSession) -> Decimal:
    """Get the admin-managed default commission percentage for new vendors."""
    result = await db.execute(
        select(AppSetting).where(AppSetting.key == COMMISSION_SETTING_KEY)
    )
    setting = result.scalar_one_or_none()
    return normalize_commission_rate(setting.value if setting else None)


def get_vendor_commission_rate(vendor: Optional[Vendor]) -> Decimal:
    """Get a vendor commission percentage, falling back to the platform default."""
    return normalize_commission_rate(vendor.commission_rate if vendor else None)
