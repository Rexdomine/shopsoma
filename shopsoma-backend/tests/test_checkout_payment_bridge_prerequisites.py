"""Milestone 4 production-route payment prerequisite contracts."""

from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import func, select

from app.api.v1 import payments
from app.core.config import settings
from app.models.checkout_shipping_estimate import OrderInventoryCoverage
from app.models.order import Order
from app.models.stock_payment_persistence import (
    PaymentAttempt,
    PaymentAttemptReservation,
    StockReservation,
)
from app.services.shipping.capabilities import DomesticShippingCapabilities
from tests.test_checkout_estimate_api import _domestic_catalogue


async def create_enforced_checkout(
    client,
    db_session,
    vendor_user,
    customer_user,
    monkeypatch,
    *,
    quantity=1,
    select_option=True,
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    product.total_stock = max(product.total_stock, quantity)
    await db_session.commit()
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST",
        str(customer_user["user"].id),
    )
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda _settings: DomesticShippingCapabilities(True, True, False),
    )
    created = await client.post(
        "/api/v1/orders",
        headers=customer_user["headers"],
        json={
            "items": [{"product_id": str(product.id), "quantity": quantity}],
            "shipping_address_id": str(address.id),
            "currency": "NGN",
        },
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    estimated = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates",
        headers={
            **customer_user["headers"],
            "X-Idempotency-Key": f"estimate-{uuid.uuid4()}",
        },
    )
    assert estimated.status_code == 201, estimated.text
    estimate = estimated.json()
    if select_option:
        selected = await client.post(
            f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
            f"/options/{estimate['options'][0]['id']}/select",
            headers={
                **customer_user["headers"],
                "X-Idempotency-Key": f"select-{uuid.uuid4()}",
            },
        )
        assert selected.status_code == 200, selected.text
    order = await db_session.get(Order, uuid.UUID(order_id))
    await db_session.refresh(order)
    return order, product


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
async def test_real_initialization_routes_bind_m3_truth_and_ignore_client_currency(
    client, db_session, vendor_user, customer_user, monkeypatch, provider
):
    order, _ = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    selection_id = order.checkout_estimate_selection_id
    expected_amount = Decimal(order.total_amount).quantize(Decimal("0.01"))
    expected_currency = order.currency
    customer_email = customer_user["user"].email
    observed = {}
    if provider == "stripe":
        customer_user["user"].stripe_customer_id = "cus_m4_existing"
        await db_session.commit()

        def create_intent(**kwargs):
            observed.update(kwargs)
            return SimpleNamespace(id="pi_m4", client_secret="secret_m4")

        monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_intent)
    else:
        monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "sk_test_placeholder")

        class Response:
            status_code = 200
            text = ""

            def json(self):
                return {
                    "status": True,
                    "data": {
                        "authorization_url": "https://paystack.invalid/authorize",
                        "access_code": "m4",
                        "reference": "m4-paystack-reference",
                    },
                }

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return None

            async def post(self, _url, **kwargs):
                observed.update(kwargs["json"])
                return Response()

        monkeypatch.setattr(payments.httpx, "AsyncClient", Client)

    response = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_email,
            "payment_gateway": provider,
            "currency": "USD",
        },
    )
    assert response.status_code == 200, response.text
    db_session.expire_all()
    attempt = await db_session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.order_id == order_id)
    )
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
    assert attempt.workflow_cohort == "domestic_checkout_v1"
    assert attempt.checkout_estimate_selection_id == selection_id
    assert memberships == coverage_reservations
    assert attempt.currency == expected_currency == "NGN"
    assert attempt.amount == expected_amount
    if provider == "stripe":
        assert observed["amount"] == int(attempt.amount * 100)
        assert observed["currency"] == "ngn"
    else:
        assert observed["amount"] == int(attempt.amount * 100)
        assert observed["currency"] == "NGN"


@pytest.mark.asyncio
async def test_incomplete_m3_coverage_blocks_provider_before_call(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, _ = await create_enforced_checkout(
        client,
        db_session,
        vendor_user,
        customer_user,
        monkeypatch,
        select_option=False,
    )
    order_id = order.id
    customer_email = customer_user["user"].email
    calls = 0

    def forbidden_provider_call(**_kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("provider must not be called")

    customer_user["user"].stripe_customer_id = "cus_m4_existing"
    await db_session.commit()
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "create", forbidden_provider_call
    )
    response = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_email,
            "payment_gateway": "stripe",
            "currency": "NGN",
        },
    )
    assert response.status_code == 409
    assert calls == 0
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(PaymentAttempt)
            .where(PaymentAttempt.order_id == order_id)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_gate_off_does_not_strand_existing_enforced_attempt(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, _ = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    customer_email = customer_user["user"].email
    customer_user["user"].stripe_customer_id = "cus_m4_existing"
    await db_session.commit()
    monkeypatch.setattr(
        payments.stripe.PaymentIntent,
        "create",
        lambda **_kwargs: SimpleNamespace(id="pi_recovery", client_secret="secret"),
    )
    first = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_email,
            "payment_gateway": "stripe",
            "currency": "NGN",
        },
    )
    assert first.status_code == 200, first.text
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", False)
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda _settings: DomesticShippingCapabilities(False, False, False),
    )
    replay = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_email,
            "payment_gateway": "stripe",
            "currency": "USD",
        },
    )
    assert replay.status_code == 200, replay.text
