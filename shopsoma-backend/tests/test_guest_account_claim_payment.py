"""Tests for guest account claim emails after successful payment."""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import payments
from app.models.order import FulfillmentStatus, Order, PaymentStatus
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.models.user import User, UserRole
from app.schemas.payment import PaymentVerifyRequest


class _FakePaystackResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": True,
            "data": {
                "status": "success",
                "reference": "SHP-CLAIM-1",
                "amount": 6000000,
                "currency": "NGN",
                "gateway_response": "Successful",
            },
        }


class _FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, *args, **kwargs):
        return _FakePaystackResponse()


async def _create_payment_order(
    db_session: AsyncSession,
    *,
    email: str,
    hashed_password: Optional[str],
    is_guest_created: bool,
    reference: str = "SHP-CLAIM-1",
) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name="Guest Buyer",
        hashed_password=hashed_password,
        role=UserRole.CUSTOMER,
        is_active=True,
        is_guest_created=is_guest_created,
    )
    db_session.add(user)
    await db_session.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number=reference,
        customer_id=user.id,
        currency="NGN",
        subtotal=Decimal("60000.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("60000.00"),
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.flush()

    db_session.add(
        Payment(
            id=uuid.uuid4(),
            order_id=order.id,
            transaction_id=reference,
            payment_gateway=PaymentGateway.PAYSTACK,
            payment_method="paystack",
            amount=Decimal("60000.00"),
            currency="NGN",
            status=TransactionStatus.PENDING,
        )
    )
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_successful_guest_paystack_verification_sends_claim_email_once(
    db_session: AsyncSession,
    monkeypatch,
):
    await _create_payment_order(
        db_session,
        email="newguest@example.com",
        hashed_password=None,
        is_guest_created=True,
    )

    claim_emails = []

    async def fake_send_account_claim_email(email, name, claim_link):
        claim_emails.append(email)
        return True

    async def fake_send_payment_receipt_email(**kwargs):
        return True

    monkeypatch.setattr(payments.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(
        payments.email_service,
        "send_account_claim_email",
        fake_send_account_claim_email,
    )
    monkeypatch.setattr(
        payments.email_service,
        "send_payment_receipt_email",
        fake_send_payment_receipt_email,
    )

    verify_data = PaymentVerifyRequest(
        reference="SHP-CLAIM-1",
        payment_gateway="paystack",
    )

    first_response = await payments._verify_paystack_payment(verify_data, db_session)
    second_response = await payments._verify_paystack_payment(verify_data, db_session)

    assert first_response.status is True
    assert second_response.status is True
    assert claim_emails == ["newguest@example.com"]


@pytest.mark.asyncio
async def test_successful_registered_user_payment_does_not_send_claim_email(
    db_session: AsyncSession,
    monkeypatch,
):
    await _create_payment_order(
        db_session,
        email="registered@example.com",
        hashed_password="hashed-password",
        is_guest_created=False,
    )

    claim_emails = []

    async def fake_send_account_claim_email(email, name, claim_link):
        claim_emails.append(email)
        return True

    async def fake_send_payment_receipt_email(**kwargs):
        return True

    monkeypatch.setattr(payments.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(
        payments.email_service,
        "send_account_claim_email",
        fake_send_account_claim_email,
    )
    monkeypatch.setattr(
        payments.email_service,
        "send_payment_receipt_email",
        fake_send_payment_receipt_email,
    )

    response = await payments._verify_paystack_payment(
        PaymentVerifyRequest(reference="SHP-CLAIM-1", payment_gateway="paystack"),
        db_session,
    )

    assert response.status is True
    assert claim_emails == []


@pytest.mark.asyncio
@pytest.mark.parametrize("gateway", ["stripe", "paystack"])
async def test_verify_notifications_run_once_only_after_durable_first_completion(
    db_session: AsyncSession, monkeypatch, gateway
):
    reference = "pi_claim_1" if gateway == "stripe" else "SHP-CLAIM-1"
    await _create_payment_order(
        db_session,
        email=f"{gateway}-guest@example.com",
        hashed_password=None,
        is_guest_created=True,
        reference=reference,
    )
    events = []
    original_commit = db_session.commit

    async def recording_commit():
        await original_commit()
        events.append("commit")

    async def fake_receipt(**kwargs):
        events.append("receipt")

    async def fake_claim(email, name, claim_link):
        events.append("claim")

    monkeypatch.setattr(db_session, "commit", recording_commit)
    monkeypatch.setattr(payments.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(
        payments.stripe.PaymentIntent,
        "retrieve",
        lambda payment_intent_id: SimpleNamespace(
            id=payment_intent_id,
            status="succeeded",
            amount=6000000,
            currency="ngn",
            metadata={},
        ),
    )
    monkeypatch.setattr(
        payments.email_service, "send_payment_receipt_email", fake_receipt
    )
    monkeypatch.setattr(payments.email_service, "send_account_claim_email", fake_claim)
    verify_data = PaymentVerifyRequest(
        reference=reference if gateway == "paystack" else None,
        payment_intent_id=reference if gateway == "stripe" else None,
        payment_gateway=gateway,
    )
    verify = (
        payments._verify_stripe_payment
        if gateway == "stripe"
        else payments._verify_paystack_payment
    )

    await verify(verify_data, db_session)
    await verify(verify_data, db_session)

    assert events == ["commit", "receipt", "claim", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("gateway", ["stripe", "paystack"])
async def test_verify_commit_failure_sends_no_notifications(
    db_session: AsyncSession, monkeypatch, gateway
):
    reference = "pi_commit_failure" if gateway == "stripe" else "SHP-CLAIM-1"
    await _create_payment_order(
        db_session,
        email=f"{gateway}-failure@example.com",
        hashed_password=None,
        is_guest_created=True,
        reference=reference,
    )
    notifications = []

    async def failing_commit():
        raise RuntimeError("forced commit failure")

    async def fake_receipt(**kwargs):
        notifications.append("receipt")

    async def fake_claim(email, name, claim_link):
        notifications.append("claim")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    monkeypatch.setattr(payments.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(
        payments.stripe.PaymentIntent,
        "retrieve",
        lambda payment_intent_id: SimpleNamespace(
            id=payment_intent_id,
            status="succeeded",
            amount=6000000,
            currency="ngn",
            metadata={},
        ),
    )
    monkeypatch.setattr(
        payments.email_service, "send_payment_receipt_email", fake_receipt
    )
    monkeypatch.setattr(payments.email_service, "send_account_claim_email", fake_claim)
    verify_data = PaymentVerifyRequest(
        reference=reference if gateway == "paystack" else None,
        payment_intent_id=reference if gateway == "stripe" else None,
        payment_gateway=gateway,
    )
    verify = (
        payments._verify_stripe_payment
        if gateway == "stripe"
        else payments._verify_paystack_payment
    )

    with pytest.raises(RuntimeError, match="forced commit failure"):
        await verify(verify_data, db_session)

    assert notifications == []
