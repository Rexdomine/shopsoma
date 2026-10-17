"""One effective provider policy for settings and new checkout estimates."""
import json
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.app_setting import AppSetting
from app.schemas.app_setting import ShippingProviderSettings
from app.services.shipping.capabilities import domestic_shipping_capabilities


async def shipping_provider_settings(db):
    rows = dict((await db.execute(
        select(AppSetting.key, AppSetting.value).where(AppSetting.key.in_((
            "shipping_provider", "shipping_use_shipbubble", "shipping_enabled_providers",
        )))
    )).all())
    shipbubble_ready = settings.shipbubble_configured
    dhl_ready = (
        settings.ENVIRONMENT != "production"
        and domestic_shipping_capabilities(settings).checkout_enabled
    )
    dhl_secure_checkout_routing = (
        settings.DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED
        and settings.DOMESTIC_CHECKOUT_COHORT_PERCENTAGE == 100
        and settings.ENVIRONMENT != "production"
        and settings.DHL_ENVIRONMENT == "sandbox"
    )
    combined_ready = bool(shipbubble_ready or (dhl_ready and dhl_secure_checkout_routing))

    raw_enabled = rows.get("shipping_enabled_providers")
    enabled_providers = None
    if raw_enabled:
        try:
            parsed = json.loads(raw_enabled)
            if isinstance(parsed, list):
                valid = [p for p in parsed if p in ("manual", "shipbubble", "dhl")]
                if valid:
                    enabled_providers = list(dict.fromkeys(valid))
        except Exception:
            enabled_providers = None

    provider = rows.get("shipping_provider")
    if not provider:
        # Before the exclusive setting existed the secure route used the DHL
        # capability gate. Preserve that behavior without activating new gates.
        provider = (
            "shipbubble"
            if (rows.get("shipping_use_shipbubble") or "").lower() == "true"
            else ("dhl" if dhl_ready else "manual")
        )
    elif provider == "dhl" and not dhl_secure_checkout_routing:
        provider = "manual"
    elif provider == "combined" and not combined_ready:
        provider = "shipbubble" if shipbubble_ready else ("dhl" if (dhl_ready and dhl_secure_checkout_routing) else "manual")

    if enabled_providers is None:
        if provider == "combined":
            enabled_providers = ["dhl", "shipbubble"]
        elif provider in ("manual", "shipbubble", "dhl"):
            enabled_providers = [provider]
        else:
            enabled_providers = ["manual"]

    return ShippingProviderSettings(
        provider=provider,
        enabled_providers=enabled_providers,
        checkout_estimates_required=(
            (provider == "shipbubble" and shipbubble_ready)
            or (provider == "dhl" and dhl_ready and dhl_secure_checkout_routing)
            or (provider == "combined" and combined_ready)
        ),
        use_shipbubble=provider in ("shipbubble", "combined") or "shipbubble" in enabled_providers,
        readiness={
            "manual": True,
            "shipbubble": shipbubble_ready,
            "dhl": dhl_ready,
            "combined": combined_ready,
        },
    )



async def require_manual_order_pricing(db):
    """Reject nonmanual selection without changing pre-selection DHL routing."""
    rows = dict((await db.execute(
        select(AppSetting.key, AppSetting.value).where(AppSetting.key.in_((
            "shipping_provider", "shipping_use_shipbubble", "shipping_enabled_providers",
        )))
    )).all())
    raw_enabled = rows.get("shipping_enabled_providers")
    if raw_enabled:
        try:
            parsed = json.loads(raw_enabled)
            if isinstance(parsed, list) and parsed == ["manual"]:
                return
            elif isinstance(parsed, list) and "manual" not in parsed:
                raise HTTPException(status_code=503, detail="Use secure checkout delivery estimates; manual pricing requires manual mode")
        except Exception:
            pass

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
        provider = "manual"
    if provider != "manual":
        raise HTTPException(status_code=503, detail="Use secure checkout delivery estimates; manual pricing requires manual mode")
