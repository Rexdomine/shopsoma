"""Tests to verify vendors only receive order notification emails when payment is confirmed PAID."""

import hmac
import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import payments
from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.models.product import Product, ProductStatus, ModerationStatus
from app.models.vendor_pickup import VendorNotification
from app.services.email_service import EmailService
from app.services.order_notification_service import OrderNotificationService
from app.services.vendor_notification_service import VendorNotificationService


@pytest.mark.asyncio
async def test_vendor_notification_service_skips_when_order_pending(
    db_session: AsyncSession, vendor_user, monkeypatch
):
    """VendorNotificationService must suppress emails for orders with pending payment."""
    vendor = vendor_user["vendor"]
    order = Order(
        id=uuid.uuid4(),
        order_number="SHP-TEST-PENDING-001",
        customer_id=vendor_user["user"].id,
        currency="NGN",
        subtotal=Decimal("15000.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("15000.00"),
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.commit()

    email_calls = []

    async def mock_send_email(*args, **kwargs):
        email_calls.append(kwargs)
        return True

    email_service = EmailService()
    monkeypatch.setattr(email_service, "send_vendor_new_order_email", mock_send_email)

    service = VendorNotificationService(email_service)
    await service.send_order_notification(
        db=db_session,
        vendor_id=str(vendor.id),
        order_id=str(order.id),
        order_number=order.order_number,
        order_date=datetime.now(timezone.utc),
        items=[{"product_title": "Item 1", "quantity": 1, "vendor_payout": 15000.0}],
        total_payout=15000.0,
        scheduled_pickup_date=datetime.now(timezone.utc),
        currency="NGN",
    )

    # Must NOT send email for pending payment
    assert len(email_calls) == 0


@pytest.mark.asyncio
async def test_vendor_notification_service_sends_when_order_paid(
    db_session: AsyncSession, vendor_user, monkeypatch
):
    """VendorNotificationService must dispatch email when order payment status is PAID."""
    vendor = vendor_user["vendor"]
    order = Order(
        id=uuid.uuid4(),
        order_number="SHP-TEST-PAID-001",
        customer_id=vendor_user["user"].id,
        currency="NGN",
        subtotal=Decimal("15000.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("15000.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.commit()

    email_calls = []

    async def mock_send_email(*args, **kwargs):
        email_calls.append(kwargs)
        return True

    email_service = EmailService()
    monkeypatch.setattr(email_service, "send_vendor_new_order_email", mock_send_email)

    service = VendorNotificationService(email_service)
    await service.send_order_notification(
        db=db_session,
        vendor_id=str(vendor.id),
        order_id=str(order.id),
        order_number=order.order_number,
        order_date=datetime.now(timezone.utc),
        items=[{"product_title": "Item 1", "quantity": 1, "vendor_payout": 15000.0}],
        total_payout=15000.0,
        scheduled_pickup_date=datetime.now(timezone.utc),
        currency="NGN",
    )

    assert len(email_calls) == 1
    assert email_calls[0]["order_number"] == order.order_number
    assert email_calls[0]["email"] == vendor.user.email

    # Check notification in db has email_sent=True
    notification = await db_session.scalar(
        select(VendorNotification).where(
            VendorNotification.vendor_id == vendor.id,
            VendorNotification.order_id == order.id,
        )
    )
    assert notification is not None
    assert notification.email_sent is True


@pytest.mark.asyncio
async def test_order_notification_service_suppresses_vendors_when_pending(
    db_session: AsyncSession, vendor_user, monkeypatch
):
    """OrderNotificationService._notify_vendors must return False and not email when payment is PENDING."""
    vendor = vendor_user["vendor"]
    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor.id,
        title="Pending Dress",
        base_price=Decimal("10000.00"),
        currency="NGN",
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number="SHP-TEST-PENDING-NOTIF",
        customer_id=vendor_user["user"].id,
        currency="NGN",
        subtotal=Decimal("10000.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("10000.00"),
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor.id,
        product_title=product.title,
        quantity=1,
        unit_price=Decimal("10000.00"),
        subtotal=Decimal("10000.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("1000.00"),
        vendor_payout=Decimal("9000.00"),
        currency="NGN",
    )
    order.items = [item]
    db_session.add_all([order, item])
    await db_session.commit()

    email_calls = []

    async def mock_send_email(*args, **kwargs):
        email_calls.append(kwargs)
        return True

    service = OrderNotificationService(db_session)
    monkeypatch.setattr(service.email_service, "send_email", mock_send_email)

    result = await service.notify_status_change(order, FulfillmentStatus.ORDER_RECEIVED)
    assert result["vendor_notified"] is False
    assert len(email_calls) == 0


@pytest.mark.asyncio
async def test_order_notification_service_notifies_vendors_when_paid(
    db_session: AsyncSession, vendor_user, monkeypatch
):
    """OrderNotificationService._notify_vendors sends emails when payment is PAID."""
    vendor = vendor_user["vendor"]
    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor.id,
        title="Paid Dress",
        base_price=Decimal("10000.00"),
        currency="NGN",
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number="SHP-TEST-PAID-NOTIF",
        customer_id=vendor_user["user"].id,
        currency="NGN",
        subtotal=Decimal("10000.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("10000.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor.id,
        product_title=product.title,
        quantity=1,
        unit_price=Decimal("10000.00"),
        subtotal=Decimal("10000.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("1000.00"),
        vendor_payout=Decimal("9000.00"),
        currency="NGN",
    )
    order.items = [item]
    db_session.add_all([order, item])
    await db_session.commit()

    email_calls = []

    async def mock_send_email(*args, **kwargs):
        email_calls.append(kwargs)
        return True

    service = OrderNotificationService(db_session)
    monkeypatch.setattr(service.email_service, "send_email", mock_send_email)

    result = await service.notify_status_change(order, FulfillmentStatus.ORDER_RECEIVED)
    assert result["vendor_notified"] is True
    assert len(email_calls) == 1


class _FakePaystackResponse:
    def __init__(self, reference: str, amount: int = 5000000, status: str = "success"):
        self._reference = reference
        self._amount = amount
        self._status = status

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "status": True,
            "data": {
                "status": self._status,
                "reference": self._reference,
                "amount": self._amount,
                "currency": "NGN",
                "gateway_response": "Successful",
            },
        }


class _FakeAsyncClient:
    def __init__(self, response: _FakePaystackResponse):
        self._response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def get(self, *args, **kwargs):
        return self._response


@pytest.mark.asyncio
async def test_paystack_verification_dispatches_vendor_notifications(
    client: AsyncClient, db_session: AsyncSession, vendor_user, customer_user, monkeypatch
):
    """When Paystack payment is verified, vendors receive new order notification emails."""
    vendor = vendor_user["vendor"]
    customer = customer_user["user"]
    ref = f"SHP-VTEST-{uuid.uuid4().hex[:6]}"

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor.id,
        title="Artisan Jacket",
        base_price=Decimal("50000.00"),
        currency="NGN",
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number=ref,
        customer_id=customer.id,
        currency="NGN",
        subtotal=Decimal("50000.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("50000.00"),
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor.id,
        product_title=product.title,
        quantity=1,
        unit_price=Decimal("50000.00"),
        subtotal=Decimal("50000.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("5000.00"),
        vendor_payout=Decimal("45000.00"),
        currency="NGN",
    )
    db_session.add(item)

    payment = Payment(
        id=uuid.uuid4(),
        order_id=order.id,
        transaction_id=ref,
        payment_gateway=PaymentGateway.PAYSTACK,
        payment_method="paystack",
        amount=Decimal("50000.00"),
        currency="NGN",
        status=TransactionStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()

    vendor_emails = []

    async def mock_send_vendor_email(*args, **kwargs):
        vendor_emails.append(kwargs)
        return True

    from app.services.email_service import email_service
    monkeypatch.setattr(email_service, "send_vendor_new_order_email", mock_send_vendor_email)

    fake_client = _FakeAsyncClient(_FakePaystackResponse(reference=ref, amount=5000000))
    monkeypatch.setattr("httpx.AsyncClient", lambda *args, **kwargs: fake_client)

    verify_payload = {
        "payment_gateway": "paystack",
        "reference": ref,
    }
    response = await client.post("/api/v1/payments/verify", json=verify_payload)
    assert response.status_code == 200, response.text

    # Vendor email should now have been sent!
    assert len(vendor_emails) == 1
    assert vendor_emails[0]["order_number"] == ref
    assert vendor_emails[0]["email"] == vendor.user.email
    assert vendor_emails[0]["total_payout"] == 45000.0

    # Ensure in-app notification is marked email_sent=True
    notification = await db_session.scalar(
        select(VendorNotification).where(
            VendorNotification.vendor_id == vendor.id,
            VendorNotification.order_id == order.id,
        )
    )
    assert notification is not None
    assert notification.email_sent is True


@pytest.mark.asyncio
async def test_paystack_webhook_dispatches_vendor_notifications_and_prevents_duplicate(
    client: AsyncClient, db_session: AsyncSession, vendor_user, customer_user, monkeypatch
):
    """Paystack webhook sends vendor email, and subsequent webhook replay does not re-send."""
    vendor = vendor_user["vendor"]
    customer = customer_user["user"]
    ref = f"SHP-WH-{uuid.uuid4().hex[:6]}"

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor.id,
        title="Silk Scarf",
        base_price=Decimal("20000.00"),
        currency="NGN",
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number=ref,
        customer_id=customer.id,
        currency="NGN",
        subtotal=Decimal("20000.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("20000.00"),
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor.id,
        product_title=product.title,
        quantity=1,
        unit_price=Decimal("20000.00"),
        subtotal=Decimal("20000.00"),
        commission_rate=Decimal("15.00"),
        commission_amount=Decimal("3000.00"),
        vendor_payout=Decimal("17000.00"),
        currency="NGN",
    )
    db_session.add(item)

    payment = Payment(
        id=uuid.uuid4(),
        order_id=order.id,
        transaction_id=ref,
        payment_gateway=PaymentGateway.PAYSTACK,
        payment_method="paystack",
        amount=Decimal("20000.00"),
        currency="NGN",
        status=TransactionStatus.PENDING,
    )
    db_session.add(payment)
    await db_session.commit()

    vendor_emails = []

    async def mock_send_vendor_email(*args, **kwargs):
        vendor_emails.append(kwargs)
        return True

    from app.services.email_service import email_service
    monkeypatch.setattr(email_service, "send_vendor_new_order_email", mock_send_vendor_email)

    webhook_secret = "test_webhook_secret_key"
    monkeypatch.setattr(payments, "PAYSTACK_SECRET_KEY", webhook_secret)

    webhook_payload = {
        "event": "charge.success",
        "data": {
            "id": 998877,
            "reference": ref,
            "amount": 2000000,
            "currency": "NGN",
            "status": "success",
        },
    }
    body_bytes = json.dumps(webhook_payload).encode("utf-8")
    signature = hmac.new(
        webhook_secret.encode("utf-8"), body_bytes, hashlib.sha512
    ).hexdigest()

    headers = {"x-paystack-signature": signature}
    resp1 = await client.post("/api/v1/payments/webhook/paystack", content=body_bytes, headers=headers)
    assert resp1.status_code == 200, resp1.text

    assert len(vendor_emails) == 1
    assert vendor_emails[0]["order_number"] == ref

    # Second call (replay) should NOT send a duplicate email
    resp2 = await client.post("/api/v1/payments/webhook/paystack", content=body_bytes, headers=headers)
    assert resp2.status_code == 200
    assert len(vendor_emails) == 1
