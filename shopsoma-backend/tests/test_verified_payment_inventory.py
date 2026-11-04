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


@pytest.mark.usefixtures("enabled_stripe")
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


@pytest.mark.asyncio
async def test_paystack_last_item_in_stock_cancel_and_retry_succeeds_without_duplicate_reference(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, product = await create_enforced_checkout(
        client,
        db_session,
        vendor_user,
        customer_user,
        monkeypatch,
        quantity=2,
    )
    order_id = order.id
    assert product.total_stock == 2
    monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setattr(
        payments.email_service,
        "send_payment_receipt_email",
        _successful_side_effect,
    )
    monkeypatch.setattr(
        payments, "send_account_claim_email_if_guest", _successful_side_effect
    )

    provider_state = {"verify_status": "abandoned", "initialized_refs": []}

    class _PaystackRetryClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **kwargs):
            ref = kwargs["json"]["reference"]
            if ref in provider_state["initialized_refs"]:
                return SimpleNamespace(
                    status_code=400,
                    text="Duplicate Transaction Reference",
                    json=lambda: {
                        "status": False,
                        "message": "Duplicate Transaction Reference",
                    },
                )
            provider_state["initialized_refs"].append(ref)
            return SimpleNamespace(
                status_code=200,
                text="",
                json=lambda: {
                    "status": True,
                    "data": {
                        "authorization_url": f"https://paystack.invalid/authorize/{ref}",
                        "access_code": f"access_{ref}",
                        "reference": ref,
                    },
                },
            )

        async def get(self, url, **_kwargs):
            ref = url.rsplit("/", 1)[-1]
            return SimpleNamespace(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {
                    "status": True,
                    "data": {
                        "id": 901,
                        "status": provider_state["verify_status"],
                        "reference": ref,
                        "amount": int(Decimal(order.total_amount) * 100),
                        "currency": order.currency,
                        "gateway_response": (
                            "The transaction was not completed"
                            if provider_state["verify_status"] == "abandoned"
                            else "Successful"
                        ),
                    },
                },
            )

    monkeypatch.setattr(payments.httpx, "AsyncClient", _PaystackRetryClient)

    first_init = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_user["user"].email,
            "payment_gateway": "paystack",
            "callback_url": "https://staging.shopsoma.com/payment/verify",
        },
    )
    assert first_init.status_code == 200, first_init.text
    first_ref = first_init.json()["reference"]

    # Customer cancels/abandons the first Paystack popup and clicks Retry
    second_init = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_user["user"].email,
            "payment_gateway": "paystack",
            "callback_url": "https://staging.shopsoma.com/payment/verify",
        },
    )
    assert second_init.status_code == 200, second_init.text
    second_ref = second_init.json()["reference"]
    assert second_ref != first_ref

    # Customer completes the retried Paystack payment
    provider_state["verify_status"] = "success"
    verified = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "paystack",
            "reference": second_ref,
        },
    )
    assert verified.status_code == 200, verified.text

    db_session.expire_all()
    persisted_order = await db_session.get(Order, order_id)
    await db_session.refresh(product)
    attempts = list(
        await db_session.scalars(
            select(PaymentAttempt)
            .where(PaymentAttempt.order_id == order_id)
            .order_by(PaymentAttempt.created_at.asc())
        )
    )
    reservations = list(
        await db_session.scalars(
            select(StockReservation)
            .where(StockReservation.order_id == order_id)
            .order_by(StockReservation.created_at.asc())
        )
    )
    assert persisted_order.payment_status == PaymentStatus.PAID
    assert product.total_stock == 0
    assert [attempt.state for attempt in attempts] == ["failed", "verified"]
    assert attempts[1].supersedes_attempt_id == attempts[0].id
    assert [res.state for res in reservations] == ["released", "consumed"]


@pytest.mark.asyncio
async def test_paystack_retry_reconciles_already_paid_attempt_instead_of_replaying_duplicate_reference(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, product = await create_enforced_checkout(
        client,
        db_session,
        vendor_user,
        customer_user,
        monkeypatch,
        quantity=2,
    )
    order_id = order.id
    monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", "sk_test_placeholder")
    monkeypatch.setattr(
        payments.email_service,
        "send_payment_receipt_email",
        _successful_side_effect,
    )
    monkeypatch.setattr(
        payments, "send_account_claim_email_if_guest", _successful_side_effect
    )

    class _PaystackPaidOnRetryClient:
        post_calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **kwargs):
            type(self).post_calls += 1
            ref = kwargs["json"]["reference"]
            return SimpleNamespace(
                status_code=200,
                text="",
                json=lambda: {
                    "status": True,
                    "data": {
                        "authorization_url": f"https://paystack.invalid/authorize/{ref}",
                        "access_code": f"access_{ref}",
                        "reference": ref,
                    },
                },
            )

        async def get(self, url, **_kwargs):
            ref = url.rsplit("/", 1)[-1]
            return SimpleNamespace(
                status_code=200,
                raise_for_status=lambda: None,
                json=lambda: {
                    "status": True,
                    "data": {
                        "id": 902,
                        "status": "success",
                        "reference": ref,
                        "amount": int(Decimal(order.total_amount) * 100),
                        "currency": order.currency,
                        "gateway_response": "Successful",
                    },
                },
            )

    monkeypatch.setattr(payments.httpx, "AsyncClient", _PaystackPaidOnRetryClient)

    first_init = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_user["user"].email,
            "payment_gateway": "paystack",
            "callback_url": "https://staging.shopsoma.com/payment/verify",
        },
    )
    assert first_init.status_code == 200, first_init.text

    # Customer completed payment on Paystack, callback/verify was missed, and customer clicks Retry
    retry_init = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_user["user"].email,
            "payment_gateway": "paystack",
            "callback_url": "https://staging.shopsoma.com/payment/verify",
        },
    )
    assert retry_init.status_code == 400
    assert retry_init.json()["detail"] == "Order has already been paid"
    assert _PaystackPaidOnRetryClient.post_calls == 1

    db_session.expire_all()
    persisted_order = await db_session.get(Order, order_id)
    await db_session.refresh(product)
    reservation = await db_session.scalar(
        select(StockReservation).where(StockReservation.order_id == order_id)
    )
    assert persisted_order.payment_status == PaymentStatus.PAID
    assert reservation.state == "consumed"
    assert product.total_stock == 0
