"""Regression tests for production ShipBubble vendor status sync & non-prod email guard."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
from app.models.product import Product, ProductStatus
from app.models.shipbubble_shipment import ShipbubbleShipment
from app.models.vendor_pickup import OrderType, PickupStatus, VendorNotification, VendorPickup
from app.services.email_service import EmailService
from app.services.orders.fulfillment_sync import (
    can_apply_carrier_status_transition,
    resolve_effective_item_fulfillment_status,
)
from app.services.shipping.shipbubble_tracking import sync_shipbubble_shipment_status
from app.services.vendor_notification_service import VendorNotificationService


def test_carrier_status_transition_monotonic_guard():
    # Stale ShipBubble "confirmed" -> PICKUP_SCHEDULED must never regress DELIVERED or IN_TRANSIT
    assert not can_apply_carrier_status_transition(
        FulfillmentStatus.DELIVERED,
        FulfillmentStatus.PICKUP_SCHEDULED,
        is_webhook=False,
    )
    assert not can_apply_carrier_status_transition(
        FulfillmentStatus.DELIVERED,
        FulfillmentStatus.IN_TRANSIT,
        is_webhook=True,
    )
    assert not can_apply_carrier_status_transition(
        FulfillmentStatus.IN_TRANSIT,
        FulfillmentStatus.PICKUP_SCHEDULED,
        is_webhook=False,
    )
    assert not can_apply_carrier_status_transition(
        FulfillmentStatus.DELIVERED,
        FulfillmentStatus.CANCELLED,
        is_webhook=True,
    )

    # Forward transitions are allowed
    assert can_apply_carrier_status_transition(
        FulfillmentStatus.PICKUP_SCHEDULED,
        FulfillmentStatus.IN_TRANSIT,
        is_webhook=False,
    )
    assert can_apply_carrier_status_transition(
        FulfillmentStatus.OUT_FOR_DELIVERY,
        FulfillmentStatus.DELIVERED,
        is_webhook=False,
    )
    # Explicit post-delivery return webhook is allowed, but polling is not
    assert can_apply_carrier_status_transition(
        FulfillmentStatus.DELIVERED,
        FulfillmentStatus.RETURNED,
        is_webhook=True,
    )
    assert not can_apply_carrier_status_transition(
        FulfillmentStatus.DELIVERED,
        FulfillmentStatus.RETURNED,
        is_webhook=False,
    )


def test_resolve_effective_item_fulfillment_status_handles_domestic_checkout_v1():
    dummy_order = SimpleNamespace(fulfillment_status=FulfillmentStatus.DELIVERED)
    dummy_item = SimpleNamespace(
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        inventory_policy="stock_managed",
    )
    dummy_pickup = SimpleNamespace(
        status=PickupStatus.IN_TRANSIT,
        ready_for_pickup_at=datetime.now(timezone.utc),
        actual_pickup_date=datetime.now(timezone.utc),
        scheduled_pickup_date=datetime.now(timezone.utc),
        pickup_window_start=None,
    )

    assert (
        resolve_effective_item_fulfillment_status(dummy_item, dummy_order, dummy_pickup)
        == FulfillmentStatus.DELIVERED
    )

    # Individually cancelled items stay cancelled even if order later delivers remaining items
    cancelled_item = SimpleNamespace(
        fulfillment_status=FulfillmentStatus.CANCELLED,
        inventory_policy="stock_managed",
    )
    assert (
        resolve_effective_item_fulfillment_status(cancelled_item, dummy_order, dummy_pickup)
        == FulfillmentStatus.CANCELLED
    )


@pytest.mark.asyncio
async def test_sync_shipbubble_does_not_regress_delivered_order(
    db_session: AsyncSession,
    vendor_user,
    customer_user,
):
    original_delivered_at = datetime(2026, 10, 27, 11, 41, 43, tzinfo=timezone.utc)
    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="MMBM SOCKS",
        base_price=Decimal("13500.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid4(),
        order_number="SHP-20261020-REGCHECK",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("13500.00"),
        shipping_cost=Decimal("8188.25"),
        tax_amount=Decimal("1626.62"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("23314.87"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        delivery_provider="shipbubble:GIG Logistics",
        tracking_number="SB-D40825FE22EF",
        delivered_at=original_delivered_at,
    )
    db_session.add(order)
    await db_session.flush()

    shipment = ShipbubbleShipment(
        id=uuid4(),
        order_id=order.id,
        request_token="tok_regcheck",
        courier_id="gigl",
        service_code="gigl",
        courier_name="GIG Logistics",
        shipbubble_order_id="SB-REGCHECK-001",
        status="confirmed",
        shipping_fee=Decimal("8188.25"),
        currency="NGN",
    )
    db_session.add(shipment)
    await db_session.commit()

    fake_service = AsyncMock()
    fake_service.track_shipments.return_value = [{"status": "confirmed"}]

    with patch(
        "app.services.shipping.shipbubble_tracking.get_shipbubble_service",
        return_value=fake_service,
    ):
        await sync_shipbubble_shipment_status(db_session, order=order)

    await db_session.refresh(order)
    assert order.fulfillment_status == FulfillmentStatus.DELIVERED
    assert order.delivered_at == original_delivered_at


@pytest.mark.asyncio
async def test_shipbubble_webhook_completes_vendor_pickup_and_blocks_regression(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    monkeypatch,
):
    api_key = "sb_sandbox_webhook_test_key"
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", api_key)

    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Webhook Socks",
        base_price=Decimal("13500.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid4(),
        order_number="SHP-20261020-SBWH01",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("13500.00"),
        shipping_cost=Decimal("5000.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("18500.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.IN_TRANSIT,
        delivery_provider="shipbubble:GIG Logistics",
        tracking_number="SB-WH-001",
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        unit_price=Decimal("13500.00"),
        quantity=1,
        subtotal=Decimal("13500.00"),
        commission_rate=Decimal("12.50"),
        commission_amount=Decimal("1687.50"),
        vendor_payout=Decimal("11812.50"),
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(item)
    await db_session.flush()

    pickup = VendorPickup(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        order_id=order.id,
        order_item_id=item.id,
        order_type=OrderType.RTW,
        status=PickupStatus.IN_TRANSIT,
        actual_pickup_date=datetime.now(timezone.utc) - timedelta(days=2),
    )
    db_session.add(pickup)

    shipment = ShipbubbleShipment(
        id=uuid4(),
        order_id=order.id,
        request_token="tok_wh_001",
        courier_id="gigl",
        service_code="gigl",
        courier_name="GIG Logistics",
        shipbubble_order_id="SB-WH-001",
        status="in_transit",
        shipping_fee=Decimal("5000.00"),
        currency="NGN",
    )
    db_session.add(shipment)
    await db_session.commit()

    def _sign(body: bytes) -> str:
        return hmac.new(api_key.encode("utf-8"), body, hashlib.sha512).hexdigest()

    # 1. Deliver via ShipBubble webhook
    delivered_payload = json.dumps(
        {"event": "shipment.status.changed", "order_id": "SB-WH-001", "status": "delivered"}
    ).encode("utf-8")
    resp = await client.post(
        "/api/v1/shipping/webhooks/shipbubble",
        content=delivered_payload,
        headers={"x-ship-signature": _sign(delivered_payload)},
    )
    assert resp.status_code == 200

    await db_session.refresh(order)
    await db_session.refresh(item)
    await db_session.refresh(pickup)
    assert order.fulfillment_status == FulfillmentStatus.DELIVERED
    assert order.delivered_at is not None
    assert item.fulfillment_status == FulfillmentStatus.DELIVERED
    assert pickup.status == PickupStatus.COMPLETED
    assert pickup.completed_at is not None

    # 2. Out-of-order stale webhook ("picked_up") must NOT regress order back from DELIVERED
    stale_payload = json.dumps(
        {"event": "shipment.status.changed", "order_id": "SB-WH-001", "status": "picked_up"}
    ).encode("utf-8")
    resp2 = await client.post(
        "/api/v1/shipping/webhooks/shipbubble",
        content=stale_payload,
        headers={"x-ship-signature": _sign(stale_payload)},
    )
    assert resp2.status_code == 200
    await db_session.refresh(order)
    assert order.fulfillment_status == FulfillmentStatus.DELIVERED


@pytest.mark.asyncio
async def test_vendor_order_endpoints_surface_delivered_item_status_and_preserve_delivered_at(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
):
    first_delivered_at = datetime(2026, 10, 27, 11, 41, 43, tzinfo=timezone.utc)
    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Delivered Socks",
        base_price=Decimal("13500.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid4(),
        order_number="SHP-20261020-VENDVIEW",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("13500.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("13500.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        delivered_at=first_delivered_at,
    )
    db_session.add(order)
    await db_session.flush()

    # Simulate an item whose DB row remained order_received (as on domestic_checkout_v1 orders)
    item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        unit_price=Decimal("13500.00"),
        quantity=1,
        subtotal=Decimal("13500.00"),
        commission_rate=Decimal("12.50"),
        commission_amount=Decimal("1687.50"),
        vendor_payout=Decimal("11812.50"),
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(item)
    await db_session.commit()

    list_resp = await client.get("/api/v1/vendor/orders", headers=vendor_user["headers"])
    assert list_resp.status_code == 200
    listed_order = next(
        o for o in list_resp.json()["orders"] if o["order_number"] == "SHP-20261020-VENDVIEW"
    )
    assert listed_order["fulfillment_status"] == "delivered"
    assert listed_order["items"][0]["fulfillment_status"] == "delivered"

    detail_resp = await client.get(
        f"/api/v1/vendor/orders/{order.id}", headers=vendor_user["headers"]
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["items"][0]["fulfillment_status"] == "delivered"

    # Re-applying DELIVERED via admin must preserve the original delivered_at timestamp
    patch_resp = await client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        json={"fulfillment_status": "delivered", "admin_notes": "Confirming delivery"},
        headers=admin_user["headers"],
    )
    assert patch_resp.status_code == 200
    await db_session.refresh(order)
    assert order.delivered_at == first_delivered_at


@pytest.mark.asyncio
async def test_non_production_email_guard_blocks_real_vendors_and_allows_allowlist(
    db_session: AsyncSession,
    vendor_user,
    monkeypatch,
):
    service = EmailService()
    fake_api = MagicMock()
    fake_api.send_transac_email.return_value = SimpleNamespace(message_id="msg-123")
    service.enabled = True
    service.api_instance = fake_api
    monkeypatch.setattr(settings, "BREVO_API_KEY", "xkeysib-fake-key")

    # 1. In development/staging with empty allowlist, real vendor email is suppressed
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "ALLOW_NON_PROD_EXTERNAL_EMAILS", False)
    monkeypatch.setattr(settings, "NON_PROD_EMAIL_ALLOWLIST", "qa@shopsoma.com,@internal.test")

    with patch("app.services.email_service.brevo_python") as mock_brevo:
        mock_brevo.SendSmtpEmail = MagicMock()
        suppressed = await service.send_email(
            to_email="jacklynnwandison@gmail.com",
            to_name="Coal by Jacklyn",
            subject="New Order Received · SHP-20261112-B6603A66",
            html_content="<p>Test</p>",
        )
        assert suppressed is False
        fake_api.send_transac_email.assert_not_called()

        # 2. Allowlisted exact email and domain are allowed in non-prod
        allowed_exact = await service.send_email(
            to_email="qa@shopsoma.com",
            to_name="QA",
            subject="Test",
            html_content="<p>Test</p>",
        )
        assert allowed_exact is True
        assert fake_api.send_transac_email.call_count == 1

        allowed_domain = await service.send_email(
            to_email="tester@internal.test",
            to_name="Tester",
            subject="Test",
            html_content="<p>Test</p>",
        )
        assert allowed_domain is True
        assert fake_api.send_transac_email.call_count == 2

        # 3. Production sends to real vendor emails without restriction
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        prod_sent = await service.send_email(
            to_email="jacklynnwandison@gmail.com",
            to_name="Coal by Jacklyn",
            subject="Real Production Order",
            html_content="<p>Real</p>",
        )
        assert prod_sent is True
        assert fake_api.send_transac_email.call_count == 3

    # 4. VendorNotificationService records email_sent=False when non-prod guard suppresses email
    monkeypatch.setattr(settings, "ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "ALLOW_NON_PROD_EXTERNAL_EMAILS", False)
    monkeypatch.setattr(settings, "NON_PROD_EMAIL_ALLOWLIST", "")

    vendor = vendor_user["vendor"]
    order = Order(
        id=uuid4(),
        order_number="SHP-STAGING-SUPPRESSED",
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
    db_session.add(order)
    await db_session.commit()

    notif_service = VendorNotificationService(service)
    await notif_service.send_order_notification(
        db=db_session,
        vendor_id=str(vendor.id),
        order_id=str(order.id),
        order_number=order.order_number,
        order_date=datetime.now(timezone.utc),
        items=[{"product_title": "Aifo skirt", "quantity": 2, "vendor_payout": 367500.0}],
        total_payout=367500.0,
        currency="NGN",
    )

    notif = await db_session.scalar(
        select(VendorNotification).where(
            VendorNotification.vendor_id == vendor.id,
            VendorNotification.order_id == order.id,
        )
    )
    assert notif is not None
    assert notif.email_sent is False
    assert notif.email_sent_at is None
