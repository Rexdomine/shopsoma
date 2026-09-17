"""Shared predicates for customer-facing vendor eligibility."""

from sqlalchemy import and_

from app.models.product import Product
from app.models.user import User
from app.models.vendor import Vendor


def customer_visible_vendor_product_filter():
    """Require a vendor account and storefront that may accept new customer sales."""
    return Product.vendor.has(
        and_(
            Vendor.approved.is_(True),
            Vendor.is_onboarding.is_(False),
            Vendor.store_active.is_(True),
            Vendor.store_deleted_at.is_(None),
            Vendor.user.has(User.is_active.is_(True)),
        )
    )
