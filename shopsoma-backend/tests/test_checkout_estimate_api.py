"""Production-reachable Milestone 3 checkout-estimate API contracts."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
import hashlib
import hmac
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import event, func, select, text

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.models.address import Address
from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimate,
    CheckoutShippingEstimateSelection,
    OrderInventoryCoverage,
)
from app.models.order import Order, OrderItem
from app.models.order_guest_capability import OrderGuestCapability
from app.models.payment import Payment
from app.models.product import ModerationStatus, Product, ProductStatus
from app.models.shipping_rate import ShippingRate
from app.models.stock_payment_persistence import StockReservation
from app.models.user import User
from app.models import VendorNotification
from app.models.vendor_pickup import VendorPickup
from app.services.checkout import estimates as checkout_estimates
from tests.conftest import TestSessionLocal, test_engine


@asynccontextmanager
async def _isolated_route_client(application_name: str):
    previous_override = app.dependency_overrides.get(get_db)

    async def isolated_db():
        async with TestSessionLocal() as session:
            await session.execute(
                text("SELECT set_config('application_name', :name, false)"),
                {"name": application_name},
            )
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.rollback()

    app.dependency_overrides[get_db] = isolated_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as route_client:
            yield route_client
    finally:
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


async def _domestic_catalogue(db_session, vendor_user, customer_user=None):
    address = None
    if customer_user:
        address = Address(
            id=uuid.uuid4(),
            user_id=customer_user["user"].id,
            full_name="Checkout Customer",
            phone_number="08000000000",
            address_line1="1 Safe Street",
            city="Lagos",
            state="Lagos",
            country="Nigeria",
        )
    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Reserved Dress",
        description="Milestone 3 stock subject",
        base_price=Decimal("80000.00"),
        currency="NGN",
        total_stock=2,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    rates = [
        ShippingRate(
            id=uuid.uuid4(),
            name="Standard",
            description="3-5 days",
            base_rate=Decimal("1500.00"),
            country="Nigeria",
            state="Lagos",
            min_delivery_days=3,
            max_delivery_days=5,
            is_active=True,
            is_default=True,
            priority=0,
        ),
        ShippingRate(
            id=uuid.uuid4(),
            name="Express",
            description="1-2 days",
            base_rate=Decimal("3000.00"),
            country="Nigeria",
            state="Lagos",
            min_delivery_days=1,
            max_delivery_days=2,
            is_active=True,
            is_default=False,
            priority=1,
        ),
    ]
    db_session.add_all([row for row in [address, product, *rates] if row is not None])
    await db_session.commit()
    return address, product


def _guest_order_payload(product_id, email):
    return {
        "items": [{"product_id": str(product_id), "quantity": 1}],
        "guest_address": {
            "full_name": "Guest Checkout",
            "phone_number": "08000000000",
            "address_line1": "2 Capability Street",
            "city": "Lagos",
            "state": "Lagos",
            "country": "Nigeria",
        },
        "customer_email": email,
        "currency": "NGN",
    }


async def _create_authenticated_estimate(
    client, customer_user, address, product, *, key: str
):
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
    assert created.json()["checkout_capability"] is None
    order_id = created.json()["id"]
    estimate_response = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates",
        headers={**customer_user["headers"], "X-Idempotency-Key": key},
    )
    assert estimate_response.status_code == 201, estimate_response.text
    return order_id, estimate_response.json()


async def _assert_no_prerequisite_writes(db_session, order_id):
    db_session.expire_all()
    order = await db_session.get(Order, uuid.UUID(order_id))
    assert order.checkout_estimate_selection_id is None
    assert order.checkout_prerequisites_completed_at is None
    assert Decimal(order.shipping_cost) == Decimal("0.00")
    assert Decimal(order.total_amount) == (
        Decimal(order.subtotal)
        + Decimal(order.tax_amount)
        - Decimal(order.discount_amount)
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(CheckoutShippingEstimateSelection)
        )
        == 0
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(StockReservation)) == 0
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(OrderInventoryCoverage)
        )
        == 0
    )


async def _write_counts(db_session):
    return {
        "addresses": await db_session.scalar(select(func.count()).select_from(Address)),
        "capabilities": await db_session.scalar(
            select(func.count()).select_from(OrderGuestCapability)
        ),
        "orders": await db_session.scalar(select(func.count()).select_from(Order)),
        "users": await db_session.scalar(select(func.count()).select_from(User)),
    }


async def _wait_for_route_lock(application_name: str):
    async with test_engine.connect() as observer:
        for _ in range(300):
            waiting = await observer.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE application_name=:name AND wait_event_type='Lock'"
                ),
                {"name": application_name},
            )
            if waiting:
                return
            await asyncio.sleep(0.02)
        activity = (
            await observer.execute(
                text(
                    "SELECT state, wait_event_type, wait_event "
                    "FROM pg_stat_activity WHERE application_name=:name"
                ),
                {"name": application_name},
            )
        ).all()
    raise AssertionError(
        f"production route lock wait not observed; activity={activity}"
    )


@pytest.mark.asyncio
async def test_unauthenticated_saved_address_is_rejected_without_writes(
    client, db_session, vendor_user, customer_user
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    before = await _write_counts(db_session)

    response = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address_id": str(address.id),
            "currency": "NGN",
        },
    )

    assert response.status_code in {401, 403}
    assert await _write_counts(db_session) == before


@pytest.mark.asyncio
async def test_other_users_saved_address_is_rejected_without_writes(
    client, db_session, vendor_user, customer_user
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    before = await _write_counts(db_session)

    response = await client.post(
        "/api/v1/orders",
        headers=vendor_user["headers"],
        json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address_id": str(address.id),
            "currency": "NGN",
        },
    )

    assert response.status_code in {403, 404}
    assert await _write_counts(db_session) == before


@pytest.mark.asyncio
async def test_guest_email_matching_password_account_requires_login_without_writes(
    client, db_session, vendor_user, customer_user
):
    _, product = await _domestic_catalogue(db_session, vendor_user)
    before = await _write_counts(db_session)

    response = await client.post(
        "/api/v1/orders",
        json=_guest_order_payload(product.id, customer_user["user"].email),
    )

    assert response.status_code in {409, 401, 403}
    assert await _write_counts(db_session) == before


@pytest.mark.asyncio
async def test_create_order_then_create_estimate_requires_explicit_selection(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    made_to_order = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Made-to-order Dress",
        description="Milestone 3 non-reserved subject",
        base_price=Decimal("80000.00"),
        currency="NGN",
        total_stock=0,
        made_to_order=True,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(made_to_order)
    await db_session.commit()
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST",
        str(customer_user["user"].id),
    )

    async def no_external_call(*_args, **_kwargs):
        raise AssertionError("enforced prerequisite order attempted external transport")

    monkeypatch.setattr(
        "app.services.email_service.email_service.send_order_confirmation_email",
        no_external_call,
    )
    monkeypatch.setattr(
        "app.services.email_service.email_service.send_admin_order_notification",
        no_external_call,
    )
    monkeypatch.setattr(
        "app.services.vendor_notification_service.VendorNotificationService.send_order_notification",
        no_external_call,
    )

    created = await client.post(
        "/api/v1/orders",
        headers=customer_user["headers"],
        json={
            "items": [
                {"product_id": str(product.id), "quantity": 1},
                {"product_id": str(made_to_order.id), "quantity": 1},
            ],
            "shipping_address_id": str(address.id),
            "currency": "NGN",
        },
    )
    assert created.status_code == 201, created.text
    order_payload = created.json()
    order_id = order_payload["id"]
    assert order_payload["workflow_cohort"] == "domestic_checkout_v1"
    assert order_payload["checkout_prerequisites_completed_at"] is None
    assert Decimal(order_payload["shipping_cost"]) == Decimal("0.00")

    await db_session.refresh(product)
    assert product.total_stock == 2
    items = (
        (
            await db_session.execute(
                select(OrderItem).where(OrderItem.order_id == order_id)
            )
        )
        .scalars()
        .all()
    )
    item = next(row for row in items if row.product_id == product.id)
    mto_item = next(row for row in items if row.product_id == made_to_order.id)
    item_id = item.id
    mto_item_id = mto_item.id
    item_quantity = item.quantity
    item_unit_price = item.unit_price
    item_currency = item.currency
    assert item.inventory_policy == "stock_managed"
    assert item.inventory_subject_kind == "product"
    assert item.inventory_subject_id == product.id
    assert mto_item.inventory_policy == "made_to_order"
    assert mto_item.inventory_subject_id is None

    estimate_response = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates",
        headers={**customer_user["headers"], "X-Idempotency-Key": "estimate-1"},
    )
    assert estimate_response.status_code == 201, estimate_response.text
    estimate = estimate_response.json()
    assert len(estimate["options"]) == 2
    assert estimate["selected_option"] is None

    selection_count = await db_session.scalar(
        select(func.count()).select_from(CheckoutShippingEstimateSelection)
    )
    coverage_count = await db_session.scalar(
        select(func.count()).select_from(OrderInventoryCoverage)
    )
    assert selection_count == 0
    assert coverage_count == 0

    selected = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
        f"/options/{estimate['options'][1]['id']}/select",
        headers={**customer_user["headers"], "X-Idempotency-Key": "select-1"},
    )
    assert selected.status_code == 200, selected.text
    selected_payload = selected.json()
    assert selected_payload["selected_option"]["id"] == estimate["options"][1]["id"]
    assert Decimal(selected_payload["server_payable_total"]) > Decimal("160000.00")

    replay = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
        f"/options/{estimate['options'][1]['id']}/select",
        headers={**customer_user["headers"], "X-Idempotency-Key": "select-1"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["selected_option"]["id"] == estimate["options"][1]["id"]

    conflicting = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
        f"/options/{estimate['options'][0]['id']}/select",
        headers={**customer_user["headers"], "X-Idempotency-Key": "select-1"},
    )
    assert conflicting.status_code == 409

    persisted_order = await db_session.get(Order, uuid.UUID(order_id))
    completed_at = persisted_order.checkout_prerequisites_completed_at
    selection_id = persisted_order.checkout_estimate_selection_id
    new_key = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
        f"/options/{estimate['options'][1]['id']}/select",
        headers={**customer_user["headers"], "X-Idempotency-Key": "select-2"},
    )
    assert new_key.status_code == 409, new_key.text
    assert new_key.json()["detail"] == "checkout prerequisites already completed"
    await db_session.refresh(persisted_order)
    assert persisted_order.checkout_prerequisites_completed_at == completed_at
    assert persisted_order.checkout_estimate_selection_id == selection_id
    assert persisted_order.checkout_prerequisites_completed_at is not None
    coverage = (
        (
            await db_session.execute(
                select(OrderInventoryCoverage).where(
                    OrderInventoryCoverage.order_id == persisted_order.id
                )
            )
        )
        .scalars()
        .all()
    )
    assert {row.order_item_id for row in coverage} == {item_id, mto_item_id}
    stock_coverage = next(row for row in coverage if row.order_item_id == item_id)
    mto_coverage = next(row for row in coverage if row.order_item_id == mto_item_id)
    assert mto_coverage.reservation_id is None
    reservation = await db_session.get(StockReservation, stock_coverage.reservation_id)
    assert reservation.order_item_id == item_id
    assert (
        reservation.checkout_estimate_selection_id
        == stock_coverage.checkout_estimate_selection_id
    )
    assert reservation.quantity == item_quantity
    assert reservation.unit_price == item_unit_price
    assert reservation.currency == item_currency

    await db_session.refresh(product)
    assert product.total_stock == 2
    assert await db_session.scalar(select(func.count()).select_from(Payment)) == 0
    assert await db_session.scalar(select(func.count()).select_from(VendorPickup)) == 0
    assert (
        await db_session.scalar(select(func.count()).select_from(VendorNotification))
        == 0
    )


@pytest.mark.asyncio
async def test_guest_capability_is_issued_once_and_authorizes_only_its_order(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    _, product = await _domestic_catalogue(db_session, vendor_user)
    pepper = "m3-test-pepper-not-a-production-secret"
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)
    monkeypatch.setattr(settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION", 7)
    monkeypatch.setattr(
        settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER", SecretStr(pepper)
    )

    created = await client.post(
        "/api/v1/orders", json=_guest_order_payload(product.id, "guest-m3@example.test")
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert list(payload).count("checkout_capability") == 1
    capability = payload["checkout_capability"]
    assert capability and len(capability) >= 32

    persisted = (
        await db_session.execute(
            select(OrderGuestCapability).where(
                OrderGuestCapability.order_id == uuid.UUID(payload["id"])
            )
        )
    ).scalar_one()
    assert persisted.scope == "checkout_prerequisites"
    assert (
        persisted.token_digest
        == hmac.new(pepper.encode(), capability.encode(), hashlib.sha256).digest()
    )
    assert capability.encode() not in persisted.token_digest

    headers = {
        "X-ShopSoma-Checkout-Capability": capability,
        "X-Idempotency-Key": "guest-estimate-1",
    }
    estimate_response = await client.post(
        f"/api/v1/orders/{payload['id']}/checkout-estimates", headers=headers
    )
    assert estimate_response.status_code == 201, estimate_response.text
    assert "checkout_capability" not in estimate_response.json()
    estimate = estimate_response.json()
    replay = await client.post(
        f"/api/v1/orders/{payload['id']}/checkout-estimates", headers=headers
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == estimate["id"]
    listed = await client.get(
        f"/api/v1/orders/{payload['id']}/checkout-estimates",
        headers={"X-ShopSoma-Checkout-Capability": capability},
    )
    assert listed.status_code == 200
    fetched = await client.get(
        f"/api/v1/orders/{payload['id']}/checkout-estimates/{estimate['id']}",
        headers={"X-ShopSoma-Checkout-Capability": capability},
    )
    assert fetched.status_code == 200

    stranger = await client.get(
        f"/api/v1/orders/{payload['id']}/checkout-estimates",
        headers=customer_user["headers"],
    )
    assert stranger.status_code == 404
    other = await client.post(
        "/api/v1/orders", json=_guest_order_payload(product.id, "other-m3@example.test")
    )
    assert other.status_code == 201
    wrong_order = await client.post(
        f"/api/v1/orders/{other.json()['id']}/checkout-estimates",
        headers={**headers, "X-Idempotency-Key": "wrong-order"},
    )
    assert wrong_order.status_code == 404

    selected_headers = {
        "X-ShopSoma-Checkout-Capability": capability,
        "X-Idempotency-Key": "guest-select-1",
    }
    selection_url = (
        f"/api/v1/orders/{payload['id']}/checkout-estimates/{estimate['id']}"
        f"/options/{estimate['options'][0]['id']}/select"
    )
    selected = await client.post(selection_url, headers=selected_headers)
    assert selected.status_code == 200, selected.text
    selected_replay = await client.post(selection_url, headers=selected_headers)
    assert selected_replay.status_code == 200
    assert (
        selected_replay.json()["selected_option"]["id"] == estimate["options"][0]["id"]
    )

    persisted.revoked_at = func.statement_timestamp()
    persisted.row_version += 1
    await db_session.commit()
    revoked = await client.get(
        f"/api/v1/orders/{payload['id']}/checkout-estimates",
        headers={"X-ShopSoma-Checkout-Capability": capability},
    )
    assert revoked.status_code == 404

    expired_token = "expired-capability-token-with-sufficient-entropy"
    database_now = await db_session.scalar(select(text("clock_timestamp()")))
    db_session.add(
        OrderGuestCapability(
            order_id=uuid.UUID(payload["id"]),
            original_customer_id=uuid.UUID(payload["customer_id"]),
            scope="checkout_prerequisites",
            token_digest=hmac.new(
                pepper.encode(), expired_token.encode(), hashlib.sha256
            ).digest(),
            pepper_key_version=7,
            created_at=database_now - timedelta(days=1),
            expires_at=database_now - timedelta(microseconds=1),
        )
    )
    await db_session.commit()
    expired = await client.get(
        f"/api/v1/orders/{payload['id']}/checkout-estimates",
        headers={"X-ShopSoma-Checkout-Capability": expired_token},
    )
    assert expired.status_code == 404


@pytest.mark.asyncio
async def test_enforced_guest_order_fails_closed_without_capability_config(
    client, db_session, vendor_user, monkeypatch
):
    _, product = await _domestic_catalogue(db_session, vendor_user)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)
    monkeypatch.setattr(settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION", None)
    monkeypatch.setattr(settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER", SecretStr(""))

    response = await client.post(
        "/api/v1/orders",
        json=_guest_order_payload(product.id, "unconfigured@example.test"),
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "guest checkout is not available"


@pytest.mark.asyncio
async def test_selection_rechecks_database_clock_after_waiting_for_estimate_lock(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST",
        str(customer_user["user"].id),
    )
    monkeypatch.setattr("app.services.checkout.estimates._ESTIMATE_TTL_SECONDS", 300)
    monkeypatch.setattr(
        "app.services.checkout.estimates._estimate_expiry_delta",
        lambda _ttl: timedelta(seconds=1),
    )
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
    estimate_response = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates",
        headers={
            **customer_user["headers"],
            "X-Idempotency-Key": "expiry-estimate",
        },
    )
    assert estimate_response.status_code == 201, estimate_response.text
    estimate = estimate_response.json()
    estimate_expires_at = datetime.fromisoformat(estimate["expires_at"])
    database_now = await db_session.scalar(select(text("clock_timestamp()")))
    assert estimate_expires_at <= database_now + timedelta(seconds=2)
    option_id = estimate["options"][0]["id"]
    application_name = f"m3-estimate-expiry-{uuid.uuid4().hex}"
    estimate_lock_started = asyncio.Event()
    event_loop = asyncio.get_running_loop()

    def signal_estimate_lock_start(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ):
        normalized = " ".join(statement.lower().split())
        if (
            "from checkout_shipping_estimates" in normalized
            and "for update" in normalized
        ):
            event_loop.call_soon_threadsafe(estimate_lock_started.set)

    blocker = await test_engine.connect()
    blocker_tx = await blocker.begin()
    await blocker.execute(
        text("SELECT 1 FROM checkout_shipping_estimates WHERE id=:id FOR UPDATE"),
        {"id": estimate["id"]},
    )
    event.listen(
        test_engine.sync_engine, "before_cursor_execute", signal_estimate_lock_start
    )
    try:
        async with _isolated_route_client(application_name) as contender:
            selection_task = asyncio.create_task(
                contender.post(
                    f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
                    f"/options/{option_id}/select",
                    headers={
                        **customer_user["headers"],
                        "X-Idempotency-Key": "expiry-selection",
                    },
                )
            )
            await asyncio.wait_for(estimate_lock_started.wait(), timeout=3)
            assert blocker_tx.is_active
            assert not selection_task.done()
            route_entered_at = await blocker.scalar(select(text("clock_timestamp()")))
            assert route_entered_at < estimate_expires_at
            database_now = await blocker.scalar(select(text("clock_timestamp()")))
            while database_now <= estimate_expires_at:
                database_now = await blocker.scalar(select(text("clock_timestamp()")))
            assert database_now > estimate_expires_at
            await blocker_tx.commit()
            response = await asyncio.wait_for(selection_task, timeout=3)
    finally:
        event.remove(
            test_engine.sync_engine, "before_cursor_execute", signal_estimate_lock_start
        )
        if blocker_tx.is_active:
            await blocker_tx.rollback()
        await blocker.close()

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "expired checkout estimate"
    db_session.expire_all()
    order = await db_session.get(Order, uuid.UUID(order_id))
    assert order.checkout_estimate_selection_id is None
    assert order.checkout_prerequisites_completed_at is None
    assert (
        await db_session.scalar(
            select(func.count()).select_from(CheckoutShippingEstimateSelection)
        )
        == 0
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(StockReservation)) == 0
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(OrderInventoryCoverage)
        )
        == 0
    )


@pytest.mark.asyncio
async def test_concurrent_same_order_selection_converges_on_one_write(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings, "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST", str(customer_user["user"].id)
    )
    order_id, estimate = await _create_authenticated_estimate(
        client, customer_user, address, product, key="concurrent-estimate"
    )
    option_id = estimate["options"][0]["id"]
    url = (
        f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
        f"/options/{option_id}/select"
    )
    headers = {
        **customer_user["headers"],
        "X-Idempotency-Key": "concurrent-selection",
    }
    async with _isolated_route_client("m3-concurrent-selection") as route_client:
        responses = await asyncio.gather(
            route_client.post(url, headers=headers),
            route_client.post(url, headers=headers),
        )

    assert [response.status_code for response in responses] == [200, 200]
    assert {response.json()["selected_option"]["id"] for response in responses} == {
        option_id
    }
    assert (
        await db_session.scalar(
            select(func.count()).select_from(CheckoutShippingEstimateSelection)
        )
        == 1
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(StockReservation)) == 1
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(OrderInventoryCoverage)
        )
        == 1
    )


@pytest.mark.asyncio
async def test_insufficient_stock_rolls_back_every_prerequisite_write(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings, "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST", str(customer_user["user"].id)
    )
    order_id, estimate = await _create_authenticated_estimate(
        client, customer_user, address, product, key="stock-estimate"
    )
    product.total_stock = 0
    await db_session.commit()
    response = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
        f"/options/{estimate['options'][0]['id']}/select",
        headers={**customer_user["headers"], "X-Idempotency-Key": "stock-selection"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "insufficient stock"
    await _assert_no_prerequisite_writes(db_session, order_id)


@pytest.mark.asyncio
async def test_stale_destination_snapshot_rolls_back_through_selection_route(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings, "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST", str(customer_user["user"].id)
    )
    order_id, estimate = await _create_authenticated_estimate(
        client, customer_user, address, product, key="stale-estimate"
    )
    address.city = "Abuja"
    await db_session.commit()
    response = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
        f"/options/{estimate['options'][0]['id']}/select",
        headers={**customer_user["headers"], "X-Idempotency-Key": "stale-selection"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "stale checkout estimate"
    await _assert_no_prerequisite_writes(db_session, order_id)


@pytest.mark.asyncio
async def test_address_change_committed_during_selection_lock_wait_fails_closed(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings, "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST", str(customer_user["user"].id)
    )
    order_id, estimate = await _create_authenticated_estimate(
        client, customer_user, address, product, key="waiting-address-estimate"
    )
    option_id = estimate["options"][0]["id"]
    application_name = f"m3-waiting-address-{uuid.uuid4().hex}"
    blocker = await test_engine.connect()
    blocker_tx = await blocker.begin()
    await blocker.execute(
        text("UPDATE addresses SET city='Abuja' WHERE id=:id"), {"id": address.id}
    )
    await blocker.execute(
        text("SELECT 1 FROM checkout_shipping_estimates WHERE id=:id FOR UPDATE"),
        {"id": estimate["id"]},
    )
    try:
        async with _isolated_route_client(application_name) as contender:
            selection_task = asyncio.create_task(
                contender.post(
                    f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
                    f"/options/{option_id}/select",
                    headers={
                        **customer_user["headers"],
                        "X-Idempotency-Key": "waiting-address-selection",
                    },
                )
            )
            await _wait_for_route_lock(application_name)
            await blocker_tx.commit()
            response = await asyncio.wait_for(selection_task, timeout=3)
    finally:
        if blocker_tx.is_active:
            await blocker_tx.rollback()
        await blocker.close()

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "stale checkout estimate"
    await _assert_no_prerequisite_writes(db_session, order_id)


@pytest.mark.asyncio
async def test_item_change_committed_during_selection_lock_wait_fails_closed(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings, "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST", str(customer_user["user"].id)
    )
    order_id, estimate = await _create_authenticated_estimate(
        client, customer_user, address, product, key="waiting-item-estimate"
    )
    option_id = estimate["options"][0]["id"]
    application_name = f"m3-waiting-item-{uuid.uuid4().hex}"
    route_lock_started = asyncio.Event()
    mutation_committed = asyncio.Event()
    event_loop = asyncio.get_running_loop()
    original_reload = checkout_estimates.reload_checkout_order

    def signal_route_lock_start(
        _connection, _cursor, statement, _parameters, _context, _executemany
    ):
        normalized = " ".join(statement.lower().split())
        if "from orders" in normalized and "for update" in normalized:
            event_loop.call_soon_threadsafe(route_lock_started.set)

    async def assert_mutation_committed_before_reload(db, order):
        assert mutation_committed.is_set()
        return await original_reload(db, order)

    monkeypatch.setattr(
        checkout_estimates,
        "reload_checkout_order",
        assert_mutation_committed_before_reload,
    )
    event.listen(
        test_engine.sync_engine, "before_cursor_execute", signal_route_lock_start
    )
    blocker = await test_engine.connect()
    blocker_tx = await blocker.begin()
    await blocker.execute(
        text(
            "UPDATE order_items "
            "SET unit_price=unit_price + 1, subtotal=subtotal + 1 "
            "WHERE order_id=:order_id"
        ),
        {"order_id": order_id},
    )
    await blocker.execute(
        text("SELECT 1 FROM checkout_shipping_estimates WHERE id=:id FOR UPDATE"),
        {"id": estimate["id"]},
    )
    try:
        async with _isolated_route_client(application_name) as contender:
            selection_task = asyncio.create_task(
                contender.post(
                    f"/api/v1/orders/{order_id}/checkout-estimates/{estimate['id']}"
                    f"/options/{option_id}/select",
                    headers={
                        **customer_user["headers"],
                        "X-Idempotency-Key": "waiting-item-selection",
                    },
                )
            )
            await asyncio.wait_for(route_lock_started.wait(), timeout=3)
            assert not selection_task.done()
            await blocker_tx.commit()
            mutation_committed.set()
            response = await asyncio.wait_for(selection_task, timeout=3)
    finally:
        event.remove(
            test_engine.sync_engine, "before_cursor_execute", signal_route_lock_start
        )
        if blocker_tx.is_active:
            await blocker_tx.rollback()
        await blocker.close()

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "stale checkout estimate"
    await _assert_no_prerequisite_writes(db_session, order_id)


@pytest.mark.asyncio
async def test_previous_pepper_capability_remains_valid_after_rotation(
    client, db_session, vendor_user, monkeypatch
):
    _, product = await _domestic_catalogue(db_session, vendor_user)
    previous_pepper = "m3-previous-pepper-test-value"
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)
    monkeypatch.setattr(settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION", 8)
    monkeypatch.setattr(
        settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER", SecretStr(previous_pepper)
    )
    created = await client.post(
        "/api/v1/orders",
        json=_guest_order_payload(product.id, "rotated-guest@example.test"),
    )
    assert created.status_code == 201, created.text
    payload = created.json()

    monkeypatch.setattr(settings, "CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION", 9)
    monkeypatch.setattr(
        settings,
        "CHECKOUT_CAPABILITY_ACTIVE_PEPPER",
        SecretStr("m3-current-pepper-test-value"),
    )
    monkeypatch.setattr(settings, "CHECKOUT_CAPABILITY_PREVIOUS_PEPPER_VERSION", 8)
    monkeypatch.setattr(
        settings, "CHECKOUT_CAPABILITY_PREVIOUS_PEPPER", SecretStr(previous_pepper)
    )
    response = await client.get(
        f"/api/v1/orders/{payload['id']}/checkout-estimates",
        headers={"X-ShopSoma-Checkout-Capability": payload["checkout_capability"]},
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_gate_off_order_preserves_legacy_path_without_bridge_rows(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", False)

    async def successful_notification(*_args, **_kwargs):
        return True

    monkeypatch.setattr(
        "app.services.email_service.email_service.send_order_confirmation_email",
        successful_notification,
    )
    monkeypatch.setattr(
        "app.services.email_service.email_service.send_admin_order_notification",
        successful_notification,
    )
    monkeypatch.setattr(
        "app.services.vendor_notification_service.VendorNotificationService.send_order_notification",
        successful_notification,
    )
    response = await client.post(
        "/api/v1/orders",
        headers=customer_user["headers"],
        json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address_id": str(address.id),
            "currency": "NGN",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["workflow_cohort"] == "legacy_pre_bridge"
    assert payload["workflow_policy_version"] == "legacy_pre_bridge_v1"
    assert payload["checkout_prerequisites_completed_at"] is None
    await db_session.refresh(product)
    assert product.total_stock == 1
    assert await db_session.scalar(select(func.count()).select_from(VendorPickup)) == 1
    assert (
        await db_session.scalar(select(func.count()).select_from(VendorNotification))
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(CheckoutShippingEstimate)
        )
        == 0
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(OrderGuestCapability))
        == 0
    )
    assert (
        await db_session.scalar(select(func.count()).select_from(StockReservation)) == 0
    )
    assert (
        await db_session.scalar(
            select(func.count()).select_from(OrderInventoryCoverage)
        )
        == 0
    )
