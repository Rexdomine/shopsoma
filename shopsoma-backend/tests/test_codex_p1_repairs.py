"""Production-faithful regressions for the consolidated Codex P1 repair ledger."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.checkout_outbox import CheckoutOutboxEvent
from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimate,
    CheckoutShippingEstimateOption,
    OrderInventoryCoverage,
)
from app.models.payment import Payment
from app.models.setting import Setting
from app.models.order import FulfillmentStatus, Order, PaymentStatus
from app.models.product import Product
from app.models.shipping_rate import ShippingRate
from app.models.stock_payment_persistence import (
    PaymentAttempt,
    PaymentAttemptEvidence,
    StockReservation,
)
from app.models.vendor_pickup import OrderType, VendorNotification, VendorPickup
from app.services.checkout.outbox import enqueue_checkout_event
from tests.conftest import TestSessionLocal, _ASYNC_TEST_DATABASE_URL
from tests.test_checkout_estimate_api import _domestic_catalogue
from tests.test_checkout_payment_bridge_prerequisites import create_enforced_checkout


@pytest.mark.asyncio
async def test_authenticated_unpaid_enforced_cancellation_releases_reservation_without_restoring_stock(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, product = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    product_id = product.id
    stock_before = product.total_stock
    reservation = await db_session.scalar(
        select(StockReservation).where(StockReservation.order_id == order_id)
    )
    assert reservation.state == "active"
    reservation_id = reservation.id

    cancelled = await client.post(
        f"/api/v1/orders/{order_id}/cancel",
        headers=customer_user["headers"],
        json={"cancellation_reason": "Changed my mind"},
    )
    replay = await client.post(
        f"/api/v1/orders/{order_id}/cancel",
        headers=customer_user["headers"],
        json={"cancellation_reason": "Replay"},
    )

    assert cancelled.status_code == 200, cancelled.text
    assert replay.status_code == 400, replay.text
    db_session.expire_all()
    persisted_order = await db_session.get(Order, order_id)
    persisted_product = await db_session.get(Product, product_id)
    persisted_reservation = await db_session.get(StockReservation, reservation_id)
    assert persisted_order.fulfillment_status == FulfillmentStatus.CANCELLED
    assert persisted_product.total_stock == stock_before
    assert persisted_reservation.state == "released"
    assert persisted_reservation.terminal_reason == "checkout_cancelled"
    assert persisted_reservation.terminal_at is not None
    assert persisted_reservation.row_version == 2
    assert (
        await db_session.scalar(
            text(
                "SELECT claimed_txid IS NOT NULL FROM stock_payment_lock_coordinator "
                "WHERE subject_kind='reservation' AND subject_id=:reservation_id"
            ),
            {"reservation_id": reservation_id},
        )
        is True
    )


@pytest.mark.asyncio
async def test_paid_made_to_order_cancellation_does_not_restore_stock(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, product = await create_enforced_checkout(
        client,
        db_session,
        vendor_user,
        customer_user,
        monkeypatch,
        made_to_order=True,
    )
    order_id = order.id
    product_id = product.id
    stock_before = product.total_stock
    order.payment_status = PaymentStatus.PAID
    await db_session.commit()

    cancelled = await client.post(
        f"/api/v1/orders/{order_id}/cancel",
        headers=customer_user["headers"],
        json={"cancellation_reason": "Vendor cannot fulfil"},
    )

    assert cancelled.status_code == 200, cancelled.text
    db_session.expire_all()
    persisted_product = await db_session.get(Product, product_id)
    assert persisted_product.total_stock == stock_before


@pytest.mark.asyncio
@pytest.mark.parametrize("unresolved_state", ["call_started", "abandoned_unknown"])
async def test_enforced_cancellation_rejects_unresolved_attempt_and_late_success_finalizes_once(
    client, db_session, vendor_user, customer_user, monkeypatch, unresolved_state
):
    from tests.test_verified_payment_inventory import initialize_stripe, verify_stripe

    order, product = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    stock_before = product.total_stock
    attempt = await initialize_stripe(
        client,
        db_session,
        customer_user,
        monkeypatch,
        order,
        transaction_id=f"pi_cancel_{unresolved_state}",
    )
    if unresolved_state == "abandoned_unknown":
        persisted_attempt = await db_session.get(PaymentAttempt, attempt.id)
        await db_session.execute(text("SET LOCAL session_replication_role = replica"))
        await db_session.execute(
            text(
                "UPDATE payment_attempts "
                "SET claim_expires_at=clock_timestamp() - interval '1 second' "
                "WHERE id=:attempt_id"
            ),
            {"attempt_id": attempt.id},
        )
        await db_session.execute(text("SET LOCAL session_replication_role = origin"))
        unknown_evidence = PaymentAttemptEvidence(
            attempt_id=attempt.id,
            source="cancellation_regression",
            event_id=f"unknown:{attempt.id.hex}",
            evidence_type="outcome_unknown",
            provider=persisted_attempt.provider,
            provider_reference=persisted_attempt.provider_reference,
            evidence_hash=uuid.uuid4().hex * 2,
            observed_at=await db_session.scalar(text("SELECT clock_timestamp()")),
        )
        db_session.add(unknown_evidence)
        await db_session.flush()
        await db_session.execute(
            text("SELECT coordinate_payment_attempt_write(:attempt_id, :order_id)"),
            {"attempt_id": attempt.id, "order_id": order_id},
        )
        await db_session.execute(
            text("SELECT set_config('shopsoma.payment_lease_token', :token, true)"),
            {"token": str(persisted_attempt.lease_token)},
        )
        persisted_attempt.state = "abandoned_unknown"
        persisted_attempt.terminal_evidence_id = unknown_evidence.id
        persisted_attempt.row_version += 1
        await db_session.commit()
    db_session.expire_all()
    reservation = await db_session.scalar(
        select(StockReservation).where(StockReservation.order_id == order_id)
    )
    reservation_id = reservation.id
    attempt_before = await db_session.get(PaymentAttempt, attempt.id)
    payment_before = await db_session.scalar(
        select(Payment).where(Payment.order_id == order_id)
    )
    attempt_before_cancel = (
        attempt_before.state,
        attempt_before.lease_token,
        attempt_before.claim_expires_at,
        attempt_before.terminal_evidence_id,
        attempt_before.terminal_at,
        attempt_before.row_version,
    )
    payment_before_cancel = (
        payment_before.status,
        payment_before.gateway_response,
        payment_before.completed_at,
        payment_before.failed_at,
        payment_before.failure_reason,
    )

    first_cancel = await client.post(
        f"/api/v1/orders/{order_id}/cancel",
        headers=customer_user["headers"],
        json={"cancellation_reason": "Changed my mind"},
    )
    replay_cancel = await client.post(
        f"/api/v1/orders/{order_id}/cancel",
        headers=customer_user["headers"],
        json={"cancellation_reason": "Try again"},
    )

    assert first_cancel.status_code == replay_cancel.status_code == 409
    db_session.expire_all()
    persisted_order = await db_session.get(Order, order_id)
    persisted_reservation = await db_session.get(StockReservation, reservation_id)
    persisted_attempt = await db_session.get(PaymentAttempt, attempt.id)
    persisted_payment = await db_session.scalar(
        select(Payment).where(Payment.order_id == order_id)
    )
    await db_session.refresh(product)
    assert persisted_order.fulfillment_status == FulfillmentStatus.ORDER_RECEIVED
    assert persisted_order.cancelled_at is None
    assert persisted_order.cancellation_reason is None
    assert persisted_reservation.state == "active"
    assert (
        persisted_attempt.state,
        persisted_attempt.lease_token,
        persisted_attempt.claim_expires_at,
        persisted_attempt.terminal_evidence_id,
        persisted_attempt.terminal_at,
        persisted_attempt.row_version,
    ) == attempt_before_cancel
    assert persisted_attempt.state == unresolved_state
    assert (
        persisted_payment.status,
        persisted_payment.gateway_response,
        persisted_payment.completed_at,
        persisted_payment.failed_at,
        persisted_payment.failure_reason,
    ) == payment_before_cancel
    assert product.total_stock == stock_before

    first_success = await verify_stripe(client, monkeypatch, attempt)
    replay_success = await verify_stripe(client, monkeypatch, attempt)

    assert first_success.status_code == replay_success.status_code == 200
    db_session.expire_all()
    persisted_order = await db_session.get(Order, order_id)
    persisted_reservation = await db_session.get(StockReservation, reservation_id)
    persisted_attempt = await db_session.get(PaymentAttempt, attempt.id)
    await db_session.refresh(product)
    assert persisted_order.payment_status == PaymentStatus.PAID
    assert persisted_order.fulfillment_status == FulfillmentStatus.ORDER_RECEIVED
    assert persisted_reservation.state == "consumed"
    assert persisted_reservation.row_version == 2
    assert persisted_attempt.state == "verified"
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttemptEvidence.id)).where(
                PaymentAttemptEvidence.attempt_id == attempt.id,
                PaymentAttemptEvidence.evidence_type == "payment_verified",
            )
        )
        == 1
    )
    assert product.total_stock == stock_before - persisted_reservation.quantity


@pytest.mark.asyncio
async def test_authenticated_legacy_cancellation_keeps_physical_stock_restoration(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    from app.core.config import settings

    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    stock_before = product.total_stock
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", False)
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
    await db_session.refresh(product)
    assert product.total_stock == stock_before - 1

    cancelled = await client.post(
        f"/api/v1/orders/{created.json()['id']}/cancel",
        headers=customer_user["headers"],
        json={"cancellation_reason": "Legacy control"},
    )

    assert cancelled.status_code == 200, cancelled.text
    await db_session.refresh(product)
    assert product.total_stock == stock_before


@pytest.mark.asyncio
async def test_usd_estimate_converts_ngn_rate_and_threshold_before_persistence(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    rates = list(
        await db_session.scalars(select(ShippingRate).order_by(ShippingRate.priority))
    )
    rates[0].base_rate = Decimal("5000.00")
    rates[0].min_order_value = Decimal("70000.00")
    rates[0].max_order_value = Decimal("90000.00")
    rates[1].is_active = False
    db_session.add(
        Setting(
            key="exchange_rate_usd_to_ngn",
            value="833",
            description="Authoritative test rate",
        )
    )
    await db_session.commit()

    from app.core.config import settings

    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST",
        str(customer_user["user"].id),
    )
    created = await client.post(
        "/api/v1/orders",
        headers=customer_user["headers"],
        json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address_id": str(address.id),
            "currency": "USD",
        },
    )
    assert created.status_code == 201, created.text
    assert Decimal(created.json()["subtotal"]) == Decimal("96.04")

    estimated = await client.post(
        f"/api/v1/orders/{created.json()['id']}/checkout-estimates",
        headers={
            **customer_user["headers"],
            "X-Idempotency-Key": f"usd-estimate-{uuid.uuid4().hex}",
        },
    )

    assert estimated.status_code == 201, estimated.text
    assert estimated.json()["currency"] == "USD"
    assert len(estimated.json()["options"]) == 1
    assert Decimal(estimated.json()["options"][0]["amount"]) == Decimal("6.00")
    option = await db_session.get(
        CheckoutShippingEstimateOption,
        uuid.UUID(estimated.json()["options"][0]["id"]),
    )
    assert option.currency == "USD"
    assert option.amount == Decimal("6.00")


@pytest.mark.asyncio
async def test_ngn_estimate_keeps_ngn_rate_without_conversion(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, _ = await create_enforced_checkout(
        client,
        db_session,
        vendor_user,
        customer_user,
        monkeypatch,
        select_option=False,
    )
    option = await db_session.scalar(
        select(CheckoutShippingEstimateOption)
        .join(
            CheckoutShippingEstimate,
            CheckoutShippingEstimate.id == CheckoutShippingEstimateOption.estimate_id,
        )
        .where(CheckoutShippingEstimate.order_id == order.id)
        .order_by(CheckoutShippingEstimateOption.amount)
        .limit(1)
    )
    # The production route persists the seeded NGN 1,500 rate unchanged.
    assert option.currency == "NGN"
    assert option.amount == Decimal("1500.00")


@pytest.mark.asyncio
@pytest.mark.parametrize("configured_value", [None, "", "0", "-1", "NaN", "Infinity"])
async def test_usd_estimate_fails_closed_without_valid_authoritative_fx(
    client,
    db_session,
    vendor_user,
    customer_user,
    monkeypatch,
    configured_value,
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    db_session.add(
        Setting(
            key="exchange_rate_usd_to_ngn",
            value="833",
            description="Authoritative test rate",
        )
    )
    await db_session.commit()

    from app.core.config import settings

    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST",
        str(customer_user["user"].id),
    )
    created = await client.post(
        "/api/v1/orders",
        headers=customer_user["headers"],
        json={
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "shipping_address_id": str(address.id),
            "currency": "USD",
        },
    )
    assert created.status_code == 201, created.text

    setting = await db_session.scalar(
        select(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
    )
    if configured_value is None:
        await db_session.execute(
            delete(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
        )
    else:
        setting.value = configured_value
    await db_session.commit()

    estimated = await client.post(
        f"/api/v1/orders/{created.json()['id']}/checkout-estimates",
        headers={
            **customer_user["headers"],
            "X-Idempotency-Key": f"invalid-fx-{uuid.uuid4().hex}",
        },
    )

    assert estimated.status_code == 503, estimated.text
    assert estimated.json()["detail"] == "authoritative exchange rate unavailable"
    assert (
        await db_session.scalar(
            select(func.count(CheckoutShippingEstimate.id)).where(
                CheckoutShippingEstimate.order_id == uuid.UUID(created.json()["id"])
            )
        )
        == 0
    )


@pytest.mark.asyncio
async def test_free_shipping_option_survives_real_estimate_and_selection_route(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    address, product = await _domestic_catalogue(db_session, vendor_user, customer_user)
    rates = list(
        await db_session.scalars(select(ShippingRate).order_by(ShippingRate.priority))
    )
    rates[0].name = "Free Shipping"
    rates[0].base_rate = Decimal("0.00")
    rates[1].is_active = False
    await db_session.commit()

    from app.core.config import settings

    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST",
        str(customer_user["user"].id),
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
    estimated = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates",
        headers={
            **customer_user["headers"],
            "X-Idempotency-Key": f"free-estimate-{uuid.uuid4().hex}",
        },
    )
    assert estimated.status_code == 201, estimated.text
    option = estimated.json()["options"][0]
    assert Decimal(option["amount"]) == Decimal("0.00")

    selected = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{estimated.json()['id']}"
        f"/options/{option['id']}/select",
        headers={
            **customer_user["headers"],
            "X-Idempotency-Key": f"free-select-{uuid.uuid4().hex}",
        },
    )
    assert selected.status_code == 200, selected.text
    assert Decimal(selected.json()["selected_option"]["amount"]) == Decimal("0.00")


async def _fail_initialized_stripe_payment(client, monkeypatch, attempt):
    from app.api.v1 import payments

    canceled = SimpleNamespace(
        id=attempt.provider_transaction_id,
        status="canceled",
        amount=int(Decimal(attempt.amount) * 100),
        currency=attempt.currency.lower(),
        metadata={"shopsoma_payment_reference": attempt.provider_reference},
        last_payment_error=SimpleNamespace(message="Canceled"),
    )
    monkeypatch.setattr(
        payments.stripe.PaymentIntent, "retrieve", lambda _value: canceled
    )
    response = await client.post(
        "/api/v1/payments/verify",
        json={
            "payment_gateway": "stripe",
            "payment_intent_id": attempt.provider_transaction_id,
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_failed_payment_retry_re_reserves_exact_stock_once_before_provider(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    from app.api.v1 import payments
    from tests.test_verified_payment_inventory import initialize_stripe

    customer_email = customer_user["user"].email
    order, _ = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    first = await initialize_stripe(
        client,
        db_session,
        customer_user,
        monkeypatch,
        order,
        transaction_id="pi_retry_released",
    )
    await _fail_initialized_stripe_payment(client, monkeypatch, first)
    db_session.expire_all()
    old_reservation = await db_session.scalar(
        select(StockReservation).where(StockReservation.order_id == order_id)
    )
    assert old_reservation.state == "released"

    provider_calls = 0

    def create_intent(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return SimpleNamespace(id="pi_retry_success", client_secret="retry_secret")

    monkeypatch.setattr(payments.stripe.PaymentIntent, "create", create_intent)
    payload = {
        "order_id": str(order_id),
        "email": customer_email,
        "payment_gateway": "stripe",
        "currency": "NGN",
    }
    retried = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json=payload,
    )
    replay = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json=payload,
    )

    assert retried.status_code == replay.status_code == 200
    assert provider_calls == 1
    db_session.expire_all()
    reservations = list(
        await db_session.scalars(
            select(StockReservation)
            .where(StockReservation.order_id == order_id)
            .order_by(StockReservation.created_at)
        )
    )
    attempts = list(
        await db_session.scalars(
            select(PaymentAttempt)
            .where(PaymentAttempt.order_id == order_id)
            .order_by(PaymentAttempt.created_at)
        )
    )
    coverage_reservation_id = await db_session.scalar(
        select(OrderInventoryCoverage.reservation_id).where(
            OrderInventoryCoverage.order_id == order_id
        )
    )
    assert [row.state for row in reservations] == ["released", "active"]
    assert coverage_reservation_id == reservations[-1].id
    assert len(attempts) == 2
    assert attempts[-1].supersedes_attempt_id == attempts[0].id
    assert sorted(
        await db_session.scalars(
            select(Payment.transaction_id).where(Payment.order_id == order_id)
        )
    ) == ["pi_retry_released", "pi_retry_success"]


@pytest.mark.asyncio
async def test_failed_payment_retry_with_insufficient_stock_rolls_back_before_provider(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    from app.api.v1 import payments
    from tests.test_verified_payment_inventory import initialize_stripe

    customer_email = customer_user["user"].email
    order, product = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    first = await initialize_stripe(
        client,
        db_session,
        customer_user,
        monkeypatch,
        order,
        transaction_id="pi_retry_insufficient",
    )
    await _fail_initialized_stripe_payment(client, monkeypatch, first)
    await db_session.refresh(product)
    product.total_stock = 0
    await db_session.commit()
    provider_calls = 0

    def forbidden_provider(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider boundary must remain closed")

    monkeypatch.setattr(payments.stripe.PaymentIntent, "create", forbidden_provider)
    retried = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_email,
            "payment_gateway": "stripe",
            "currency": "NGN",
        },
    )

    assert retried.status_code == 409, retried.text
    assert provider_calls == 0
    db_session.expire_all()
    assert (
        await db_session.scalar(
            select(func.count(StockReservation.id)).where(
                StockReservation.order_id == order_id
            )
        )
        == 1
    )
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttempt.id)).where(
                PaymentAttempt.order_id == order_id
            )
        )
        == 1
    )


@pytest.mark.asyncio
async def test_quarantined_legacy_order_rejects_payment_initialization_before_provider(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    from app.api.v1 import payments

    order, _ = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    order_id = order.id
    order.workflow_cohort = "legacy_ambiguous_quarantined"
    order.workflow_policy_version = "legacy_quarantine_v1"
    order.checkout_access_mode = "legacy_quarantined"
    await db_session.commit()

    provider_calls = 0

    def forbidden_provider(**_kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise AssertionError("provider boundary must remain closed")

    monkeypatch.setattr(payments.stripe.PaymentIntent, "create", forbidden_provider)
    response = await client.post(
        "/api/v1/payments/initialize",
        headers=customer_user["headers"],
        json={
            "order_id": str(order_id),
            "email": customer_user["user"].email,
            "payment_gateway": "stripe",
            "currency": "NGN",
        },
    )

    assert response.status_code == 409, response.text
    assert provider_calls == 0
    assert (
        await db_session.scalar(
            select(func.count(PaymentAttempt.id)).where(PaymentAttempt.order_id == order_id)
        )
        == 0
    )


def test_checkout_outbox_task_is_registered_on_production_worker_entrypoint():
    from app.celery_app import celery_app

    assert "app.tasks.checkout_outbox.dispatch_checkout_outbox" in celery_app.tasks
    schedule = celery_app.conf.beat_schedule["dispatch-checkout-outbox"]
    assert schedule["task"] == "app.tasks.checkout_outbox.dispatch_checkout_outbox"


def test_checkout_outbox_sync_ticks_dispose_pooled_engine_between_event_loops(
    monkeypatch,
):
    from app.tasks import checkout_outbox

    pooled_engine = create_async_engine(
        _ASYNC_TEST_DATABASE_URL, pool_size=1, max_overflow=0
    )
    progress = []

    async def database_tick():
        async with pooled_engine.connect() as connection:
            progress.append(await connection.scalar(text("SELECT 1")))
        return {"progress": len(progress)}

    monkeypatch.setattr(checkout_outbox, "engine", pooled_engine, raising=False)
    monkeypatch.setattr(checkout_outbox, "dispatch_checkout_events_once", database_tick)

    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None
    try:
        assert checkout_outbox.dispatch_checkout_outbox() == {"progress": 1}
        assert checkout_outbox.dispatch_checkout_outbox() == {"progress": 2}
        assert progress == [1, 1]
    finally:
        if previous_loop is not None:
            asyncio.set_event_loop(previous_loop)


def test_checkout_outbox_sync_tick_disposes_engine_when_dispatch_raises(monkeypatch):
    from app.tasks import checkout_outbox

    disposed_on = []

    class TrackedEngine:
        async def dispose(self):
            disposed_on.append(asyncio.get_running_loop())

    async def failed_tick():
        raise RuntimeError("dispatch failed")

    monkeypatch.setattr(checkout_outbox, "engine", TrackedEngine(), raising=False)
    monkeypatch.setattr(checkout_outbox, "dispatch_checkout_events_once", failed_tick)

    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None
    try:
        with pytest.raises(RuntimeError, match="dispatch failed"):
            checkout_outbox.dispatch_checkout_outbox()
    finally:
        if previous_loop is not None:
            asyncio.set_event_loop(previous_loop)

    assert len(disposed_on) == 1
    assert disposed_on[0].is_closed()


@pytest.mark.asyncio
async def test_late_payment_exception_dispatch_fails_durably_in_outbox(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, _ = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    event = await enqueue_checkout_event(
        db_session,
        event_type="late_payment_exception",
        source_id=uuid.uuid4(),
        order_id=order.id,
        payload={
            "version": 1,
            "order_id": str(order.id),
            "workflow_cohort": "domestic_checkout_v1",
            "reason_code": "reservation_released",
        },
    )
    event_id = event.id
    await db_session.commit()

    from app.tasks.checkout_outbox import dispatch_checkout_events_once

    result = await dispatch_checkout_events_once(
        session_factory=TestSessionLocal, owner="test-worker", limit=10
    )

    assert result == {"claimed": 1, "completed": 0, "retried": 0, "failed": 1}
    db_session.expire_all()
    persisted = await db_session.get(CheckoutOutboxEvent, event_id)
    assert persisted.status == "failed"
    assert (
        persisted.failure_code
        == "late-payment:reservation_released:manual-reconciliation-required"
    )


@pytest.mark.asyncio
async def test_verified_event_dispatches_vendor_start_effects_exactly_once(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, _ = await create_enforced_checkout(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
    event = await enqueue_checkout_event(
        db_session,
        event_type="payment_verified_start_order",
        source_id=uuid.uuid4(),
        order_id=order.id,
        payload={
            "version": 1,
            "order_id": str(order.id),
            "workflow_cohort": "domestic_checkout_v1",
        },
    )
    order.payment_status = PaymentStatus.PAID
    await db_session.commit()
    event_id = event.id

    from app.tasks.checkout_outbox import dispatch_checkout_events_once

    await db_session.refresh(order, ["items"])
    expected_pickups = len(order.items)
    order_id = order.id
    first = await dispatch_checkout_events_once(
        session_factory=TestSessionLocal, owner="test-worker", limit=10
    )
    second = await dispatch_checkout_events_once(
        session_factory=TestSessionLocal, owner="test-worker", limit=10
    )

    assert first == {"claimed": 1, "completed": 1, "retried": 0, "failed": 0}
    assert second == {"claimed": 0, "completed": 0, "retried": 0, "failed": 0}
    db_session.expire_all()
    assert (
        await db_session.scalar(
            select(func.count(VendorPickup.id)).where(VendorPickup.order_id == order_id)
        )
        == expected_pickups
    )
    assert (
        await db_session.scalar(
            select(func.count(VendorNotification.id)).where(
                VendorNotification.order_id == order_id,
                VendorNotification.notification_type == "order_placed",
            )
        )
        == 1
    )
    persisted = await db_session.get(CheckoutOutboxEvent, event_id)
    assert persisted.status == "completed"


@pytest.mark.asyncio
async def test_verified_event_marks_made_to_order_pickup_with_custom_timeline(
    client, db_session, vendor_user, customer_user, monkeypatch
):
    order, _ = await create_enforced_checkout(
        client,
        db_session,
        vendor_user,
        customer_user,
        monkeypatch,
        made_to_order=True,
    )
    await db_session.refresh(order, ["items"])
    item = order.items[0]
    item_id = item.id
    event = await enqueue_checkout_event(
        db_session,
        event_type="payment_verified_start_order",
        source_id=uuid.uuid4(),
        order_id=order.id,
        payload={
            "version": 1,
            "order_id": str(order.id),
            "workflow_cohort": "domestic_checkout_v1",
        },
    )
    order.payment_status = PaymentStatus.PAID
    await db_session.commit()

    from app.tasks.checkout_outbox import dispatch_checkout_events_once

    result = await dispatch_checkout_events_once(
        session_factory=TestSessionLocal, owner="test-worker", limit=10
    )

    assert result == {"claimed": 1, "completed": 1, "retried": 0, "failed": 0}
    db_session.expire_all()
    pickup = await db_session.scalar(
        select(VendorPickup).where(VendorPickup.order_item_id == item_id)
    )
    assert pickup.order_type == OrderType.MADE_TO_ORDER
    assert pickup.estimated_production_days == 7
    assert pickup.scheduled_pickup_date >= datetime.now(timezone.utc) + timedelta(days=6)
