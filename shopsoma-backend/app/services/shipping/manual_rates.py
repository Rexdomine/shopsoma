"""Shared destination matching for manual preview, review and durable quotes."""
from sqlalchemy import func, or_, select

from app.models.shipping_rate import ShippingRate


def manual_rates_query(country, state):
    country = country.strip().lower()
    countries = ("ng", "nigeria") if country in {"ng", "nigeria"} else (country,)
    return select(ShippingRate).where(
        ShippingRate.is_active.is_(True),
        func.lower(func.trim(ShippingRate.country)).in_(countries),
        or_(
            func.lower(func.trim(ShippingRate.state)) == (state or "").strip().lower(),
            ShippingRate.state.is_(None),
            func.trim(ShippingRate.state) == "",
        ),
    ).order_by(ShippingRate.is_default.desc(), ShippingRate.priority, ShippingRate.id)
