"""Milestone 4 authenticated late-payment convergence contracts."""

from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.api.v1 import payments
from app.models.checkout_outbox import CheckoutOutboxEvent
from app.models.order import Order, PaymentStatus, FulfillmentStatus
from app.models.stock_payment_persistence import StockReservation
from tests.test_checkout_payment_bridge_prerequisites import create_enforced_checkout
from tests.test_verified_payment_inventory import initialize_stripe


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
