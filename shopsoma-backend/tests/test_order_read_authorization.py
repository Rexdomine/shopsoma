"""Bounded read authorization regressions using production order creation on PG."""

from datetime import timedelta
import hashlib
import hmac
import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text, func

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.models.order_guest_capability import OrderGuestCapability, OrderCurrentOwner
from tests.test_checkout_estimate_api import _domestic_catalogue, _guest_order_payload


@pytest.fixture
def cohort(monkeypatch, request):
    modern = request.param
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", modern)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)
    monkeypatch.setattr(settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION", 7)
    monkeypatch.setattr(
        settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER", SecretStr("read-test-pepper")
    )
    return modern


@pytest.mark.asyncio
@pytest.mark.parametrize("cohort", [False, True], indirect=True)
@pytest.mark.parametrize("suffix", ["", "/tracking"])
async def test_registered_order_read_actors(
    client, db_session, vendor_user, customer_user, admin_user, cohort, suffix
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    created = await client.post(
        "/api/v1/orders",
        headers=customer_user["headers"],
        json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address_id": str(address.id),
            "currency": "NGN",
        },
    )
    assert created.status_code == 201, created.text
    stranger = User(
        id=uuid.uuid4(),
        email="stranger-read@example.test",
        hashed_password="unused-test-hash",
        full_name="Stranger",
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db_session.add(stranger)
    await db_session.commit()
    token = create_access_token(data={"sub": str(stranger.id)})
    actors = {
        "anonymous": {},
        "stranger": {"Authorization": f"Bearer {token}"},
        "vendor": vendor_user["headers"],
        "owner": customer_user["headers"],
        "admin": admin_user["headers"],
    }
    actual = {}
    for actor, headers in actors.items():
        response = await client.get(
            f"/api/v1/orders/{created.json()['id']}{suffix}", headers=headers
        )
        actual[actor] = (
            response.status_code
            if actor in {"owner", "admin"}
            else response.status_code in {403, 404}
        )
    assert actual == {
        "anonymous": True,
        "stranger": True,
        "vendor": True,
        "owner": 200,
        "admin": 200,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("cohort", [True], indirect=True)
@pytest.mark.parametrize("suffix", ["", "/tracking"])
async def test_secure_guest_read_capabilities(
    client, db_session, vendor_user, customer_user, admin_user, cohort, suffix
):
    _, product = await _domestic_catalogue(db_session, vendor_user)
    created = await client.post(
        "/api/v1/orders",
        json=_guest_order_payload(product.id, "read-guest@example.test"),
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    url = f"/api/v1/orders/{payload['id']}{suffix}"
    token = payload["checkout_capability"]
    actual = {}
    for label, headers in {
        "valid": {"X-ShopSoma-Checkout-Capability": token},
        "missing": {},
        "wrong": {"X-ShopSoma-Checkout-Capability": "wrong-token"},
        "customer": customer_user["headers"],
        "vendor": vendor_user["headers"],
        "admin": admin_user["headers"],
    }.items():
        response = await client.get(url, headers=headers)
        actual[label] = response.status_code
        if response.status_code == 200:
            assert token not in response.text
    cap = (
        await db_session.execute(
            select(OrderGuestCapability).where(
                OrderGuestCapability.order_id == uuid.UUID(payload["id"])
            )
        )
    ).scalar_one()
    cap.revoked_at = func.statement_timestamp()
    cap.row_version += 1
    await db_session.commit()
    actual["revoked"] = (
        await client.get(url, headers={"X-ShopSoma-Checkout-Capability": token})
    ).status_code
    now = await db_session.scalar(select(text("clock_timestamp()")))
    expired = "expired-order-read-test-token"
    db_session.add(
        OrderGuestCapability(
            order_id=uuid.UUID(payload["id"]),
            original_customer_id=uuid.UUID(payload["customer_id"]),
            scope="checkout_prerequisites",
            token_digest=hmac.new(
                b"read-test-pepper", expired.encode(), hashlib.sha256
            ).digest(),
            pepper_key_version=7,
            created_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=1),
        )
    )
    await db_session.commit()
    actual["expired"] = (
        await client.get(url, headers={"X-ShopSoma-Checkout-Capability": expired})
    ).status_code
    assert actual == {
        "valid": 200,
        "missing": 404,
        "wrong": 404,
        "customer": 404,
        "vendor": 404,
        "admin": 200,
        "revoked": 404,
        "expired": 404,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("cohort", [False], indirect=True)
@pytest.mark.parametrize("suffix", ["", "/tracking"])
async def test_legacy_guest_read_requires_persisted_passwordless_active_guest(
    client, db_session, vendor_user, customer_user, cohort, suffix
):
    _, product = await _domestic_catalogue(db_session, vendor_user)
    created = await client.post(
        "/api/v1/orders",
        json=_guest_order_payload(product.id, "legacy-read@example.test"),
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["checkout_capability"] is None
    url = f"/api/v1/orders/{payload['id']}{suffix}"
    guest = await db_session.get(User, uuid.UUID(payload["customer_id"]))
    actual = {"guest": (await client.get(url)).status_code}
    actual["stranger_denied"] = (
        await client.get(url, headers=customer_user["headers"])
    ).status_code in {403, 404}
    for field, value, original in [
        ("is_active", False, True),
        ("hashed_password", "registered-test-hash", None),
        ("is_guest_created", False, True),
    ]:
        setattr(guest, field, value)
        await db_session.commit()
        actual[field] = (await client.get(url)).status_code in {403, 404}
        setattr(guest, field, original)
        await db_session.commit()
    assert actual == {
        "guest": 200,
        "stranger_denied": True,
        "is_active": True,
        "hashed_password": True,
        "is_guest_created": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("cohort", [True], indirect=True)
@pytest.mark.parametrize("suffix", ["", "/tracking"])
async def test_claimed_order_reads_use_canonical_owner(
    client, db_session, vendor_user, customer_user, cohort, suffix
):
    _, product = await _domestic_catalogue(db_session, vendor_user)
    created = await client.post(
        "/api/v1/orders",
        json=_guest_order_payload(product.id, "claimed-read@example.test"),
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    order_id = uuid.UUID(payload["id"])
    now = await db_session.scalar(select(text("clock_timestamp()")))
    claim = OrderGuestCapability(
        order_id=order_id,
        original_customer_id=uuid.UUID(payload["customer_id"]),
        scope="claim_order",
        token_digest=hashlib.sha256(b"claim-read-test").digest(),
        pepper_key_version=7,
        created_at=now,
        expires_at=now + timedelta(days=1),
    )
    db_session.add(claim)
    await db_session.flush()
    owner = await db_session.get(OrderCurrentOwner, order_id)
    owner.current_authenticated_user_id = customer_user["user"].id
    owner.claim_capability_id = claim.id
    owner.claim_idempotency_key = "read-test-claim"
    owner.claimed_at = func.statement_timestamp()
    owner.row_version += 1
    await db_session.commit()
    url = f"/api/v1/orders/{order_id}{suffix}"
    canonical = await client.get(url, headers=customer_user["headers"])
    stale_token = create_access_token(data={"sub": payload["customer_id"]})
    stale = await client.get(url, headers={"Authorization": f"Bearer {stale_token}"})
    revoked = await client.get(
        url, headers={"X-ShopSoma-Checkout-Capability": payload["checkout_capability"]}
    )
    assert (canonical.status_code, stale.status_code, revoked.status_code) == (
        200,
        404,
        404,
    )
