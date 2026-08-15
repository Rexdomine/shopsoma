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
from app.models.checkout_shipping_estimate import OrderInventoryCoverage
from app.models.order_guest_capability import OrderGuestCapability
from app.models.payment import Payment
from app.models.stock_payment_persistence import (
    PaymentAttempt,
    PaymentAttemptReservation,
)
from app.models.user import User
from app.schemas.payment import PaymentInitializeResponse
from app.services.shipping.capabilities import DomesticShippingCapabilities
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


async def _create_select_initialize_usd_route_journey(
    client, db_session, vendor_user, customer_user, monkeypatch, *, guest: bool
):
    address, product = await _domestic_catalogue(
        db_session, vendor_user, None if guest else customer_user
    )
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda _settings: DomesticShippingCapabilities(True, True, False),
    )
    if guest:
        monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)
        monkeypatch.setattr(settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION", 7)
        monkeypatch.setattr(
            settings,
            "CHECKOUT_CAPABILITY_ACTIVE_PEPPER",
            SecretStr("m5-usd-route-test-pepper"),
        )
        email = "guest-usd-m5@example.com"
        order_body = _guest_order_payload(product.id, email)
        order_body["currency"] = "USD"
        order_headers = {}
    else:
        monkeypatch.setattr(
            settings,
            "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST",
            str(customer_user["user"].id),
        )
        email = customer_user["user"].email
        order_body = {
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address_id": str(address.id),
            "currency": "USD",
        }
        order_headers = customer_user["headers"]

    before_orders = await db_session.scalar(select(func.count(Order.id)))
    created = await client.post(
        "/api/v1/orders", headers=order_headers, json=order_body
    )
    assert created.status_code == 201, created.text
    created_payload = created.json()
    order_id = uuid.UUID(created_payload["id"])
    capability = created_payload.get("checkout_capability")
    assert bool(capability) is guest
    actor_headers = (
        {"X-ShopSoma-Checkout-Capability": capability}
        if guest
        else customer_user["headers"]
    )

    estimated = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates",
        headers={**actor_headers, "X-Idempotency-Key": f"usd-estimate-{guest}"},
    )
    assert estimated.status_code == 201, estimated.text
    estimate = estimated.json()
    assert estimate["selected_option"] is None
    selected = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
        f"/options/{estimate['options'][0]['id']}/select",
        headers={**actor_headers, "X-Idempotency-Key": f"usd-select-{guest}"},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["selected_option"]["id"] == estimate["options"][0]["id"]

    customer = await db_session.get(User, uuid.UUID(created_payload["customer_id"]))
    customer.stripe_customer_id = f"cus_m5_usd_{'guest' if guest else 'auth'}"
    await db_session.commit()
    provider_calls = []

    def create_intent(**kwargs):
        provider_calls.append(kwargs)
        return SimpleNamespace(
            id=f"pi_m5_usd_{'guest' if guest else 'auth'}",
            client_secret=f"secret_m5_usd_{'guest' if guest else 'auth'}",
        )

    monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_intent)
    initialize_body = {
        "order_id": str(order_id),
        "email": email,
        "payment_gateway": "stripe",
    }
    assert "checkout_capability" not in initialize_body
    initialized = await client.post(
        "/api/v1/payments/initialize", headers=actor_headers, json=initialize_body
    )
    assert initialized.status_code == 200, initialized.text
    replay = await client.post(
        "/api/v1/payments/initialize", headers=actor_headers, json=initialize_body
    )
    assert replay.status_code == 200, replay.text

    db_session.expire_all()
    order = await db_session.get(Order, order_id)
    attempt = await db_session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.order_id == order_id)
    )
    payments_for_order = (
        await db_session.scalars(select(Payment).where(Payment.order_id == order_id))
    ).all()
    memberships = set(
        await db_session.scalars(
            select(PaymentAttemptReservation.reservation_id).where(
                PaymentAttemptReservation.attempt_id == attempt.id
            )
        )
    )
    coverage_reservations = set(
        await db_session.scalars(
            select(OrderInventoryCoverage.reservation_id).where(
                OrderInventoryCoverage.order_id == order_id,
                OrderInventoryCoverage.reservation_id.is_not(None),
            )
        )
    )
    payload = initialized.json()
    replay_payload = replay.json()
    assert Decimal(payload["amount"]) == Decimal(replay_payload["amount"])
    assert {key: value for key, value in payload.items() if key != "amount"} == {
        key: value for key, value in replay_payload.items() if key != "amount"
    }
    assert payload["payment_gateway"] == "stripe"
    assert Decimal(payload["amount"]) == attempt.amount == order.total_amount
    assert payload["amount_minor"] == int(order.total_amount * 100)
    assert payload["currency"] == attempt.currency == order.currency == "USD"
    assert payload["reference"] == attempt.provider_reference
    assert (
        attempt.checkout_estimate_selection_id == order.checkout_estimate_selection_id
    )
    assert memberships == coverage_reservations
    assert memberships
    assert len(provider_calls) == 1
    assert provider_calls[0]["amount"] == int(order.total_amount * 100)
    assert provider_calls[0]["currency"] == "usd"
    assert len(payments_for_order) == 1
    assert await db_session.scalar(select(func.count(Order.id))) == before_orders + 1


@pytest.mark.asyncio
async def test_authenticated_usd_production_route_journey_is_canonical_and_idempotent(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    await _create_select_initialize_usd_route_journey(
        client,
        db_session,
        vendor_user,
        customer_user,
        monkeypatch,
        guest=False,
    )


@pytest.mark.asyncio
async def test_guest_usd_production_route_journey_uses_order_scoped_header_and_is_idempotent(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    await _create_select_initialize_usd_route_journey(
        client,
        db_session,
        vendor_user,
        customer_user,
        monkeypatch,
        guest=True,
    )
