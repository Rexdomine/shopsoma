"""Public preview compatibility before partial-cohort order classification."""
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.api.v1 import shipping_rates
from app.core.config import settings
from app.models.app_setting import AppSetting
from app.models.shipping_rate import ShippingRate
from app.services.checkout import estimates


@pytest.mark.asyncio
@pytest.mark.parametrize("audience", ["guest", "enrolled", "nonenrolled"])
@pytest.mark.parametrize(
    "key,value,expected_status",
    [
        (None, None, 200),
        ("shipping_provider", "dhl", 503),
        ("shipping_provider", "manual", 200),
        ("shipping_provider", "shipbubble", 503),
        ("shipping_use_shipbubble", "true", 503),
    ],
    ids=["absent", "explicit-dhl", "manual", "explicit-shipbubble", "legacy-shipbubble"],
)
async def test_public_preview_with_ready_dhl_partial_cohort(
    client, db_session, customer_user, monkeypatch, audience, key, value, expected_status
):
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    monkeypatch.setattr(settings, "DHL_ENVIRONMENT", "sandbox")
    for flag in (
        "DHL_ENABLED", "DHL_DOMESTIC_WORKFLOW_ENABLED",
        "DHL_DOMESTIC_PROVIDER_CALLS_ENABLED", "DHL_DOMESTIC_CHECKOUT_ENABLED",
        "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED",
    ):
        monkeypatch.setattr(settings, flag, True)
    for credential in ("DHL_API_USERNAME", "DHL_API_PASSWORD", "DHL_EXPORT_ACCOUNT_NUMBER"):
        monkeypatch.setattr(settings, credential, SecretStr("local-test-only"))
    cohort_id = str(customer_user["user"].id) if audience == "enrolled" else str(uuid4())
    monkeypatch.setattr(settings, "DHL_DOMESTIC_SANDBOX_COHORT_IDS", cohort_id)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_ALLOWLIST", cohort_id)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 0)

    dhl_adapter = Mock(side_effect=AssertionError("Preview must not construct a DHL adapter"))
    shipbubble_adapter = Mock(side_effect=AssertionError("Preview must not call ShipBubble"))
    monkeypatch.setattr(estimates, "create_sandbox_domestic_rate_adapter", dhl_adapter)
    monkeypatch.setattr(shipping_rates, "get_shipbubble_service", shipbubble_adapter)

    assert db_session.bind.dialect.name == "postgresql"
    assert await db_session.scalar(select(AppSetting).where(
        AppSetting.key.in_(("shipping_provider", "shipping_use_shipbubble"))
    )) is None
    if key:
        db_session.add(AppSetting(key=key, value=value, value_type="string"))
    rate = ShippingRate(
        name="Partial cohort preview", base_rate=Decimal("1500.00"),
        country="Nigeria", state="Lagos", is_active=True, is_default=True,
    )
    db_session.add(rate)
    await db_session.commit()

    config = await client.get("/api/v1/settings/shipping-provider")
    assert config.status_code == 200, config.text
    assert config.json()["readiness"]["dhl"] is True
    assert config.json()["checkout_estimates_required"] is False
    if key is None:
        assert config.json()["provider"] == "dhl"

    headers = {} if audience == "guest" else customer_user["headers"]
    response = await client.post(
        "/api/v1/shipping-rates/calculate", headers=headers,
        json={"country": "Nigeria", "state": "Lagos", "order_value": 60000},
    )
    dhl_adapter.assert_not_called()
    shipbubble_adapter.assert_not_called()
    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        assert [item["id"] for item in response.json()["available_rates"]] == [str(rate.id)]
        assert response.json()["recommended_rate"]["id"] == str(rate.id)
        assert Decimal(str(response.json()["recommended_rate"]["base_rate"])) == Decimal("1500")
    else:
        assert "requires manual mode" in response.json()["detail"]
