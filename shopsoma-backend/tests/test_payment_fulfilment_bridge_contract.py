"""Launch-critical payment/fulfilment bridge contracts."""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.v1 import payments
from app.models.order import FulfillmentStatus, Order, PaymentStatus
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.models.stock_payment_persistence import (
    PaymentAttempt,
    PaymentAttemptEvidence,
    PaymentAttemptReservation,
)
from app.schemas.payment import PaymentInitializeRequest, PaymentVerifyRequest
from app.services.payments.fulfilment_bridge import (
    PaymentBridgeError,
    PaymentInitializationTruth,
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


def _load_review_helpers():
    path = Path(__file__).with_name("test_stock_payment_review_findings.py")
    spec = importlib.util.spec_from_file_location("bridge_review_helpers", path)
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
    lookup_calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, *args, **kwargs):
        type(self).calls += 1
        return _PaystackInitializationResponse()

    async def get(self, *args, **kwargs):
        type(self).lookup_calls += 1
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"status": True, "data": {"status": "pending"}},
        )


async def _unattempted_route_subject(db_session, vendor_user, customer_user):
    stock = _load_stock_helpers()
    graph, intent, quote, option, selection, sku = await stock._checkout_subject(
        db_session, vendor_user, customer_user
    )
    reservation = stock._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.commit()
    return graph, quote, option, selection, reservation


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
async def test_production_initialize_creates_authoritative_attempt_before_provider(
    db_session, vendor_user, customer_user, monkeypatch, provider
) -> None:
    graph, quote, option, selection, reservation = await _unattempted_route_subject(
        db_session, vendor_user, customer_user
    )
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda settings: DomesticShippingCapabilities(True, True, False),
    )
    observed = {}

    async def capture_attempt():
        attempt = await db_session.scalar(
            select(PaymentAttempt).where(PaymentAttempt.order_id == graph["order"].id)
        )
        assert attempt is not None
        memberships = set(
            await db_session.scalars(
                select(PaymentAttemptReservation.reservation_id).where(
                    PaymentAttemptReservation.attempt_id == attempt.id
                )
            )
        )
        observed.update(
            attempt=attempt,
            memberships=memberships,
            amount=attempt.amount,
            currency=attempt.currency,
        )

    if provider == "stripe":
        customer_user["user"].stripe_customer_id = "cus_existing"
        await db_session.commit()

        def create_intent(**kwargs):
            observed["payload"] = kwargs
            assert observed["attempt"].state == "call_started"
            return SimpleNamespace(id="pi_created", client_secret="secret_created")

        original_truth = payments.payment_initialization_truth

        async def capture_truth(*args, **kwargs):
            truth = await original_truth(*args, **kwargs)
            await capture_attempt()
            return truth

        monkeypatch.setattr(payments, "payment_initialization_truth", capture_truth)
        monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_intent)
    else:
        _PaystackInitializationClient.calls = 0
        _PaystackInitializationClient.lookup_calls = 0
        monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "sk_test_placeholder")

        class CapturingPaystackClient(_PaystackInitializationClient):
            async def post(self, *args, **kwargs):
                await capture_attempt()
                observed["payload"] = kwargs["json"]
                assert observed["attempt"].state == "call_started"
                return await super().post(*args, **kwargs)

        monkeypatch.setattr(payments.httpx, "AsyncClient", CapturingPaystackClient)

    request = PaymentInitializeRequest(
        order_id=graph["order"].id,
        email=customer_user["user"].email,
        payment_gateway=provider,
        currency=graph["order"].currency,
        callback_url=None,
    )
    response = await payments.initialize_payment(
        request, current_user=customer_user["user"], db=db_session
    )

    attempt = observed["attempt"]
    assert response.status is True
    assert attempt.provider == provider
    assert attempt.quote_id == quote.id
    assert attempt.quote_option_id == option.id
    assert attempt.quote_selection_id == selection.id
    assert observed["memberships"] == {reservation.id}
    assert observed["amount"] == graph["order"].total_amount
    assert observed["currency"] == graph["order"].currency
    assert observed["payload"]["amount"] == int(graph["order"].total_amount * 100)


@pytest.mark.asyncio
async def test_initialization_anchors_selection_to_smallest_reservation_in_full_cohort(
    db_session, vendor_user, customer_user
) -> None:
    stock = _load_stock_helpers()
    review = _load_review_helpers()
    graph, intent, quote, option, oldest_selection, sku = await stock._checkout_subject(
        db_session, vendor_user, customer_user
    )
    alternate_intent, alternate_quote, alternate_option, anchor_selection = (
        await review._alternate_selection(
            db_session, stock, graph, customer_user["user"].id
        )
    )
    oldest_reservation = stock._reservation(
        graph,
        intent,
        quote,
        option,
        oldest_selection,
        customer_user["user"].id,
        sku,
        id=uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    )
    anchor_reservation = stock._reservation(
        graph,
        alternate_intent,
        alternate_quote,
        alternate_option,
        anchor_selection,
        customer_user["user"].id,
        sku,
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    )
    db_session.add_all([oldest_reservation, anchor_reservation])
    await db_session.commit()

    first = await payment_initialization_truth(
        db_session,
        order=graph["order"],
        provider="stripe",
        capabilities=DomesticShippingCapabilities(True, True, False),
    )
    second = await payment_initialization_truth(
        db_session,
        order=graph["order"],
        provider="stripe",
        capabilities=DomesticShippingCapabilities(True, True, False),
    )
    await db_session.commit()

    attempt = await db_session.get(PaymentAttempt, first.attempt_id)
    memberships = set(
        await db_session.scalars(
            select(PaymentAttemptReservation.reservation_id).where(
                PaymentAttemptReservation.attempt_id == attempt.id
            )
        )
    )
    assert first.attempt_id == second.attempt_id
    assert attempt.quote_selection_id == anchor_selection.id
    assert attempt.quote_id == alternate_quote.id
    assert attempt.quote_option_id == alternate_option.id
    assert attempt.intent_id == alternate_intent.id
    assert memberships == {oldest_reservation.id, anchor_reservation.id}


@pytest.mark.asyncio
async def test_created_attempt_replay_does_not_duplicate_attempt_or_membership(
    db_session, vendor_user, customer_user, monkeypatch
) -> None:
    graph, _, _, _, reservation = await _unattempted_route_subject(
        db_session, vendor_user, customer_user
    )
    customer_user["user"].stripe_customer_id = "cus_existing"
    await db_session.commit()
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda settings: DomesticShippingCapabilities(True, True, False),
    )
    calls = []

    def create_intent(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id="pi_replay", client_secret="secret_replay")

    monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_intent)
    request = PaymentInitializeRequest(
        order_id=graph["order"].id,
        email=customer_user["user"].email,
        payment_gateway="stripe",
        currency=graph["order"].currency,
        callback_url=None,
    )

    await payments.initialize_payment(
        request, current_user=customer_user["user"], db=db_session
    )
    await payments.initialize_payment(
        request, current_user=customer_user["user"], db=db_session
    )

    attempts = list(
        await db_session.scalars(
            select(PaymentAttempt).where(PaymentAttempt.order_id == graph["order"].id)
        )
    )
    memberships = list(
        await db_session.scalars(
            select(PaymentAttemptReservation.reservation_id).where(
                PaymentAttemptReservation.attempt_id == attempts[0].id
            )
        )
    )
    assert len(attempts) == 1
    assert memberships == [reservation.id]
    assert len(calls) == 2
    assert calls[0]["idempotency_key"] == calls[1]["idempotency_key"]


@pytest.mark.asyncio
async def test_concurrent_provider_initialization_converges_to_one_attempt(
    db_session, vendor_user, customer_user
) -> None:
    graph, _, _, _, reservation = await _unattempted_route_subject(
        db_session, vendor_user, customer_user
    )
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)
    ready = asyncio.Event()

    async def initialize(provider):
        async with maker() as session:
            order = await session.get(Order, graph["order"].id)
            ready.set()
            await ready.wait()
            try:
                truth = await payment_initialization_truth(
                    session,
                    order=order,
                    provider=provider,
                    capabilities=DomesticShippingCapabilities(True, True, False),
                )
                await session.commit()
                return truth
            except PaymentBridgeError as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(initialize("stripe"), initialize("paystack"))
    attempts = list(
        await db_session.scalars(
            select(PaymentAttempt).where(PaymentAttempt.order_id == graph["order"].id)
        )
    )
    memberships = list(
        await db_session.scalars(
            select(PaymentAttemptReservation.reservation_id).where(
                PaymentAttemptReservation.attempt_id == attempts[0].id
            )
        )
    )
    assert (
        sum(isinstance(result, PaymentInitializationTruth) for result in results) == 1
    )
    assert sum(isinstance(result, PaymentBridgeError) for result in results) == 1
    assert len(attempts) == 1
    assert memberships == [reservation.id]


@pytest.mark.asyncio
async def test_enforced_selected_quote_without_reservations_fails_closed(
    db_session, vendor_user, customer_user
) -> None:
    stock = _load_stock_helpers()
    graph, *_ = await stock._checkout_subject(db_session, vendor_user, customer_user)

    with pytest.raises(PaymentBridgeError, match="subject binding is invalid"):
        await payment_initialization_truth(
            db_session,
            order=graph["order"],
            provider="stripe",
            capabilities=DomesticShippingCapabilities(True, True, False),
        )


@pytest.mark.asyncio
async def test_disabled_gate_and_genuine_legacy_order_do_not_create_attempt(
    db_session, customer_user
) -> None:
    order = Order(
        order_number=f"LEGACY-INIT-{uuid.uuid4().hex[:10]}",
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

    disabled = await payment_initialization_truth(
        db_session,
        order=order,
        provider="stripe",
        capabilities=DomesticShippingCapabilities(True, False, False),
    )
    legacy = await payment_initialization_truth(
        db_session,
        order=order,
        provider="stripe",
        capabilities=DomesticShippingCapabilities(True, True, False),
    )

    assert disabled.bridge_applied is False
    assert legacy.bridge_applied is False
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttempt.id)).where(
                PaymentAttempt.order_id == order.id
            )
        )
        == 0
    )


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
        _PaystackInitializationClient.lookup_calls = 0
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
        assert retry_error.status_code == 503
        assert retry_error.detail == "Payment initialization outcome is not definitive"
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
async def test_stripe_intent_accept_then_payment_commit_loss_reconciles_canonically(
    db_session, vendor_user, customer_user, monkeypatch
) -> None:
    graph, attempt = await _pending_route_attempt(
        db_session, vendor_user, customer_user, "stripe"
    )
    customer_user["user"].stripe_customer_id = "cus_committed"
    await db_session.commit()
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda settings: DomesticShippingCapabilities(True, True, False),
    )
    intent_calls = []
    provider_intents = {}

    def create_intent(**kwargs):
        intent_calls.append(kwargs)
        key = kwargs["idempotency_key"]
        return provider_intents.setdefault(
            key, SimpleNamespace(id="pi_accepted", client_secret="secret_accepted")
        )

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

    async def fail_payment_mapping_commit():
        nonlocal commit_calls
        commit_calls += 1
        if commit_calls == 2:
            raise RuntimeError("intent accepted; payment mapping commit lost")
        await original_commit()

    monkeypatch.setattr(db_session, "commit", fail_payment_mapping_commit)
    with pytest.raises(RuntimeError, match="payment mapping commit lost"):
        await payments._initialize_stripe_payment(request, graph["order"], db_session)
    assert customer_user["user"].stripe_customer_id == "cus_committed"
    assert len(intent_calls) == 1
    monkeypatch.setattr(db_session, "commit", original_commit)
    await db_session.rollback()
    await db_session.refresh(graph["order"])

    response = await payments._initialize_stripe_payment(
        request, graph["order"], db_session
    )

    intent_key = f"shopsoma-payment-attempt:{attempt.id}:payment-intent"
    canonical_payments = (
        (
            await db_session.execute(
                select(Payment).where(Payment.order_id == graph["order"].id)
            )
        )
        .scalars()
        .all()
    )
    assert response.payment_intent_id == "pi_accepted"
    assert [call["idempotency_key"] for call in intent_calls] == [
        intent_key,
        intent_key,
    ]
    assert len(provider_intents) == 1
    assert len(canonical_payments) == 1
    payment = canonical_payments[0]
    assert payment.order_id == graph["order"].id
    assert payment.amount == attempt.amount
    assert payment.currency == attempt.currency
    assert payment.payment_gateway == PaymentGateway.STRIPE
    assert payment.transaction_id == "pi_accepted"


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


async def _call_started_route_payment(db_session, vendor_user, customer_user, provider):
    graph, attempt = await _pending_route_attempt(
        db_session, vendor_user, customer_user, provider
    )
    await payment_initialization_truth(
        db_session,
        order=graph["order"],
        provider=provider,
        capabilities=DomesticShippingCapabilities(True, True, False),
    )
    transaction_id = (
        f"pi_{attempt.id.hex}" if provider == "stripe" else attempt.provider_reference
    )
    payment = Payment(
        order_id=attempt.order_id,
        transaction_id=transaction_id,
        payment_gateway=PaymentGateway(provider),
        payment_method=provider,
        amount=attempt.amount,
        currency=attempt.currency,
        status=TransactionStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()
    await db_session.refresh(attempt)
    return graph, attempt, payment


async def _prepare_failure_reconciliation(db_session, attempt, starting_state):
    if starting_state == "fresh_call_started":
        return

    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE payment_attempts "
            "SET claim_expires_at=clock_timestamp() - interval '1 second' "
            "WHERE id=:attempt_id"
        ),
        {"attempt_id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await db_session.refresh(attempt)
    if starting_state == "call_started":
        await db_session.commit()
        return

    unknown = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="provider_reconciliation",
        event_id=f"unknown:{attempt.id.hex}",
        evidence_type="outcome_unknown",
        provider=attempt.provider,
        provider_reference=attempt.provider_reference,
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(unknown)
    await db_session.flush()
    await db_session.execute(
        text("SELECT coordinate_payment_attempt_write(:attempt_id, :order_id)"),
        {"attempt_id": attempt.id, "order_id": attempt.order_id},
    )
    await db_session.execute(
        text("SELECT set_config('shopsoma.payment_lease_token', :token, true)"),
        {"token": str(attempt.lease_token)},
    )
    attempt.state = "abandoned_unknown"
    attempt.terminal_evidence_id = unknown.id
    attempt.row_version += 1
    await db_session.commit()
    await db_session.refresh(attempt)


async def _invoke_authenticated_failure(
    provider, transport, db, monkeypatch, *, attempt, payment
):
    if provider == "stripe":
        intent = SimpleNamespace(
            id=payment.transaction_id,
            status="canceled",
            amount=int(attempt.amount * 100),
            currency=attempt.currency.lower(),
            metadata={"shopsoma_payment_reference": attempt.provider_reference},
            last_payment_error=SimpleNamespace(message="Card declined"),
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
            id=f"evt_failed_{attempt.id.hex}",
            type="payment_intent.canceled",
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
        "id": 9,
        "status": "failed",
        "reference": attempt.provider_reference,
        "amount": int(attempt.amount * 100),
        "currency": attempt.currency,
        "gateway_response": "Declined",
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
            PaymentVerifyRequest(
                payment_gateway="paystack", reference=attempt.provider_reference
            ),
            db,
        )
    request = _AuthenticatedWebhookRequest({"event": "charge.failed", "data": data})
    monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "secret")
    signature = hmac.new(b"secret", request.body_bytes, hashlib.sha512).hexdigest()
    return await payments.paystack_webhook(request, signature, db)


@pytest.mark.asyncio
async def test_retryable_stripe_failure_then_success_keeps_one_attempt_and_one_effect(
    db_session, vendor_user, customer_user, monkeypatch
) -> None:
    graph, attempt, payment = await _call_started_route_payment(
        db_session, vendor_user, customer_user, "stripe"
    )
    effects = 0

    async def claim(customer):
        nonlocal effects
        effects += 1

    monkeypatch.setattr(payments, "send_account_claim_email_if_guest", claim)
    retryable = SimpleNamespace(
        id=payment.transaction_id,
        status="requires_payment_method",
        amount=int(attempt.amount * 100),
        amount_received=0,
        currency=attempt.currency.lower(),
        metadata={"shopsoma_payment_reference": attempt.provider_reference},
        last_payment_error=SimpleNamespace(message="Try another card"),
    )
    failed_event = SimpleNamespace(
        id=f"evt_retryable_{attempt.id.hex}",
        type="payment_intent.payment_failed",
        data=SimpleNamespace(object=retryable),
    )
    monkeypatch.setattr(payments.settings, "STRIPE_WEBHOOK_SECRET", "secret")
    monkeypatch.setattr(
        payments.stripe.Webhook, "construct_event", lambda **kwargs: failed_event
    )
    request = _AuthenticatedWebhookRequest({"signed": True})
    assert await payments.stripe_webhook(request, "signature", db_session) == {
        "status": "success"
    }

    await db_session.refresh(attempt)
    await db_session.refresh(payment)
    assert attempt.state == "call_started"
    assert payment.status == TransactionStatus.PENDING

    succeeded = SimpleNamespace(
        id=payment.transaction_id,
        status="succeeded",
        amount=int(attempt.amount * 100),
        amount_received=int(attempt.amount * 100),
        currency=attempt.currency.lower(),
        metadata={"shopsoma_payment_reference": attempt.provider_reference},
    )
    success_event = SimpleNamespace(
        id=f"evt_success_{attempt.id.hex}",
        type="payment_intent.succeeded",
        data=SimpleNamespace(object=succeeded),
    )
    monkeypatch.setattr(
        payments.stripe.Webhook, "construct_event", lambda **kwargs: success_event
    )
    await payments.stripe_webhook(request, "signature", db_session)
    await payments.stripe_webhook(request, "signature", db_session)

    await db_session.refresh(attempt)
    await db_session.refresh(payment)
    await db_session.refresh(graph["order"])
    assert attempt.state == "verified"
    assert payment.status == TransactionStatus.COMPLETED
    assert graph["order"].payment_status == PaymentStatus.PAID
    assert effects == 1
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttempt.id)).where(
                PaymentAttempt.order_id == graph["order"].id
            )
        )
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,transport", [("stripe", "webhook"), ("paystack", "callback")]
)
@pytest.mark.parametrize(
    "starting_state", ["fresh_call_started", "call_started", "abandoned_unknown"]
)
async def test_definitive_failure_route_recovers_missing_mapping_and_replays(
    db_session,
    vendor_user,
    customer_user,
    monkeypatch,
    provider,
    transport,
    starting_state,
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
    await db_session.refresh(attempt)
    await _prepare_failure_reconciliation(db_session, attempt, starting_state)

    payment_stub = SimpleNamespace(transaction_id=attempt.provider_reference)
    first = await _invoke_authenticated_failure(
        provider,
        transport,
        db_session,
        monkeypatch,
        attempt=attempt,
        payment=payment_stub,
    )
    second = await _invoke_authenticated_failure(
        provider,
        transport,
        db_session,
        monkeypatch,
        attempt=attempt,
        payment=payment_stub,
    )

    mappings = list(
        await db_session.scalars(
            select(Payment).where(Payment.order_id == graph["order"].id)
        )
    )
    await db_session.refresh(attempt)
    await db_session.refresh(graph["order"])
    if transport == "callback":
        assert first.status is True
        assert second.status is True
    else:
        assert first == second == {"status": "success"}
    assert len(mappings) == 1
    assert mappings[0].transaction_id == attempt.provider_reference
    assert mappings[0].status == TransactionStatus.FAILED
    assert attempt.state == "failed"
    assert graph["order"].payment_status == PaymentStatus.FAILED
    definitive_evidence = list(
        await db_session.scalars(
            select(PaymentAttemptEvidence).where(
                PaymentAttemptEvidence.attempt_id == attempt.id,
                PaymentAttemptEvidence.evidence_type == "payment_failed",
            )
        )
    )
    assert len(definitive_evidence) == 1

    successor = await payment_initialization_truth(
        db_session,
        order=graph["order"],
        provider=provider,
        capabilities=DomesticShippingCapabilities(True, True, False),
    )
    assert successor.attempt_id != attempt.id
    successor_attempt = await db_session.get(PaymentAttempt, successor.attempt_id)
    assert successor_attempt.supersedes_attempt_id == attempt.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,transport", [("stripe", "webhook"), ("paystack", "callback")]
)
async def test_definitive_failure_route_unassociable_is_retryable_without_mutation(
    db_session, monkeypatch, provider, transport
) -> None:
    before = (
        await db_session.scalar(select(func.count(Payment.id))),
        await db_session.scalar(select(func.count(PaymentAttemptEvidence.id))),
        await db_session.scalar(select(func.count(Order.id))),
    )
    missing = SimpleNamespace(
        id=uuid.uuid4(),
        provider_reference=f"missing-{provider}-{uuid.uuid4().hex}",
        amount=Decimal("1.00"),
        currency="NGN",
    )
    payment_stub = SimpleNamespace(transaction_id=missing.provider_reference)

    with pytest.raises(HTTPException) as caught:
        await _invoke_authenticated_failure(
            provider,
            transport,
            db_session,
            monkeypatch,
            attempt=missing,
            payment=payment_stub,
        )

    assert caught.value.status_code == 503
    assert (
        await db_session.scalar(select(func.count(Payment.id))),
        await db_session.scalar(select(func.count(PaymentAttemptEvidence.id))),
        await db_session.scalar(select(func.count(Order.id))),
    ) == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,transport", [("stripe", "webhook"), ("paystack", "callback")]
)
async def test_definitive_failure_route_mismatch_rolls_back_atomically(
    db_session, vendor_user, customer_user, monkeypatch, provider, transport
) -> None:
    graph, attempt, payment = await _call_started_route_payment(
        db_session, vendor_user, customer_user, provider
    )
    observed = SimpleNamespace(
        id=attempt.id,
        provider_reference=f"mismatch-{uuid.uuid4().hex}",
        amount=attempt.amount,
        currency=attempt.currency,
    )
    with pytest.raises(HTTPException) as caught:
        if provider == "stripe":
            await _invoke_authenticated_failure(
                provider,
                transport,
                db_session,
                monkeypatch,
                attempt=observed,
                payment=payment,
            )
        else:
            data = {
                "id": 29,
                "status": "failed",
                "reference": observed.provider_reference,
                "amount": int(observed.amount * 100),
                "currency": observed.currency,
                "gateway_response": "Declined",
            }

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
                    payment_gateway="paystack", reference=payment.transaction_id
                ),
                db_session,
            )

    assert caught.value.status_code == 409
    await db_session.refresh(attempt)
    await db_session.refresh(payment)
    await db_session.refresh(graph["order"])
    assert attempt.state == "call_started"
    assert payment.status == TransactionStatus.PENDING
    assert graph["order"].payment_status == PaymentStatus.PENDING
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttemptEvidence.id)).where(
                PaymentAttemptEvidence.attempt_id == attempt.id
            )
        )
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,transport", [("stripe", "webhook"), ("paystack", "callback")]
)
async def test_definitive_failure_route_never_downgrades_completed_truth(
    db_session, vendor_user, customer_user, monkeypatch, provider, transport
) -> None:
    graph, attempt, payment = await _call_started_route_payment(
        db_session, vendor_user, customer_user, provider
    )
    await finalize_verified_payment(
        db_session,
        payment=payment,
        provider=provider,
        provider_reference=attempt.provider_reference,
        observed_amount=attempt.amount,
        observed_currency=attempt.currency,
        event_id=f"completed:{attempt.id.hex}",
        evidence_payload={"status": "success"},
    )
    await db_session.commit()

    await _invoke_authenticated_failure(
        provider,
        transport,
        db_session,
        monkeypatch,
        attempt=attempt,
        payment=payment,
    )

    await db_session.refresh(attempt)
    await db_session.refresh(payment)
    await db_session.refresh(graph["order"])
    assert attempt.state == "verified"
    assert payment.status == TransactionStatus.COMPLETED
    assert graph["order"].payment_status == PaymentStatus.PAID
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttemptEvidence.id)).where(
                PaymentAttemptEvidence.attempt_id == attempt.id,
                PaymentAttemptEvidence.evidence_type == "payment_failed",
            )
        )
        == 0
    )


@pytest.mark.asyncio
async def test_paystack_failed_webhook_missing_mapping_mismatch_is_retryable(
    db_session, vendor_user, customer_user, monkeypatch
) -> None:
    graph, attempt = await _pending_route_attempt(
        db_session, vendor_user, customer_user, "paystack"
    )
    await payment_initialization_truth(
        db_session,
        order=graph["order"],
        provider="paystack",
        capabilities=DomesticShippingCapabilities(True, True, False),
    )
    await db_session.commit()
    order_id = graph["order"].id
    data = {
        "id": 19,
        "status": "failed",
        "reference": f"unassociated-{uuid.uuid4().hex}",
        "amount": int(attempt.amount * 100),
        "currency": attempt.currency,
        "gateway_response": "Declined",
    }
    request = _AuthenticatedWebhookRequest({"event": "charge.failed", "data": data})
    monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "secret")
    signature = hmac.new(b"secret", request.body_bytes, hashlib.sha512).hexdigest()

    with pytest.raises(HTTPException) as caught:
        await payments.paystack_webhook(request, signature, db_session)

    assert caught.value.status_code == 503
    assert (
        await db_session.scalar(
            select(func.count(Payment.id)).where(Payment.order_id == order_id)
        )
        == 0
    )


async def _terminal_route_attempt(
    db_session, vendor_user, customer_user, monkeypatch, provider, terminal_state
):
    if terminal_state == "failed":
        graph, attempt, payment = await _call_started_route_payment(
            db_session, vendor_user, customer_user, provider
        )
        await _invoke_authenticated_failure(
            provider,
            "callback",
            db_session,
            monkeypatch,
            attempt=attempt,
            payment=payment,
        )
    else:
        graph, attempt = await _pending_route_attempt(
            db_session, vendor_user, customer_user, provider
        )
        await db_session.execute(text("SET LOCAL session_replication_role = replica"))
        await db_session.execute(
            text(
                "UPDATE payment_attempts SET state='expired', "
                "terminal_at=clock_timestamp(), row_version=row_version + 1 "
                "WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
        await db_session.execute(text("SET LOCAL session_replication_role = origin"))
        await db_session.commit()
    await db_session.refresh(attempt)
    assert attempt.state == terminal_state
    return graph, attempt


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
@pytest.mark.parametrize("terminal_state", ["failed", "expired"])
async def test_production_initialize_creates_terminal_attempt_successor_before_provider(
    db_session,
    vendor_user,
    customer_user,
    monkeypatch,
    provider,
    terminal_state,
) -> None:
    graph, predecessor = await _terminal_route_attempt(
        db_session,
        vendor_user,
        customer_user,
        monkeypatch,
        provider,
        terminal_state,
    )
    predecessor_provider = predecessor.provider
    predecessor_reference = predecessor.provider_reference
    memberships = set(
        await db_session.scalars(
            select(PaymentAttemptReservation.reservation_id).where(
                PaymentAttemptReservation.attempt_id == predecessor.id
            )
        )
    )
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda settings: DomesticShippingCapabilities(True, True, False),
    )
    observed = {}

    async def capture_successor():
        successor = await db_session.scalar(
            select(PaymentAttempt).where(
                PaymentAttempt.supersedes_attempt_id == predecessor.id
            )
        )
        assert successor is not None
        observed["successor"] = successor
        observed["memberships"] = set(
            await db_session.scalars(
                select(PaymentAttemptReservation.reservation_id).where(
                    PaymentAttemptReservation.attempt_id == successor.id
                )
            )
        )
        assert successor.state == "call_started"

    if provider == "stripe":
        customer_user["user"].stripe_customer_id = "cus_existing"
        await db_session.commit()

        def create_intent(**kwargs):
            observed["provider_calls"] = observed.get("provider_calls", 0) + 1
            observed["payload"] = kwargs
            return SimpleNamespace(id="pi_successor", client_secret="secret_successor")

        original_truth = payments.payment_initialization_truth

        async def capture_truth(*args, **kwargs):
            truth = await original_truth(*args, **kwargs)
            await capture_successor()
            return truth

        monkeypatch.setattr(payments, "payment_initialization_truth", capture_truth)
        monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_intent)
    else:
        _PaystackInitializationClient.calls = 0
        _PaystackInitializationClient.lookup_calls = 0
        monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "sk_test_placeholder")

        class CapturingPaystackClient(_PaystackInitializationClient):
            async def post(self, *args, **kwargs):
                observed["provider_calls"] = observed.get("provider_calls", 0) + 1
                await capture_successor()
                observed["payload"] = kwargs["json"]
                return await super().post(*args, **kwargs)

        monkeypatch.setattr(payments.httpx, "AsyncClient", CapturingPaystackClient)

    response = await payments.initialize_payment(
        PaymentInitializeRequest(
            order_id=graph["order"].id,
            email=customer_user["user"].email,
            payment_gateway=provider,
            currency=graph["order"].currency,
            callback_url=None,
        ),
        current_user=customer_user["user"],
        db=db_session,
    )

    successor = observed["successor"]
    await db_session.refresh(predecessor)
    assert response.status is True
    assert predecessor.provider == predecessor_provider
    assert predecessor.provider_reference == predecessor_reference
    assert successor.provider == provider
    assert successor.provider_reference != predecessor_reference
    assert successor.idempotency_key != predecessor.idempotency_key
    assert successor.supersedes_attempt_id == predecessor.id
    assert observed["memberships"] == memberships
    assert observed["payload"]["amount"] == int(successor.amount * 100)

    if provider == "stripe":
        retry = await payments.initialize_payment(
            PaymentInitializeRequest(
                order_id=graph["order"].id,
                email=customer_user["user"].email,
                payment_gateway=provider,
                currency=graph["order"].currency,
                callback_url=None,
            ),
            current_user=customer_user["user"],
            db=db_session,
        )
        assert retry.payment_intent_id == response.payment_intent_id
        assert observed["provider_calls"] == 2
    else:
        with pytest.raises(HTTPException) as caught:
            await payments.initialize_payment(
                PaymentInitializeRequest(
                    order_id=graph["order"].id,
                    email=customer_user["user"].email,
                    payment_gateway=provider,
                    currency=graph["order"].currency,
                    callback_url=None,
                ),
                current_user=customer_user["user"],
                db=db_session,
            )
        assert caught.value.status_code == 503
        assert observed["provider_calls"] == 1

    attempts = list(
        await db_session.scalars(
            select(PaymentAttempt).where(PaymentAttempt.order_id == graph["order"].id)
        )
    )
    assert len(attempts) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
async def test_concurrent_terminal_retry_converges_to_one_successor(
    db_session, vendor_user, customer_user, monkeypatch, provider
) -> None:
    graph, predecessor = await _terminal_route_attempt(
        db_session,
        vendor_user,
        customer_user,
        monkeypatch,
        provider,
        "expired",
    )
    predecessor_memberships = set(
        await db_session.scalars(
            select(PaymentAttemptReservation.reservation_id).where(
                PaymentAttemptReservation.attempt_id == predecessor.id
            )
        )
    )
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def initialize():
        async with maker() as session:
            order = await session.get(Order, graph["order"].id)
            try:
                truth = await payment_initialization_truth(
                    session,
                    order=order,
                    provider=provider,
                    capabilities=DomesticShippingCapabilities(True, True, False),
                )
                await session.commit()
                return truth
            except PaymentBridgeError as exc:
                await session.rollback()
                return exc

    results = await asyncio.gather(initialize(), initialize())
    successors = list(
        await db_session.scalars(
            select(PaymentAttempt).where(
                PaymentAttempt.supersedes_attempt_id == predecessor.id
            )
        )
    )
    assert len(successors) == 1
    successor_memberships = set(
        await db_session.scalars(
            select(PaymentAttemptReservation.reservation_id).where(
                PaymentAttemptReservation.attempt_id == successors[0].id
            )
        )
    )
    assert successor_memberships == predecessor_memberships
    assert all(isinstance(result, PaymentInitializationTruth) for result in results)
    assert {result.attempt_id for result in results} == {successors[0].id}
    if provider == "paystack":
        assert sum(result.provider_call_required for result in results) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
@pytest.mark.parametrize("transport", ["callback", "webhook"])
@pytest.mark.parametrize(
    "starting_state",
    ["fresh_call_started", "call_started", "abandoned_unknown"],
)
async def test_authenticated_failure_reconciles_expired_attempt_atomically(
    db_session,
    vendor_user,
    customer_user,
    monkeypatch,
    provider,
    transport,
    starting_state,
) -> None:
    graph, attempt, payment = await _call_started_route_payment(
        db_session, vendor_user, customer_user, provider
    )
    await _prepare_failure_reconciliation(db_session, attempt, starting_state)

    first = await _invoke_authenticated_failure(
        provider,
        transport,
        db_session,
        monkeypatch,
        attempt=attempt,
        payment=payment,
    )
    second = await _invoke_authenticated_failure(
        provider,
        transport,
        db_session,
        monkeypatch,
        attempt=attempt,
        payment=payment,
    )

    await db_session.refresh(attempt)
    await db_session.refresh(payment)
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
    if transport == "callback":
        assert first.status is (provider == "paystack")
        assert second.status is (provider == "paystack")
    else:
        assert first == {"status": "success"}
        assert second == {"status": "success"}
    assert attempt.state == "failed"
    definitive_evidence = [
        item for item in evidence if item.evidence_type == "payment_failed"
    ]
    assert attempt.terminal_evidence_id == definitive_evidence[0].id
    assert payment.status == TransactionStatus.FAILED
    assert graph["order"].payment_status == PaymentStatus.FAILED
    assert len(definitive_evidence) == 1
    assert definitive_evidence[0].source == "payment.failed"
    assert definitive_evidence[0].provider == provider
    assert definitive_evidence[0].provider_reference == attempt.provider_reference


@pytest.mark.asyncio
async def test_mismatched_authenticated_failure_cannot_mutate_bridge_truth(
    db_session, vendor_user, customer_user, monkeypatch
) -> None:
    graph, attempt, payment = await _call_started_route_payment(
        db_session, vendor_user, customer_user, "stripe"
    )
    mismatched = SimpleNamespace(
        id=payment.transaction_id,
        status="canceled",
        amount=int(attempt.amount * 100),
        currency=attempt.currency.lower(),
        metadata={"shopsoma_payment_reference": "mismatched-reference"},
        last_payment_error=SimpleNamespace(message="Card declined"),
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda value: mismatched
    )

    with pytest.raises(HTTPException) as error:
        await payments._verify_stripe_payment(
            PaymentVerifyRequest(
                payment_gateway="stripe", payment_intent_id=payment.transaction_id
            ),
            db_session,
        )

    assert error.value.status_code == 409
    await db_session.refresh(attempt)
    await db_session.refresh(payment)
    await db_session.refresh(graph["order"])
    assert attempt.state == "call_started"
    assert payment.status == TransactionStatus.PENDING
    assert graph["order"].payment_status == PaymentStatus.PENDING
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttemptEvidence.id)).where(
                PaymentAttemptEvidence.attempt_id == attempt.id
            )
        )
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
@pytest.mark.parametrize(
    "sequence",
    [
        ("callback", "webhook", "callback", "webhook"),
        ("webhook", "callback", "webhook", "callback"),
    ],
    ids=["callback-first", "webhook-first"],
)
async def test_missing_mapping_serial_callback_webhook_orders_converge_once(
    db_session,
    vendor_user,
    customer_user,
    monkeypatch,
    provider,
    sequence,
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
    effects = {"receipt": 0, "claim": 0, "initialization": 0}

    async def receipt(**kwargs):
        effects["receipt"] += 1

    async def claim(customer):
        effects["claim"] += 1

    def unexpected_stripe_initialization(**kwargs):
        effects["initialization"] += 1
        raise AssertionError("recovery must not initialize another provider payment")

    monkeypatch.setattr(payments.email_service, "send_payment_receipt_email", receipt)
    monkeypatch.setattr(payments, "send_account_claim_email_if_guest", claim)
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "create", unexpected_stripe_initialization
    )

    responses = []
    for transport in sequence:
        responses.append(
            await _invoke_authenticated_route(
                provider,
                transport,
                db_session,
                monkeypatch,
                reference=attempt.provider_reference,
                amount=attempt.amount,
                currency=attempt.currency,
            )
        )

    canonical_payments = (
        (
            await db_session.execute(
                select(Payment).where(Payment.order_id == graph["order"].id)
            )
        )
        .scalars()
        .all()
    )
    evidence_count = await db_session.scalar(
        select(func.count(PaymentAttemptEvidence.id)).where(
            PaymentAttemptEvidence.attempt_id == attempt.id
        )
    )
    await db_session.refresh(graph["order"])
    await db_session.refresh(attempt)

    assert all(
        (
            response.status is True
            if transport == "callback"
            else response == {"status": "success"}
        )
        for transport, response in zip(sequence, responses)
    )
    assert len(canonical_payments) == 1
    assert evidence_count == 1
    assert attempt.customer_id == customer_user["user"].id
    assert attempt.state == "verified"
    assert graph["order"].payment_status == PaymentStatus.PAID
    assert graph["order"].fulfillment_status == FulfillmentStatus.PREPARING_FOR_PICKUP
    assert effects["claim"] == 1
    assert effects["receipt"] == (1 if sequence[0] == "callback" else 0)
    assert effects["initialization"] == 0


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


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["stripe", "paystack"])
@pytest.mark.parametrize("transport", ["callback", "webhook"])
async def test_authenticated_success_after_claim_expiry_reconciles_legally_once(
    db_session, vendor_user, customer_user, monkeypatch, provider, transport
) -> None:
    graph, attempt, payment = await _call_started_route_payment(
        db_session, vendor_user, customer_user, provider
    )
    await _prepare_failure_reconciliation(db_session, attempt, "call_started")
    effects = {"receipt": 0, "claim": 0}

    async def receipt(**kwargs):
        effects["receipt"] += 1

    async def claim(customer):
        effects["claim"] += 1

    monkeypatch.setattr(payments.email_service, "send_payment_receipt_email", receipt)
    monkeypatch.setattr(payments, "send_account_claim_email_if_guest", claim)
    for _ in range(2):
        await _invoke_authenticated_route(
            provider,
            transport,
            db_session,
            monkeypatch,
            reference=attempt.provider_reference,
            amount=attempt.amount,
            currency=attempt.currency,
        )

    await db_session.refresh(attempt)
    canonical_transaction_id = (
        f"pi_{attempt.provider_reference}"
        if provider == "stripe"
        else attempt.provider_reference
    )
    payment = await db_session.scalar(
        select(Payment).where(Payment.transaction_id == canonical_transaction_id)
    )
    await db_session.refresh(graph["order"])
    evidence = list(
        await db_session.scalars(
            select(PaymentAttemptEvidence).where(
                PaymentAttemptEvidence.attempt_id == attempt.id
            )
        )
    )
    assert attempt.state == "verified"
    assert payment.status == TransactionStatus.COMPLETED
    assert graph["order"].payment_status == PaymentStatus.PAID
    assert [item.evidence_type for item in evidence] == [
        "outcome_unknown",
        "payment_verified",
    ]
    assert attempt.terminal_evidence_id == evidence[-1].id
    assert effects["claim"] == 1
    assert effects["receipt"] <= 1


class _PaystackInitializationRecoveryClient:
    post_calls = 0
    get_calls = 0
    post_failure = "non_200"
    verify_status = "failed"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, *args, **kwargs):
        type(self).post_calls += 1
        if type(self).post_failure == "network":
            raise httpx.ConnectError("synthetic initialization failure")
        return SimpleNamespace(
            status_code=502,
            text="gateway unavailable",
            json=lambda: {"status": False, "message": "gateway unavailable"},
        )

    async def get(self, url, *args, **kwargs):
        type(self).get_calls += 1
        if type(self).verify_status == "unreachable":
            raise httpx.ConnectError("synthetic reconciliation failure")
        reference = url.rsplit("/", 1)[-1]
        data = {
            "id": 41,
            "status": type(self).verify_status,
            "reference": reference,
            "amount": 0,
            "currency": "NGN",
            "gateway_response": "Declined",
        }
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"status": True, "data": data},
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("post_failure", ["non_200", "network"])
async def test_paystack_initialization_error_reconciles_definitive_rejection(
    db_session, vendor_user, customer_user, monkeypatch, post_failure
) -> None:
    graph, _, _, _, _ = await _unattempted_route_subject(
        db_session, vendor_user, customer_user
    )
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda settings: DomesticShippingCapabilities(True, True, False),
    )
    monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "sk_test_synthetic")
    client = _PaystackInitializationRecoveryClient
    client.post_calls = client.get_calls = 0
    client.post_failure = post_failure
    client.verify_status = "failed"
    monkeypatch.setattr(payments.httpx, "AsyncClient", client)
    request = PaymentInitializeRequest(
        order_id=graph["order"].id,
        email=customer_user["user"].email,
        payment_gateway="paystack",
        currency=graph["order"].currency,
        callback_url=None,
    )

    with pytest.raises(HTTPException) as caught:
        await payments.initialize_payment(
            request, current_user=customer_user["user"], db=db_session
        )

    attempt = await db_session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.order_id == graph["order"].id)
    )
    payment = await db_session.scalar(
        select(Payment).where(Payment.order_id == graph["order"].id)
    )
    assert caught.value.status_code == 400
    assert client.post_calls == 1
    assert client.get_calls == 1
    assert attempt.state == "failed"
    assert payment.transaction_id == attempt.provider_reference
    assert payment.status == TransactionStatus.FAILED
    successor = await payment_initialization_truth(
        db_session,
        order=graph["order"],
        provider="paystack",
        capabilities=DomesticShippingCapabilities(True, True, False),
    )
    assert successor.attempt_id != attempt.id


@pytest.mark.asyncio
async def test_paystack_ambiguous_initialization_retries_lookup_without_duplicate_post(
    db_session, vendor_user, customer_user, monkeypatch
) -> None:
    graph, _, _, _, _ = await _unattempted_route_subject(
        db_session, vendor_user, customer_user
    )
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda settings: DomesticShippingCapabilities(True, True, False),
    )
    monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "sk_test_synthetic")
    client = _PaystackInitializationRecoveryClient
    client.post_calls = client.get_calls = 0
    client.post_failure = "network"
    client.verify_status = "unreachable"
    monkeypatch.setattr(payments.httpx, "AsyncClient", client)
    request = PaymentInitializeRequest(
        order_id=graph["order"].id,
        email=customer_user["user"].email,
        payment_gateway="paystack",
        currency=graph["order"].currency,
        callback_url=None,
    )

    for expired in (False, True):
        if expired:
            attempt = await db_session.scalar(
                select(PaymentAttempt).where(
                    PaymentAttempt.order_id == graph["order"].id
                )
            )
            await _prepare_failure_reconciliation(db_session, attempt, "call_started")
        with pytest.raises(HTTPException) as caught:
            await payments.initialize_payment(
                request, current_user=customer_user["user"], db=db_session
            )
        assert caught.value.status_code == 503

    attempt = await db_session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.order_id == graph["order"].id)
    )
    assert client.post_calls == 1
    assert client.get_calls == 2
    assert attempt.state in {"call_started", "abandoned_unknown"}
    assert (
        await db_session.scalar(
            select(func.count(Payment.id)).where(Payment.order_id == graph["order"].id)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_stripe_canceled_callback_recovers_missing_mapping_before_failure(
    db_session, vendor_user, customer_user, monkeypatch
) -> None:
    graph, attempt = await _pending_route_attempt(
        db_session, vendor_user, customer_user, "stripe"
    )
    await payment_initialization_truth(
        db_session,
        order=graph["order"],
        provider="stripe",
        capabilities=DomesticShippingCapabilities(True, True, False),
    )
    await db_session.commit()
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE payment_attempts "
            "SET claim_expires_at=clock_timestamp() + interval '5 minutes' "
            "WHERE id=:attempt_id"
        ),
        {"attempt_id": attempt.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))
    await db_session.commit()
    await db_session.refresh(attempt)
    transaction_id = f"pi_{attempt.id.hex}"
    canceled = SimpleNamespace(
        id=transaction_id,
        status="canceled",
        amount=int(attempt.amount * 100),
        currency=attempt.currency.lower(),
        metadata={"shopsoma_payment_reference": attempt.provider_reference},
        last_payment_error=SimpleNamespace(message="Canceled"),
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda value: canceled
    )

    for _ in range(2):
        response = await payments._verify_stripe_payment(
            PaymentVerifyRequest(
                payment_gateway="stripe",
                payment_intent_id=transaction_id,
                reference=None,
            ),
            db_session,
        )
        assert response.status is False

    payment = await db_session.scalar(
        select(Payment).where(Payment.transaction_id == transaction_id)
    )
    await db_session.refresh(attempt)
    assert payment.order_id == graph["order"].id
    assert payment.status == TransactionStatus.FAILED
    assert attempt.state == "failed"
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttemptEvidence.id)).where(
                PaymentAttemptEvidence.attempt_id == attempt.id,
                PaymentAttemptEvidence.evidence_type == "payment_failed",
            )
        )
        == 1
    )
