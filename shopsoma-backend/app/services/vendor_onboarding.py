"""Vendor onboarding state transitions."""
from datetime import datetime

from app.models.vendor import Vendor


def reconcile_vendor_onboarding(vendor: Vendor) -> None:
    """Complete onboarding only when all required vendor records are present.

    Existing completed vendors remain completed during rollout; this evaluator only
    advances vendors that are currently in onboarding.
    """
    if not vendor.is_onboarding:
        return

    has_featured_storefront_image = bool(
        vendor.featured_storefront_image_url
        and vendor.featured_storefront_image_url.strip()
    )
    if (
        vendor.brand_info_completed
        and vendor.payout_info_completed
        and has_featured_storefront_image
    ):
        vendor.is_onboarding = False
        vendor.onboarding_completed_at = datetime.utcnow()
