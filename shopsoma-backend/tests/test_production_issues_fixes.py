"""Regression tests for production ShipBubble vendor status sync & non-prod email guard."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import hmac
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import payments
from app.core.config import settings
from app.models.address import Address
from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
from app.models.product import ModerationStatus, Product, ProductStatus
from app.models.shipbubble_shipment import ShipbubbleShipment, ShipbubbleWebhookEvent
from app.models.shipping_rate import ShippingRate
from app.models.stock_payment_persistence import PaymentAttempt, StockReservation
from app.models.vendor_pickup import OrderType, PickupStatus, VendorNotification, VendorPickup
from app.services.email_service import EmailService
from app.services.orders.fulfillment_sync import (
    can_apply_carrier_status_transition,
    resolve_effective_item_fulfillment_status,
)
from app.services.shipbubble_service import ShipBubbleError
from app.services.shipping.capabilities import DomesticShippingCapabilities
from app.services.shipping.carrier_reconciliation import reconcile_active_carrier_shipments_once
from app.services.shipping.shipbubble_tracking import sync_shipbubble_shipment_status
from app.services.vendor_notification_service import VendorNotificationService
from tests.conftest import TestSessionLocal


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


@pytest.mark.asyncio
async def test_shipbubble_unmatched_webhook_surfaces_status_and_retries(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    monkeypatch,
    caplog,
):
    api_key = "sb_sandbox_unmatched_wh_key"
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", api_key)

    def _sign(body: bytes) -> str:
        return hmac.new(api_key.encode("utf-8"), body, hashlib.sha512).hexdigest()

    # 1. Missing order_id -> 422 and status='unmatched'
    missing_payload = json.dumps(
        {"event": "shipment.status.changed", "status": "in_transit"}
    ).encode("utf-8")
    missing_resp = await client.post(
        "/api/v1/shipping/webhooks/shipbubble",
        content=missing_payload,
        headers={"x-ship-signature": _sign(missing_payload)},
    )
    assert missing_resp.status_code == 422
    assert missing_resp.json()["status"] == "unmatched"
    assert missing_resp.json()["matched"] is False

    # 2. Unknown shipbubble_order_id -> 404, warning logged, status='unmatched'
    unknown_payload = json.dumps(
        {"event": "shipment.status.changed", "order_id": "SB-UNKNOWN-999", "status": "in_transit"}
    ).encode("utf-8")
    with caplog.at_level(logging.WARNING):
        unknown_resp = await client.post(
            "/api/v1/shipping/webhooks/shipbubble",
            content=unknown_payload,
            headers={"x-ship-signature": _sign(unknown_payload)},
        )
    assert unknown_resp.status_code == 404
    assert unknown_resp.json()["status"] == "unmatched"
    assert unknown_resp.json()["matched"] is False
    assert unknown_resp.json()["shipbubble_order_id"] == "SB-UNKNOWN-999"
    assert any("SB-UNKNOWN-999" in rec.message for rec in caplog.records)

    unmatched_event = await db_session.scalar(
        select(ShipbubbleWebhookEvent).where(ShipbubbleWebhookEvent.event_id == "SB-UNKNOWN-999")
    )
    assert unmatched_event is not None
    assert unmatched_event.status == "unmatched"
    assert unmatched_event.error_message is not None

    # 3. Once the shipment exists, replaying the previously unmatched payload succeeds
    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Retry Webhook Dress",
        base_price=Decimal("20000.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid4(),
        order_number="SHP-20261123-WHRETRY",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("20000.00"),
        shipping_cost=Decimal("2500.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("22500.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.PICKUP_SCHEDULED,
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        unit_price=Decimal("20000.00"),
        quantity=1,
        subtotal=Decimal("20000.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("2000.00"),
        vendor_payout=Decimal("18000.00"),
        fulfillment_status=FulfillmentStatus.PICKUP_SCHEDULED,
    )
    db_session.add(item)
    await db_session.flush()

    pickup = VendorPickup(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        order_id=order.id,
        order_item_id=item.id,
        order_type=OrderType.RTW,
        status=PickupStatus.SCHEDULED,
    )
    shipment = ShipbubbleShipment(
        id=uuid4(),
        order_id=order.id,
        request_token="tok_wh_retry",
        courier_id="gigl",
        service_code="gigl",
        courier_name="GIG Logistics",
        shipbubble_order_id="SB-UNKNOWN-999",
        status="pending",
        shipping_fee=Decimal("2500.00"),
        currency="NGN",
    )
    db_session.add_all([pickup, shipment])
    await db_session.commit()

    replay_resp = await client.post(
        "/api/v1/shipping/webhooks/shipbubble",
        content=unknown_payload,
        headers={"x-ship-signature": _sign(unknown_payload)},
    )
    assert replay_resp.status_code == 200
    assert replay_resp.json()["status"] == "ok"

    await db_session.refresh(unmatched_event)
    await db_session.refresh(order)
    await db_session.refresh(item)
    await db_session.refresh(pickup)
    assert unmatched_event.status == "processed"
    assert order.fulfillment_status == FulfillmentStatus.IN_TRANSIT
    assert item.fulfillment_status == FulfillmentStatus.IN_TRANSIT
    assert pickup.status == PickupStatus.SHIPPED_TO_CUSTOMER
    assert pickup.actual_pickup_date is not None


@pytest.mark.asyncio
async def test_manual_tracking_sync_errors_honestly_on_unbooked_and_provider_error(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
):
    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Sync Honesty Coat",
        base_price=Decimal("30000.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid4(),
        order_number="SHP-20261123-SYNCHONEST",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("30000.00"),
        shipping_cost=Decimal("2000.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("32000.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.PICKUP_SCHEDULED,
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        unit_price=Decimal("30000.00"),
        quantity=1,
        subtotal=Decimal("30000.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("3000.00"),
        vendor_payout=Decimal("27000.00"),
        fulfillment_status=FulfillmentStatus.PICKUP_SCHEDULED,
    )
    db_session.add(item)
    await db_session.flush()

    pickup = VendorPickup(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        order_id=order.id,
        order_item_id=item.id,
        order_type=OrderType.RTW,
        status=PickupStatus.SCHEDULED,
    )
    db_session.add(pickup)
    await db_session.commit()

    # 1. No ShipbubbleShipment linked -> 409 Conflict
    unbooked_resp = await client.post(
        f"/api/v1/orders/{order.id}/tracking/sync",
        headers=admin_user["headers"],
    )
    assert unbooked_resp.status_code == 409
    assert "no booked ShipBubble shipment" in unbooked_resp.json()["detail"]

    shipment = ShipbubbleShipment(
        id=uuid4(),
        order_id=order.id,
        request_token="tok_sync_honest",
        courier_id="test_1_courier",
        service_code="test_1_courier",
        courier_name="Bubble Express",
        shipbubble_order_id="SB-HONEST-001",
        status="pending",
        shipping_fee=Decimal("2000.00"),
        currency="NGN",
    )
    db_session.add(shipment)
    await db_session.commit()

    # 2. Provider error -> 502 Bad Gateway
    failing_service = AsyncMock()
    failing_service.track_shipments.side_effect = ShipBubbleError("upstream timeout")
    with patch(
        "app.services.shipping.shipbubble_tracking.get_shipbubble_service",
        return_value=failing_service,
    ):
        err_resp = await client.post(
            f"/api/v1/orders/{order.id}/tracking/sync",
            headers=admin_user["headers"],
        )
    assert err_resp.status_code == 502
    assert "upstream timeout" in err_resp.json()["detail"]

    # 3. Empty provider response -> 502 Bad Gateway
    empty_service = AsyncMock()
    empty_service.track_shipments.return_value = []
    with patch(
        "app.services.shipping.shipbubble_tracking.get_shipbubble_service",
        return_value=empty_service,
    ):
        empty_resp = await client.post(
            f"/api/v1/orders/{order.id}/tracking/sync",
            headers=admin_user["headers"],
        )
    assert empty_resp.status_code == 502

    # 4. Successful provider sync -> 200 with sync_result and aligned pickup/item
    ok_service = AsyncMock()
    ok_service.track_shipments.return_value = [{"status": "in_transit"}]
    with patch(
        "app.services.shipping.shipbubble_tracking.get_shipbubble_service",
        return_value=ok_service,
    ):
        ok_resp = await client.post(
            f"/api/v1/orders/{order.id}/tracking/sync",
            headers=admin_user["headers"],
        )
    assert ok_resp.status_code == 200
    assert ok_resp.json()["sync_result"] == {"synced": True}

    await db_session.refresh(order)
    await db_session.refresh(item)
    await db_session.refresh(pickup)
    assert order.fulfillment_status == FulfillmentStatus.IN_TRANSIT
    assert item.fulfillment_status == FulfillmentStatus.IN_TRANSIT
    assert pickup.status == PickupStatus.SHIPPED_TO_CUSTOMER
    assert pickup.actual_pickup_date is not None


@pytest.mark.asyncio
async def test_admin_backward_status_change_requires_confirmation_and_keeps_items_and_pickups_in_step(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
):
    first_delivered_at = datetime(2026, 11, 20, 8, 55, 44, tzinfo=timezone.utc)
    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Backward Guard Top",
        base_price=Decimal("15000.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid4(),
        order_number="SHP-20261123-BACKWARD",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("15000.00"),
        shipping_cost=Decimal("1000.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("16000.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        delivered_at=first_delivered_at,
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        unit_price=Decimal("15000.00"),
        quantity=1,
        subtotal=Decimal("15000.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("1500.00"),
        vendor_payout=Decimal("13500.00"),
        fulfillment_status=FulfillmentStatus.DELIVERED,
    )
    db_session.add(item)
    await db_session.flush()

    pickup = VendorPickup(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        order_id=order.id,
        order_item_id=item.id,
        order_type=OrderType.RTW,
        status=PickupStatus.COMPLETED,
        actual_pickup_date=first_delivered_at - timedelta(hours=2),
        completed_at=first_delivered_at,
    )
    db_session.add(pickup)
    await db_session.commit()

    # 1. Unconfirmed backward move -> 409 Conflict
    blocked_resp = await client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        json={"fulfillment_status": "in_transit"},
        headers=admin_user["headers"],
    )
    assert blocked_resp.status_code == 409

    # 2. confirm_backward=True without admin_notes reason -> 409 Conflict
    missing_reason_resp = await client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        json={"fulfillment_status": "in_transit", "confirm_backward": True},
        headers=admin_user["headers"],
    )
    assert missing_reason_resp.status_code == 409

    # 3. Confirmed backward move with reason -> 200 OK and rolls back item + pickup in step
    confirmed_resp = await client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        json={
            "fulfillment_status": "in_transit",
            "confirm_backward": True,
            "admin_notes": "Customer reported non-delivery; courier re-attempting",
        },
        headers=admin_user["headers"],
    )
    assert confirmed_resp.status_code == 200

    await db_session.refresh(order)
    await db_session.refresh(item)
    await db_session.refresh(pickup)
    assert order.fulfillment_status == FulfillmentStatus.IN_TRANSIT
    assert order.delivered_at == first_delivered_at
    assert item.fulfillment_status == FulfillmentStatus.IN_TRANSIT
    assert pickup.status == PickupStatus.SHIPPED_TO_CUSTOMER
    assert pickup.completed_at is None

    vendor_detail = await client.get(
        f"/api/v1/vendor/orders/{order.id}",
        headers=vendor_user["headers"],
    )
    assert vendor_detail.status_code == 200
    assert vendor_detail.json()["fulfillment_status"] == "in_transit"
    assert vendor_detail.json()["items"][0]["fulfillment_status"] == "in_transit"


@pytest.mark.asyncio
async def test_simulator_picked_up_sets_actual_pickup_date_and_advances_pickup(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
    monkeypatch,
):
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", "sb_sandbox_simulator_test")

    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Sim Track Jacket",
        base_price=Decimal("25000.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid4(),
        order_number="SHP-20261123-SIMSYNC",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("25000.00"),
        shipping_cost=Decimal("1000.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("26000.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.PICKUP_SCHEDULED,
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        unit_price=Decimal("25000.00"),
        quantity=1,
        subtotal=Decimal("25000.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("2500.00"),
        vendor_payout=Decimal("22500.00"),
        fulfillment_status=FulfillmentStatus.PICKUP_SCHEDULED,
    )
    db_session.add(item)
    await db_session.flush()

    pickup = VendorPickup(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        order_id=order.id,
        order_item_id=item.id,
        order_type=OrderType.RTW,
        status=PickupStatus.SCHEDULED,
        actual_pickup_date=None,
    )
    shipment = ShipbubbleShipment(
        id=uuid4(),
        order_id=order.id,
        request_token="tok_sim_sync",
        courier_id="test_1_courier",
        service_code="test_1_courier",
        courier_name="Bubble Express",
        shipbubble_order_id="SB-SIM-001",
        status="pending",
        shipping_fee=Decimal("1000.00"),
        currency="NGN",
    )
    db_session.add_all([pickup, shipment])
    await db_session.commit()

    fake_sb = AsyncMock()
    fake_sb.simulate_webhook.return_value = {"status": "success"}
    with patch("app.services.shipbubble_service.get_shipbubble_service", return_value=fake_sb):
        picked_resp = await client.post(
            f"/api/v1/orders/{order.id}/tracking/simulate",
            json={"status": "picked_up"},
            headers=admin_user["headers"],
        )
        assert picked_resp.status_code == 200

        await db_session.refresh(order)
        await db_session.refresh(item)
        await db_session.refresh(pickup)
        assert order.fulfillment_status == FulfillmentStatus.PICKED_UP
        assert item.fulfillment_status == FulfillmentStatus.PICKED_UP
        assert pickup.status == PickupStatus.IN_TRANSIT
        assert pickup.actual_pickup_date is not None

        transit_resp = await client.post(
            f"/api/v1/orders/{order.id}/tracking/simulate",
            json={"status": "in_transit"},
            headers=admin_user["headers"],
        )
        assert transit_resp.status_code == 200

        await db_session.refresh(pickup)
        assert pickup.status == PickupStatus.SHIPPED_TO_CUSTOMER

        # Backward simulate must be rejected
        backward_sim = await client.post(
            f"/api/v1/orders/{order.id}/tracking/simulate",
            json={"status": "picked_up"},
            headers=admin_user["headers"],
        )
        assert backward_sim.status_code == 409


def test_fresh_paid_rtw_order_with_placeholder_schedule_stays_order_received():
    order = SimpleNamespace(fulfillment_status=FulfillmentStatus.ORDER_RECEIVED)
    item = SimpleNamespace(
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        inventory_policy="stock_managed",
    )
    placeholder_pickup = SimpleNamespace(
        status=PickupStatus.SCHEDULED,
        ready_for_pickup_at=None,
        pickup_window_start=None,
        scheduled_pickup_date=datetime.now(timezone.utc) + timedelta(hours=48),
        actual_pickup_date=None,
    )
    assert (
        resolve_effective_item_fulfillment_status(item, order, placeholder_pickup)
        == FulfillmentStatus.ORDER_RECEIVED
    )

    explicit_window_pickup = SimpleNamespace(
        status=PickupStatus.SCHEDULED,
        ready_for_pickup_at=None,
        pickup_window_start=datetime.now(timezone.utc) + timedelta(hours=2),
        scheduled_pickup_date=datetime.now(timezone.utc) + timedelta(hours=48),
        actual_pickup_date=None,
    )
    assert (
        resolve_effective_item_fulfillment_status(item, order, explicit_window_pickup)
        == FulfillmentStatus.PICKUP_SCHEDULED
    )


@pytest.mark.usefixtures("enabled_stripe")
@pytest.mark.asyncio
async def test_domestic_checkout_v1_consumed_reservation_allows_order_item_status_sync(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
    monkeypatch,
):
    address = Address(
        id=uuid4(),
        user_id=customer_user["user"].id,
        full_name="Domestic Buyer",
        phone_number="08000000000",
        address_line1="10 Admiralty Way",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
    )
    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Domestic Cohort Tunic",
        description="Trigger regression guard item",
        base_price=Decimal("40000.00"),
        currency="NGN",
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    rate = ShippingRate(
        id=uuid4(),
        name="Standard Lagos",
        description="2-4 days",
        base_rate=Decimal("2000.00"),
        country="Nigeria",
        state="Lagos",
        min_delivery_days=2,
        max_delivery_days=4,
        is_active=True,
        is_default=True,
        priority=0,
    )
    db_session.add_all([address, product, rate])
    await db_session.commit()

    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST",
        str(customer_user["user"].id),
    )
    monkeypatch.setattr(
        payments,
        "domestic_shipping_capabilities",
        lambda _settings: DomesticShippingCapabilities(True, True, False),
    )
    monkeypatch.setattr(settings, "STRIPE_SECRET_KEY", "sk_test_domestic_sync")
    monkeypatch.setattr(payments.stripe, "api_key", "sk_test_domestic_sync")

    created = await client.post(
        "/api/v1/orders",
        headers=customer_user["headers"],
        json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address_id": str(address.id),
            "currency": "NGN",
        },
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]

    est_resp = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates",
        headers={
            **customer_user["headers"],
            "X-Idempotency-Key": f"est-{uuid4()}",
        },
    )
    assert est_resp.status_code == 201, est_resp.text
    est = est_resp.json()
    sel_resp = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{est['id']}/options/{est['options'][0]['id']}/select",
        headers={
            **customer_user["headers"],
            "X-Idempotency-Key": f"sel-{uuid4()}",
        },
    )
    assert sel_resp.status_code == 200, sel_resp.text

    customer_user["user"].stripe_customer_id = "cus_domestic_sync"
    await db_session.commit()

    pi_id = f"pi_dom_{uuid4().hex[:10]}"
    monkeypatch.setattr(
        payments.stripe.PaymentIntent,
        "create",
        lambda **_kwargs: SimpleNamespace(id=pi_id, client_secret=f"secret_{pi_id}"),
    )
    init_resp = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": order_id,
            "email": customer_user["user"].email,
            "payment_gateway": "stripe",
            "currency": "NGN",
        },
    )
    assert init_resp.status_code == 200, init_resp.text

    order_uuid = UUID(order_id)
    db_session.expire_all()
    attempt = await db_session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.order_id == order_uuid)
    )
    assert attempt is not None

    intent = SimpleNamespace(
        id=pi_id,
        status="succeeded",
        amount=int(Decimal(attempt.amount) * 100),
        amount_received=int(Decimal(attempt.amount) * 100),
        currency=attempt.currency.lower(),
        metadata={"shopsoma_payment_reference": attempt.provider_reference},
    )
    monkeypatch.setattr(payments.stripe.PaymentIntent, "retrieve", lambda _val: intent)
    monkeypatch.setattr(
        payments.email_service,
        "send_payment_receipt_email",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        payments,
        "send_account_claim_email_if_guest",
        AsyncMock(return_value=True),
    )
    verify_resp = await client.post(
        "/api/v1/payments/verify",
        json={"payment_gateway": "stripe", "payment_intent_id": pi_id},
    )
    assert verify_resp.status_code == 200, verify_resp.text

    db_session.expire_all()
    order_row = await db_session.get(Order, order_uuid)
    reservation = await db_session.scalar(
        select(StockReservation).where(StockReservation.order_id == order_uuid)
    )
    assert order_row.workflow_cohort == "domestic_checkout_v1"
    assert order_row.checkout_prerequisites_completed_at is not None
    assert order_row.payment_status == PaymentStatus.PAID
    assert reservation.state == "consumed"

    # Admin advancing to in_transit and delivered must update stored order_items.fulfillment_status in PostgreSQL
    transit_resp = await client.patch(
        f"/api/v1/admin/orders/{order_id}/status",
        json={"fulfillment_status": "in_transit"},
        headers=admin_user["headers"],
    )
    assert transit_resp.status_code == 200, transit_resp.text

    delivered_resp = await client.patch(
        f"/api/v1/admin/orders/{order_id}/status",
        json={"fulfillment_status": "delivered"},
        headers=admin_user["headers"],
    )
    assert delivered_resp.status_code == 200, delivered_resp.text

    db_session.expire_all()
    item_row = await db_session.scalar(
        select(OrderItem).where(OrderItem.order_id == order_uuid)
    )
    assert item_row.fulfillment_status == FulfillmentStatus.DELIVERED


@pytest.mark.asyncio
async def test_scheduled_carrier_reconciliation_advances_active_orders_and_isolates_errors(
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    monkeypatch,
):
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", "sb_sandbox_reconcile_key")

    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Reconcile Linen Set",
        base_price=Decimal("22000.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()

    async def _seed_order(
        order_number: str,
        order_status: FulfillmentStatus,
        sb_id: str,
        sb_status: str,
        pickup_status: PickupStatus,
    ) -> tuple[Order, OrderItem, VendorPickup]:
        ord_row = Order(
            id=uuid4(),
            order_number=order_number,
            customer_id=customer_user["user"].id,
            subtotal=Decimal("22000.00"),
            shipping_cost=Decimal("1000.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("23000.00"),
            payment_status=PaymentStatus.PAID,
            fulfillment_status=order_status,
            delivered_at=datetime.now(timezone.utc) if order_status == FulfillmentStatus.DELIVERED else None,
        )
        db_session.add(ord_row)
        await db_session.flush()

        item_row = OrderItem(
            id=uuid4(),
            order_id=ord_row.id,
            product_id=product.id,
            vendor_id=vendor_user["vendor"].id,
            product_title=product.title,
            unit_price=Decimal("22000.00"),
            quantity=1,
            subtotal=Decimal("22000.00"),
            commission_rate=Decimal("10.00"),
            commission_amount=Decimal("2200.00"),
            vendor_payout=Decimal("19800.00"),
            fulfillment_status=order_status,
        )
        db_session.add(item_row)
        await db_session.flush()

        pickup_row = VendorPickup(
            id=uuid4(),
            vendor_id=vendor_user["vendor"].id,
            order_id=ord_row.id,
            order_item_id=item_row.id,
            order_type=OrderType.RTW,
            status=pickup_status,
        )
        shipment_row = ShipbubbleShipment(
            id=uuid4(),
            order_id=ord_row.id,
            request_token=f"tok_{sb_id}",
            courier_id="test_1_courier",
            service_code="test_1_courier",
            courier_name="Bubble Express",
            shipbubble_order_id=sb_id,
            status=sb_status,
            shipping_fee=Decimal("1000.00"),
            currency="NGN",
        )
        db_session.add_all([pickup_row, shipment_row])
        return ord_row, item_row, pickup_row

    ok_order, ok_item, ok_pickup = await _seed_order(
        "SHP-RECON-OK",
        FulfillmentStatus.PICKUP_SCHEDULED,
        "SB-RECON-OK",
        "pending",
        PickupStatus.SCHEDULED,
    )
    err_order, _, _ = await _seed_order(
        "SHP-RECON-ERR",
        FulfillmentStatus.PICKED_UP,
        "SB-RECON-ERR",
        "picked_up",
        PickupStatus.IN_TRANSIT,
    )
    await _seed_order(
        "SHP-RECON-DONE",
        FulfillmentStatus.DELIVERED,
        "SB-RECON-DONE",
        "completed",
        PickupStatus.COMPLETED,
    )
    await db_session.commit()
    ok_order_id = ok_order.id
    ok_item_id = ok_item.id
    ok_pickup_id = ok_pickup.id
    err_order_id = err_order.id

    polled_ids: list[str] = []

    async def _track_shipments(order_ids: list[str]):
        polled_ids.extend(order_ids)
        if order_ids == ["SB-RECON-OK"]:
            return [{"status": "in_transit"}]
        raise ShipBubbleError("gateway timeout")

    fake_service = AsyncMock()
    fake_service.track_shipments.side_effect = _track_shipments

    with patch(
        "app.services.shipping.shipbubble_tracking.get_shipbubble_service",
        return_value=fake_service,
    ):
        summary = await reconcile_active_carrier_shipments_once(session_factory=TestSessionLocal)

    assert summary == {
        "scanned": 2,
        "updated": 1,
        "unchanged": 0,
        "errors": 1,
        "skipped_unconfigured": 0,
    }
    assert set(polled_ids) == {"SB-RECON-OK", "SB-RECON-ERR"}
    assert "SB-RECON-DONE" not in polled_ids

    db_session.expire_all()
    refreshed_ok_order = await db_session.get(Order, ok_order_id)
    refreshed_ok_item = await db_session.get(OrderItem, ok_item_id)
    refreshed_ok_pickup = await db_session.get(VendorPickup, ok_pickup_id)
    refreshed_err_order = await db_session.get(Order, err_order_id)
    assert refreshed_ok_order.fulfillment_status == FulfillmentStatus.IN_TRANSIT
    assert refreshed_ok_item.fulfillment_status == FulfillmentStatus.IN_TRANSIT
    assert refreshed_ok_pickup.status == PickupStatus.SHIPPED_TO_CUSTOMER
    assert refreshed_ok_pickup.actual_pickup_date is not None
    assert refreshed_err_order.fulfillment_status == FulfillmentStatus.PICKED_UP
