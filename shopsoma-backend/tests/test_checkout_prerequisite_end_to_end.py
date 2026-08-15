"""Milestone 5 inert end-to-end checkout/payment response contracts."""

from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.api.v1 import payments
from app.core.config import settings
from app.models.order import Order
from app.models.order_guest_capability import OrderGuestCapability
from app.models.payment import Payment
from app.models.stock_payment_persistence import PaymentAttempt
from app.models.user import User
from app.schemas.payment import PaymentInitializeResponse
from tests.test_checkout_estimate_api import _domestic_catalogue, _guest_order_payload
from tests.test_checkout_payment_bridge_prerequisites import create_enforced_checkout


@pytest.mark.parametrize("currency", ["NGN", "USD"])
def test_payment_initialization_response_exposes_server_provider_truth(currency):
    response = PaymentInitializeResponse(
        status=True,
        message="ready",
        payment_gateway="paystack",
        reference="server-reference",
        amount=Decimal("10.05"),
        amount_minor=1005,
        currency=currency,
        provider_payload={"access_code": "server-access"},
    )

    assert response.amount == Decimal("10.05")
    assert response.amount_minor == 1005
    assert response.currency == currency
    assert response.provider_payload == {"access_code": "server-access"}


@pytest.mark.asyncio
async def test_authenticated_order_estimate_selection_reservation_mock_payment_returns_exact_truth(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, _ = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )

    customer_user["user"].stripe_customer_id = "cus_m5_existing"
    await db_session.commit()
    observed = {}

    def create_intent(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(id="pi_m5_ngn", client_secret="secret_m5")

    monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_intent)
    response = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order.id),
            "email": customer_user["user"].email,
            "payment_gateway": "stripe",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert Decimal(payload["amount"]) == Decimal(order.total_amount)
    assert payload["amount_minor"] == observed["amount"]
    assert payload["currency"] == order.currency
    assert payload["provider_payload"] == {
        "client_secret": "secret_m5",
        "payment_intent_id": "pi_m5_ngn",
    }


async def create_enforced_guest_checkout(
    client, db_session, vendor_user, monkeypatch, *, email="guest-m5@example.com"
):
    _, product = await _domestic_catalogue(db_session, vendor_user)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)
    monkeypatch.setattr(settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION", 7)
    monkeypatch.setattr(
        settings,
        "CHECKOUT_CAPABILITY_ACTIVE_PEPPER",
        SecretStr("m5-test-pepper-not-a-production-secret"),
    )
    created = await client.post(
        "/api/v1/orders", json=_guest_order_payload(product.id, email)
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    capability = payload["checkout_capability"]
    estimate_response = await client.post(
        f"/api/v1/orders/{payload['id']}/checkout-estimates",
        headers={
            "X-ShopSoma-Checkout-Capability": capability,
            "X-Idempotency-Key": f"estimate-{uuid.uuid4()}",
        },
    )
    assert estimate_response.status_code == 201, estimate_response.text
    estimate = estimate_response.json()
    selected = await client.post(
        f"/api/v1/orders/{payload['id']}/checkout-estimates/{estimate['id']}"
        f"/options/{estimate['options'][0]['id']}/select",
        headers={
            "X-ShopSoma-Checkout-Capability": capability,
            "X-Idempotency-Key": f"select-{uuid.uuid4()}",
        },
    )
    assert selected.status_code == 200, selected.text
    order = await db_session.get(Order, uuid.UUID(payload["id"]))
    return order, capability, email


@pytest.mark.asyncio
async def test_enforced_guest_payment_requires_active_order_scoped_capability_without_residue(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, capability, email = await create_enforced_guest_checkout(
        client, db_session, vendor_user, monkeypatch
    )
    _, wrong_capability, _ = await create_enforced_guest_checkout(
        client,
        db_session,
        vendor_user,
        monkeypatch,
        email="wrong-order-m5@example.com",
    )

    async def initialize(headers=None):
        return await client.post(
            "/api/v1/payments/initialize",
            headers=headers,
            json={
                "order_id": str(order.id),
                "email": email,
                "payment_gateway": "stripe",
            },
        )

    forbidden_calls = 0

    def forbidden_provider_call(**_kwargs):
        nonlocal forbidden_calls
        forbidden_calls += 1
        raise AssertionError("unauthorized checkout must not call a provider")

    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "create", forbidden_provider_call
    )
    responses = [
        await initialize(),
        await initialize(customer_user["headers"]),
        await initialize({"X-ShopSoma-Checkout-Capability": wrong_capability}),
    ]
    assert [response.status_code for response in responses] == [404, 404, 404]
    assert {response.json()["detail"] for response in responses} == {
        "checkout not available"
    }
    assert forbidden_calls == 0
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttempt.id)).where(
                PaymentAttempt.order_id == order.id
            )
        )
        == 0
    )
    assert (
        await db_session.scalar(
            select(func.count(Payment.id)).where(Payment.order_id == order.id)
        )
        == 0
    )

    persisted = await db_session.scalar(
        select(OrderGuestCapability).where(
            OrderGuestCapability.order_id == order.id,
            OrderGuestCapability.scope == "checkout_prerequisites",
        )
    )
    persisted.revoked_at = func.statement_timestamp()
    persisted.row_version += 1
    await db_session.commit()
    revoked = await initialize({"X-ShopSoma-Checkout-Capability": capability})
    assert revoked.status_code == 404
    assert revoked.json()["detail"] == "checkout not available"
    assert forbidden_calls == 0


@pytest.mark.asyncio
async def test_enforced_guest_capability_initializes_from_server_truth(
    client, db_session, vendor_user, monkeypatch
):
    order, capability, email = await create_enforced_guest_checkout(
        client, db_session, vendor_user, monkeypatch
    )
    customer = await db_session.get(User, order.customer_id)
    customer.stripe_customer_id = "cus_m5_guest"
    await db_session.commit()
    observed = {}

    def create_intent(**kwargs):
        observed.update(kwargs)
        return SimpleNamespace(id="pi_m5_guest", client_secret="secret_m5_guest")

    monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_intent)
    response = await client.post(
        "/api/v1/payments/initialize",
        headers={"X-ShopSoma-Checkout-Capability": capability},
        json={
            "order_id": str(order.id),
            "email": email,
            "payment_gateway": "stripe",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert Decimal(payload["amount"]) == Decimal(order.total_amount)
    assert payload["amount_minor"] == observed["amount"]
    assert payload["currency"] == order.currency
    assert payload["reference"]
    assert payload["provider_payload"] == {
        "client_secret": "secret_m5_guest",
        "payment_intent_id": "pi_m5_guest",
    }
