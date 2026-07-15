"""Fail-closed domestic shipping capability evaluation."""

from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class DomesticShippingCapabilities:
    """Effective domestic workflow capabilities safe to share with callers."""

    workflow_enabled: bool
    quote_enforcement_enabled: bool
    provider_calls_enabled: bool


def domestic_shipping_capabilities(
    settings: Settings,
) -> DomesticShippingCapabilities:
    """Return effective gates, applying prerequisites without exposing configuration."""
    workflow_enabled = settings.DHL_DOMESTIC_WORKFLOW_ENABLED
    return DomesticShippingCapabilities(
        workflow_enabled=workflow_enabled,
        quote_enforcement_enabled=(
            workflow_enabled and settings.DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED
        ),
        provider_calls_enabled=(
            workflow_enabled
            and settings.DHL_DOMESTIC_PROVIDER_CALLS_ENABLED
            and settings.dhl_configured
        ),
    )
