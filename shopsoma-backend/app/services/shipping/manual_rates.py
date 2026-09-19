"""Shared destination matching for manual preview, review and durable quotes."""
from sqlalchemy import func, or_, select

from app.models.shipping_rate import ShippingRate


_FCT_STATE_ALIASES = ("abuja", "fct", "federal capital territory")


def manual_state_aliases(state: str | None) -> tuple[str, ...]:
    normalized = (state or "").strip().lower()
    return _FCT_STATE_ALIASES if normalized in _FCT_STATE_ALIASES else (normalized,)


def manual_rates_query(country, state):
    country = country.strip().lower()
    countries = ("ng", "nigeria") if country in {"ng", "nigeria"} else (country,)
    state_aliases = manual_state_aliases(state)
    return select(ShippingRate).where(
        ShippingRate.is_active.is_(True),
        func.lower(func.trim(ShippingRate.country)).in_(countries),
        # Preserve an admin repair path for legacy labels, but never project
        # whitespace-padded names into the strict estimate-option contract.
        ShippingRate.name == func.trim(ShippingRate.name),
        # Historical rows may predate the estimate-option constraint. Keep
        # them available for admin reads, but never project invalid delivery
        # windows into a new checkout estimate or order.
        ShippingRate.min_delivery_days >= 0,
        ShippingRate.min_delivery_days <= ShippingRate.max_delivery_days,
        ShippingRate.max_delivery_days <= 365,
        or_(
            func.lower(func.trim(ShippingRate.state)).in_(state_aliases),
            ShippingRate.state.is_(None),
            func.trim(ShippingRate.state) == "",
        ),
    ).order_by(ShippingRate.is_default.desc(), ShippingRate.priority, ShippingRate.id)
