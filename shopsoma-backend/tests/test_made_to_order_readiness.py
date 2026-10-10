"""Made-to-order vendor readiness + per-item pickup scheduling.

Covers the vendor "Ready for Shopsoma Pickup" transition, the one-time admin email,
per-vendor/per-item readiness on the admin order detail, and admin pickup gating.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_vendor(db_session: AsyncSession, *, email: str, business_name: str):
    from app.core.security import create_access_token, get_password_hash
    from app.models.user import User, UserRole
    from app.models.vendor import KYCStatus, Vendor

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=get_password_hash("VendorPass123"),
        full_name=business_name,
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user.id,
        business_name=business_name,
        kyc_status=KYCStatus.APPROVED,
        approved=True,
        is_onboarding=False,
        brand_info_completed=True,
        featured_storefront_image_url=f"/uploads/vendors/{user.id}/fixture.webp",
        payout_info_completed=True,
    )
    db_session.add(vendor)
    await db_session.commit()
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    return {"user": user, "vendor": vendor, "headers": {"Authorization": f"Bearer {token}"}}


async def _create_order(
    db_session: AsyncSession,
    customer_user,
    lines,
    *,
    payment_status=None,
    with_pickups: bool = True,
):
    """Create one paid customer order with one item per ``(vendor, made_to_order, title)``."""
    from app.models.address import Address, AddressType
    from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
    from app.models.product import ModerationStatus, Product, ProductStatus
    from app.models.vendor_pickup import OrderType, PickupStatus, VendorPickup

    address = Address(
        id=uuid.uuid4(),
        user_id=customer_user["user"].id,
        address_type=AddressType.SHIPPING,
        full_name="MTO Customer",
        phone_number="08000000000",
        address_line1="1 Ready Street",
        city="Lagos",
        state="Lagos",
        postal_code="100001",
        country="Nigeria",
        is_default=True,
    )
    db_session.add(address)
    await db_session.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number=f"SHP-MTO-{uuid.uuid4().hex[:8].upper()}",
        customer_id=customer_user["user"].id,
        shipping_address_id=address.id,
        billing_address_id=address.id,
        currency="NGN",
        subtotal=Decimal("100.00") * len(lines),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00") * len(lines),
        payment_status=payment_status or PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.flush()

    items = []
    pickups = []
    for vendor, made_to_order, title in lines:
        product = Product(
            id=uuid.uuid4(),
            vendor_id=vendor.id,
            title=title,
            description=title,
            base_price=Decimal("100.00"),
            currency="NGN",
            total_stock=5,
            made_to_order=made_to_order,
            status=ProductStatus.ACTIVE,
            moderation_status=ModerationStatus.APPROVED,
        )
        db_session.add(product)
        await db_session.flush()
        item = OrderItem(
            id=uuid.uuid4(),
            order_id=order.id,
            product_id=product.id,
            vendor_id=vendor.id,
            product_title=title,
            unit_price=Decimal("100.00"),
            currency="NGN",
            quantity=2,
            subtotal=Decimal("200.00"),
            commission_rate=Decimal("15.00"),
            commission_amount=Decimal("30.00"),
            vendor_payout=Decimal("170.00"),
            fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        )
        db_session.add(item)
        await db_session.flush()
        items.append(item)
        if with_pickups:
            # Mirrors the legacy checkout path, which always provisions an RTW pickup.
            pickup = VendorPickup(
                id=uuid.uuid4(),
                vendor_id=vendor.id,
                order_id=order.id,
                order_item_id=item.id,
                order_type=OrderType.RTW,
                status=PickupStatus.SCHEDULED,
            )
            db_session.add(pickup)
            pickups.append(pickup)

    await db_session.commit()
    # Endpoints share this session and roll it back on rejected requests, which
    # expires ORM instances; hand tests plain-value snapshots instead.
    return (
        SimpleNamespace(id=order.id, order_number=order.order_number),
        [SimpleNamespace(id=item.id) for item in items],
        [SimpleNamespace(id=pickup.id) for pickup in pickups],
    )


@pytest.fixture
def captured_ready_emails(monkeypatch):
    from app.api.v1 import vendors as vendors_api

    calls = []

    async def _capture(**kwargs):
        calls.append(kwargs)
        return True

    monkeypatch.setattr(
        vendors_api.email_service, "send_admin_made_to_order_ready_email", _capture
    )
    return calls


def _ready_url(order_id, item_id) -> str:
    return f"/api/v1/vendor/orders/{order_id}/items/{item_id}/ready-for-pickup"


def _item(payload, item_id):
    return next(row for row in payload["items"] if row["id"] == str(item_id))


@pytest.mark.asyncio
async def test_vendor_marks_made_to_order_item_ready_once(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
    captured_ready_emails,
):
    from app.models.vendor_pickup import OrderType, VendorPickup

    order, (item,), (pickup,) = await _create_order(
        db_session, customer_user, [(vendor_user["vendor"], True, "MTO Trousers")]
    )

    detail = await client.get(
        f"/api/v1/vendor/orders/{order.id}", headers=vendor_user["headers"]
    )
    assert detail.status_code == 200, detail.text
    before = _item(detail.json(), item.id)
    assert before["made_to_order"] is True
    assert before["readiness_state"] == "being_prepared"
    assert before["ready_for_pickup_at"] is None

    first = await client.post(_ready_url(order.id, item.id), headers=vendor_user["headers"])
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["already_ready"] is False
    assert body["readiness_state"] == "ready_for_pickup"
    assert body["ready_for_pickup_at"] is not None
    assert body["pickup"]["id"] == str(pickup.id)

    second = await client.post(_ready_url(order.id, item.id), headers=vendor_user["headers"])
    assert second.status_code == 200, second.text
    assert second.json()["already_ready"] is True
    assert second.json()["ready_for_pickup_at"] == body["ready_for_pickup_at"]

    # Exactly one admin notification, with the information needed to act on it.
    assert len(captured_ready_emails) == 1
    email = captured_ready_emails[0]
    assert email["order_id"] == str(order.id)
    assert email["order_number"] == order.order_number
    assert email["vendor_name"] == vendor_user["vendor"].business_name
    assert email["product_title"] == "MTO Trousers"
    assert email["quantity"] == 2
    assert email["customer_email"] == customer_user["user"].email
    assert email["ready_at"] is not None
    assert any(r["email"] == admin_user["user"].email for r in email["recipients"])

    # Persisted (survives a fresh read / page refresh).
    row = await db_session.scalar(
        select(VendorPickup)
        .where(VendorPickup.id == pickup.id)
        .execution_options(populate_existing=True)
    )
    assert row.ready_for_pickup_at is not None
    assert row.ready_for_pickup_marked_by == vendor_user["user"].id
    assert row.order_type == OrderType.MADE_TO_ORDER

    refreshed = await client.get(
        f"/api/v1/vendor/orders/{order.id}", headers=vendor_user["headers"]
    )
    after = _item(refreshed.json(), item.id)
    assert after["readiness_state"] == "ready_for_pickup"
    assert after["ready_for_pickup_at"] is not None


@pytest.mark.asyncio
async def test_mark_ready_creates_missing_pickup_row(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    captured_ready_emails,
):
    from app.models.vendor_pickup import VendorPickup

    order, (item,), _ = await _create_order(
        db_session,
        customer_user,
        [(vendor_user["vendor"], True, "MTO Kaftan")],
        with_pickups=False,
    )

    response = await client.post(_ready_url(order.id, item.id), headers=vendor_user["headers"])
    assert response.status_code == 200, response.text
    rows = (
        await db_session.scalars(
            select(VendorPickup).where(VendorPickup.order_item_id == item.id)
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].ready_for_pickup_at is not None
    assert len(captured_ready_emails) == 1


@pytest.mark.asyncio
async def test_mark_ready_authorization_and_validation(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
    captured_ready_emails,
):
    from app.models.order import PaymentStatus
    from app.models.vendor_pickup import VendorPickup

    other = await _create_vendor(
        db_session, email="vendor-b@test.com", business_name="Vendor B"
    )
    order, (mine, rtw, theirs), pickups = await _create_order(
        db_session,
        customer_user,
        [
            (vendor_user["vendor"], True, "Vendor A MTO"),
            (vendor_user["vendor"], False, "Vendor A RTW"),
            (other["vendor"], True, "Vendor B MTO"),
        ],
    )
    _other_order, (foreign_item,), _ = await _create_order(
        db_session, customer_user, [(vendor_user["vendor"], True, "Other order MTO")]
    )
    unpaid, (unpaid_item,), _ = await _create_order(
        db_session,
        customer_user,
        [(vendor_user["vendor"], True, "Unpaid MTO")],
        payment_status=PaymentStatus.PENDING,
    )

    # Another vendor cannot mark Vendor A's item.
    forbidden = await client.post(_ready_url(order.id, mine.id), headers=other["headers"])
    assert forbidden.status_code == 403

    # Customers and admins cannot use the vendor action.
    as_customer = await client.post(
        _ready_url(order.id, mine.id), headers=customer_user["headers"]
    )
    assert as_customer.status_code == 403
    as_admin = await client.post(_ready_url(order.id, mine.id), headers=admin_user["headers"])
    assert as_admin.status_code in (403, 404)

    # Item must belong to the order in the URL.
    mismatch = await client.post(
        _ready_url(order.id, foreign_item.id), headers=vendor_user["headers"]
    )
    assert mismatch.status_code == 404

    # Unpaid orders cannot be marked ready.
    unpaid_res = await client.post(
        _ready_url(unpaid.id, unpaid_item.id), headers=vendor_user["headers"]
    )
    assert unpaid_res.status_code == 409

    assert captured_ready_emails == []
    rows = (
        await db_session.scalars(
            select(VendorPickup)
            .where(VendorPickup.order_id == order.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    assert all(row.ready_for_pickup_at is None for row in rows)

    # Ready-to-wear items can be marked ready by their vendor once paid.
    rtw_res = await client.post(_ready_url(order.id, rtw.id), headers=vendor_user["headers"])
    assert rtw_res.status_code == 200
    assert rtw_res.json()["readiness_state"] == "ready_for_pickup"
    assert rtw_res.json()["made_to_order"] is False
    assert len(captured_ready_emails) == 1
    assert captured_ready_emails[0]["item_type"] == "ready_to_wear"


@pytest.mark.asyncio
async def test_multi_vendor_order_tracks_readiness_and_pickup_per_item(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
    captured_ready_emails,
):
    vendor_b = await _create_vendor(
        db_session, email="vendor-b@test.com", business_name="Vendor B"
    )
    vendor_c = await _create_vendor(
        db_session, email="vendor-c@test.com", business_name="Vendor C"
    )
    order, (item_a, item_b, item_c, item_rtw), (pickup_a, pickup_b, pickup_c, _) = (
        await _create_order(
            db_session,
            customer_user,
            [
                (vendor_user["vendor"], True, "Vendor A Trousers"),
                (vendor_b["vendor"], True, "Vendor B Leggings"),
                (vendor_c["vendor"], True, "Vendor C Kaftan"),
                (vendor_b["vendor"], False, "Vendor B Ready Tee"),
            ],
        )
    )

    ready_a = await client.post(_ready_url(order.id, item_a.id), headers=vendor_user["headers"])
    assert ready_a.status_code == 200
    ready_c = await client.post(_ready_url(order.id, item_c.id), headers=vendor_c["headers"])
    assert ready_c.status_code == 200
    assert len(captured_ready_emails) == 2

    detail = await client.get(f"/api/v1/admin/orders/{order.id}", headers=admin_user["headers"])
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    # The customer order stays grouped as one order.
    assert payload["id"] == str(order.id)
    assert len(payload["items"]) == 4

    a = _item(payload, item_a.id)
    b = _item(payload, item_b.id)
    c = _item(payload, item_c.id)
    rtw = _item(payload, item_rtw.id)
    assert a["made_to_order"] is True and a["readiness_state"] == "ready_for_pickup"
    assert a["ready_for_pickup_at"] is not None
    assert a["pickup"]["id"] == str(pickup_a.id)
    assert a["pickup"]["order_item_id"] == str(item_a.id)
    # Vendor A becoming ready does not make Vendor B ready.
    assert b["made_to_order"] is True and b["readiness_state"] == "being_prepared"
    assert b["ready_for_pickup_at"] is None
    assert c["readiness_state"] == "ready_for_pickup"
    # Ready-to-wear items keep their existing behaviour (no readiness state).
    assert rtw["made_to_order"] is False and rtw["readiness_state"] is None

    window_start = datetime.now(timezone.utc) + timedelta(days=1)
    schedule = {
        "pickup_window_start": window_start.isoformat(),
        "pickup_window_end": (window_start + timedelta(hours=3)).isoformat(),
        "courier_name": "Shopsoma Rider",
    }

    # Vendor B is not ready -> scheduling is refused.
    blocked = await client.patch(
        f"/api/v1/admin/orders/{order.id}/pickup/{pickup_b.id}",
        headers=admin_user["headers"],
        json=schedule,
    )
    assert blocked.status_code == 409
    blocked_progress = await client.patch(
        f"/api/v1/admin/orders/{order.id}/pickup/{pickup_b.id}",
        headers=admin_user["headers"],
        json={"pickup_status": "in_transit"},
    )
    assert blocked_progress.status_code == 409
    # Notes stay editable on unready items.
    notes_ok = await client.patch(
        f"/api/v1/admin/orders/{order.id}/pickup/{pickup_b.id}",
        headers=admin_user["headers"],
        json={"admin_notes": "Vendor says 3 more days"},
    )
    assert notes_ok.status_code == 200

    # Vendor A is ready -> schedule it alone, without waiting for B.
    scheduled = await client.patch(
        f"/api/v1/admin/orders/{order.id}/pickup/{pickup_a.id}",
        headers=admin_user["headers"],
        json=schedule,
    )
    assert scheduled.status_code == 200, scheduled.text
    scheduled_payload = scheduled.json()
    assert _item(scheduled_payload, item_a.id)["readiness_state"] == "pickup_scheduled"
    assert _item(scheduled_payload, item_a.id)["pickup"]["courier_name"] == "Shopsoma Rider"
    assert _item(scheduled_payload, item_b.id)["readiness_state"] == "being_prepared"
    assert _item(scheduled_payload, item_c.id)["readiness_state"] == "ready_for_pickup"

    picked = await client.patch(
        f"/api/v1/admin/orders/{order.id}/pickup/{pickup_a.id}",
        headers=admin_user["headers"],
        json={"pickup_status": "in_transit"},
    )
    assert picked.status_code == 200, picked.text
    assert _item(picked.json(), item_a.id)["readiness_state"] == "picked_up"
    assert _item(picked.json(), item_c.id)["readiness_state"] == "ready_for_pickup"

    # Picked-up item cannot be re-marked ready / re-notified.
    again = await client.post(_ready_url(order.id, item_a.id), headers=vendor_user["headers"])
    assert again.status_code == 200
    assert again.json()["already_ready"] is True
    assert len(captured_ready_emails) == 2


@pytest.mark.asyncio
async def test_admin_pickup_endpoint_rejects_invalid_window_and_non_admins(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
    captured_ready_emails,
):
    order, (item,), (pickup,) = await _create_order(
        db_session, customer_user, [(vendor_user["vendor"], True, "MTO Dress")]
    )
    await client.post(_ready_url(order.id, item.id), headers=vendor_user["headers"])

    start = datetime.now(timezone.utc) + timedelta(days=1)
    url = f"/api/v1/admin/orders/{order.id}/pickup/{pickup.id}"
    body = {"pickup_window_start": start.isoformat()}

    as_vendor = await client.patch(url, headers=vendor_user["headers"], json=body)
    assert as_vendor.status_code == 403
    as_customer = await client.patch(url, headers=customer_user["headers"], json=body)
    assert as_customer.status_code == 403

    inverted = await client.patch(
        url,
        headers=admin_user["headers"],
        json={
            "pickup_window_start": start.isoformat(),
            "pickup_window_end": (start - timedelta(hours=1)).isoformat(),
        },
    )
    assert inverted.status_code == 400

    wrong_order = await client.patch(
        f"/api/v1/admin/orders/{uuid.uuid4()}/pickup/{pickup.id}",
        headers=admin_user["headers"],
        json=body,
    )
    assert wrong_order.status_code == 404


@pytest.mark.asyncio
async def test_non_made_to_order_pickup_scheduling_unchanged(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
):
    order, (item,), (pickup,) = await _create_order(
        db_session, customer_user, [(vendor_user["vendor"], False, "Ready Tee")]
    )
    start = datetime.now(timezone.utc) + timedelta(days=1)
    response = await client.patch(
        f"/api/v1/admin/orders/{order.id}/pickup/{pickup.id}",
        headers=admin_user["headers"],
        json={
            "pickup_window_start": start.isoformat(),
            "pickup_window_end": (start + timedelta(hours=2)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    row = _item(response.json(), item.id)
    assert row["made_to_order"] is False
    assert row["readiness_state"] is None
    assert row["pickup"]["pickup_window_start"] is not None


@pytest.mark.asyncio
async def test_order_level_pickup_schedule_skips_unready_made_to_order_items(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
    monkeypatch,
):
    from app.api.v1 import admin_orders as admin_orders_api
    from app.models.vendor_pickup import VendorPickup

    async def _noop_notify_status_change(self, order, new_status, pickup_details=None):
        return None

    class _NoopConnectionManager:
        def get_connection_count(self, order_id: str) -> int:
            return 0

        async def send_order_update(self, order_id: str, data: dict):
            return None

    monkeypatch.setattr(
        admin_orders_api.OrderNotificationService,
        "notify_status_change",
        _noop_notify_status_change,
    )
    monkeypatch.setattr(
        admin_orders_api, "get_connection_manager", lambda: _NoopConnectionManager()
    )

    order, _items, (mto_pickup, rtw_pickup) = await _create_order(
        db_session,
        customer_user,
        [
            (vendor_user["vendor"], True, "Unready MTO"),
            (vendor_user["vendor"], False, "Ready RTW"),
        ],
    )
    start = datetime.now(timezone.utc) + timedelta(days=1)
    response = await client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        headers=admin_user["headers"],
        json={
            "fulfillment_status": "pickup_scheduled",
            "pickup_window_start": start.isoformat(),
            "pickup_window_end": (start + timedelta(hours=2)).isoformat(),
        },
    )
    assert response.status_code == 200, response.text

    rows = {
        row.id: row
        for row in (
            await db_session.scalars(
                select(VendorPickup)
                .where(VendorPickup.order_id == order.id)
                .execution_options(populate_existing=True)
            )
        ).all()
    }
    assert rows[mto_pickup.id].pickup_window_start is None
    assert rows[rtw_pickup.id].pickup_window_start is not None


@pytest.mark.asyncio
async def test_admin_made_to_order_ready_email_content(monkeypatch):
    from app.services.email_service import EmailService

    service = EmailService()
    sent = []

    async def _send_email(to_email, to_name, subject, html_content, template_params=None):
        sent.append({"to": to_email, "subject": subject, "html": html_content})
        return True

    monkeypatch.setattr(service, "send_email", _send_email)
    order_id = str(uuid.uuid4())
    ok = await service.send_admin_made_to_order_ready_email(
        recipients=[{"email": "ops@shopsoma.test", "name": "Ops"}],
        order_id=order_id,
        order_number="SHP-123",
        customer_name="Ada <Customer>",
        customer_email="ada@example.com",
        vendor_name="Vendor A",
        product_title="Made-to-order Trousers",
        quantity=2,
        ready_at=datetime(2026, 10, 4, 9, 30, tzinfo=timezone.utc),
        variant_summary="Size: M",
    )

    assert ok is True
    assert len(sent) == 1
    message = sent[0]
    assert message["to"] == "ops@shopsoma.test"
    assert "Made-to-order item ready for Shopsoma pickup" in message["subject"]
    assert "SHP-123" in message["subject"]
    html = message["html"]
    for expected in (
        "SHP-123",
        order_id,
        "Vendor A",
        "Made-to-order Trousers",
        "Size: M",
        "ada@example.com",
        f"/admin/orders/{order_id}",
        "04 October 2026",
    ):
        assert expected in html
    # Customer-provided content is escaped.
    assert "Ada &lt;Customer&gt;" in html
    assert "<Customer>" not in html

    assert (
        await service.send_admin_made_to_order_ready_email(
            recipients=[],
            order_id=order_id,
            order_number="SHP-123",
            customer_name=None,
            customer_email=None,
            vendor_name="Vendor A",
            product_title="X",
            quantity=1,
            ready_at=datetime.now(timezone.utc),
        )
        is False
    )


@pytest.mark.asyncio
async def test_admin_ready_to_wear_ready_email_content(monkeypatch):
    from app.services.email_service import EmailService

    service = EmailService()
    sent = []

    async def _send_email(to_email, to_name, subject, html_content, template_params=None):
        sent.append({"to": to_email, "subject": subject, "html": html_content})
        return True

    monkeypatch.setattr(service, "send_email", _send_email)
    order_id = str(uuid.uuid4())
    ok = await service.send_admin_made_to_order_ready_email(
        recipients=[{"email": "ops@shopsoma.test", "name": "Ops"}],
        order_id=order_id,
        order_number="SHP-RTW-456",
        customer_name="Kolawole",
        customer_email="kola@example.com",
        vendor_name="Vendor RTW",
        product_title="Classic Silk Shirt",
        quantity=1,
        ready_at=datetime(2026, 10, 8, 14, 0, tzinfo=timezone.utc),
        variant_summary="Size: L • Color: Blue",
        item_type="ready_to_wear",
    )

    assert ok is True
    assert len(sent) == 1
    message = sent[0]
    assert message["to"] == "ops@shopsoma.test"
    assert "Ready-to-wear item available & ready for Shopsoma pickup" in message["subject"]
    assert "SHP-RTW-456" in message["subject"]
    html = message["html"]
    for expected in (
        "SHP-RTW-456",
        order_id,
        "Vendor RTW",
        "Classic Silk Shirt",
        "Ready-to-wear",
        "Size: L • Color: Blue",
        "kola@example.com",
        "ready-to-wear</strong> item is in stock, available",
        f"/admin/orders/{order_id}",
    ):
        assert expected in html


@pytest.mark.asyncio
async def test_admin_marks_item_ready_and_schedules_individual_pickup_notifying_vendor(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    admin_user,
    monkeypatch,
):
    from app.services.email_service import EmailService

    sent_emails = []

    async def _capture_send_email(self, to_email, to_name, subject, html_content, template_params=None):
        sent_emails.append({
            "to": to_email,
            "to_name": to_name,
            "subject": subject,
            "html": html_content,
        })
        return True

    monkeypatch.setattr(EmailService, "send_email", _capture_send_email)

    order, (item,), (pickup,) = await _create_order(
        db_session, customer_user, [(vendor_user["vendor"], True, "Bespoke Agbada")]
    )

    # 1. Admin marks item ready on behalf of vendor
    mark_ready_res = await client.post(
        f"/api/v1/admin/orders/{order.id}/items/{item.id}/ready-for-pickup",
        headers=admin_user["headers"],
    )
    assert mark_ready_res.status_code == 200, mark_ready_res.text
    item_data = _item(mark_ready_res.json(), item.id)
    assert item_data["readiness_state"] == "ready_for_pickup"
    assert item_data["ready_for_pickup_at"] is not None

    # 2. Admin schedules pickup for this individual item
    start = datetime.now(timezone.utc) + timedelta(days=1)
    end = start + timedelta(hours=3)
    schedule_res = await client.patch(
        f"/api/v1/admin/orders/{order.id}/pickup/{pickup.id}",
        headers=admin_user["headers"],
        json={
            "pickup_window_start": start.isoformat(),
            "pickup_window_end": end.isoformat(),
            "courier_name": "Kwik Delivery",
            "rider_id": "RIDER-99",
        },
    )
    assert schedule_res.status_code == 200, schedule_res.text
    sched_item = _item(schedule_res.json(), item.id)
    assert sched_item["readiness_state"] == "pickup_scheduled"
    assert sched_item["pickup"]["status"] == "scheduled"
    assert sched_item["pickup"]["courier_name"] == "Kwik Delivery"

    # 3. Verify vendor was notified via email about this specific item pickup
    vendor_emails = [e for e in sent_emails if e["to"] == vendor_user["user"].email]
    assert len(vendor_emails) >= 1
    vendor_email = vendor_emails[-1]
    assert order.order_number in vendor_email["subject"] or order.order_number in vendor_email["html"]
    assert "Bespoke Agbada" in vendor_email["html"]
    assert "Kwik Delivery" in vendor_email["html"]
    assert "RIDER-99" in vendor_email["html"]

