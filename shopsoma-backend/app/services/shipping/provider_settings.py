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
    secure_checkout_routing = (
        settings.DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED
        and settings.DOMESTIC_CHECKOUT_COHORT_PERCENTAGE == 100
        and settings.ENVIRONMENT != "production"
        and settings.DHL_ENVIRONMENT == "sandbox"
    )
    provider = rows.get("shipping_provider")
    if not provider:
        # Before the exclusive setting existed the secure route used the DHL
        # capability gate. Preserve that behavior without activating new gates.
        # Keep the effective provider as DHL when the capability is ready so
        # already-classified domestic orders can create DHL estimates during a
        # partial rollout. The public preliminary endpoint still remains
        # manual because checkout_estimates_required is false below.
        provider = "dhl" if dhl_ready else (
            "shipbubble" if (rows.get("shipping_use_shipbubble") or "").lower() == "true" else "manual"
        )
    elif provider == "dhl" and not secure_checkout_routing:
        # A rollout rollback must not strand the partial/legacy population on
        # the provider-only preview endpoint. Resolve the stale persisted
        # selection to the safe manual preview mode until full routing returns.
        provider = "manual"
    return ShippingProviderSettings(
        provider=provider,
        checkout_estimates_required=(
            secure_checkout_routing
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
    secure_checkout_routing = (
        settings.DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED
        and settings.DOMESTIC_CHECKOUT_COHORT_PERCENTAGE == 100
        and settings.ENVIRONMENT != "production"
        and settings.DHL_ENVIRONMENT == "sandbox"
    )
    if provider == "dhl" and not secure_checkout_routing:
        # Match shipping_provider_settings(): a stale DHL selection is
        # effectively manual while the rollout is partial or rolled back.
        provider = "manual"
    if provider != "manual":
        raise HTTPException(status_code=503, detail="Use secure checkout delivery estimates; manual pricing requires manual mode")
