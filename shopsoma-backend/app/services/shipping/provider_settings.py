"""One effective provider policy for settings and new checkout estimates."""
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.app_setting import AppSetting
from app.schemas.app_setting import ShippingProviderSettings
from app.services.shipping.capabilities import domestic_shipping_capabilities


async def shipping_provider_settings(db):
    rows = dict((await db.execute(
        select(AppSetting.key, AppSetting.value).where(AppSetting.key.in_((
            "shipping_provider", "shipping_use_shipbubble",
        )))
    )).all())
    dhl_ready = (
        settings.ENVIRONMENT != "production"
        and domestic_shipping_capabilities(settings).checkout_enabled
    )
    provider = rows.get("shipping_provider")
    if not provider:
        # Before the exclusive setting existed the secure route used the DHL
        # capability gate. Preserve that behavior without activating new gates.
        provider = "dhl" if dhl_ready else (
            "shipbubble" if (rows.get("shipping_use_shipbubble") or "").lower() == "true" else "manual"
        )
    return ShippingProviderSettings(
        provider=provider,
        checkout_estimates_required=(
            settings.DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED
            and settings.DOMESTIC_CHECKOUT_COHORT_PERCENTAGE == 100
            and settings.ENVIRONMENT != "production"
            and settings.DHL_ENVIRONMENT == "sandbox"
        ),
        use_shipbubble=provider == "shipbubble",
        readiness={"manual": True, "shipbubble": False, "dhl": dhl_ready},
    )


async def require_manual_order_pricing(db):
    """Reject nonmanual selection without changing pre-selection DHL routing."""
    rows = dict((await db.execute(
        select(AppSetting.key, AppSetting.value).where(AppSetting.key.in_((
            "shipping_provider", "shipping_use_shipbubble",
        )))
    )).all())
    provider = rows.get("shipping_provider") or (
        "shipbubble" if (rows.get("shipping_use_shipbubble") or "").lower() == "true" else "manual"
    )
    if provider != "manual":
        raise HTTPException(status_code=503, detail="Use secure checkout delivery estimates; manual pricing requires manual mode")
