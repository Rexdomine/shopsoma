"""Automated tests for combined shipping provider mode (DHL Express + ShipBubble couriers)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.app_setting import AppSetting
from app.models.order import Order
from app.services.shipbubble_service import ShipbubbleRateOption, ShipbubbleRatesResult
from tests.test_dhl_e2e_sandbox import (
    _create_checkout_order_for_dhl,
    _enable_dhl_checkout_settings,
)


def _mock_dhl_offers() -> tuple[SimpleNamespace, ...]:
    eta_dt = (datetime.now(UTC) + timedelta(days=2)).date()
    return (
        SimpleNamespace(
            provider_product_code="N",
            provider_service_code="DOM-N",
            service_label="DHL DOMESTIC EXPRESS",
            rate=SimpleNamespace(
                total_amount=Decimal("12500.00"),
                currency="NGN",
                carrier_transit_days=2,
                estimated_carrier_delivery_date=eta_dt,
            ),
        ),
    )


def _mock_shipbubble_rates() -> ShipbubbleRatesResult:
    couriers = [
        ShipbubbleRateOption(
            courier_id="gig-logistics",
            courier_name="GIG Logistics Standard",
            service_code="gig-std",
            rate_card_amount=Decimal("3500.00"),
            total_wallet_amount=Decimal("3300.00"),
            currency="NGN",
            delivery_eta="2-3 days",
            min_delivery_days=2,
            max_delivery_days=3,
            courier_image="https://example.com/gig.png",
        ),
        ShipbubbleRateOption(
            courier_id="topship",
            courier_name="Topship Express",
            service_code="topship-exp",
            rate_card_amount=Decimal("4200.00"),
            total_wallet_amount=Decimal("4000.00"),
            currency="NGN",
            delivery_eta="1-2 days",
            min_delivery_days=1,
            max_delivery_days=2,
            courier_image="https://example.com/topship.png",
        ),
    ]
    return ShipbubbleRatesResult(
        request_token="sb-test-request-token-12345",
        couriers=couriers,
        cheapest_courier=couriers[0],
        fastest_courier=couriers[1],
    )


@pytest.mark.asyncio
async def test_combined_shipping_settings_schema_and_switch(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Admin can configure 'combined' provider mode through shipping settings endpoint."""
    admin_token = admin_user["token"]
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", "sb_live_secret_key_12345")

    # 1. Update shipping provider to 'combined'
    res = await client.put(
        "/api/v1/settings/shipping-provider",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"provider": "combined"},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["provider"] == "combined"
    assert "combined" in data["readiness"]
    assert data["use_shipbubble"] is True

    # 2. Verify setting was persisted in database
    setting = await db_session.scalar(
        select(AppSetting).where(AppSetting.key == "shipping_provider")
    )
    assert setting is not None
    assert setting.value == "combined"


@pytest.mark.asyncio
async def test_combined_shipping_returns_both_dhl_and_shipbubble_options(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Combined mode returns both DHL Express and ShipBubble couriers in estimate options."""
    cohort_seed = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", "sb_live_secret_key_12345")
    await _enable_dhl_checkout_settings(
        db_session,
        monkeypatch,
        cohort_seed=cohort_seed,
        actor_id=admin_user["user"].id,
    )

    # Set shipping provider to 'combined'
    provider_row = await db_session.scalar(
        select(AppSetting).where(AppSetting.key == "shipping_provider")
    )
    provider_row.value = "combined"
    await db_session.commit()

    order = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="NGN",
        subtotal=Decimal("50000.00"),
    )

    customer_token = customer_user["token"]

    with patch(
        "app.services.checkout.estimates._dhl_checkout_options",
        new=AsyncMock(return_value=_mock_dhl_offers()),
    ), patch(
        "app.services.checkout.estimates._shipbubble_checkout_options",
        new=AsyncMock(return_value=_mock_shipbubble_rates()),
    ):
        est_res = await client.post(
            f"/api/v1/orders/{order.id}/checkout-estimates",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"comb-est-{order.id.hex[:12]}",
            },
        )
        assert est_res.status_code == 201, est_res.text
        body = est_res.json()
        options = body["options"]

        # Should contain DHL option + 2 ShipBubble options = 3 total options
        assert len(options) == 3

        dhl_opts = [o for o in options if o.get("provider_metadata", {}).get("provider") == "dhl"]
        sb_opts = [o for o in options if o.get("provider_metadata", {}).get("provider") == "shipbubble"]

        assert len(dhl_opts) == 1
        assert "DHL" in dhl_opts[0]["service_label"]
        assert Decimal(str(dhl_opts[0]["amount"])) == Decimal("12500.00")

        assert len(sb_opts) == 2
        labels = [o["service_label"] for o in sb_opts]
        assert any("GIG Logistics" in lbl for lbl in labels)
        assert any("Topship" in lbl for lbl in labels)

        # 3. Select DHL option -> order delivery_provider is set to 'dhl'
        sel_dhl_res = await client.post(
            f"/api/v1/orders/{order.id}/checkout-estimates/{body['id']}/options/{dhl_opts[0]['id']}/select",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"sel-dhl-{order.id.hex[:12]}",
            },
        )
        assert sel_dhl_res.status_code == 200, sel_dhl_res.text
        await db_session.refresh(order)
        assert order.delivery_provider == "dhl"


@pytest.mark.asyncio
async def test_combined_shipping_select_shipbubble_option_persists_provider(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Selecting a ShipBubble option under combined mode correctly sets delivery_provider to 'shipbubble'."""
    cohort_seed = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", "sb_live_secret_key_12345")
    await _enable_dhl_checkout_settings(
        db_session,
        monkeypatch,
        cohort_seed=cohort_seed,
        actor_id=admin_user["user"].id,
    )

    provider_row = await db_session.scalar(
        select(AppSetting).where(AppSetting.key == "shipping_provider")
    )
    provider_row.value = "combined"
    await db_session.commit()

    order = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="NGN",
        subtotal=Decimal("50000.00"),
    )

    customer_token = customer_user["token"]

    with patch(
        "app.services.checkout.estimates._dhl_checkout_options",
        new=AsyncMock(return_value=_mock_dhl_offers()),
    ), patch(
        "app.services.checkout.estimates._shipbubble_checkout_options",
        new=AsyncMock(return_value=_mock_shipbubble_rates()),
    ):
        est_res = await client.post(
            f"/api/v1/orders/{order.id}/checkout-estimates",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"comb-sb-est-{order.id.hex[:12]}",
            },
        )
        assert est_res.status_code == 201, est_res.text
        body = est_res.json()
        sb_opt = next(
            o for o in body["options"]
            if o.get("provider_metadata", {}).get("provider") == "shipbubble"
        )

        sel_res = await client.post(
            f"/api/v1/orders/{order.id}/checkout-estimates/{body['id']}/options/{sb_opt['id']}/select",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"sel-sb-{order.id.hex[:12]}",
            },
        )
        assert sel_res.status_code == 200, sel_res.text
        await db_session.refresh(order)
        assert order.delivery_provider == "shipbubble"


@pytest.mark.asyncio
async def test_combined_shipping_resilience_when_one_provider_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """If one provider fails, the other provider's options are still returned cleanly."""
    cohort_seed = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", "sb_live_secret_key_12345")
    await _enable_dhl_checkout_settings(
        db_session,
        monkeypatch,
        cohort_seed=cohort_seed,
        actor_id=admin_user["user"].id,
    )

    provider_row = await db_session.scalar(
        select(AppSetting).where(AppSetting.key == "shipping_provider")
    )
    provider_row.value = "combined"
    await db_session.commit()

    order = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="NGN",
        subtotal=Decimal("50000.00"),
    )
    customer_token = customer_user["token"]

    # 1. DHL fails, ShipBubble succeeds -> returns ShipBubble options
    with patch(
        "app.services.checkout.estimates._dhl_checkout_options",
        new=AsyncMock(side_effect=Exception("DHL network timeout")),
    ), patch(
        "app.services.checkout.estimates._shipbubble_checkout_options",
        new=AsyncMock(return_value=_mock_shipbubble_rates()),
    ):
        res1 = await client.post(
            f"/api/v1/orders/{order.id}/checkout-estimates",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"fallback-sb-{order.id.hex[:12]}",
            },
        )
        assert res1.status_code == 201, res1.text
        body1 = res1.json()
        assert len(body1["options"]) == 2
        assert all(o["provider_metadata"]["provider"] == "shipbubble" for o in body1["options"])

    # 2. ShipBubble fails, DHL succeeds -> returns DHL options
    order2 = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="NGN",
        subtotal=Decimal("50000.00"),
    )
    with patch(
        "app.services.checkout.estimates._dhl_checkout_options",
        new=AsyncMock(return_value=_mock_dhl_offers()),
    ), patch(
        "app.services.checkout.estimates._shipbubble_checkout_options",
        new=AsyncMock(side_effect=Exception("ShipBubble 500 server error")),
    ):
        res2 = await client.post(
            f"/api/v1/orders/{order2.id}/checkout-estimates",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"fallback-dhl-{order2.id.hex[:12]}",
            },
        )
        assert res2.status_code == 201, res2.text
        body2 = res2.json()
        assert len(body2["options"]) == 1
        assert body2["options"][0]["provider_metadata"]["provider"] == "dhl"


@pytest.mark.asyncio
async def test_three_way_shipping_providers_settings_and_estimate_options(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Admin enables all three providers (manual + DHL + ShipBubble); checkout displays options from all three."""
    cohort_seed = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", "sb_live_secret_key_12345")
    await _enable_dhl_checkout_settings(
        db_session,
        monkeypatch,
        cohort_seed=cohort_seed,
        actor_id=admin_user["user"].id,
    )

    admin_token = admin_user["token"]

    # Seed an eligible manual rate for Abuja / FCT
    from app.models.shipping_rate import ShippingRate
    manual_rate = ShippingRate(
        id=uuid.uuid4(),
        name="Standard Abuja Delivery",
        description="2-3 days",
        base_rate=Decimal("2500.00"),
        country="Nigeria",
        state="FCT",
        min_delivery_days=2,
        max_delivery_days=3,
        is_active=True,
        is_default=True,
        priority=1,
    )
    db_session.add(manual_rate)
    await db_session.commit()

    # 1. Admin configures all 3 providers
    put_res = await client.put(
        "/api/v1/settings/shipping-provider",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"enabled_providers": ["manual", "dhl", "shipbubble"]},
    )
    assert put_res.status_code == 200, put_res.text
    put_data = put_res.json()
    assert put_data["provider"] == "combined"
    assert put_data["enabled_providers"] == ["manual", "dhl", "shipbubble"]

    # 2. Customer creates checkout estimate
    order = await _create_checkout_order_for_dhl(
        db_session,
        customer_user=customer_user,
        vendor_user=vendor_user,
        cohort_seed=cohort_seed,
        currency="NGN",
        subtotal=Decimal("50000.00"),
    )
    customer_token = customer_user["token"]

    with patch(
        "app.services.checkout.estimates._dhl_checkout_options",
        new=AsyncMock(return_value=_mock_dhl_offers()),
    ), patch(
        "app.services.checkout.estimates._shipbubble_checkout_options",
        new=AsyncMock(return_value=_mock_shipbubble_rates()),
    ):
        est_res = await client.post(
            f"/api/v1/orders/{order.id}/checkout-estimates",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"three-way-est-{order.id.hex[:12]}",
            },
        )
        assert est_res.status_code == 201, est_res.text
        options = est_res.json()["options"]

        dhl_opts = [o for o in options if o.get("provider_metadata", {}).get("provider") == "dhl"]
        sb_opts = [o for o in options if o.get("provider_metadata", {}).get("provider") == "shipbubble"]
        manual_opts = [o for o in options if o.get("provider_metadata", {}).get("provider") == "manual"]

        assert len(dhl_opts) == 1
        assert len(sb_opts) == 2
        assert len(manual_opts) >= 1  # Standard / Express manual rates
        assert any("DHL" in o["service_label"] for o in dhl_opts)
        assert any("Standard" in o["service_label"] or "Express" in o["service_label"] for o in manual_opts)

        # 3. Customer selects manual option -> order delivery_provider is 'manual'
        chosen_manual = manual_opts[0]
        sel_res = await client.post(
            f"/api/v1/orders/{order.id}/checkout-estimates/{est_res.json()['id']}/options/{chosen_manual['id']}/select",
            headers={
                "Authorization": f"Bearer {customer_token}",
                "X-Idempotency-Key": f"sel-manual-{order.id.hex[:12]}",
            },
        )
        assert sel_res.status_code == 200, sel_res.text
        await db_session.refresh(order)
        assert order.delivery_provider == "manual"
        assert Decimal(str(order.shipping_cost)) == Decimal(str(chosen_manual["amount"]))


@pytest.mark.asyncio
async def test_admin_toggle_shipping_provider_combinations_and_validation(
    client: AsyncClient,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
):
    """Admin can independently enable/disable each provider and validation rejects empty sets."""
    monkeypatch.setattr(settings, "SHIPBUBBLE_API_KEY", "sb_live_secret_key_12345")
    admin_token = admin_user["token"]

    # Toggle to manual only
    res_man = await client.put(
        "/api/v1/settings/shipping-provider",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"enabled_providers": ["manual"]},
    )
    assert res_man.status_code == 200, res_man.text
    assert res_man.json()["provider"] == "manual"
    assert res_man.json()["enabled_providers"] == ["manual"]

    # Toggle to manual + shipbubble
    res_man_sb = await client.put(
        "/api/v1/settings/shipping-provider",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"enabled_providers": ["manual", "shipbubble"]},
    )
    assert res_man_sb.status_code == 200, res_man_sb.text
    assert res_man_sb.json()["provider"] == "combined"
    assert res_man_sb.json()["enabled_providers"] == ["manual", "shipbubble"]

    # Reject empty list
    res_empty = await client.put(
        "/api/v1/settings/shipping-provider",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"enabled_providers": []},
    )
    assert res_empty.status_code in (400, 422), res_empty.text

