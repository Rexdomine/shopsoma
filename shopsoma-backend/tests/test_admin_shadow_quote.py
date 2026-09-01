import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models.domestic_rate_quote import (
    DomesticRateAttempt,
    DomesticRateOffer,
    DomesticRateResponse,
)
from app.models.package_custody import OutboundShipmentIntent
from app.services.admin_shadow_quote import ShadowQuoteError, run_admin_shadow_quote
from app.services.dhl.rating import (
    DHLDomesticRateOffer,
    DHLDomesticRateResult,
    DHLRateAdapterError,
)
from app.services.shipping.contracts import DomesticRate
from tests.test_domestic_rate_persistence import _subject
from tests.test_package_custody_persistence import _ready_package


class _FakeAdapter:
    async def rate(self, resolved_hub, request):
        return DHLDomesticRateResult(
            result_kind="success",
            offers=(
                DHLDomesticRateOffer(
                    provider_product_code="P",
                    provider_service_code="S",
                    service_label="DHL Sandbox Express",
                    rate=DomesticRate(
                        rate_id="shadow-rate-p",
                        service_id="shadow-service-s",
                        package=request.package,
                        total_amount=Decimal("4500.00"),
                        currency="NGN",
                        carrier_transit_days=2,
                        estimated_carrier_delivery_date=None,
                    ),
                ),
            ),
        )


def _settings(cohort_id):
    return Settings(
        SECRET_KEY="shadow-quote-test-secret",
        DATABASE_URL="postgresql://shadow:***@localhost:5432/shadow_test",
        DHL_ENABLED=True,
        DHL_ENVIRONMENT="sandbox",
        DHL_API_USERNAME="sandbox-user",
        DHL_API_PASSWORD="sandbox-pass",
        DHL_EXPORT_ACCOUNT_NUMBER="123456789",
        DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=True,
        DHL_DOMESTIC_QUOTE_TTL_SECONDS=1800,
        DHL_DOMESTIC_SANDBOX_COHORT_IDS=str(cohort_id),
        CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION=7,
        CHECKOUT_CAPABILITY_ACTIVE_PEPPER="shadow-pepper",
        _env_file=None,
    )


@pytest.mark.asyncio
async def test_admin_shadow_quote_persists_lawful_evidence_and_floors_planned_ship_date(
    monkeypatch, db_session, vendor_user, customer_user, admin_user
):
    from app.services import admin_shadow_quote as shadow_quote_service

    graph, package, seal, intent = await _subject(db_session, vendor_user, customer_user)
    monkeypatch.setattr(
        "app.services.admin_shadow_quote.create_sandbox_domestic_rate_adapter",
        lambda **kwargs: _FakeAdapter(),
    )

    frozen_today = date.today() + timedelta(days=5)

    class _FutureDate(date):
        @classmethod
        def today(cls):
            return frozen_today

    monkeypatch.setattr(shadow_quote_service, "date", _FutureDate)
    settings = _settings(graph["cohort"].id)

    result = await run_admin_shadow_quote(
        db=db_session,
        order_id=graph["order"].id,
        admin=admin_user["user"],
        settings=settings,
        identity_key=b"shadow-pepper",
        identity_key_version="checkout-capability-v7",
    )

    assert result.result_kind == "success"
    assert result.environment == "sandbox"
    assert result.offers_count == 1

    attempt = (
        await db_session.execute(
            select(DomesticRateAttempt).where(
                DomesticRateAttempt.order_id == graph["order"].id
            )
        )
    ).scalar_one()
    response = (
        await db_session.execute(
            select(DomesticRateResponse).where(
                DomesticRateResponse.attempt_id == attempt.id
            )
        )
    ).scalar_one()
    offer = (
        await db_session.execute(
            select(DomesticRateOffer).where(DomesticRateOffer.response_id == response.id)
        )
    ).scalar_one()

    assert attempt.classification == "success"
    assert attempt.call_started_at is not None
    assert attempt.result_recorded_at is not None
    assert attempt.account_alias == "dhl-ng-sandbox"
    assert attempt.planned_ship_date == frozen_today
    assert response.completion_txid == attempt.completion_txid
    assert response.ttl_seconds == 1800
    assert offer.service_label == "DHL Sandbox Express"
    assert offer.total_amount == Decimal("4500.00")


@pytest.mark.asyncio
async def test_admin_shadow_quote_requires_package_id_when_multiple_ready_packages(
    monkeypatch, db_session, vendor_user, customer_user, admin_user
):
    graph, _package, _seal, _intent = await _subject(
        db_session, vendor_user, customer_user
    )
    package2, _version2, _item2, seal2 = await _ready_package(db_session, graph)
    intent2 = OutboundShipmentIntent(
        package_id=package2.id,
        package_version=1,
        seal_id=seal2.id,
        order_id=graph["order"].id,
        origin_hub_id=graph["hub"].id,
        destination_name="Rate Test Customer",
        destination_phone="+234****0000",
        destination_address_line1="1 Private Destination Road",
        destination_city="Lagos",
        destination_state="Lagos",
        destination_postal_code="100001",
        destination_country_code="NG",
        source_command="prepare_outbound",
        idempotency_key=f"intent-{uuid.uuid4().hex}",
        created_by_id=graph["operator_id"],
    )
    db_session.add(intent2)
    await db_session.flush()
    monkeypatch.setattr(
        "app.services.admin_shadow_quote.create_sandbox_domestic_rate_adapter",
        lambda **kwargs: _FakeAdapter(),
    )

    settings = _settings(graph["cohort"].id)

    with pytest.raises(
        ShadowQuoteError, match="multiple ready packages for order; package_id is required"
    ):
        await run_admin_shadow_quote(
            db=db_session,
            order_id=graph["order"].id,
            admin=admin_user["user"],
            settings=settings,
            identity_key=b"shadow-pepper",
            identity_key_version="checkout-capability-v7",
        )

    result = await run_admin_shadow_quote(
        db=db_session,
        order_id=graph["order"].id,
        ready_package_id=package2.id,
        admin=admin_user["user"],
        settings=settings,
        identity_key=b"shadow-pepper",
        identity_key_version="checkout-capability-v7",
    )

    assert result.result_kind == "success"
    selected_attempt = (
        await db_session.execute(
            select(DomesticRateAttempt).where(DomesticRateAttempt.package_id == package2.id)
        )
    ).scalar_one()
    assert selected_attempt.package_id == package2.id


@pytest.mark.asyncio
async def test_admin_shadow_quote_rejects_non_allowlisted_cohort(
    monkeypatch, db_session, vendor_user, customer_user, admin_user
):
    graph, _package, _seal, _intent = await _subject(
        db_session, vendor_user, customer_user
    )
    monkeypatch.setattr(
        "app.services.admin_shadow_quote.create_sandbox_domestic_rate_adapter",
        lambda **kwargs: _FakeAdapter(),
    )

    settings = _settings(uuid.uuid4())

    with pytest.raises(ShadowQuoteError, match="outside sandbox cohort allowlist"):
        await run_admin_shadow_quote(
            db=db_session,
            order_id=graph["order"].id,
            admin=admin_user["user"],
            settings=settings,
            identity_key=b"shadow-pepper",
            identity_key_version="checkout-capability-v7",
        )


@pytest.mark.asyncio
async def test_admin_shadow_quote_persists_failure_when_adapter_factory_rejects(
    monkeypatch, db_session, vendor_user, customer_user, admin_user
):
    graph, _package, _seal, _intent = await _subject(
        db_session, vendor_user, customer_user
    )

    def _raise_adapter_error(**kwargs):
        raise DHLRateAdapterError("domestic DHL provider calls are disabled")

    monkeypatch.setattr(
        "app.services.admin_shadow_quote.create_sandbox_domestic_rate_adapter",
        _raise_adapter_error,
    )

    result = await run_admin_shadow_quote(
        db=db_session,
        order_id=graph["order"].id,
        admin=admin_user["user"],
        settings=_settings(graph["cohort"].id),
        identity_key=b"shadow-pepper",
        identity_key_version="checkout-capability-v7",
    )

    assert result.result_kind == "failed"
    assert result.offers_count == 0
    assert result.note == "adapter rate failed; evidence persisted with admin attribution"

    attempt = (
        await db_session.execute(
            select(DomesticRateAttempt).where(
                DomesticRateAttempt.order_id == graph["order"].id
            )
        )
    ).scalar_one()
    assert attempt.classification == "failure"
    assert attempt.failure_code == "adapter_rate_failure"

    responses = (
        await db_session.execute(
            select(DomesticRateResponse).where(
                DomesticRateResponse.attempt_id == attempt.id
            )
        )
    ).scalars().all()
    assert responses == []
