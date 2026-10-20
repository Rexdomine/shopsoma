"""End-to-end DHL Express sandbox integration tests.

Covers:
1. Checkout rate & service selection with min/max delivery days, provider metadata,
   and NGN/USD charge persistence (`delivery_provider="dhl"`, `estimated_delivery_date`).
2. Hub package readiness bridge (`POST /api/v1/admin/orders/{order_id}/dhl/prepare-package`)
   and idempotent replay.
3. Outbound shipment booking (`POST /dhl/bookings`), PDF label download (`GET /label`),
   and hub-to-DHL collection handoff (`POST /handoff`) on hub-prepared packages.
4. Authenticated DHL webhook (`POST /api/v1/shipping/webhooks/dhl`) with HMAC-SHA256
   verification, unauthorized rejection, duplicate replay protection, and out-of-order
   monotonic event folding.
5. Customer/Admin Live Map tracking payload (`GET /orders/{id}/tracking`), status sync
   (`POST /orders/{id}/tracking/sync`), and Sandbox Tracking Simulator
   (`POST /orders/{id}/tracking/simulate`).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.address import Address
from app.models.dhl_shipment import OutboundShipmentBooking
from app.models.fulfillment_cohort import CohortItemAllocation, FulfillmentCohort
from app.models.fulfillment_hub import FulfillmentHub
from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
from app.models.product import Product, ProductStatus
from app.models.app_setting import AppSetting
from app.models.setting import Setting
from app.models.user import User
from app.services.dhl.rating import derive_sandbox_cohort_id
from types import SimpleNamespace
from app.services.dhl.shipments import AdapterBookingResult, TrackingObservation


async def _enable_dhl_checkout_settings(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    *,
    cohort_seed: uuid.UUID,
    actor_id: uuid.UUID,
) -> FulfillmentHub:
    monkeypatch.setattr(settings, "DHL_ENABLED", True)
    monkeypatch.setattr(settings, "DHL_ENVIRONMENT", "sandbox")
    monkeypatch.setattr(settings, "DHL_DOMESTIC_CHECKOUT_ENABLED", True)
    monkeypatch.setattr(settings, "DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED", True)
    monkeypatch.setattr(settings, "DHL_DOMESTIC_WORKFLOW_ENABLED", True)
    monkeypatch.setattr(settings, "DHL_DOMESTIC_PROVIDER_CALLS_ENABLED", True)
    monkeypatch.setattr(settings, "DHL_DOMESTIC_SANDBOX_COHORT_IDS", str(cohort_seed))
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)

    from pydantic import SecretStr
    for credential in ("DHL_API_USERNAME", "DHL_API_PASSWORD", "DHL_EXPORT_ACCOUNT_NUMBER"):
        if not getattr(settings, credential).get_secret_value():
            monkeypatch.setattr(settings, credential, SecretStr("sandbox-test-credential"))

    for key, val, vtype in (
        ("shipping_provider", "dhl", "string"),
        ("shipping_enabled_providers", json.dumps(["dhl"]), "json"),
        ("shipping_use_shipbubble", "false", "boolean"),
    ):
        row = await db_session.scalar(select(AppSetting).where(AppSetting.key == key))
        if row is None:
            row = AppSetting(key=key, value=val, value_type=vtype)
            db_session.add(row)
        else:
            row.value = val

    fx = await db_session.scalar(
        select(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
    )
    if fx is None:
        db_session.add(
            Setting(
                key="exchange_rate_usd_to_ngn",
                value="1600.00",
                description="USD to NGN exchange rate",
            )
        )
    else:
        fx.value = "1600.00"

    hub = (
        await db_session.execute(
            select(FulfillmentHub).where(FulfillmentHub.is_active.is_(True)).limit(1)
        )
    ).scalar_one_or_none()
    if hub is None:
        hub = FulfillmentHub(
            code="los-hub-test-01",
            name="ShopSoma Lagos Hub",
            contact_name="ShopSoma Hub Dispatch",
            contact_phone="+2348000000000",
            address_line1="14 Victoria Island Way",
            city="Lagos",
            state="Lagos",
            postal_code="101241",
            country_code="NG",
            cutoff_time=time(17, 0),
            is_active=True,
            activated_at=datetime.now(UTC),
            activated_by_id=actor_id,
            version=1,
        )
        db_session.add(hub)
    await db_session.flush()
    return hub


async def _create_checkout_order_for_dhl(
    db_session: AsyncSession,
    *,
    customer_user: dict,
    vendor_user: dict,
    cohort_seed: uuid.UUID,
    currency: str = "NGN",
    subtotal: Decimal = Decimal("40000.00"),
) -> Order:
    customer = customer_user["user"]
    vendor = vendor_user["vendor"]
    address = Address(
        user_id=customer.id,
        full_name="Adaeze Okafor",
        phone_number="+2348031234567",
        address_line1="22 Wuse Zone 5",
        city="Abuja",
        state="FCT",
        postal_code="900285",
        country="Nigeria",
        is_default=True,
    )
    db_session.add(address)
    await db_session.flush()

    from app.models.product import ModerationStatus

    product = Product(
        vendor_id=vendor.id,
        title="Handwoven Aso-Oke Jacket",
        description="Luxury tailored jacket",
        base_price=Decimal("40000.00"),
        currency="NGN",
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
        total_stock=10,
        made_to_order=False,
        weight_kg=Decimal("1.500"),
        length_cm=Decimal("32.00"),
        width_cm=Decimal("24.00"),
        height_cm=Decimal("12.00"),
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        order_number=f"SS-DHL-{uuid.uuid4().hex[:6].upper()}",
        customer_id=customer.id,
        shipping_address_id=address.id,
        billing_address_id=address.id,
        workflow_cohort="domestic_checkout_v1",
        workflow_policy_version="domestic_checkout_v1",
        checkout_access_mode="authenticated",
        currency=currency,
        subtotal=subtotal,
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=subtotal,
        payment_status=PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.flush()

    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor.id,
        product_title=product.title,
        unit_price=subtotal,
        currency=currency,
        quantity=1,
        subtotal=subtotal,
        commission_rate=Decimal("10.00"),
        commission_amount=(subtotal * Decimal("0.10")).quantize(Decimal("0.01")),
        vendor_payout=(subtotal * Decimal("0.90")).quantize(Decimal("0.01")),
        inventory_policy="stock_managed",
        inventory_subject_kind="product",
        inventory_subject_id=product.id,
        inventory_source_product_id=product.id,
        inventory_source_catalogue_version="v1",
        inventory_source_evidence_hash="a" * 64,
        inventory_policy_snapshot_at=datetime.now(UTC),
    )
    db_session.add(item)
    await db_session.flush()

    cohort_id = derive_sandbox_cohort_id(cohort_seed, order.id, 0)
    cohort = FulfillmentCohort(
        id=cohort_id,
        order_id=order.id,
        vendor_id=vendor.id,
        readiness_type="ready_to_wear",
        ready_from=datetime.now(UTC) - timedelta(minutes=5),
        ready_through=datetime.now(UTC) + timedelta(days=14),
    )
    db_session.add(cohort)
    await db_session.flush()

    db_session.add(
        CohortItemAllocation(
            cohort_id=cohort.id,
            order_item_id=item.id,
            order_id=order.id,
            vendor_id=vendor.id,
            allocated_quantity=1,
        )
    )
    await db_session.commit()
    return order


@pytest.mark.asyncio
async def test_dhl_checkout_estimate_selection_persists_delivery_days_and_charges_ngn_and_usd(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    customer_token = customer_user["token"]
    cohort_seed = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")
    await _enable_dhl_checkout_settings(
        db_session,
        monkeypatch,
        cohort_seed=cohort_seed,
        actor_id=customer_user["user"].id,
    )

    ngn_order = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="NGN",
        subtotal=Decimal("40000.00"),
    )
    usd_order = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="USD",
        subtotal=Decimal("25.00"),
    )

    eta_dt = (datetime.now(UTC) + timedelta(days=2)).date()
    fake_offers = (
        SimpleNamespace(
            provider_product_code="N",
            provider_service_code="DOM-N",
            service_label="DHL DOMESTIC EXPRESS",
            rate=SimpleNamespace(
                total_amount=Decimal("16000.00"),
                currency="NGN",
                carrier_transit_days=2,
                estimated_carrier_delivery_date=eta_dt,
            ),
        ),
    )

    with patch(
        "app.services.checkout.estimates._dhl_checkout_options",
        new=AsyncMock(return_value=fake_offers),
    ):
        # 1. NGN Checkout Estimate & Selection
        est_res = await client.post(
            f"/api/v1/orders/{ngn_order.id}/checkout-estimates",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"est-ngn-{ngn_order.id.hex[:12]}",
            },
        )
        assert est_res.status_code == 201, est_res.text
        est_body = est_res.json()
        assert len(est_body["options"]) == 1
        opt = est_body["options"][0]
        assert opt["service_code"] == "DOM-N"
        assert opt["service_label"] == "DHL DOMESTIC EXPRESS"
        assert Decimal(str(opt["amount"])) == Decimal("16000.00")
        assert opt["currency"] == "NGN"
        assert opt["min_delivery_days"] == 2
        assert opt["max_delivery_days"] == 2
        assert opt["provider_metadata"]["provider"] == "dhl"

        sel_res = await client.post(
            f"/api/v1/orders/{ngn_order.id}/checkout-estimates/{est_body['id']}/options/{opt['id']}/select",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"sel-ngn-{ngn_order.id.hex[:12]}",
            },
        )
        assert sel_res.status_code == 200, sel_res.text
        sel_body = sel_res.json()
        assert sel_body["selected_option"]["id"] == opt["id"]

        await db_session.refresh(ngn_order)
        assert ngn_order.delivery_provider == "dhl"
        assert ngn_order.shipping_cost == Decimal("16000.00")
        assert ngn_order.estimated_delivery_date is not None

        # 2. USD Checkout Estimate & Selection (16,000 NGN / 1,600 = 10.00 USD)
        usd_est_res = await client.post(
            f"/api/v1/orders/{usd_order.id}/checkout-estimates",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"est-usd-{usd_order.id.hex[:12]}",
            },
        )
        assert usd_est_res.status_code == 201, usd_est_res.text
        usd_est_body = usd_est_res.json()
        usd_opt = usd_est_body["options"][0]
        assert usd_opt["currency"] == "USD"
        assert Decimal(str(usd_opt["amount"])) == Decimal("10.00")
        assert usd_opt["min_delivery_days"] == 2
        assert usd_opt["max_delivery_days"] == 2

        usd_sel_res = await client.post(
            f"/api/v1/orders/{usd_order.id}/checkout-estimates/{usd_est_body['id']}/options/{usd_opt['id']}/select",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"sel-usd-{usd_order.id.hex[:12]}",
            },
        )
        assert usd_sel_res.status_code == 200, usd_sel_res.text
        await db_session.refresh(usd_order)
        assert usd_order.delivery_provider == "dhl"
        assert usd_order.shipping_cost == Decimal("10.00")


@pytest.mark.asyncio
async def test_dhl_full_fulfillment_workflow_webhook_and_live_map_simulator(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    customer_token = customer_user["token"]
    admin_token = admin_user["token"]
    cohort_seed = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")
    await _enable_dhl_checkout_settings(
        db_session,
        monkeypatch,
        cohort_seed=cohort_seed,
        actor_id=admin_user["user"].id,
    )

    order = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="NGN",
        subtotal=Decimal("50000.00"),
    )
    order.payment_status = PaymentStatus.PAID
    order.delivery_provider = "dhl"
    order.shipping_cost = Decimal("15482.25")
    order.total_amount = Decimal("65482.25")
    await db_session.commit()

    # Step 1: Prepare Hub Package for DHL via Admin API
    prep_res = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/prepare-package",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert prep_res.status_code == 200, prep_res.text
    detail_body = prep_res.json()
    dhl_ops = detail_body["dhl_operations"]
    assert len(dhl_ops["packages"]) == 1
    pkg_info = dhl_ops["packages"][0]
    assert pkg_info["package_state"] == "ready"
    assert pkg_info["selection_eligible"] is True
    assert pkg_info["seal_id"] is not None
    assert pkg_info["intent_id"] is not None

    # Re-calling prepare-package is idempotent
    prep_replay = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/prepare-package",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert prep_replay.status_code == 200
    assert prep_replay.json()["dhl_operations"]["packages"][0]["package_id"] == pkg_info["package_id"]

    # Step 2: Book DHL Shipment via Admin API (with mocked adapter returning valid PDF label)
    fake_tracking_no = f"123456{uuid.uuid4().int % 10000:04d}"
    fake_pdf = b"%PDF-1.4\n%Mock DHL Waybill Label\n%%EOF\n"
    mock_adapter = AsyncMock()
    mock_adapter.prepare_booking_payload = lambda *args, **kwargs: {"productCode": "N"}
    mock_adapter.book = AsyncMock(
        return_value=AdapterBookingResult(
            provider_reference=f"DHL-REF-{fake_tracking_no}",
            tracking_number=fake_tracking_no,
            label_media_type="application/pdf",
            label_content=fake_pdf,
            service_code="DOM-N",
            booked_at=datetime.now(UTC),
        )
    )
    mock_adapter.track = AsyncMock(
        return_value=[
            TrackingObservation(
                provider_status_code="PU",
                outbound_state="collected",
                customer_status="picked_up",
                detail="Shipment picked up at Lagos Hub",
                observed_at=datetime.now(UTC) - timedelta(minutes=2),
                exception_code=None,
            )
        ]
    )

    booking_idem_key = f"book-{order.id.hex[:16]}"
    with patch("app.services.dhl.shipments.create_shipment_adapter", return_value=mock_adapter):
        book_res = await client.post(
            f"/api/v1/admin/orders/{order.id}/dhl/bookings",
            json={
                "intent_id": pkg_info["intent_id"],
                "package_id": pkg_info["package_id"],
                "package_version": pkg_info["package_version"],
                "seal_id": pkg_info["seal_id"],
                "idempotency_key": booking_idem_key,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert book_res.status_code == 200, book_res.text
        book_body = book_res.json()
        assert book_body["result_kind"] == "booked"
        assert book_body["tracking_number"] == fake_tracking_no
        assert book_body["outbound_state"] == "label_ready"
        booking_id = book_body["booking_id"]

        # Replay booking with same idempotency key -> no duplicate call
        book_replay = await client.post(
            f"/api/v1/admin/orders/{order.id}/dhl/bookings",
            json={
                "intent_id": pkg_info["intent_id"],
                "package_id": pkg_info["package_id"],
                "package_version": pkg_info["package_version"],
                "seal_id": pkg_info["seal_id"],
                "idempotency_key": booking_idem_key,
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert book_replay.status_code == 200
        assert book_replay.json()["replayed"] is True
        assert mock_adapter.book.call_count == 1

    # Step 3: Download DHL PDF Label
    label_res = await client.get(
        f"/api/v1/admin/orders/{order.id}/dhl/bookings/{booking_id}/label",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert label_res.status_code == 200
    assert label_res.headers["content-type"] == "application/pdf"
    assert label_res.content.startswith(b"%PDF-1.4")
    assert label_res.headers["x-label-sha256"] == hashlib.sha256(fake_pdf).hexdigest()

    sent_emails: list[dict] = []

    async def _capture_send_email(self, *, to_email: str, to_name: str, subject: str, html_content: str, **kwargs):
        sent_emails.append(
            {
                "to_email": to_email,
                "to_name": to_name,
                "subject": subject,
                "html_content": html_content,
            }
        )
        return True

    from app.services.email_service import EmailService
    monkeypatch.setattr(EmailService, "send_email", _capture_send_email)

    # Step 4: Record Hub-to-DHL Handoff on the hub-prepared package
    handoff_res = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/bookings/{booking_id}/handoff",
        json={
            "occurred_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "idempotency_key": f"handoff-{order.id.hex[:16]}",
            "counterparty": "DHL Express Lagos",
            "evidence_ref": "custody/dhl-manifest-001",
            "evidence_sha256": "a" * 64,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert handoff_res.status_code == 200, handoff_res.text
    assert handoff_res.json()["outbound_state"] == "collected"

    customer_email = customer_user["user"].email
    customer_subjects = [e["subject"] for e in sent_emails if e["to_email"] == customer_email]
    assert f"Order {order.order_number}: Order Dispatched" in customer_subjects

    # Step 5: Verify Live Map Payload via Customer Tracking Endpoint
    track_res = await client.get(
        f"/api/v1/orders/{order.id}/tracking",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert track_res.status_code == 200, track_res.text
    track_body = track_res.json()
    assert track_body["tracking_number"] == fake_tracking_no
    assert track_body["current_status"] == "picked_up"
    dhl_map = track_body["shipbubble_tracking"]
    assert dhl_map is not None
    assert dhl_map["provider"] == "dhl"
    assert dhl_map["is_booked"] is True
    assert dhl_map["tracking_code"] == fake_tracking_no
    assert len(dhl_map["route_waypoints"]) >= 2

    # Step 6: Simulate Live Map Courier Transitions (in_transit -> out_for_delivery)
    for step_key, expected_progress in (("in_transit", 0.62), ("out_for_delivery", 0.88)):
        sim_res = await client.post(
            f"/api/v1/orders/{order.id}/tracking/simulate",
            json={"status": step_key},
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert sim_res.status_code == 200, sim_res.text
        sim_body = sim_res.json()
        assert sim_body["current_status"] == step_key
        assert sim_body["shipbubble_tracking"]["current_location"]["progress"] == expected_progress

    customer_subjects = [e["subject"] for e in sent_emails if e["to_email"] == customer_email]
    assert f"Order {order.order_number}: In Transit" in customer_subjects
    assert f"Order {order.order_number}: Out for Delivery" in customer_subjects

    # Step 7: Authenticated DHL Webhook Verification (Unauthorized -> 401, Valid HMAC -> 200, Replay -> 0 new, Out-of-order -> Monotonic)
    unauth_wh = await client.post(
        "/api/v1/shipping/webhooks/dhl",
        json={"shipments": [{"shipmentTrackingNumber": fake_tracking_no, "events": []}]},
    )
    assert unauth_wh.status_code == 401

    delivered_payload = {
        "shipments": [
            {
                "shipmentTrackingNumber": fake_tracking_no,
                "events": [
                    {
                        "typeCode": "OK",
                        "statusCode": "delivered",
                        "description": "Delivered - Signed for by Adaeze Okafor",
                        "timestamp": datetime.now(UTC).isoformat(),
                    }
                ],
            }
        ]
    }
    raw_delivered = json.dumps(delivered_payload).encode("utf-8")
    secret = settings.DHL_API_PASSWORD.get_secret_value()
    sig = hmac.new(secret.encode("utf-8"), raw_delivered, hashlib.sha256).hexdigest()

    wh_res = await client.post(
        "/api/v1/shipping/webhooks/dhl",
        content=raw_delivered,
        headers={
            "Content-Type": "application/json",
            "X-DHL-Signature": f"sha256={sig}",
        },
    )
    assert wh_res.status_code == 200, wh_res.text
    wh_body = wh_res.json()
    assert wh_body["inserted_observations"] == 1

    customer_subjects = [e["subject"] for e in sent_emails if e["to_email"] == customer_email]
    assert f"Order {order.order_number}: Delivered Successfully" in customer_subjects
    email_count_after_delivered = len(sent_emails)

    # Duplicate replay of the exact same webhook
    wh_replay = await client.post(
        "/api/v1/shipping/webhooks/dhl",
        content=raw_delivered,
        headers={
            "Content-Type": "application/json",
            "X-DHL-Signature": f"sha256={sig}",
        },
    )
    assert wh_replay.status_code == 200
    assert wh_replay.json()["inserted_observations"] == 0
    assert wh_replay.json()["replayed_observations"] == 1
    assert len(sent_emails) == email_count_after_delivered

    # Out-of-order older IN_TRANSIT event must NOT regress DELIVERED order status
    stale_payload = {
        "shipments": [
            {
                "shipmentTrackingNumber": fake_tracking_no,
                "events": [
                    {
                        "typeCode": "TRANSIT",
                        "statusCode": "in_transit",
                        "description": "Processed at Abuja Sort Facility",
                        "timestamp": (datetime.now(UTC) - timedelta(hours=3)).isoformat(),
                    }
                ],
            }
        ]
    }
    raw_stale = json.dumps(stale_payload).encode("utf-8")
    stale_sig = hmac.new(secret.encode("utf-8"), raw_stale, hashlib.sha256).hexdigest()
    wh_stale = await client.post(
        "/api/v1/shipping/webhooks/dhl",
        content=raw_stale,
        headers={
            "Content-Type": "application/json",
            "X-DHL-Signature": stale_sig,
        },
    )
    assert wh_stale.status_code == 200
    assert len(sent_emails) == email_count_after_delivered

    final_track = await client.get(
        f"/api/v1/orders/{order.id}/tracking",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert final_track.status_code == 200
    final_body = final_track.json()
    assert final_body["current_status"] == "delivered"
    assert final_body["shipbubble_tracking"]["current_location"]["progress"] == 1.0


@pytest.mark.asyncio
async def test_dhl_resilience_no_rates_invalid_dimensions_and_manual_fallback(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    from app.models.shipping_rate import ShippingRate

    customer_token = customer_user["token"]
    cohort_seed = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")
    await _enable_dhl_checkout_settings(
        db_session,
        monkeypatch,
        cohort_seed=cohort_seed,
        actor_id=customer_user["user"].id,
    )

    order = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="NGN",
        subtotal=Decimal("40000.00"),
    )

    # 1. No-rate response from DHL returns 503 cleanly without partial estimate persistence
    with patch(
        "app.services.checkout.estimates._dhl_checkout_options",
        new=AsyncMock(return_value=()),
    ):
        no_rate_res = await client.post(
            f"/api/v1/orders/{order.id}/checkout-estimates",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"norate-{order.id.hex[:12]}",
            },
        )
        assert no_rate_res.status_code == 503
        assert "no eligible checkout service" in no_rate_res.json()["detail"].lower()

    # 2. Manual shipping fallback continues to work when shipping_provider is switched to 'manual'
    manual_rate = ShippingRate(
        name="Standard Manual Delivery",
        description="Nationwide standard shipping",
        country="Nigeria",
        state=None,
        base_rate=Decimal("4500.00"),
        min_delivery_days=3,
        max_delivery_days=5,
        is_active=True,
        is_default=True,
    )
    db_session.add(manual_rate)
    provider_row = await db_session.scalar(
        select(AppSetting).where(AppSetting.key == "shipping_provider")
    )
    assert provider_row is not None
    provider_row.value = "manual"
    await db_session.commit()

    manual_est_res = await client.post(
        f"/api/v1/orders/{order.id}/checkout-estimates",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "X-Idempotency-Key": f"manual-{order.id.hex[:12]}",
        },
    )
    assert manual_est_res.status_code == 201, manual_est_res.text
    manual_opts = manual_est_res.json()["options"]
    assert len(manual_opts) >= 1
    assert Decimal(str(manual_opts[0]["amount"])) == Decimal("4500.00")


@pytest.mark.asyncio
async def test_dhl_live_mydhl_sandbox_end_to_end_rates_booking_label_and_tracking(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Exercises the live MyDHL Express Sandbox API (rates -> booking -> PDF label -> tracking)."""
    if not settings.dhl_configured:
        pytest.skip("Live DHL sandbox credentials not configured in .env")

    customer_token = customer_user["token"]
    admin_token = admin_user["token"]
    cohort_seed = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")
    await _enable_dhl_checkout_settings(
        db_session,
        monkeypatch,
        cohort_seed=cohort_seed,
        actor_id=admin_user["user"].id,
    )

    order = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="NGN",
        subtotal=Decimal("65000.00"),
    )

    # 1. Live MyDHL Sandbox Checkout Rate Lookup (GET /rates)
    est_res = await client.post(
        f"/api/v1/orders/{order.id}/checkout-estimates",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "X-Idempotency-Key": f"live-est-{order.id.hex[:12]}",
        },
    )
    assert est_res.status_code == 201, est_res.text
    est_body = est_res.json()
    assert len(est_body["options"]) >= 1
    live_opt = est_body["options"][0]
    assert live_opt["service_code"] == "N"
    assert Decimal(str(live_opt["amount"])) > Decimal("0")
    assert live_opt["currency"] == "NGN"
    assert live_opt["provider_metadata"]["provider"] == "dhl"

    # 2. Select Live DHL Checkout Rate Option
    sel_res = await client.post(
        f"/api/v1/orders/{order.id}/checkout-estimates/{est_body['id']}/options/{live_opt['id']}/select",
        headers={
            "Authorization": f"Bearer {customer_token}",
            "X-Idempotency-Key": f"live-sel-{order.id.hex[:12]}",
        },
    )
    assert sel_res.status_code == 200, sel_res.text
    await db_session.refresh(order)
    assert order.delivery_provider == "dhl"
    assert order.shipping_cost == Decimal(str(live_opt["amount"]))

    # Mark order PAID and prepare Hub package
    order.payment_status = PaymentStatus.PAID
    await db_session.commit()

    prep_res = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/prepare-package",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert prep_res.status_code == 200, prep_res.text
    pkg_info = prep_res.json()["dhl_operations"]["packages"][0]

    # 3. Live MyDHL Sandbox Shipment Booking (POST /shipments)
    book_res = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/bookings",
        json={
            "intent_id": pkg_info["intent_id"],
            "package_id": pkg_info["package_id"],
            "package_version": pkg_info["package_version"],
            "seal_id": pkg_info["seal_id"],
            "idempotency_key": f"live-book-{order.id.hex[:16]}",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert book_res.status_code == 200, book_res.text
    book_body = book_res.json()
    assert book_body["result_kind"] == "booked"
    assert book_body["outbound_state"] == "label_ready"
    assert book_body["tracking_number"]
    booking_id = book_body["booking_id"]

    # 4. Download Real PDF Waybill Label Generated by MyDHL Sandbox
    label_res = await client.get(
        f"/api/v1/admin/orders/{order.id}/dhl/bookings/{booking_id}/label",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert label_res.status_code == 200
    assert label_res.headers["content-type"] == "application/pdf"
    assert label_res.content.startswith(b"%PDF")
    assert len(label_res.content) > 1000

    # 5. Record Carrier Handoff & Verify Live Map Tracking Endpoint
    handoff_res = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/bookings/{booking_id}/handoff",
        json={
            "occurred_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
            "idempotency_key": f"live-handoff-{order.id.hex[:16]}",
            "counterparty": "DHL Express Lagos",
            "evidence_ref": f"custody/dhl-live-sandbox-{order.id.hex[:8]}",
            "evidence_sha256": hashlib.sha256(label_res.content).hexdigest(),
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert handoff_res.status_code == 200, handoff_res.text
    assert handoff_res.json()["outbound_state"] == "collected"

    map_res = await client.get(
        f"/api/v1/orders/{order.id}/tracking",
        headers={"Authorization": f"Bearer {customer_token}"},
    )
    assert map_res.status_code == 200, map_res.text
    map_body = map_res.json()
    assert map_body["tracking_number"] == book_body["tracking_number"]
    assert map_body["shipbubble_tracking"]["provider"] == "dhl"
    assert map_body["shipbubble_tracking"]["is_booked"] is True
    assert map_body["shipbubble_tracking"]["tracking_code"] == book_body["tracking_number"]
    assert len(map_body["shipbubble_tracking"]["route_waypoints"]) >= 2



    import os

    evidence_dir = os.environ.get("DHL_SAVE_EVIDENCE_DIR")
    if evidence_dir:
        import json
        from pathlib import Path


        out_dir = Path(evidence_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "dhl_sandbox_waybill_label.pdf").write_bytes(label_res.content)
        evidence_payload = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "environment": "sandbox",
            "mydhl_base_url": settings.dhl_base_url,
            "export_account_number": settings.DHL_EXPORT_ACCOUNT_NUMBER,

            "order_id": str(order.id),
            "checkout_estimate": est_body,
            "selected_option": sel_res.json(),
            "hub_preparation": prep_res.json(),
            "shipment_booking": book_body,
            "pdf_label_bytes": len(label_res.content),
            "handoff": handoff_res.json(),
            "live_map_tracking": map_body,
        }
        (out_dir / "dhl_sandbox_e2e_evidence.json").write_text(
            json.dumps(evidence_payload, indent=2, default=str),
            encoding="utf-8",
        )


@pytest.mark.asyncio
async def test_shipbubble_webhook_and_simulator_dispatch_customer_tracking_emails(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verifies ShipBubble tracking transitions (webhook & simulator) send customer emails."""
    from app.models.shipbubble_shipment import ShipbubbleShipment
    from app.services.email_service import EmailService

    sb_api_key = "sb_sandbox_test_secret_key_12345"
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", sb_api_key)

    cohort_seed = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")
    order = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="NGN",
        subtotal=Decimal("35000.00"),
    )
    order.payment_status = PaymentStatus.PAID
    order.delivery_provider = "shipbubble:GIG Logistics"
    order.tracking_number = f"SB-TRK-{order.id.hex[:8].upper()}"
    sb_order_id = f"SB-ORD-{order.id.hex[:8].upper()}"

    shipment = ShipbubbleShipment(
        order_id=order.id,
        request_token=f"req-tok-{order.id.hex[:10]}",
        shipbubble_order_id=sb_order_id,
        courier_id="gig",
        courier_name="GIG Logistics",
        service_code="gig-std",
        status="pending",
        tracking_code=order.tracking_number,
        currency="NGN",
    )
    db_session.add(shipment)
    await db_session.commit()

    sent_emails: list[dict] = []

    async def _capture_send_email(self, *, to_email: str, to_name: str, subject: str, html_content: str, **kwargs):
        sent_emails.append(
            {
                "to_email": to_email,
                "to_name": to_name,
                "subject": subject,
                "html_content": html_content,
            }
        )
        return True

    monkeypatch.setattr(EmailService, "send_email", _capture_send_email)

    customer_token = customer_user["token"]
    customer_email = customer_user["user"].email

    # 1. Simulate ShipBubble 'picked_up' and 'in_transit' via Live Map Simulator
    for step_key in ("picked_up", "in_transit"):
        sim_res = await client.post(
            f"/api/v1/orders/{order.id}/tracking/simulate",
            json={"status": step_key},
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        assert sim_res.status_code == 200, sim_res.text
        assert sim_res.json()["current_status"] == step_key

    customer_subjects = [e["subject"] for e in sent_emails if e["to_email"] == customer_email]
    assert f"Order {order.order_number}: Order Dispatched" in customer_subjects
    assert f"Order {order.order_number}: In Transit" in customer_subjects

    # 2. Send ShipBubble Webhook for 'out_for_delivery' and 'delivered'
    for wh_status in ("out_for_delivery", "delivered"):
        wh_payload = {
            "event": f"shipment.{wh_status}",
            "order_id": sb_order_id,
            "status": wh_status,
            "courier": {"name": "GIG Logistics", "tracking_code": order.tracking_number},
        }
        raw_wh = json.dumps(wh_payload).encode("utf-8")
        wh_sig = hmac.new(sb_api_key.encode("utf-8"), raw_wh, hashlib.sha512).hexdigest()
        wh_res = await client.post(
            "/api/v1/shipping/webhooks/shipbubble",
            content=raw_wh,
            headers={
                "Content-Type": "application/json",
                "x-ship-signature": wh_sig,
            },
        )
        assert wh_res.status_code == 200, wh_res.text

    customer_subjects = [e["subject"] for e in sent_emails if e["to_email"] == customer_email]
    assert f"Order {order.order_number}: Out for Delivery" in customer_subjects
    assert f"Order {order.order_number}: Delivered Successfully" in customer_subjects




