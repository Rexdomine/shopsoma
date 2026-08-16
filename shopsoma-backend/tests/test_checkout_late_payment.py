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


@pytest.fixture(autouse=True)
def _disable_receipt_email(monkeypatch):
    async def successful_receipt(**_kwargs):
        return True

    monkeypatch.setattr(
        payments.email_service, "send_payment_receipt_email", successful_receipt
    )


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
