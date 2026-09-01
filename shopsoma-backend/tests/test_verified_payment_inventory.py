"""Milestone 4 verified-payment inventory contracts through production routes."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.api.v1 import payments
from app.models.checkout_outbox import CheckoutOutboxEvent
from app.models.order import Order, PaymentStatus
from app.models.payment import Payment
from app.models.stock_payment_persistence import (
    PaymentAttempt,
    PaymentAttemptEvidence,
    StockReservation,
)
from tests.test_checkout_payment_bridge_prerequisites import create_enforced_checkout


async def initialize_stripe(
    client,
    db_session,
    customer_user,
    monkeypatch,
    order,
    *,
    transaction_id="pi_m4_paid",
):
    order_id = order.id
    customer_email = customer_user["user"].email
    customer_user["user"].stripe_customer_id = "cus_m4_existing"
    await db_session.commit()
    monkeypatch.setattr(
        payments.stripe.PaymentIntent,
        "create",
        lambda **_kwargs: SimpleNamespace(
            id=transaction_id, client_secret=f"secret_{transaction_id}"
        ),
    )
    initialized = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_email,
            "payment_gateway": "stripe",
            "currency": "NGN",
        },
    )
    assert initialized.status_code == 200, initialized.text
    db_session.expire_all()
    attempt = await db_session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.order_id == order_id)
    )
    return SimpleNamespace(
        id=attempt.id,
        order_id=attempt.order_id,
        provider_transaction_id=transaction_id,
        provider_reference=attempt.provider_reference,
        amount=attempt.amount,
        currency=attempt.currency,
    )


async def _successful_side_effect(*_args, **_kwargs):
    return True


async def verify_stripe(client, monkeypatch, attempt):
    intent = SimpleNamespace(
        id=attempt.provider_transaction_id,
        status="succeeded",
        amount=int(Decimal(attempt.amount) * 100),
        amount_received=int(Decimal(attempt.amount) * 100),
        currency=attempt.currency.lower(),
        metadata={"shopsoma_payment_reference": attempt.provider_reference},
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda _value: intent
    )
    monkeypatch.setattr(
        payments.email_service,
        "send_payment_receipt_email",
        _successful_side_effect,
    )
    monkeypatch.setattr(
        payments, "send_account_claim_email_if_guest", _successful_side_effect
    )
    return await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": attempt.provider_transaction_id,
        },
    )


@pytest.mark.asyncio
async def test_duplicate_verified_callback_consumes_stock_and_writes_one_outbox(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, product = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    initial_stock = product.total_stock
    attempt = await initialize_stripe(
        client, db_session, customer_user, monkeypatch, order
    )

    first = await verify_stripe(client, monkeypatch, attempt)
    second = await verify_stripe(client, monkeypatch, attempt)
    assert first.status_code == second.status_code == 200

    db_session.expire_all()
    persisted_order = await db_session.get(Order, order_id)
    await db_session.refresh(product)
    reservation = await db_session.scalar(
        select(StockReservation).where(StockReservation.order_id == order_id)
    )
    assert persisted_order.payment_status == PaymentStatus.PAID
    assert reservation.state == "consumed"
    assert product.total_stock == initial_stock - reservation.quantity
    persisted_payments = list(
        await db_session.scalars(select(Payment).where(Payment.order_id == order_id))
    )
    assert len(persisted_payments) == 1, [
        payment.transaction_id for payment in persisted_payments
    ]
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(PaymentAttemptEvidence)
            .where(PaymentAttemptEvidence.attempt_id == attempt.id)
        )
        == 1
    )
    events = (
        await db_session.scalars(
            select(CheckoutOutboxEvent).where(CheckoutOutboxEvent.order_id == order_id)
        )
    ).all()
    assert [event.event_type for event in events] == ["payment_verified_start_order"]
    assert events[0].payload == {
        "version": 1,
        "order_id": str(order_id),
        "workflow_cohort": "domestic_checkout_v1",
    }
