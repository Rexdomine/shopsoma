"""Milestone 4 authenticated late-payment convergence contracts."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.api.v1 import payments
from app.models.checkout_outbox import CheckoutOutboxEvent
from app.models.order import Order, PaymentStatus, FulfillmentStatus
from app.models.payment import Payment, TransactionStatus
from app.models.stock_payment_persistence import (
    PaymentAttempt,
    PaymentAttemptEvidence,
    StockReservation,
)
from tests.test_checkout_payment_bridge_prerequisites import create_enforced_checkout
from tests.test_verified_payment_inventory import initialize_stripe


# Canonical payment identity table (authenticated evidence is provider-returned
# callback data or a signature-verified webhook payload):
#
# Path                         Provider object key      Attempt correlation
# Stripe callback             intent.id (`pi_...`)     metadata reference
# Stripe webhook              payment_intent.id        metadata reference
# Paystack callback/webhook    data.reference           data.reference/metadata
# Missing-map recovery         authenticated key above  exact fenced attempt
# Claim-expiry/completed replay same as originating path exact fenced attempt
# Late predecessor success     predecessor object key   predecessor metadata ref
#
# Payment.transaction_id is always the provider object mapping key. Provider and
# payment_method use canonical lower-case names. Attempt/order bind amount,
# currency, and order; signed/retrieved provider evidence authoritatively binds
# the provider object and internal attempt reference without equating them.


@pytest.fixture(autouse=True)
def _disable_receipt_email(monkeypatch):
    async def successful_receipt(**_kwargs):
        return True

    monkeypatch.setattr(
        payments.email_service, "send_payment_receipt_email", successful_receipt
    )


class _AuthenticatedStripeWebhookRequest:
    async def body(self):
        return b'{"authenticated":true}'


@pytest.mark.asyncio
async def test_stripe_webhook_preserves_distinct_provider_object_and_attempt_reference(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, _ = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    attempt = await initialize_stripe(
        client,
        db_session,
        customer_user,
        monkeypatch,
        order,
        transaction_id="pi_distinct_webhook_object",
    )
    assert attempt.provider_transaction_id != attempt.provider_reference
    intent = SimpleNamespace(
        id=attempt.provider_transaction_id,
        amount_received=int(Decimal(attempt.amount) * 100),
        currency=attempt.currency.lower(),
        metadata={"shopsoma_payment_reference": attempt.provider_reference},
    )
    event = SimpleNamespace(
        id="evt_distinct_webhook_object",
        type="payment_intent.succeeded",
        data=SimpleNamespace(object=intent),
    )
    monkeypatch.setattr(payments.settings, "STRIPE_WEBHOOK_SECRET", "test-secret")
    monkeypatch.setattr(
        payments.stripe.Webhook, "construct_event", lambda **_kwargs: event
    )

    response = await payments.stripe_webhook(
        _AuthenticatedStripeWebhookRequest(), "test-signature", db_session
    )

    assert response == {"status": "success"}
    persisted_payment = await db_session.scalar(
        select(Payment).where(Payment.transaction_id == attempt.provider_transaction_id)
    )
    persisted_attempt = await db_session.get(PaymentAttempt, attempt.id)
    assert persisted_payment.status == TransactionStatus.COMPLETED
    assert persisted_attempt.state == "verified"


@pytest.mark.asyncio
async def test_late_success_after_definitive_failure_is_paid_without_oversell(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, product = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    initial_stock = product.total_stock
    attempt = await initialize_stripe(
        client,
        db_session,
        customer_user,
        monkeypatch,
        order,
        transaction_id="pi_m4_late",
    )
    canceled = SimpleNamespace(
        id=attempt.provider_transaction_id,
        status="canceled",
        amount=int(Decimal(attempt.amount) * 100),
        currency=attempt.currency.lower(),
        metadata={"shopsoma_payment_reference": attempt.provider_reference},
        last_payment_error=SimpleNamespace(message="Canceled"),
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda _value: canceled
    )
    failed = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": attempt.provider_transaction_id,
        },
    )
    assert failed.status_code == 200, failed.text
    db_session.expire_all()
    reservation = await db_session.scalar(
        select(StockReservation).where(StockReservation.order_id == order_id)
    )
    assert reservation.state == "released"

    succeeded = SimpleNamespace(
        id=attempt.provider_transaction_id,
        status="succeeded",
        amount=int(Decimal(attempt.amount) * 100),
        amount_received=int(Decimal(attempt.amount) * 100),
        currency=attempt.currency.lower(),
        metadata={"shopsoma_payment_reference": attempt.provider_reference},
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda _value: succeeded
    )
    late = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": attempt.provider_transaction_id,
        },
    )
    assert late.status_code == 200, late.text
    db_session.expire_all()
    persisted_order = await db_session.get(Order, order_id)
    await db_session.refresh(product)
    events = (
        await db_session.scalars(
            select(CheckoutOutboxEvent).where(CheckoutOutboxEvent.order_id == order_id)
        )
    ).all()
    assert persisted_order.payment_status == PaymentStatus.PAID
    assert persisted_order.fulfillment_status == FulfillmentStatus.ORDER_RECEIVED
    assert product.total_stock >= 0
    assert product.total_stock in {initial_stock, initial_stock - 1}
    assert [event.event_type for event in events] == [
        "payment_failed_release",
        "late_payment_exception",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("mapping_present", [True, False])
async def test_late_predecessor_success_resolves_exact_attempt_without_mutating_successor(
    client,
    db_session,
    vendor_user,
    customer_user,
    monkeypatch,
    mapping_present,
):
    order, product = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    initial_stock = product.total_stock
    customer_email = customer_user["user"].email
    predecessor = await initialize_stripe(
        client,
        db_session,
        customer_user,
        monkeypatch,
        order,
        transaction_id="pi_late_predecessor",
    )
    failed_intent = SimpleNamespace(
        id=predecessor.provider_transaction_id,
        status="canceled",
        amount=int(Decimal(predecessor.amount) * 100),
        currency=predecessor.currency.lower(),
        metadata={"shopsoma_payment_reference": predecessor.provider_reference},
        last_payment_error=SimpleNamespace(message="Canceled"),
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda _value: failed_intent
    )
    failed = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": predecessor.provider_transaction_id,
        },
    )
    assert failed.status_code == 200, failed.text

    provider_calls = 0

    def create_successor(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return SimpleNamespace(
            id="pi_late_successor", client_secret="secret_late_successor"
        )

    monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_successor)
    initialized = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order.id),
            "email": customer_email,
            "payment_gateway": "stripe",
            "currency": "NGN",
        },
    )
    assert initialized.status_code == 200, initialized.text
    successor = await db_session.scalar(
        select(PaymentAttempt).where(
            PaymentAttempt.supersedes_attempt_id == predecessor.id
        )
    )
    assert successor is not None
    successor_id = successor.id
    predecessor_id = predecessor.id
    successor_identity = (
        successor.state,
        successor.provider,
        successor.provider_reference,
        successor.lease_token,
        successor.row_version,
    )
    if not mapping_present:
        payment = await db_session.scalar(
            select(Payment).where(
                Payment.transaction_id == predecessor.provider_transaction_id
            )
        )
        await db_session.delete(payment)
        await db_session.commit()

    succeeded_intent = SimpleNamespace(
        id=predecessor.provider_transaction_id,
        status="succeeded",
        amount=int(Decimal(predecessor.amount) * 100),
        amount_received=int(Decimal(predecessor.amount) * 100),
        currency=predecessor.currency.lower(),
        metadata={"shopsoma_payment_reference": predecessor.provider_reference},
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda _value: succeeded_intent
    )
    first = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": predecessor.provider_transaction_id,
        },
    )
    replay = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": predecessor.provider_transaction_id,
        },
    )

    assert first.status_code == replay.status_code == 200, first.text
    db_session.expire_all()
    persisted_order = await db_session.get(Order, order_id)
    persisted_successor = await db_session.get(PaymentAttempt, successor_id)
    payments_for_order = list(
        await db_session.scalars(select(Payment).where(Payment.order_id == order_id))
    )
    events = list(
        await db_session.scalars(
            select(CheckoutOutboxEvent).where(CheckoutOutboxEvent.order_id == order_id)
        )
    )
    assert provider_calls == 1
    assert persisted_order.payment_status == PaymentStatus.PAID
    assert persisted_successor.state == successor_identity[0]
    assert (
        persisted_successor.provider,
        persisted_successor.provider_reference,
        persisted_successor.lease_token,
        persisted_successor.row_version,
    ) == successor_identity[1:]
    assert len(payments_for_order) == 2
    assert (
        sum(row.status == TransactionStatus.COMPLETED for row in payments_for_order)
        == 1
    )
    assert [event.event_type for event in events].count("late_payment_exception") == 1
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttemptEvidence.id)).where(
                PaymentAttemptEvidence.attempt_id == predecessor_id,
                PaymentAttemptEvidence.evidence_type == "payment_verified",
            )
        )
        == 0
    )
    await db_session.refresh(product)
    assert product.total_stock == initial_stock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch",
    ["reference", "amount", "currency", "method", "provider", "order"],
)
async def test_late_predecessor_success_rejects_corrupt_existing_mapping_without_mutation(
    client,
    db_session,
    vendor_user,
    customer_user,
    monkeypatch,
    mismatch,
):
    order, _ = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    customer_email = customer_user["user"].email
    predecessor = await initialize_stripe(
        client,
        db_session,
        customer_user,
        monkeypatch,
        order,
        transaction_id=f"pi_mapping_{mismatch}",
    )
    failed_intent = SimpleNamespace(
        id=predecessor.provider_transaction_id,
        status="canceled",
        amount=int(Decimal(predecessor.amount) * 100),
        currency=predecessor.currency.lower(),
        metadata={"shopsoma_payment_reference": predecessor.provider_reference},
        last_payment_error=SimpleNamespace(message="Canceled"),
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda _value: failed_intent
    )
    failed = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": predecessor.provider_transaction_id,
        },
    )
    assert failed.status_code == 200, failed.text
    monkeypatch.setattr(
        payments.stripe.PaymentIntent,
        "create",
        lambda **_kwargs: SimpleNamespace(
            id=f"pi_successor_{mismatch}", client_secret="successor_secret"
        ),
    )
    initialized = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order.id),
            "email": customer_email,
            "payment_gateway": "stripe",
            "currency": "NGN",
        },
    )
    assert initialized.status_code == 200, initialized.text
    successor = await db_session.scalar(
        select(PaymentAttempt).where(
            PaymentAttempt.supersedes_attempt_id == predecessor.id
        )
    )
    mapping = await db_session.scalar(
        select(Payment).where(
            Payment.transaction_id == predecessor.provider_transaction_id
        )
    )
    successor_id = successor.id
    mapping_id = mapping.id
    if mismatch == "reference":
        mapping.transaction_id = f"corrupt_{mapping.transaction_id}"
    elif mismatch == "amount":
        mapping.amount += Decimal("1.00")
    elif mismatch == "currency":
        mapping.currency = "USD"
    elif mismatch == "method":
        mapping.payment_method = "paystack"
    elif mismatch == "provider":
        mapping.payment_gateway = "paystack"
    else:
        await db_session.refresh(vendor_user["vendor"])
        await db_session.refresh(customer_user["user"])
        other_order, _ = await create_enforced_checkout(
            client, db_session, vendor_user, customer_user, monkeypatch
        )
        mapping.order_id = other_order.id
    await db_session.commit()
    db_session.expire_all()
    order_before = await db_session.get(Order, order_id)
    successor_before = await db_session.get(PaymentAttempt, successor_id)
    mapping_before = await db_session.get(Payment, mapping_id)
    event_count_before = await db_session.scalar(
        select(func.count(CheckoutOutboxEvent.id)).where(
            CheckoutOutboxEvent.order_id == order_id
        )
    )
    snapshots = (
        (order_before.payment_status, order_before.fulfillment_status),
        (
            successor_before.state,
            successor_before.provider_reference,
            successor_before.lease_token,
            successor_before.row_version,
        ),
        (
            mapping_before.order_id,
            mapping_before.transaction_id,
            mapping_before.payment_gateway,
            mapping_before.payment_method,
            mapping_before.amount,
            mapping_before.currency,
            mapping_before.status,
        ),
    )
    succeeded_intent = SimpleNamespace(
        id=predecessor.provider_transaction_id,
        status="succeeded",
        amount=int(Decimal(predecessor.amount) * 100),
        amount_received=int(Decimal(predecessor.amount) * 100),
        currency=predecessor.currency.lower(),
        metadata={"shopsoma_payment_reference": predecessor.provider_reference},
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda _value: succeeded_intent
    )

    response = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": predecessor.provider_transaction_id,
        },
    )

    assert response.status_code == 409, response.text
    db_session.expire_all()
    persisted_order = await db_session.get(Order, order_id)
    persisted_successor = await db_session.get(PaymentAttempt, successor_id)
    persisted_mapping = await db_session.get(Payment, mapping_id)
    assert (
        persisted_order.payment_status,
        persisted_order.fulfillment_status,
    ) == snapshots[0]
    assert (
        persisted_successor.state,
        persisted_successor.provider_reference,
        persisted_successor.lease_token,
        persisted_successor.row_version,
    ) == snapshots[1]
    assert (
        persisted_mapping.order_id,
        persisted_mapping.transaction_id,
        persisted_mapping.payment_gateway,
        persisted_mapping.payment_method,
        persisted_mapping.amount,
        persisted_mapping.currency,
        persisted_mapping.status,
    ) == snapshots[2]
    assert (
        await db_session.scalar(
            select(func.count(CheckoutOutboxEvent.id)).where(
                CheckoutOutboxEvent.order_id == order_id
            )
        )
        == event_count_before
    )


@pytest.mark.asyncio
async def test_failed_predecessor_redelivery_replays_failed_terminal_state_after_successor_init(
    client,
    db_session,
    vendor_user,
    customer_user,
    monkeypatch,
):
    order, _ = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    customer_email = customer_user["user"].email
    predecessor = await initialize_stripe(
        client,
        db_session,
        customer_user,
        monkeypatch,
        order,
        transaction_id="pi_failed_predecessor_redelivery",
    )
    failed_intent = SimpleNamespace(
        id=predecessor.provider_transaction_id,
        status="canceled",
        amount=int(Decimal(predecessor.amount) * 100),
        currency=predecessor.currency.lower(),
        metadata={"shopsoma_payment_reference": predecessor.provider_reference},
        last_payment_error=SimpleNamespace(message="Canceled"),
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda _value: failed_intent
    )
    first_failed = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": predecessor.provider_transaction_id,
        },
    )
    assert first_failed.status_code == 200, first_failed.text

    monkeypatch.setattr(
        payments.stripe.PaymentIntent,
        "create",
        lambda **_kwargs: SimpleNamespace(
            id="pi_successor_after_failed_redelivery", client_secret="successor_secret"
        ),
    )
    initialized = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order.id),
            "email": customer_email,
            "payment_gateway": "stripe",
            "currency": "NGN",
        },
    )
    assert initialized.status_code == 200, initialized.text
    successor = await db_session.scalar(
        select(PaymentAttempt).where(
            PaymentAttempt.supersedes_attempt_id == predecessor.id
        )
    )
    assert successor is not None
    successor_id = successor.id
    successor_snapshot = (
        successor.state,
        successor.provider_reference,
        successor.lease_token,
        successor.row_version,
    )

    replay_failed = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": predecessor.provider_transaction_id,
        },
    )

    assert replay_failed.status_code == 200, replay_failed.text
    db_session.expire_all()
    persisted_successor = await db_session.get(PaymentAttempt, successor_id)
    persisted_predecessor_payment = await db_session.scalar(
        select(Payment).where(
            Payment.transaction_id == predecessor.provider_transaction_id
        )
    )
    assert (
        persisted_successor.state,
        persisted_successor.provider_reference,
        persisted_successor.lease_token,
        persisted_successor.row_version,
    ) == successor_snapshot
    assert persisted_predecessor_payment is not None
    assert persisted_predecessor_payment.status == TransactionStatus.FAILED
