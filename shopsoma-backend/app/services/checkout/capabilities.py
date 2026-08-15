"""Issue and verify order-scoped guest checkout capabilities."""

from datetime import timedelta
import hashlib
import hmac
import secrets

from fastapi import HTTPException
from sqlalchemy import select, text

from app.core.config import settings
from app.models.order_guest_capability import OrderCurrentOwner, OrderGuestCapability

_SCOPE = "checkout_prerequisites"


def _digest(token: str, pepper: str) -> bytes:
    return hmac.new(pepper.encode(), token.encode(), hashlib.sha256).digest()


def _configured_peppers() -> dict[int, str]:
    peppers = {}
    active_version = settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION
    active = settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER.get_secret_value()
    if active_version and active:
        peppers[active_version] = active
    previous_version = settings.CHECKOUT_CAPABILITY_PREVIOUS_PEPPER_VERSION
    previous = settings.CHECKOUT_CAPABILITY_PREVIOUS_PEPPER.get_secret_value()
    if previous_version and previous:
        peppers[previous_version] = previous
    return peppers


async def issue_checkout_capability(db, *, order) -> str:
    """Persist only a versioned digest and return the plaintext once."""
    peppers = _configured_peppers()
    version = settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION
    if not version or version not in peppers:
        raise HTTPException(status_code=503, detail="guest checkout is not available")
    owner = (
        await db.execute(
            select(OrderCurrentOwner)
            .where(OrderCurrentOwner.order_id == order.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not owner or owner.original_customer_id != order.customer_id:
        raise HTTPException(status_code=503, detail="guest checkout is not available")
    token = secrets.token_urlsafe(32)
    database_now = await db.scalar(select(text("clock_timestamp()")))
    db.add(
        OrderGuestCapability(
            order_id=order.id,
            original_customer_id=order.customer_id,
            scope=_SCOPE,
            token_digest=_digest(token, peppers[version]),
            pepper_key_version=version,
            expires_at=database_now + timedelta(days=1),
        )
    )
    await db.flush()
    return token


async def authorize_checkout_actor(db, *, order, current_user, token):
    """Authorize an authenticated owner or an order-scoped guest capability."""
    if order.workflow_cohort in {"legacy_ambiguous_quarantined", "legacy_pre_bridge"}:
        raise HTTPException(status_code=404, detail="checkout not available")
    owner = (
        await db.execute(
            select(OrderCurrentOwner)
            .where(OrderCurrentOwner.order_id == order.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if not owner:
        raise HTTPException(status_code=404, detail="checkout not available")

    if current_user:
        canonical_user_id = (
            owner.current_authenticated_user_id or owner.original_customer_id
        )
        if canonical_user_id == current_user.id:
            return "customer", str(current_user.id)
        raise HTTPException(status_code=404, detail="checkout not available")

    peppers = _configured_peppers()
    if not token or not peppers or order.checkout_access_mode != "guest_capability":
        raise HTTPException(status_code=404, detail="checkout not available")
    capabilities = (
        (
            await db.execute(
                select(OrderGuestCapability)
                .where(
                    OrderGuestCapability.order_id == order.id,
                    OrderGuestCapability.scope == _SCOPE,
                    OrderGuestCapability.pepper_key_version.in_(peppers),
                )
                .order_by(OrderGuestCapability.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    matches = [
        row
        for row in capabilities
        if hmac.compare_digest(
            bytes(row.token_digest), _digest(token, peppers[row.pepper_key_version])
        )
    ]
    database_now = await db.scalar(select(text("clock_timestamp()")))
    capability = matches[0] if len(matches) == 1 else None
    if (
        not capability
        or capability.original_customer_id != owner.original_customer_id
        or capability.revoked_at is not None
        or capability.replaced_by_id is not None
        or capability.claimed_by_user_id is not None
        or capability.expires_at <= database_now
    ):
        raise HTTPException(status_code=404, detail="checkout not available")
    return "guest_capability", str(capability.id)
