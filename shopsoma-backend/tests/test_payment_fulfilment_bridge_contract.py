"""Launch-critical payment/fulfilment bridge contracts."""

import asyncio
from decimal import Decimal
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1 import payments
from app.models.order import FulfillmentStatus, Order, PaymentStatus
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.models.stock_payment_persistence import (
    PaymentAttemptEvidence,
    PaymentAttemptReservation,
)
from app.schemas.payment import PaymentInitializeRequest, PaymentVerifyRequest
from app.services.payments.fulfilment_bridge import (
    PaymentTruthMismatch,
    authoritative_gateway_amount,
    bridge_fulfilment_status,
    finalize_verified_payment,
    payment_initialization_truth,
    validate_verified_payment_truth,
)
from app.services.shipping.capabilities import DomesticShippingCapabilities


def _load_stock_helpers():
    path = Path(__file__).with_name("test_stock_payment_persistence.py")
    spec = importlib.util.spec_from_file_location("bridge_stock_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _PaystackInitializationResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "status": True,
            "data": {
                "authorization_url": "https://paystack.invalid/authorize",
                "access_code": "access-code",
                "reference": "provider-reference",
            },
        }


class _PaystackInitializationClient:
    calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, *args, **kwargs):
        type(self).calls += 1
        return _PaystackInitializationResponse()


def test_gateway_amount_is_derived_from_server_attempt_truth() -> None:
    assert authoritative_gateway_amount(Decimal("1050.0000"), "NGN") == (
        Decimal("1050.0000"),
        "NGN",
    )


@pytest.mark.parametrize(
    ("observed_amount", "observed_currency", "observed_reference"),
    [
        (Decimal("1049.99"), "NGN", "provider-ref"),
        (Decimal("1050.00"), "USD", "provider-ref"),
        (Decimal("1050.00"), "NGN", "wrong-ref"),
    ],
)
def test_wrong_provider_truth_is_rejected(
    observed_amount: Decimal,
    observed_currency: str,
    observed_reference: str,
) -> None:
    with pytest.raises(PaymentTruthMismatch):
        validate_verified_payment_truth(
            expected_amount=Decimal("1050.00"),
            expected_currency="NGN",
            expected_reference="provider-ref",
            observed_amount=observed_amount,
            observed_currency=observed_currency,
            observed_reference=observed_reference,
        )


def test_exact_provider_truth_is_accepted() -> None:
    validate_verified_payment_truth(
        expected_amount=Decimal("1050.0000"),
        expected_currency="NGN",
        expected_reference="provider-ref",
        observed_amount=Decimal("1050.00"),
        observed_currency="ngn",
        observed_reference="provider-ref",
    )


@pytest.mark.parametrize(
    ("paid", "package_ready", "expected"),
    [
        (False, False, FulfillmentStatus.ORDER_RECEIVED),
        (True, False, FulfillmentStatus.ORDER_RECEIVED),
        (False, True, FulfillmentStatus.ORDER_RECEIVED),
        (True, True, FulfillmentStatus.PREPARING_FOR_PICKUP),
    ],
)
def test_shipment_eligibility_requires_paid_and_package_ready(
    paid: bool,
    package_ready: bool,
    expected: FulfillmentStatus,
) -> None:
    assert (
        bridge_fulfilment_status(
            paid=paid,
            package_ready=package_ready,
            current_status=FulfillmentStatus.ORDER_RECEIVED,
        )
        == expected
    )


@pytest.mark.asyncio
async def test_legacy_finalization_is_idempotent_and_preserves_checkout_behavior(
    db_session,
    customer_user,
) -> None:
    order = Order(
        order_number="LEGACY-BRIDGE-1",
        customer_id=customer_user["user"].id,
        currency="NGN",
        subtotal=Decimal("1000.00"),
        shipping_cost=Decimal("50.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("1050.00"),
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.flush()
    payment = Payment(
        order_id=order.id,
        transaction_id="legacy-provider-ref",
        payment_gateway=PaymentGateway.PAYSTACK,
        payment_method="paystack",
        amount=Decimal("1050.00"),
        currency="NGN",
        status=TransactionStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.flush()

    first = await finalize_verified_payment(
        db_session,
        payment=payment,
        provider="paystack",
        provider_reference="legacy-provider-ref",
        observed_amount=None,
        observed_currency=None,
        event_id="legacy-event-1",
        evidence_payload={},
    )
    second = await finalize_verified_payment(
        db_session,
        payment=payment,
        provider="paystack",
        provider_reference="legacy-provider-ref",
        observed_amount=None,
        observed_currency=None,
        event_id="legacy-event-1",
        evidence_payload={},
    )

    assert first.bridge_applied is False and first.replay is False
    assert second.bridge_applied is False and second.replay is True
    assert order.payment_status == PaymentStatus.PAID
    assert order.fulfillment_status == FulfillmentStatus.PREPARING_FOR_PICKUP


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
async def test_bridge_initialization_legally_starts_attempt_then_finalizes(
    db_session,
    vendor_user,
    customer_user,
    provider,
) -> None:
    stock = _load_stock_helpers()
    graph, intent, quote, option, selection, sku = await stock._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = stock._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = stock._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        provider=provider,
        provider_reference=f"bridge-{uuid.uuid4().hex}",
    )
    db_session.add(attempt)
    await db_session.flush()
    from app.models.stock_payment_persistence import PaymentAttemptReservation

    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    truth = await payment_initialization_truth(
        db_session,
        order=graph["order"],
        provider=provider,
        capabilities=DomesticShippingCapabilities(True, True, False),
    )
    await db_session.commit()
    await db_session.refresh(attempt)
    assert truth.bridge_applied is True
    assert truth.provider_reference == attempt.provider_reference
    assert truth.lease_token == attempt.lease_token
    assert attempt.state == "call_started"
    assert attempt.lease_token is not None
    assert attempt.call_started_at is not None
    assert attempt.claim_expires_at is not None
    assert attempt.row_version == 2

    payment = Payment(
        order_id=attempt.order_id,
        transaction_id=attempt.provider_reference,
        payment_gateway=PaymentGateway(provider),
        payment_method=provider,
        amount=attempt.amount,
        currency=attempt.currency,
        status=TransactionStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.flush()

    first = await finalize_verified_payment(
        db_session,
        payment=payment,
        provider=provider,
        provider_reference=attempt.provider_reference,
        observed_amount=attempt.amount,
        observed_currency=attempt.currency,
        event_id="bridge-event-1",
        evidence_payload={"verified": True},
    )
    second = await finalize_verified_payment(
        db_session,
        payment=payment,
        provider=provider,
        provider_reference=attempt.provider_reference,
        observed_amount=attempt.amount,
        observed_currency=attempt.currency,
        event_id="bridge-webhook-2",
        evidence_payload={"transport": "webhook", "verified": True},
    )

    await db_session.refresh(attempt)
    await db_session.refresh(graph["order"])
    evidence = (
        (
            await db_session.execute(
                select(PaymentAttemptEvidence).where(
                    PaymentAttemptEvidence.attempt_id == attempt.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert first.bridge_applied is True and first.replay is False
    assert second.bridge_applied is True and second.replay is True
    assert len(evidence) == 1
    assert evidence[0].source == "payment.verified"
    assert evidence[0].event_id == f"{provider}:{attempt.provider_reference}"
    assert attempt.state == "verified"
    assert graph["order"].payment_status == PaymentStatus.PAID
    assert graph["order"].fulfillment_status == FulfillmentStatus.PREPARING_FOR_PICKUP


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
async def test_initialization_retry_replays_only_stripe(
    db_session,
    vendor_user,
    customer_user,
    monkeypatch,
    provider,
) -> None:
    stock = _load_stock_helpers()
    graph, intent, quote, option, selection, sku = await stock._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = stock._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = stock._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        provider=provider,
        provider_reference="provider-reference",
    )
    db_session.add(attempt)
    await db_session.flush()
    from app.models.stock_payment_persistence import PaymentAttemptReservation

    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda settings: DomesticShippingCapabilities(True, True, False),
    )
    provider_calls = 0
    if provider == "stripe":
        customer_user["user"].stripe_customer_id = "cus_existing"

        def create_intent(**kwargs):
            nonlocal provider_calls
            provider_calls += 1
            return SimpleNamespace(id="pi_first", client_secret="secret_first")

        monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_intent)
        initialize = payments._initialize_stripe_payment
    else:
        _PaystackInitializationClient.calls = 0
        monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "sk_test_placeholder")
        monkeypatch.setattr(
            payments.httpx, "AsyncClient", _PaystackInitializationClient
        )
        initialize = payments._initialize_paystack_payment

    request = PaymentInitializeRequest(
        order_id=graph["order"].id,
        email=customer_user["user"].email,
        payment_gateway=provider,
        currency=attempt.currency,
        callback_url=None,
    )
    first = await initialize(request, graph["order"], db_session)
    if provider == "paystack":
        provider_calls = _PaystackInitializationClient.calls
    await db_session.refresh(attempt)
    first_truth = (
        attempt.state,
        attempt.lease_token,
        attempt.row_version,
        graph["order"].payment_status,
        await db_session.scalar(
            select(func.count(Payment.id)).where(Payment.order_id == graph["order"].id)
        ),
    )

    retry_error = None
    retry = None
    if provider == "stripe":
        retry = await initialize(request, graph["order"], db_session)
    else:
        with pytest.raises(HTTPException) as caught:
            await initialize(request, graph["order"], db_session)
        retry_error = caught.value

    if provider == "paystack":
        provider_calls = _PaystackInitializationClient.calls
    await db_session.refresh(attempt)
    retry_truth = (
        attempt.state,
        attempt.lease_token,
        attempt.row_version,
        graph["order"].payment_status,
        await db_session.scalar(
            select(func.count(Payment.id)).where(Payment.order_id == graph["order"].id)
        ),
    )
    assert first.status is True
    assert first_truth[0] == "call_started"
    assert first_truth[1] is not None
    if provider == "stripe":
        assert retry is not None and retry.status is True
        assert retry.payment_intent_id == first.payment_intent_id
        assert provider_calls == 2
    else:
        assert retry_error is not None
        assert retry_error.status_code == 409
        assert retry_error.detail == "payment attempt is not ready for initialization"
        assert provider_calls == 1
    assert retry_truth == first_truth


async def _pending_route_attempt(db_session, vendor_user, customer_user, provider):
    stock = _load_stock_helpers()
    graph, intent, quote, option, selection, sku = await stock._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = stock._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = stock._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        provider=provider,
        provider_reference=f"recover-{provider}-{uuid.uuid4().hex}",
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await db_session.commit()
    return graph, attempt


@pytest.mark.asyncio
async def test_stripe_customer_accept_then_local_loss_retries_idempotently(
    db_session, vendor_user, customer_user, monkeypatch
) -> None:
    graph, attempt = await _pending_route_attempt(
        db_session, vendor_user, customer_user, "stripe"
    )
    customer_user["user"].stripe_customer_id = None
    await db_session.commit()
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda settings: DomesticShippingCapabilities(True, True, False),
    )
    calls = {"search": [], "customer": [], "intent": []}
    provider_customers = {}
    provider_intents = {}

    def search_customer(**kwargs):
        calls["search"].append(kwargs)
        # Force reconciliation through Customer.create's idempotent boundary,
        # as Stripe search indexing may lag an accepted create.
        return SimpleNamespace(data=[])

    def create_customer(**kwargs):
        calls["customer"].append(kwargs)
        key = kwargs["idempotency_key"]
        return provider_customers.setdefault(key, SimpleNamespace(id="cus_accepted"))

    def create_intent(**kwargs):
        calls["intent"].append(kwargs)
        key = kwargs["idempotency_key"]
        return provider_intents.setdefault(
            key, SimpleNamespace(id="pi_accepted", client_secret="secret_accepted")
        )

    monkeypatch.setattr(payments.stripe.Customer, "search", search_customer)
    monkeypatch.setattr(payments.stripe.Customer, "create", create_customer)
    monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_intent)
    request = PaymentInitializeRequest(
        order_id=graph["order"].id,
        email=customer_user["user"].email,
        payment_gateway="stripe",
        currency=attempt.currency,
        callback_url=None,
    )
    original_commit = db_session.commit
    commit_calls = 0

    async def fail_customer_mapping_commit():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise RuntimeError("customer accepted; local persistence lost")
        await original_commit()

    monkeypatch.setattr(db_session, "commit", fail_customer_mapping_commit)
    with pytest.raises(RuntimeError, match="local persistence lost"):
        await payments._initialize_stripe_payment(request, graph["order"], db_session)
    monkeypatch.setattr(db_session, "commit", original_commit)
    await db_session.rollback()
    await db_session.refresh(graph["order"])

    response = await payments._initialize_stripe_payment(
        request, graph["order"], db_session
    )

    customer_key = f"shopsoma-payment-attempt:{attempt.id}:customer"
    intent_key = f"shopsoma-payment-attempt:{attempt.id}:payment-intent"
    assert response.payment_intent_id == "pi_accepted"
    assert len(calls["search"]) == 2
    assert len(calls["customer"]) == 2
    assert [call["idempotency_key"] for call in calls["customer"]] == [
        customer_key,
        customer_key,
    ]
    assert len(provider_customers) == 1
    assert len(calls["intent"]) == 1
    assert calls["intent"][0]["idempotency_key"] == intent_key
    assert len(provider_intents) == 1
    assert (
        await db_session.scalar(
            select(func.count(Payment.id)).where(Payment.order_id == graph["order"].id)
        )
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
async def test_missing_mapping_recovery_is_canonical_under_replay_and_race(
    db_session, vendor_user, customer_user, monkeypatch, provider
) -> None:
    graph, attempt = await _pending_route_attempt(
        db_session, vendor_user, customer_user, provider
    )
    await payment_initialization_truth(
        db_session,
        order=graph["order"],
        provider=provider,
        capabilities=DomesticShippingCapabilities(True, True, False),
    )
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    effects = {"receipt": 0, "claim": 0}

    async def receipt(**kwargs):
        effects["receipt"] += 1

    async def claim(customer):
        effects["claim"] += 1

    monkeypatch.setattr(payments.email_service, "send_payment_receipt_email", receipt)
    monkeypatch.setattr(payments, "send_account_claim_email_if_guest", claim)

    async def recover(transport):
        async with factory() as session:
            await _invoke_authenticated_route(
                provider,
                transport,
                session,
                monkeypatch,
                reference=attempt.provider_reference,
                amount=attempt.amount,
                currency=attempt.currency,
            )

    await asyncio.gather(recover("callback"), recover("webhook"))
    await recover("callback")
    assert (
        await db_session.scalar(
            select(func.count(Payment.id)).where(Payment.order_id == graph["order"].id)
        )
        == 1
    )
    await db_session.refresh(graph["order"])
    assert graph["order"].payment_status == PaymentStatus.PAID
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttemptEvidence.id)).where(
                PaymentAttemptEvidence.attempt_id == attempt.id
            )
        )
        == 1
    )
    assert effects["claim"] == 1
    assert effects["receipt"] <= 1


class _AuthenticatedWebhookRequest:
    def __init__(self, payload):
        self.payload = payload
        self.body_bytes = json.dumps(payload).encode()

    async def body(self):
        return self.body_bytes

    async def json(self):
        return self.payload


async def _invoke_authenticated_route(
    provider, transport, db, monkeypatch, *, reference, amount, currency
):
    if provider == "stripe":
        intent = SimpleNamespace(
            id=f"pi_{reference}",
            status="succeeded",
            amount=int(amount * 100),
            amount_received=int(amount * 100),
            currency=currency.lower(),
            metadata={"shopsoma_payment_reference": reference},
        )
        if transport == "callback":
            monkeypatch.setattr(
                payments.stripe.PaymentIntent, "retrieve", lambda value: intent
            )
            return await payments._verify_stripe_payment(
                PaymentVerifyRequest(
                    payment_gateway="stripe", payment_intent_id=intent.id
                ),
                db,
            )
        event = SimpleNamespace(
            id=f"evt_{reference}",
            type="payment_intent.succeeded",
            data=SimpleNamespace(object=intent),
        )
        monkeypatch.setattr(payments.settings, "STRIPE_WEBHOOK_SECRET", "secret")
        monkeypatch.setattr(
            payments.stripe.Webhook, "construct_event", lambda **kwargs: event
        )
        return await payments.stripe_webhook(
            _AuthenticatedWebhookRequest({"signed": True}), "signature", db
        )

    data = {
        "id": 7,
        "status": "success",
        "reference": reference,
        "amount": int(amount * 100),
        "currency": currency,
    }
    if transport == "callback":

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"status": True, "data": data}

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, *args, **kwargs):
                return Response()

        monkeypatch.setattr(payments.httpx, "AsyncClient", Client)
        return await payments._verify_paystack_payment(
            PaymentVerifyRequest(payment_gateway="paystack", reference=reference), db
        )
    request = _AuthenticatedWebhookRequest({"event": "charge.success", "data": data})
    monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "secret")
    signature = hmac.new(b"secret", request.body_bytes, hashlib.sha512).hexdigest()
    return await payments.paystack_webhook(request, signature, db)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
@pytest.mark.parametrize("transport", ["callback", "webhook"])
async def test_authenticated_unassociable_route_is_retryable_without_mutation(
    db_session, monkeypatch, provider, transport
) -> None:
    before = (
        await db_session.scalar(select(func.count(Payment.id))),
        await db_session.scalar(select(func.count(PaymentAttemptEvidence.id))),
        await db_session.scalar(select(func.count(Order.id))),
    )

    with pytest.raises(HTTPException) as error:
        await _invoke_authenticated_route(
            provider,
            transport,
            db_session,
            monkeypatch,
            reference=f"missing-{provider}-{transport}",
            amount=Decimal("1.00"),
            currency="NGN",
        )

    assert error.value.status_code == 503
    assert (
        await db_session.scalar(select(func.count(Payment.id))),
        await db_session.scalar(select(func.count(PaymentAttemptEvidence.id))),
        await db_session.scalar(select(func.count(Order.id))),
    ) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
@pytest.mark.parametrize("transport", ["callback", "webhook"])
async def test_authenticated_route_recovers_missing_mapping(
    db_session, vendor_user, customer_user, monkeypatch, provider, transport
) -> None:
    graph, attempt = await _pending_route_attempt(
        db_session, vendor_user, customer_user, provider
    )
    await payment_initialization_truth(
        db_session,
        order=graph["order"],
        provider=provider,
        capabilities=DomesticShippingCapabilities(True, True, False),
    )
    await db_session.commit()
    transaction_id = (
        f"pi_{attempt.id.hex}" if provider == "stripe" else attempt.provider_reference
    )
    if provider == "stripe":
        intent = SimpleNamespace(
            id=transaction_id,
            status="succeeded",
            amount=int(attempt.amount * 100),
            amount_received=int(attempt.amount * 100),
            currency="ngn",
            metadata={"shopsoma_payment_reference": attempt.provider_reference},
        )
        if transport == "callback":
            monkeypatch.setattr(
                payments.stripe.PaymentIntent, "retrieve", lambda value: intent
            )
            await payments._verify_stripe_payment(
                PaymentVerifyRequest(
                    payment_gateway="stripe", payment_intent_id=transaction_id
                ),
                db_session,
            )
        else:
            event = SimpleNamespace(
                id=f"evt_{attempt.id.hex}",
                type="payment_intent.succeeded",
                data=SimpleNamespace(object=intent),
            )
            monkeypatch.setattr(payments.settings, "STRIPE_WEBHOOK_SECRET", "secret")
            monkeypatch.setattr(
                payments.stripe.Webhook, "construct_event", lambda **kwargs: event
            )
            await payments.stripe_webhook(
                _AuthenticatedWebhookRequest({"signed": True}), "signature", db_session
            )
    else:
        data = {
            "id": 7,
            "status": "success",
            "reference": transaction_id,
            "amount": int(attempt.amount * 100),
            "currency": "NGN",
        }
        if transport == "callback":

            class Response:
                def raise_for_status(self):
                    return None

                def json(self):
                    return {"status": True, "data": data}

            class Client:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return None

                async def get(self, *args, **kwargs):
                    return Response()

            monkeypatch.setattr(payments.httpx, "AsyncClient", Client)
            await payments._verify_paystack_payment(
                PaymentVerifyRequest(
                    payment_gateway="paystack", reference=transaction_id
                ),
                db_session,
            )
        else:
            request = _AuthenticatedWebhookRequest(
                {"event": "charge.success", "data": data}
            )
            monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "secret")
            signature = hmac.new(
                b"secret", request.body_bytes, hashlib.sha512
            ).hexdigest()
            await payments.paystack_webhook(request, signature, db_session)

    payment = await db_session.scalar(
        select(Payment).where(Payment.order_id == graph["order"].id)
    )
    await db_session.refresh(graph["order"])
    assert payment is not None
    assert payment.transaction_id == transaction_id
    assert payment.status == TransactionStatus.COMPLETED
    assert graph["order"].payment_status == PaymentStatus.PAID
