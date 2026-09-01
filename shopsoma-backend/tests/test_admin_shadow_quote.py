import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models.domestic_rate_quote import DomesticRateAttempt, DomesticRateOffer, DomesticRateResponse
from app.services.admin_shadow_quote import ShadowQuoteError, run_admin_shadow_quote
from app.services.dhl.rating import DHLDomesticRateOffer, DHLDomesticRateResult
from app.services.shipping.contracts import DomesticRate
from tests.test_domestic_rate_persistence import _subject


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


@pytest.mark.asyncio
async def test_admin_shadow_quote_persists_lawful_evidence(
    monkeypatch, db_session, vendor_user, customer_user, admin_user
):
    graph, package, seal, intent = await _subject(db_session, vendor_user, customer_user)
    monkeypatch.setattr(
        "app.services.admin_shadow_quote.create_sandbox_domestic_rate_adapter",
        lambda **kwargs: _FakeAdapter(),
    )

    settings = Settings(
        SECRET_KEY="shadow-quote-test-secret",
        DATABASE_URL="postgresql://shadow:shadow@localhost:5432/shadow_test",
        DHL_ENABLED=True,
        DHL_ENVIRONMENT="sandbox",
        DHL_API_USERNAME="sandbox-user",
        DHL_API_PASSWORD="sandbox-pass",
        DHL_EXPORT_ACCOUNT_NUMBER="123456789",
        DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=True,
        DHL_DOMESTIC_QUOTE_TTL_SECONDS=1800,
        DHL_DOMESTIC_SANDBOX_COHORT_IDS=str(graph["cohort"].id),
        CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION=7,
        CHECKOUT_CAPABILITY_ACTIVE_PEPPER="shadow-pepper",
        _env_file=None,
    )

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
            select(DomesticRateAttempt).where(DomesticRateAttempt.order_id == graph["order"].id)
        )
    ).scalar_one()
    response = (
        await db_session.execute(
            select(DomesticRateResponse).where(DomesticRateResponse.attempt_id == attempt.id)
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
    assert response.completion_txid == attempt.completion_txid
    assert response.ttl_seconds == 1800
    assert offer.service_label == "DHL Sandbox Express"
    assert offer.total_amount == Decimal("4500.00")


@pytest.mark.asyncio
async def test_admin_shadow_quote_rejects_non_allowlisted_cohort(
    monkeypatch, db_session, vendor_user, customer_user, admin_user
):
    graph, _package, _seal, _intent = await _subject(db_session, vendor_user, customer_user)
    monkeypatch.setattr(
        "app.services.admin_shadow_quote.create_sandbox_domestic_rate_adapter",
        lambda **kwargs: _FakeAdapter(),
    )

    settings = Settings(
        SECRET_KEY="shadow-quote-test-secret",
        DATABASE_URL="postgresql://shadow:shadow@localhost:5432/shadow_test",
        DHL_ENABLED=True,
        DHL_ENVIRONMENT="sandbox",
        DHL_API_USERNAME="sandbox-user",
        DHL_API_PASSWORD="sandbox-pass",
        DHL_EXPORT_ACCOUNT_NUMBER="123456789",
        DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=True,
        DHL_DOMESTIC_QUOTE_TTL_SECONDS=1800,
        DHL_DOMESTIC_SANDBOX_COHORT_IDS=str(uuid.uuid4()),
        CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION=7,
        CHECKOUT_CAPABILITY_ACTIVE_PEPPER="shadow-pepper",
        _env_file=None,
    )

    with pytest.raises(ShadowQuoteError, match="outside sandbox cohort allowlist"):
        await run_admin_shadow_quote(
            db=db_session,
            order_id=graph["order"].id,
            admin=admin_user["user"],
            settings=settings,
            identity_key=b"shadow-pepper",
            identity_key_version="checkout-capability-v7",
        )
