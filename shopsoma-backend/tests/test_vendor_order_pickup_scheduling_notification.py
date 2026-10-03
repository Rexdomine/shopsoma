"""Tests to verify that vendor order notification emails do not include hardcoded pickup dates
prior to explicit pickup scheduling by admin."""

from datetime import datetime, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
from app.models.product import Product, ProductStatus, ModerationStatus
from app.models.vendor import Vendor
from app.models.vendor_pickup import VendorNotification, VendorPickup, PickupStatus
from app.services.email_service import EmailService
from app.services.order_notification_service import OrderNotificationService
from app.services.vendor_notification_service import VendorNotificationService


def _capture_email(monkeypatch, service: EmailService):
    calls = []

    async def fake_send_email(
        to_email, to_name, subject, html_content, template_params=None
    ):
        calls.append(
            {
                "to_email": to_email,
                "to_name": to_name,
                "subject": subject,
                "html_content": html_content,
            }
        )
        return True

    monkeypatch.setattr(service, "send_email", fake_send_email)
    return calls


@pytest.mark.asyncio
async def test_initial_vendor_order_email_excludes_pickup_date(monkeypatch):
    """Initial vendor order emails must NOT display any pickup date details."""
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_vendor_new_order_email(
        email="vendor@example.com",
        name="Artisan Crafts",
        order_number="SHP-INITIAL-001",
        order_date=datetime(2026, 10, 3, 10, 0),
        items=[
            {
                "product_title": "Silk Kimono",
                "quantity": 1,
                "vendor_payout": 45000,
                "variant_details": {"size": "M", "color": "Navy"},
            }
        ],
        total_payout=45000,
        pickup_date=None,
        currency="NGN",
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )

    assert result is True
    assert len(calls) == 1
    html = calls[0]["html_content"]
    assert "Pickup Scheduled:" not in html
    assert "Order Number:</strong> SHP-INITIAL-001" in html
    assert "Order Date:</strong> 03 October 2026" in html


@pytest.mark.asyncio
async def test_vendor_order_email_excludes_pickup_date_even_if_date_passed_when_not_scheduled_status(
    monkeypatch,
):
    """If an order is in ORDER_RECEIVED status, passing a pickup_date should not render it."""
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    result = await service.send_vendor_new_order_email(
        email="vendor@example.com",
        name="Artisan Crafts",
        order_number="SHP-INITIAL-002",
        order_date=datetime(2026, 10, 3, 10, 0),
        items=[
            {
                "product_title": "Handmade Bag",
                "quantity": 1,
                "vendor_payout": 25000,
            }
        ],
        total_payout=25000,
        pickup_date=datetime(2026, 10, 5, 14, 0),
        currency="NGN",
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )

    assert result is True
    assert len(calls) == 1
    html = calls[0]["html_content"]
    assert "Pickup Scheduled:" not in html


@pytest.mark.asyncio
async def test_vendor_order_email_includes_pickup_date_when_status_is_pickup_scheduled(
    monkeypatch,
):
    """When fulfillment status is PICKUP_SCHEDULED and pickup date exists, it should be rendered."""
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    scheduled_dt = datetime(2026, 10, 5, 14, 30)
    result = await service.send_vendor_new_order_email(
        email="vendor@example.com",
        name="Artisan Crafts",
        order_number="SHP-SCHEDULED-001",
        order_date=datetime(2026, 10, 3, 10, 0),
        items=[
            {
                "product_title": "Silk Kimono",
                "quantity": 1,
                "vendor_payout": 45000,
            }
        ],
        total_payout=45000,
        pickup_date=scheduled_dt,
        currency="NGN",
        fulfillment_status=FulfillmentStatus.PICKUP_SCHEDULED,
    )

    assert result is True
    assert len(calls) == 1
    html = calls[0]["html_content"]
    assert "Pickup Scheduled:</strong> 05 October 2026 · 02:30 PM" in html


@pytest.mark.asyncio
async def test_vendor_order_email_includes_pickup_date_with_scheduling_pickup_string(
    monkeypatch,
):
    """When order_status is 'scheduling_pickup' and pickup date exists, it should be rendered."""
    service = EmailService()
    calls = _capture_email(monkeypatch, service)

    scheduled_dt = datetime(2026, 10, 6, 9, 15)
    result = await service.send_vendor_new_order_email(
        email="vendor@example.com",
        name="Artisan Crafts",
        order_number="SHP-SCHEDULED-002",
        order_date=datetime(2026, 10, 3, 10, 0),
        items=[
            {
                "product_title": "Ceramic Vase",
                "quantity": 1,
                "vendor_payout": 18000,
            }
        ],
        total_payout=18000,
        pickup_date=scheduled_dt,
        currency="NGN",
        order_status="scheduling_pickup",
    )

    assert result is True
    assert len(calls) == 1
    html = calls[0]["html_content"]
    assert "Pickup Scheduled:</strong> 06 October 2026 · 09:15 AM" in html


@pytest.mark.asyncio
async def test_vendor_notification_service_excludes_pickup_date_for_initial_order(
    db_session: AsyncSession, vendor_user, monkeypatch
):
    """VendorNotificationService sends new order email without pickup date when order is initial/order_received."""
    vendor = vendor_user["vendor"]
    order = Order(
        id=uuid.uuid4(),
        order_number="SHP-TEST-INITIAL-EMAIL",
        customer_id=vendor_user["user"].id,
        currency="NGN",
        subtotal=Decimal("20000.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("20000.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.commit()

    email_service = EmailService()
    calls = _capture_email(monkeypatch, email_service)

    service = VendorNotificationService(email_service)
    await service.send_order_notification(
        db=db_session,
        vendor_id=str(vendor.id),
        order_id=str(order.id),
        order_number=order.order_number,
        order_date=datetime.now(timezone.utc),
        items=[{"product_title": "Item 1", "quantity": 1, "vendor_payout": 20000.0}],
        total_payout=20000.0,
        scheduled_pickup_date=None,
        currency="NGN",
    )

    assert len(calls) == 1
    assert calls[0]["to_email"] == vendor_user["user"].email
    assert "Pickup Scheduled:" not in calls[0]["html_content"]


@pytest.mark.asyncio
async def test_order_notification_service_vendor_pickup_scheduled_email(
    db_session: AsyncSession, vendor_user, monkeypatch
):
    """When order status changes to PICKUP_SCHEDULED, vendor email contains pickup schedule details."""
    vendor = vendor_user["vendor"]
    order = Order(
        id=uuid.uuid4(),
        order_number="SHP-TEST-ADMIN-SCHED",
        customer_id=vendor_user["user"].id,
        currency="NGN",
        subtotal=Decimal("30000.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("30000.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.PICKUP_SCHEDULED,
    )
    db_session.add(order)
    await db_session.flush()

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor.id,
        title="Bespoke Suit",
        base_price=Decimal("30000.00"),
        currency="NGN",
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.flush()

    order_item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        vendor_id=vendor.id,
        product_id=product.id,
        product_title="Bespoke Suit",
        quantity=1,
        unit_price=Decimal("30000.00"),
        subtotal=Decimal("30000.00"),
        commission_rate=Decimal("15.00"),
        commission_amount=Decimal("4500.00"),
        vendor_payout=Decimal("25500.00"),
        currency="NGN",
    )
    db_session.add(order_item)
    await db_session.commit()

    loaded_order = (
        await db_session.execute(
            select(Order).options(selectinload(Order.items)).where(Order.id == order.id)
        )
    ).scalar_one()

    email_service = EmailService()
    calls = _capture_email(monkeypatch, email_service)

    notif_service = OrderNotificationService(db_session, email_service=email_service)
    sched_dt = datetime(2026, 10, 7, 15, 0)
    await notif_service.notify_status_change(
        order=loaded_order,
        new_status=FulfillmentStatus.PICKUP_SCHEDULED,
        pickup_details={
            "scheduled_pickup_date": sched_dt,
            "courier_name": "GIG Logistics",
        },
    )

    assert len(calls) == 1
    html = calls[0]["html_content"]
    assert "Pickup Scheduled" in html
    assert "October 07, 2026" in html
    assert "GIG Logistics" in html
