"""Tests for admin-customizable checkout stock reservation and payment hold settings."""

from datetime import timedelta
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import payments
from app.core.config import settings
from app.models.address import Address
from app.models.product import ModerationStatus, Product, ProductStatus, ProductType
from app.models.shipping_rate import ShippingRate
from app.models.stock_payment_persistence import PaymentAttempt, StockReservation


@pytest.mark.asyncio
async def test_checkout_hold_settings_defaults_and_auth(
    client: AsyncClient, customer_user, admin_user
):
    public_res = await client.get("/api/v1/settings/public/checkout-hold")
    assert public_res.status_code == 200
    assert public_res.json() == {
        "reservation_ttl_minutes": 30,
        "authorization_grace_minutes": 15,
        "release_on_payment_close": False,
        "updated_at": None,
    }

    unauth_admin = await client.get("/api/v1/settings/admin/checkout-hold")
    assert unauth_admin.status_code in (401, 403)

    customer_get = await client.get(
        "/api/v1/settings/admin/checkout-hold", headers=customer_user["headers"]
    )
    assert customer_get.status_code == 403

    customer_put = await client.put(
        "/api/v1/settings/admin/checkout-hold",
        headers=customer_user["headers"],
        json={
            "reservation_ttl_minutes": 5,
            "authorization_grace_minutes": 2,
            "release_on_payment_close": True,
        },
    )
    assert customer_put.status_code == 403

    admin_get = await client.get(
        "/api/v1/settings/admin/checkout-hold", headers=admin_user["headers"]
    )
    assert admin_get.status_code == 200
    assert admin_get.json()["reservation_ttl_minutes"] == 30


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"reservation_ttl_minutes": 0, "authorization_grace_minutes": 5, "release_on_payment_close": False},
        {"reservation_ttl_minutes": 31, "authorization_grace_minutes": 5, "release_on_payment_close": False},
        {"reservation_ttl_minutes": 10, "authorization_grace_minutes": -1, "release_on_payment_close": False},
        {"reservation_ttl_minutes": 10, "authorization_grace_minutes": 16, "release_on_payment_close": False},
    ],
)
async def test_checkout_hold_settings_rejects_out_of_range_values(
    client: AsyncClient, admin_user, payload
):
    res = await client.put(
        "/api/v1/settings/admin/checkout-hold",
        headers=admin_user["headers"],
        json=payload,
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_checkout_hold_settings_persists_and_applies_to_reservations_and_attempts(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
    vendor_user,
    customer_user,
    monkeypatch,
):
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)
    monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "sk_test_placeholder")

    class _PaystackResponse:
        status_code = 200
        text = ""

        def __init__(self, reference: str):
            self.reference = reference

        def json(self):
            return {
                "status": True,
                "data": {
                    "authorization_url": "https://paystack.invalid/checkout",
                    "access_code": "acc_hold_test",
                    "reference": self.reference,
                },
            }

    class _PaystackClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **kwargs):
            return _PaystackResponse(kwargs["json"]["reference"])

    monkeypatch.setattr(payments.httpx, "AsyncClient", _PaystackClient)

    update_res = await client.put(
        "/api/v1/settings/admin/checkout-hold",
        headers=admin_user["headers"],
        json={
            "reservation_ttl_minutes": 5,
            "authorization_grace_minutes": 2,
            "release_on_payment_close": True,
        },
    )
    assert update_res.status_code == 200, update_res.text
    saved = update_res.json()
    assert saved["reservation_ttl_minutes"] == 5
    assert saved["authorization_grace_minutes"] == 2
    assert saved["release_on_payment_close"] is True
    assert saved["updated_at"] is not None

    public_res = await client.get("/api/v1/settings/public/checkout-hold")
    assert public_res.status_code == 200
    assert public_res.json()["reservation_ttl_minutes"] == 5
    assert public_res.json()["authorization_grace_minutes"] == 2
    assert public_res.json()["release_on_payment_close"] is True

    address = Address(
        id=uuid.uuid4(),
        user_id=customer_user["user"].id,
        full_name="Hold Buyer",
        phone_number="08012345678",
        address_line1="12 Admiralty Way",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
    )
    rate = ShippingRate(
        id=uuid.uuid4(),
        name="Standard",
        description="2-4 days",
        base_rate=Decimal("1000.00"),
        country="Nigeria",
        state="Lagos",
        min_delivery_days=2,
        max_delivery_days=4,
        is_active=True,
        is_default=True,
        priority=0,
    )
    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Hold Config Item",
        description="Configurable hold item",
        base_price=Decimal("4000.00"),
        total_stock=1,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
        product_type=ProductType.SINGLE,
    )
    db_session.add_all([address, rate, product])
    await db_session.commit()

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
    order_id = created.json()["id"]

    est_res = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates",
        headers={**customer_user["headers"], "X-Idempotency-Key": f"est-{uuid.uuid4()}"},
    )
    assert est_res.status_code == 201, est_res.text
    est = est_res.json()

    sel_res = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{est['id']}/options/{est['options'][0]['id']}/select",
        headers={**customer_user["headers"], "X-Idempotency-Key": f"sel-{uuid.uuid4()}"},
    )
    assert sel_res.status_code == 200, sel_res.text

    init_res = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": order_id,
            "email": customer_user["user"].email,
            "payment_gateway": "paystack",
            "currency": "NGN",
        },
    )
    assert init_res.status_code == 200, init_res.text

    db_session.expire_all()
    reservation = await db_session.scalar(
        select(StockReservation).where(StockReservation.order_id == uuid.UUID(order_id))
    )
    attempt = await db_session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.order_id == uuid.UUID(order_id))
    )
    assert reservation is not None
    assert reservation.ttl_seconds == 300
    assert reservation.expires_at <= reservation.created_at + timedelta(seconds=300)

    assert attempt is not None
    assert attempt.payment_window_seconds == 300
    assert attempt.authorization_grace_seconds == 120
    assert attempt.authorization_deadline_at == attempt.expires_at + timedelta(seconds=120)
