"""Comprehensive tests for Promo Codes admin CRUD, checkout integration, and idempotent redemption."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.address import Address, AddressType
from app.models.order import Order, OrderItem, PaymentStatus
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.models.product import ModerationStatus, Product, ProductStatus
from app.models.promo_code import DiscountType, PromoCode
from app.models.setting import Setting
from app.models.shipping_rate import ShippingRate
from app.services.payments.fulfilment_bridge import finalize_verified_payment


async def _create_shipping_rate(
    db_session: AsyncSession,
    *,
    country: str = "United Kingdom",
    base_rate: Decimal = Decimal("2500.00"),
) -> ShippingRate:
    rate = ShippingRate(
        id=uuid.uuid4(),
        name="Standard Delivery",
        description="2-4 business days",
        base_rate=base_rate,
        country=country,
        min_delivery_days=2,
        max_delivery_days=4,
        is_active=True,
        is_default=True,
        priority=1,
    )
    db_session.add(rate)
    await db_session.flush()
    return rate


async def _create_customer_address(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    country: str = "United Kingdom",
) -> Address:
    address = Address(
        id=uuid.uuid4(),
        user_id=user_id,
        address_type=AddressType.SHIPPING,
        full_name="Promo Test Buyer",
        phone_number="+447911123456" if country != "Nigeria" else "08012345678",
        address_line1="10 Downing Street",
        city="London" if country != "Nigeria" else "Lagos",
        state="England" if country != "Nigeria" else "Lagos",
        postal_code="SW1A 2AA",
        country=country,
        is_default=True,
    )
    db_session.add(address)
    await db_session.flush()
    return address


async def _create_product(
    db_session: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    price: Decimal = Decimal("20000.00"),
    currency: str = "NGN",
) -> Product:
    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_id,
        title="Test Designer Bag",
        description="Promo eligible item",
        base_price=price,
        currency=currency,
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.flush()
    return product


def _promo_payload(**overrides):
    now = datetime.now(timezone.utc)
    payload = {
        "code": "welcome10",
        "description": "10% off welcome discount",
        "discount_type": "percentage",
        "discount_value": 10,
        "min_purchase_amount": 5000,
        "max_discount_amount": 3000,
        "usage_limit": 50,
        "usage_limit_per_user": 1,
        "valid_from": (now - timedelta(days=1)).isoformat(),
        "valid_until": (now + timedelta(days=30)).isoformat(),
        "is_active": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_promo_code_admin_rbac_and_crud(
    client: AsyncClient,
    admin_user,
    customer_user,
):
    payload = _promo_payload()

    unauth_resp = await client.get("/api/v1/promo-codes")
    assert unauth_resp.status_code in (401, 403)

    cust_create = await client.post(
        "/api/v1/promo-codes",
        json=payload,
        headers=customer_user["headers"],
    )
    assert cust_create.status_code == 403

    cust_list = await client.get(
        "/api/v1/promo-codes",
        headers=customer_user["headers"],
    )
    assert cust_list.status_code == 403

    # Admin create normalizes lowercase code to uppercase without duplicate kwarg bug
    create_resp = await client.post(
        "/api/v1/promo-codes",
        json=payload,
        headers=admin_user["headers"],
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    promo_id = created["id"]
    assert created["code"] == "WELCOME10"
    assert created["usage_count"] == 0
    assert Decimal(str(created["max_discount_amount"])) == Decimal("3000")

    # Duplicate code conflict
    dup_resp = await client.post(
        "/api/v1/promo-codes",
        json=payload,
        headers=admin_user["headers"],
    )
    assert dup_resp.status_code == 400

    # Invalid percentage (>100) and inverted date range rejected
    bad_pct = await client.post(
        "/api/v1/promo-codes",
        json=_promo_payload(code="BADPCT", discount_value=120),
        headers=admin_user["headers"],
    )
    assert bad_pct.status_code == 422

    now = datetime.now(timezone.utc)
    bad_dates = await client.post(
        "/api/v1/promo-codes",
        json=_promo_payload(
            code="BADDATE",
            valid_from=(now + timedelta(days=5)).isoformat(),
            valid_until=(now + timedelta(days=1)).isoformat(),
        ),
        headers=admin_user["headers"],
    )
    assert bad_dates.status_code == 422

    # Second code for search + active filtering
    fixed_resp = await client.post(
        "/api/v1/promo-codes",
        json=_promo_payload(
            code="SAVE5000",
            description="Flat 5000 off",
            discount_type="fixed_amount",
            discount_value=5000,
            max_discount_amount=None,
            is_active=False,
        ),
        headers=admin_user["headers"],
    )
    assert fixed_resp.status_code == 201
    fixed_id = fixed_resp.json()["id"]

    search_resp = await client.get(
        "/api/v1/promo-codes?search=SAVE5",
        headers=admin_user["headers"],
    )
    assert search_resp.status_code == 200
    assert [p["code"] for p in search_resp.json()["promo_codes"]] == ["SAVE5000"]

    active_resp = await client.get(
        "/api/v1/promo-codes?active_only=true",
        headers=admin_user["headers"],
    )
    assert active_resp.status_code == 200
    assert [p["code"] for p in active_resp.json()["promo_codes"]] == ["WELCOME10"]

    # Update conflict check & clearing nullable fields
    conflict_update = await client.put(
        f"/api/v1/promo-codes/{fixed_id}",
        json={"code": "welcome10"},
        headers=admin_user["headers"],
    )
    assert conflict_update.status_code == 400

    update_resp = await client.put(
        f"/api/v1/promo-codes/{promo_id}",
        json={"max_discount_amount": None, "is_active": False},
        headers=admin_user["headers"],
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["max_discount_amount"] is None
    assert update_resp.json()["is_active"] is False

    # Delete
    delete_resp = await client.delete(
        f"/api/v1/promo-codes/{fixed_id}",
        headers=admin_user["headers"],
    )
    assert delete_resp.status_code == 204

    get_deleted = await client.get(
        f"/api/v1/promo-codes/{fixed_id}",
        headers=admin_user["headers"],
    )
    assert get_deleted.status_code == 404


@pytest.mark.asyncio
async def test_promo_code_validation_rules_and_usd_conversion(
    client: AsyncClient,
    db_session: AsyncSession,
):
    now = datetime.now(timezone.utc)
    db_session.add(Setting(key="exchange_rate_usd_to_ngn", value="1000"))

    pct_promo = PromoCode(
        id=uuid.uuid4(),
        code="PCT20CAP",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        min_purchase_amount=Decimal("10000.00"),
        max_discount_amount=Decimal("4000.00"),
        usage_limit=5,
        usage_limit_per_user=1,
        usage_count=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=5),
        is_active=True,
    )
    fixed_promo = PromoCode(
        id=uuid.uuid4(),
        code="FLAT5000",
        discount_type=DiscountType.FIXED_AMOUNT,
        discount_value=Decimal("5000.00"),
        min_purchase_amount=Decimal("0.00"),
        usage_limit=5,
        usage_limit_per_user=1,
        usage_count=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=5),
        is_active=True,
    )
    expired_promo = PromoCode(
        id=uuid.uuid4(),
        code="OLD10",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        valid_from=now - timedelta(days=10),
        valid_until=now - timedelta(days=1),
        is_active=True,
    )
    future_promo = PromoCode(
        id=uuid.uuid4(),
        code="SOON10",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        valid_from=now + timedelta(days=1),
        valid_until=now + timedelta(days=10),
        is_active=True,
    )
    inactive_promo = PromoCode(
        id=uuid.uuid4(),
        code="OFF10",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=5),
        is_active=False,
    )
    exhausted_promo = PromoCode(
        id=uuid.uuid4(),
        code="MAXED",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("10.00"),
        usage_limit=2,
        usage_count=2,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=5),
        is_active=True,
    )
    db_session.add_all(
        [pct_promo, fixed_promo, expired_promo, future_promo, inactive_promo, exhausted_promo]
    )
    await db_session.commit()

    # Percentage with cap in NGN (20% of 50,000 = 10,000 -> capped at 4,000)
    ngn_resp = await client.post(
        "/api/v1/promo-codes/validate",
        json={"code": "pct20cap", "order_subtotal": 50000, "currency": "NGN"},
    )
    assert ngn_resp.status_code == 200
    assert ngn_resp.json()["valid"] is True
    assert Decimal(str(ngn_resp.json()["discount_amount"])) == Decimal("4000.00")

    # Percentage with cap converted to USD (rate 1000 => 4000 NGN = 4.00 USD)
    usd_resp = await client.post(
        "/api/v1/promo-codes/validate",
        json={"code": "PCT20CAP", "order_subtotal": 50, "currency": "USD"},
    )
    assert usd_resp.status_code == 200
    assert usd_resp.json()["valid"] is True
    assert Decimal(str(usd_resp.json()["discount_amount"])) == Decimal("4.00")

    # Fixed 5000 NGN converted to USD (5.00 USD), capped at subtotal (3.00 USD)
    usd_fixed = await client.post(
        "/api/v1/promo-codes/validate",
        json={"code": "FLAT5000", "order_subtotal": 3, "currency": "USD"},
    )
    assert usd_fixed.status_code == 200
    assert usd_fixed.json()["valid"] is True
    assert Decimal(str(usd_fixed.json()["discount_amount"])) == Decimal("3.00")

    # Below min purchase (min 10,000 NGN = $10)
    low_usd = await client.post(
        "/api/v1/promo-codes/validate",
        json={"code": "PCT20CAP", "order_subtotal": 9, "currency": "USD"},
    )
    assert low_usd.status_code == 200
    assert low_usd.json()["valid"] is False
    assert "$10.00" in low_usd.json()["message"]

    for code_str, expected_fragment in [
        ("OLD10", "expired"),
        ("SOON10", "not yet valid"),
        ("OFF10", "inactive"),
        ("MAXED", "usage limit reached"),
    ]:
        r = await client.post(
            "/api/v1/promo-codes/validate",
            json={"code": code_str, "order_subtotal": 20000, "currency": "NGN"},
        )
        assert r.status_code == 200
        assert r.json()["valid"] is False
        assert expected_fragment in r.json()["message"].lower()


@pytest.mark.asyncio
async def test_checkout_promo_integration_cancellation_and_idempotent_redemption(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user,
    vendor_user,
    admin_user,
):
    now = datetime.now(timezone.utc)
    rate = await _create_shipping_rate(db_session, country="United Kingdom", base_rate=Decimal("2000.00"))
    address = await _create_customer_address(
        db_session,
        user_id=customer_user["user"].id,
        country="United Kingdom",
    )
    product = await _create_product(
        db_session,
        vendor_id=vendor_user["vendor"].id,
        price=Decimal("20000.00"),
        currency="NGN",
    )
    promo = PromoCode(
        id=uuid.uuid4(),
        code="VIP20",
        description="20% off capped at 3000",
        discount_type=DiscountType.PERCENTAGE,
        discount_value=Decimal("20.00"),
        min_purchase_amount=Decimal("5000.00"),
        max_discount_amount=Decimal("3000.00"),
        usage_limit=10,
        usage_limit_per_user=1,
        usage_count=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=7),
        is_active=True,
    )
    db_session.add(promo)
    await db_session.commit()

    review_payload = {
        "items": [{"product_id": str(product.id), "quantity": 1}],
        "shipping_address_id": str(address.id),
        "shipping_rate_id": str(rate.id),
        "promo_code": "vip20",
        "currency": "NGN",
    }

    # Invalid code rejected by /orders/review
    bad_review = await client.post(
        "/api/v1/orders/review",
        json={**review_payload, "promo_code": "NOPE"},
        headers=customer_user["headers"],
    )
    assert bad_review.status_code == 400

    # Valid code applied on /orders/review (20% of 20000 = 4000, capped at 3000)
    ok_review = await client.post(
        "/api/v1/orders/review",
        json=review_payload,
        headers=customer_user["headers"],
    )
    assert ok_review.status_code == 200, ok_review.text
    review_json = ok_review.json()
    assert Decimal(str(review_json["summary"]["discount_amount"])) == Decimal("3000.00")
    assert review_json["applied_promo"]["code"] == "VIP20"

    # Invalid promo rejected by POST /orders
    bad_order = await client.post(
        "/api/v1/orders",
        json={**review_payload, "promo_code": "NOPE"},
        headers=customer_user["headers"],
    )
    assert bad_order.status_code == 400

    # First unpaid order created, then cancelled -> should NOT increment usage_count or burn per-user quota
    first_order_resp = await client.post(
        "/api/v1/orders",
        json=review_payload,
        headers=customer_user["headers"],
    )
    assert first_order_resp.status_code == 201, first_order_resp.text
    first_order_data = first_order_resp.json()
    assert first_order_data["promo_code"] == "VIP20"
    assert Decimal(str(first_order_data["discount_amount"])) == Decimal("3000.00")

    await db_session.refresh(promo)
    assert promo.usage_count == 0

    cancel_resp = await client.post(
        f"/api/v1/orders/{first_order_data['id']}/cancel",
        json={"cancellation_reason": "Changed mind"},
        headers=customer_user["headers"],
    )
    assert cancel_resp.status_code == 200, cancel_resp.text
    await db_session.refresh(promo)
    assert promo.usage_count == 0

    # Customer can still validate & place a fresh order with VIP20
    second_order_resp = await client.post(
        "/api/v1/orders",
        json=review_payload,
        headers=customer_user["headers"],
    )
    assert second_order_resp.status_code == 201, second_order_resp.text
    order_id = uuid.UUID(second_order_resp.json()["id"])

    # Platform-funded check: vendor payout & commission remain based on full item subtotal (20000.00)
    item_row = (
        await db_session.execute(select(OrderItem).where(OrderItem.order_id == order_id))
    ).scalar_one()
    assert item_row.subtotal == Decimal("20000.00")
    assert item_row.commission_amount + item_row.vendor_payout == Decimal("20000.00")

    order_row = await db_session.get(Order, order_id)
    assert order_row is not None
    assert order_row.promo_code_id == promo.id
    assert order_row.promo_code == "VIP20"
    assert order_row.promo_usage_counted is False

    # Create legacy Payment record and finalize twice -> usage_count increments strictly once
    payment = Payment(
        id=uuid.uuid4(),
        order_id=order_row.id,
        payment_gateway=PaymentGateway.PAYSTACK,
        transaction_id=f"ps_{uuid.uuid4().hex}",
        payment_method="card",
        amount=order_row.total_amount,
        currency=order_row.currency,
        status=TransactionStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()

    result1 = await finalize_verified_payment(
        db_session,
        payment=payment,
        provider="paystack",
        provider_reference=payment.transaction_id,
        observed_amount=order_row.total_amount,
        observed_currency=order_row.currency,
        event_id=f"evt_{uuid.uuid4().hex}",
        evidence_payload={"status": "success"},
    )
    await db_session.commit()
    assert result1.order.payment_status == PaymentStatus.PAID

    await db_session.refresh(order_row)
    await db_session.refresh(promo)
    assert order_row.promo_usage_counted is True
    assert promo.usage_count == 1

    # Replay payment finalization -> idempotent, stays at 1
    await finalize_verified_payment(
        db_session,
        payment=payment,
        provider="paystack",
        provider_reference=payment.transaction_id,
        observed_amount=order_row.total_amount,
        observed_currency=order_row.currency,
        event_id=f"evt_{uuid.uuid4().hex}",
        evidence_payload={"status": "success"},
    )
    await db_session.commit()
    await db_session.refresh(promo)
    assert promo.usage_count == 1

    # Same user is now blocked by usage_limit_per_user=1 (both authenticated and by guest email lookup)
    recheck_auth = await client.post(
        "/api/v1/promo-codes/validate",
        json={"code": "VIP20", "order_subtotal": 20000, "currency": "NGN"},
        headers=customer_user["headers"],
    )
    assert recheck_auth.status_code == 200
    assert recheck_auth.json()["valid"] is False
    assert "usage limit" in recheck_auth.json()["message"].lower()

    recheck_email = await client.post(
        "/api/v1/promo-codes/validate",
        json={
            "code": "VIP20",
            "order_subtotal": 20000,
            "currency": "NGN",
            "customer_email": customer_user["user"].email,
        },
    )
    assert recheck_email.status_code == 200
    assert recheck_email.json()["valid"] is False

    # Admin order detail exposes promo_code
    admin_detail = await client.get(
        f"/api/v1/admin/orders/{order_row.id}",
        headers=admin_user["headers"],
    )
    assert admin_detail.status_code == 200, admin_detail.text
    assert admin_detail.json()["promo_code"] == "VIP20"
    assert Decimal(str(admin_detail.json()["discount_amount"])) == Decimal("3000.00")


@pytest.mark.asyncio
async def test_record_order_promo_redemption_handles_order_stub_without_promo_fields():
    from types import SimpleNamespace
    from app.services.promo_code_service import record_order_promo_redemption

    class UncalledSession:
        async def execute(self, *_args, **_kwargs):
            raise AssertionError("DB should not be queried when promo_code_id is absent")

    stub_order = SimpleNamespace(id="order-stub")
    assert await record_order_promo_redemption(UncalledSession(), stub_order) is False
