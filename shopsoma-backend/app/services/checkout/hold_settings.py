"""Admin-configurable stock reservation and payment authorization hold settings."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.schemas.app_setting import CheckoutHoldSettings, CheckoutHoldSettingsUpdate

CHECKOUT_RESERVATION_TTL_KEY = "checkout_reservation_ttl_minutes"
CHECKOUT_AUTH_GRACE_KEY = "checkout_authorization_grace_minutes"
CHECKOUT_RELEASE_ON_CLOSE_KEY = "checkout_release_on_payment_close"

DEFAULT_RESERVATION_TTL_MINUTES = 30
MIN_RESERVATION_TTL_MINUTES = 1
MAX_RESERVATION_TTL_MINUTES = 30

DEFAULT_AUTHORIZATION_GRACE_MINUTES = 15
MIN_AUTHORIZATION_GRACE_MINUTES = 0
MAX_AUTHORIZATION_GRACE_MINUTES = 15

DEFAULT_RELEASE_ON_PAYMENT_CLOSE = False

_KEYS = (
    CHECKOUT_RESERVATION_TTL_KEY,
    CHECKOUT_AUTH_GRACE_KEY,
    CHECKOUT_RELEASE_ON_CLOSE_KEY,
)


def _parse_clamped_int(
    raw: str | None, *, default: int, minimum: int, maximum: int
) -> int:
    if raw is None or not str(raw).strip():
        return default
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


async def get_checkout_hold_settings(db) -> CheckoutHoldSettings:
    """Return effective checkout hold timers, falling back to safe defaults."""
    if db is None or not hasattr(db, "execute"):
        return CheckoutHoldSettings()

    rows = (
        await db.execute(select(AppSetting).where(AppSetting.key.in_(_KEYS)))
    ).scalars().all()
    by_key = {row.key: row for row in rows}

    ttl_row = by_key.get(CHECKOUT_RESERVATION_TTL_KEY)
    grace_row = by_key.get(CHECKOUT_AUTH_GRACE_KEY)
    close_row = by_key.get(CHECKOUT_RELEASE_ON_CLOSE_KEY)

    reservation_ttl_minutes = _parse_clamped_int(
        ttl_row.value if ttl_row else None,
        default=DEFAULT_RESERVATION_TTL_MINUTES,
        minimum=MIN_RESERVATION_TTL_MINUTES,
        maximum=MAX_RESERVATION_TTL_MINUTES,
    )
    authorization_grace_minutes = _parse_clamped_int(
        grace_row.value if grace_row else None,
        default=DEFAULT_AUTHORIZATION_GRACE_MINUTES,
        minimum=MIN_AUTHORIZATION_GRACE_MINUTES,
        maximum=MAX_AUTHORIZATION_GRACE_MINUTES,
    )
    release_on_payment_close = (
        (close_row.value or "").strip().lower() == "true"
        if close_row
        else DEFAULT_RELEASE_ON_PAYMENT_CLOSE
    )
    updated_at = max(
        (row.updated_at for row in rows if getattr(row, "updated_at", None) is not None),
        default=None,
    )
    return CheckoutHoldSettings(
        reservation_ttl_minutes=reservation_ttl_minutes,
        authorization_grace_minutes=authorization_grace_minutes,
        release_on_payment_close=release_on_payment_close,
        updated_at=updated_at,
    )


async def _upsert_setting(
    db: AsyncSession,
    *,
    key: str,
    value: str,
    value_type: str,
    description: str,
) -> None:
    row = (
        await db.execute(select(AppSetting).where(AppSetting.key == key))
    ).scalar_one_or_none()
    if row:
        row.value = value
        row.value_type = value_type
        row.is_public = True
        if not row.description:
            row.description = description
    else:
        db.add(
            AppSetting(
                key=key,
                value=value,
                value_type=value_type,
                description=description,
                is_public=True,
            )
        )


async def save_checkout_hold_settings(
    db: AsyncSession, payload: CheckoutHoldSettingsUpdate
) -> CheckoutHoldSettings:
    """Persist validated checkout hold timers and Paystack modal-close policy."""
    await _upsert_setting(
        db,
        key=CHECKOUT_RESERVATION_TTL_KEY,
        value=str(payload.reservation_ttl_minutes),
        value_type="string",
        description="Stock reservation hold duration in minutes after shipping option selection (1-30).",
    )
    await _upsert_setting(
        db,
        key=CHECKOUT_AUTH_GRACE_KEY,
        value=str(payload.authorization_grace_minutes),
        value_type="string",
        description="Extra payment authorization grace window in minutes after payment window expiry (0-15).",
    )
    await _upsert_setting(
        db,
        key=CHECKOUT_RELEASE_ON_CLOSE_KEY,
        value="true" if payload.release_on_payment_close else "false",
        value_type="boolean",
        description="Verify Paystack payment status when the checkout payment modal is closed so abandoned payments release stock immediately.",
    )
    await db.commit()
    return await get_checkout_hold_settings(db)
