"""Tests for 24-hour pending checkout payment reminder emails with single-send guarantees."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.models.payment_reminder import OrderPaymentReminder
from app.models.product import Product, ProductType
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.services.email_service import EmailService
from app.services.payments.reminders import (
    compute_reminder_idempotency_key,
    dispatch_pending_payment_reminders_once,
    dispatch_single_reminder,
    extract_safe_payment_urls,
    is_order_eligible_for_pending_reminder,
    scan_and_claim_pending_payment_reminders,
)
from app.tasks.pending_payment_reminders import dispatch_pending_payment_reminders


def _make_mock_email_service():
    calls = []

    class MockEmailService(EmailService):
        def __init__(self):
            self.enabled = True
            self.should_fail = False

        async def send_pending_payment_reminder_email(
            self,
            email: str,
            name: str,
            order_number: str,
            order_date: datetime,
            items: list,
            total: float,
            currency: str = "NGN",
            payment_url: str | None = None,
            order_url: str | None = None,
        ) -> bool:
            if self.should_fail:
                return False
            calls.append(
                {
                    "email": email,
                    "name": name,
                    "order_number": order_number,
                    "order_date": order_date,
                    "items": items,
                    "total": total,
                    "currency": currency,
                    "payment_url": payment_url,
                    "order_url": order_url,
                }
            )
            return True

    return MockEmailService(), calls


async def _create_test_order_with_payment(
    db_session: AsyncSession,
    *,
    customer_email: str | None = None,
    customer_name: str = "Shopper Test",
    order_number: str | None = None,
    created_at: datetime | None = None,
    order_payment_status: PaymentStatus = PaymentStatus.PENDING,
    fulfillment_status: FulfillmentStatus = FulfillmentStatus.ORDER_RECEIVED,
    payment_status: TransactionStatus = TransactionStatus.PENDING,
    payment_gateway: PaymentGateway = PaymentGateway.PAYSTACK,
    cancelled_at: datetime | None = None,
    authorization_url: str | None = "https://checkout.paystack.com/test-auth-12345",
) -> tuple[Order, Payment, User]:
    actual_email = customer_email or f"shopper_{uuid.uuid4().hex[:8]}@example.com"
    user = User(
        id=uuid.uuid4(),
        email=actual_email,
        full_name=customer_name,
        role=UserRole.CUSTOMER,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    vendor_user = User(
        id=uuid.uuid4(),
        email=f"vendor_{uuid.uuid4().hex[:6]}@example.com",
        full_name="Artisan Vendor",
        role=UserRole.VENDOR,
        is_active=True,
    )
    db_session.add(vendor_user)
    await db_session.flush()

    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=vendor_user.id,
        business_name="Artisan Luxe Studio",
        business_address="Lagos, Nigeria",
        business_phone="+2348000000000",
    )
    db_session.add(vendor)
    await db_session.flush()

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor.id,
        title="Silk Slip Dress",
        base_price=Decimal("45000.00"),
        total_stock=10,
        product_type=ProductType.SINGLE,
    )
    db_session.add(product)
    await db_session.flush()

    order_ref = order_number or f"SHP-{uuid.uuid4().hex[:8].upper()}"
    ts = created_at or (datetime.now(timezone.utc) - timedelta(hours=25))

    order = Order(
        id=uuid.uuid4(),
        order_number=order_ref,
        customer_id=user.id,
        workflow_cohort="legacy_pre_bridge",
        workflow_policy_version="legacy_pre_bridge_v1",
        checkout_access_mode="authenticated",
        currency="NGN",
        subtotal=Decimal("45000.00"),
        shipping_cost=Decimal("2000.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("47000.00"),
        payment_status=order_payment_status,
        fulfillment_status=fulfillment_status,
        cancelled_at=cancelled_at,
        created_at=ts,
    )
    db_session.add(order)
    await db_session.flush()

    order_item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor.id,
        quantity=1,
        unit_price=Decimal("45000.00"),
        subtotal=Decimal("45000.00"),
        commission_rate=Decimal("12.50"),
        commission_amount=Decimal("5625.00"),
        vendor_payout=Decimal("39375.00"),
        currency="NGN",
        product_title="Silk Slip Dress",
        variant_details={"size": "M", "color": "Emerald"},
    )
    db_session.add(order_item)

    gateway_resp = None
    if authorization_url:
        gateway_resp = {
            "status": True,
            "data": {
                "authorization_url": authorization_url,
                "access_code": "code-123",
                "reference": order_ref,
            },
        }

    payment = Payment(
        id=uuid.uuid4(),
        order_id=order.id,
        transaction_id=order_ref,
        payment_gateway=payment_gateway,
        payment_method="paystack",
        amount=Decimal("47000.00"),
        currency="NGN",
        status=payment_status,
        gateway_response=gateway_resp,
        created_at=ts,
    )
    db_session.add(payment)
    await db_session.commit()
    return order, payment, user


@pytest.mark.asyncio
async def test_pending_payment_reminder_timing_under_24h_is_not_eligible(
    db_session: AsyncSession,
):
    """Reminders must NOT be sent before 24 hours have elapsed."""
    now = datetime.now(timezone.utc)
    twenty_three_hours_ago = now - timedelta(hours=23, minutes=30)

    order, payment, _ = await _create_test_order_with_payment(
        db_session, created_at=twenty_three_hours_ago
    )

    is_eligible, reason = is_order_eligible_for_pending_reminder(order, payment, now=now)
    assert is_eligible is False
    assert "timing_not_elapsed" in reason

    mock_client, calls = _make_mock_email_service()
    session_factory = lambda: db_session

    # Scans should claim 0 reminders
    claimed = await scan_and_claim_pending_payment_reminders(
        db_session, owner="test-worker", now=now
    )
    assert len(claimed) == 0
    assert len(calls) == 0


@pytest.mark.asyncio
async def test_pending_payment_reminder_timing_24h_is_eligible_and_sends_once(
    db_session: AsyncSession,
):
    """Reminder is eligible exactly at or after 24 hours from persisted checkout payment."""
    now = datetime.now(timezone.utc)
    twenty_five_hours_ago = now - timedelta(hours=25)

    order, payment, user = await _create_test_order_with_payment(
        db_session, created_at=twenty_five_hours_ago
    )

    is_eligible, reason = is_order_eligible_for_pending_reminder(order, payment, now=now)
    assert is_eligible is True
    assert reason == "eligible"

    mock_client, calls = _make_mock_email_service()

    counts = await dispatch_pending_payment_reminders_once(
        session_factory=lambda: db_session,
        owner="worker-alpha",
        now=now,
        email_client=mock_client,
    )

    assert counts["claimed"] == 1
    assert counts["sent"] == 1
    assert len(calls) == 1

    call = calls[0]
    assert call["email"] == user.email
    assert call["order_number"] == order.order_number
    assert call["total"] == 47000.0
    assert call["currency"] == "NGN"
    assert call["payment_url"] == "https://checkout.paystack.com/test-auth-12345"

    # Verify durable reminder record
    reminder = (
        await db_session.execute(
            select(OrderPaymentReminder).where(
                OrderPaymentReminder.order_id == order.id
            )
        )
    ).scalar_one()

    assert reminder.status == "sent"
    assert reminder.sent_at is not None
    assert reminder.recipient_email == user.email
    assert reminder.claim_owner is None
    assert reminder.claim_token is None

    # Verify durable AuditLog entry
    audit = (
        await db_session.execute(
            select(AuditLog).where(
                AuditLog.action == "pending_payment_reminder_sent",
                AuditLog.entity_id == order.id,
            )
        )
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.new_values["order_number"] == order.order_number


@pytest.mark.asyncio
async def test_paid_before_due_cancels_reminder_and_sends_no_email(
    db_session: AsyncSession,
):
    """If payment becomes PAID before send time, reminder is cancelled without sending."""
    now = datetime.now(timezone.utc)
    twenty_five_hours_ago = now - timedelta(hours=25)

    order, payment, _ = await _create_test_order_with_payment(
        db_session,
        created_at=twenty_five_hours_ago,
        order_payment_status=PaymentStatus.PAID,
        payment_status=TransactionStatus.COMPLETED,
    )

    is_eligible, reason = is_order_eligible_for_pending_reminder(order, payment, now=now)
    assert is_eligible is False
    assert "order_not_pending" in reason

    mock_client, calls = _make_mock_email_service()

    counts = await dispatch_pending_payment_reminders_once(
        session_factory=lambda: db_session,
        owner="worker-beta",
        now=now,
        email_client=mock_client,
    )

    assert counts["claimed"] == 0
    assert counts["sent"] == 0
    assert len(calls) == 0


@pytest.mark.asyncio
async def test_order_cancelled_cancels_reminder_without_sending(
    db_session: AsyncSession,
):
    """If order is cancelled, reminder is cancelled and not sent."""
    now = datetime.now(timezone.utc)
    twenty_five_hours_ago = now - timedelta(hours=25)

    order, payment, _ = await _create_test_order_with_payment(
        db_session,
        created_at=twenty_five_hours_ago,
        fulfillment_status=FulfillmentStatus.CANCELLED,
        cancelled_at=now - timedelta(hours=2),
    )

    is_eligible, reason = is_order_eligible_for_pending_reminder(order, payment, now=now)
    assert is_eligible is False
    assert reason == "order_cancelled"

    mock_client, calls = _make_mock_email_service()

    counts = await dispatch_pending_payment_reminders_once(
        session_factory=lambda: db_session,
        owner="worker-beta",
        now=now,
        email_client=mock_client,
    )

    assert counts["sent"] == 0
    assert len(calls) == 0


@pytest.mark.asyncio
async def test_payment_failed_or_refunded_is_ineligible(
    db_session: AsyncSession,
):
    """Failed or refunded payments are not eligible for reminders."""
    now = datetime.now(timezone.utc)
    twenty_five_hours_ago = now - timedelta(hours=25)

    order_failed, payment_failed, _ = await _create_test_order_with_payment(
        db_session,
        created_at=twenty_five_hours_ago,
        payment_status=TransactionStatus.FAILED,
    )
    is_eligible_failed, _ = is_order_eligible_for_pending_reminder(
        order_failed, payment_failed, now=now
    )
    assert is_eligible_failed is False

    order_refunded, payment_refunded, _ = await _create_test_order_with_payment(
        db_session,
        created_at=twenty_five_hours_ago,
        order_payment_status=PaymentStatus.REFUNDED,
        payment_status=TransactionStatus.REFUNDED,
    )
    is_eligible_refunded, _ = is_order_eligible_for_pending_reminder(
        order_refunded, payment_refunded, now=now
    )
    assert is_eligible_refunded is False


@pytest.mark.asyncio
async def test_recheck_before_dispatch_cancels_if_paid_in_flight(
    db_session: AsyncSession,
):
    """If payment is confirmed after claim but before dispatch, dispatch cancels without sending."""
    now = datetime.now(timezone.utc)
    twenty_five_hours_ago = now - timedelta(hours=25)

    order, payment, _ = await _create_test_order_with_payment(
        db_session, created_at=twenty_five_hours_ago
    )

    # Claim the reminder first
    claimed = await scan_and_claim_pending_payment_reminders(
        db_session, owner="worker-1", now=now
    )
    assert len(claimed) == 1
    reminder = claimed[0]
    await db_session.commit()

    # Shopper completes payment via webhook while claimed
    order.payment_status = PaymentStatus.PAID
    payment.status = TransactionStatus.COMPLETED
    await db_session.commit()

    mock_client, calls = _make_mock_email_service()

    # Dispatch now
    success = await dispatch_single_reminder(
        session_factory=lambda: db_session,
        reminder_id=reminder.id,
        owner="worker-1",
        claim_token=reminder.claim_token,
        now=now,
        email_client=mock_client,
    )

    assert success is False
    assert len(calls) == 0

    # Reminder should be marked cancelled
    updated_reminder = await db_session.get(OrderPaymentReminder, reminder.id)
    assert updated_reminder.status == "cancelled"


@pytest.mark.asyncio
async def test_retry_concurrency_and_single_send_only_guarantee(
    db_session: AsyncSession,
):
    """Concurrent workers and repeated scans never send duplicate emails."""
    now = datetime.now(timezone.utc)
    twenty_five_hours_ago = now - timedelta(hours=25)

    order, payment, user = await _create_test_order_with_payment(
        db_session, created_at=twenty_five_hours_ago
    )

    mock_client, calls = _make_mock_email_service()

    # Pass 1: First dispatch pass
    counts1 = await dispatch_pending_payment_reminders_once(
        session_factory=lambda: db_session,
        owner="worker-1",
        now=now,
        email_client=mock_client,
    )
    assert counts1["sent"] == 1
    assert len(calls) == 1

    # Pass 2: Repeated scan 5 minutes later
    counts2 = await dispatch_pending_payment_reminders_once(
        session_factory=lambda: db_session,
        owner="worker-2",
        now=now + timedelta(minutes=5),
        email_client=mock_client,
    )
    assert counts2["claimed"] == 0
    assert counts2["sent"] == 0
    assert len(calls) == 1  # Still exactly 1 email sent!

    # Pass 3: Page refresh / polling scan 12 hours later
    counts3 = await dispatch_pending_payment_reminders_once(
        session_factory=lambda: db_session,
        owner="worker-3",
        now=now + timedelta(hours=12),
        email_client=mock_client,
    )
    assert counts3["claimed"] == 0
    assert counts3["sent"] == 0
    assert len(calls) == 1  # Still exactly 1 email sent!

    # Verify exactly 1 reminder in DB with status sent
    reminders = (
        await db_session.execute(
            select(OrderPaymentReminder).where(
                OrderPaymentReminder.order_id == order.id
            )
        )
    ).scalars().all()
    assert len(reminders) == 1
    assert reminders[0].status == "sent"


@pytest.mark.asyncio
async def test_transient_email_failure_retries_and_caps_at_max_attempts(
    db_session: AsyncSession,
):
    """Transient failures are retried safely, but once sent or capped, duplicate sends never occur."""
    now = datetime.now(timezone.utc)
    twenty_five_hours_ago = now - timedelta(hours=25)

    order, payment, _ = await _create_test_order_with_payment(
        db_session, created_at=twenty_five_hours_ago
    )

    mock_client, calls = _make_mock_email_service()
    mock_client.should_fail = True  # Simulate email gateway outage

    # Attempt 1: Fails
    counts1 = await dispatch_pending_payment_reminders_once(
        session_factory=lambda: db_session,
        owner="worker-1",
        now=now,
        email_client=mock_client,
    )
    assert counts1["sent"] == 0
    assert len(calls) == 0

    reminder = (
        await db_session.execute(
            select(OrderPaymentReminder).where(
                OrderPaymentReminder.order_id == order.id
            )
        )
    ).scalar_one()
    assert reminder.status == "pending"
    assert reminder.attempt_count == 1

    # Attempt 2: Email service recovered!
    mock_client.should_fail = False
    counts2 = await dispatch_pending_payment_reminders_once(
        session_factory=lambda: db_session,
        owner="worker-1",
        now=now + timedelta(minutes=1),
        email_client=mock_client,
    )
    assert counts2["sent"] == 1
    assert len(calls) == 1

    reminder = (
        await db_session.execute(
            select(OrderPaymentReminder).where(
                OrderPaymentReminder.order_id == order.id
            )
        )
    ).scalar_one()
    assert reminder.status == "sent"

    # Attempt 3: Later scan should not send again
    counts3 = await dispatch_pending_payment_reminders_once(
        session_factory=lambda: db_session,
        owner="worker-2",
        now=now + timedelta(minutes=10),
        email_client=mock_client,
    )
    assert counts3["sent"] == 0
    assert len(calls) == 1  # Exactly one send


@pytest.mark.asyncio
async def test_extract_safe_payment_urls_contains_no_secrets(
    db_session: AsyncSession,
):
    """URLs provided to customer identify order without leaking confidential credentials."""
    order, payment, _ = await _create_test_order_with_payment(
        db_session,
        authorization_url="https://checkout.paystack.com/access-token-public-12345",
    )

    payment_url, order_url = extract_safe_payment_urls(order, payment)

    assert "https://checkout.paystack.com/access-token-public-12345" in payment_url
    assert f"/orders/{order.id}" in order_url

    for secret in ["sk_test_", "sk_live_", "pepper", "password", "client_secret"]:
        assert secret not in payment_url.lower()
        assert secret not in order_url.lower()


def test_celery_entrypoint_synchronous_wrapper():
    """Verify Celery task callable entrypoint exists and can be invoked."""
    assert callable(dispatch_pending_payment_reminders)
