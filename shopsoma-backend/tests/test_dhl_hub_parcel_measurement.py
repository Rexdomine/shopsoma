"""Hub-measured parcels: DHL piece limits, box presets, repack lifecycle and booking gate."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import PaymentStatus
from app.models.package_custody import (
    HubPackageSeal,
    HubPackageVersion,
    OutboundShipmentIntentInvalidation,
)
from app.services.dhl.operations import project_operations
from app.services.dhl.parcel_limits import (
    ParcelValidationError,
    billable_weight_kg,
    normalize_dhl_parcel,
    volumetric_weight_kg,
)
from app.services.dhl.shipments import (
    HUB_MEASUREMENT_REQUIRED_DETAIL,
    AdapterBookingResult,
    ShipmentPhase4Error,
    _ensure_hub_measured_parcel,
)
from app.services.shipping.box_presets import (
    DEFAULT_BOX_PRESETS,
    ShippingBoxPreset,
    ShippingBoxPresetList,
)
from tests.test_dhl_e2e_sandbox import (
    _create_checkout_order_for_dhl,
    _enable_dhl_checkout_settings,
)


# --------------------------------------------------------------------------- pure rules


def test_dhl_parcel_is_normalized_to_whole_cm_longest_side_first() -> None:
    parcel = normalize_dhl_parcel("1.2374", "14.1", "39.2", "29.6")
    assert parcel.weight_kg == Decimal("1.237")
    assert (parcel.length_cm, parcel.width_cm, parcel.height_cm) == (
        Decimal("40"),
        Decimal("30"),
        Decimal("15"),
    )


def test_volumetric_and_billable_weight_follow_dhl_rules() -> None:
    # 40 x 30 x 15 / 5000 = 3.6 kg volumetric beats 1.2 kg actual -> billed 4.0 kg
    assert volumetric_weight_kg(40, 30, 15) == Decimal("3.60")
    assert billable_weight_kg(Decimal("1.2"), 40, 30, 15) == Decimal("4.0")
    # Heavy compact parcel bills on actual weight, rounded up to 0.5 kg
    assert billable_weight_kg(Decimal("2.1"), 20, 15, 5) == Decimal("2.5")
    # Never bills below the 0.5 kg minimum step
    assert billable_weight_kg(Decimal("0.05"), 10, 10, 2) == Decimal("0.5")


@pytest.mark.parametrize(
    ("values", "message"),
    [
        (("71", 40, 30, 20), "70 kg per-piece limit"),
        (("0", 40, 30, 20), "at least 0.01 kg"),
        (("2", 121, 30, 20), "Longest side 121 cm"),
        (("2", 100, 81, 20), "Second side 81 cm"),
        (("2", 40, 0, 20), "Width must be greater than 0"),
        (("abc", 40, 30, 20), "Weight must be a number"),
    ],
)
def test_dhl_parcel_rejects_values_dhl_will_not_accept(values, message) -> None:
    with pytest.raises(ParcelValidationError) as exc:
        normalize_dhl_parcel(*values)
    assert message in str(exc.value)


def test_box_presets_validate_codes_uniqueness_and_dhl_limits() -> None:
    assert len(DEFAULT_BOX_PRESETS) >= 3
    preset = ShippingBoxPreset(code=" ss-m ", name="  Medium   box ", length_cm="29.2", width_cm="40", height_cm="15")
    assert preset.code == "SS-M" and preset.name == "Medium box"
    assert (preset.length_cm, preset.width_cm, preset.height_cm) == (Decimal("40"), Decimal("30"), Decimal("15"))
    with pytest.raises(ValidationError, match="exceeds the DHL Express"):
        ShippingBoxPreset(code="HUGE", name="Huge", length_cm=130, width_cm=40, height_cm=40)
    with pytest.raises(ValidationError, match="unique"):
        ShippingBoxPresetList(presets=[preset, preset])


def test_booking_gate_rejects_estimated_parcels_only_when_enabled() -> None:
    estimated = SimpleNamespace(measurement_source="estimated")
    measured = SimpleNamespace(measurement_source="hub_measured")
    on = SimpleNamespace(DHL_REQUIRE_HUB_MEASURED_PARCEL=True)
    with pytest.raises(ShipmentPhase4Error, match=HUB_MEASUREMENT_REQUIRED_DETAIL):
        _ensure_hub_measured_parcel(on, estimated)
    _ensure_hub_measured_parcel(on, measured)
    _ensure_hub_measured_parcel(SimpleNamespace(DHL_REQUIRE_HUB_MEASURED_PARCEL=False), estimated)


def test_operations_projection_exposes_parcel_and_measurement_blocker() -> None:
    pid, seal_id, intent_id, hub_id = (str(uuid.uuid4()) for _ in range(4))
    snapshot = {
        "read_at": datetime.now(UTC),
        "order_status": "order_received",
        "packages": [{"id": pid, "current_version": 2, "hub_id": hub_id, "state": "ready", "ready_at": datetime.now(UTC).isoformat()}],
        "seals": [{"id": seal_id, "package_id": pid, "package_version": 2}],
        "intents": [{"id": intent_id, "package_id": pid, "package_version": 2, "seal_id": seal_id, "origin_hub_id": hub_id, "invalidated": False}],
        "guards": [],
        "bookings": [],
        "handoffs": [],
        "quotes": [{"intent_id": intent_id}],
        "versions": [
            {"package_id": pid, "version": 1, "weight_kg": 1.8, "length_cm": 35, "width_cm": 28, "height_cm": 12, "measurement_source": "estimated", "box_preset_code": None},
            {"package_id": pid, "version": 2, "weight_kg": 2.1, "length_cm": 40, "width_cm": 30, "height_cm": 15, "measurement_source": "hub_measured", "box_preset_code": "SS-M"},
        ],
        "items": [{"package_id": pid, "package_version": 2}],
    }
    package = project_operations(snapshot, require_hub_measurement=True)["packages"][0]
    assert package["selection_eligible"] is True
    parcel = package["parcel"]
    assert parcel["measurement_source"] == "hub_measured"
    assert parcel["box_preset_code"] == "SS-M"
    assert parcel["billable_weight_kg"] == Decimal("4.0")
    assert parcel["estimated_contents_weight_kg"] == Decimal("1.8")

    snapshot["versions"][1]["measurement_source"] = "estimated"
    package = project_operations(snapshot, require_hub_measurement=True)["packages"][0]
    assert package["selection_blockers"] == ["parcel_not_measured"]
    assert project_operations(snapshot)["packages"][0]["selection_eligible"] is True


# --------------------------------------------------------------------------- lifecycle


def _mock_adapter(tracking: str) -> AsyncMock:
    adapter = AsyncMock()
    adapter.calls = []

    def _prepare(intent, order, hub, package_version, quoted, contents=None):  # noqa: ANN001
        adapter.calls.append(package_version)
        return {"productCode": "N"}

    adapter.prepare_booking_payload = _prepare
    adapter.book = AsyncMock(
        return_value=AdapterBookingResult(
            provider_reference=f"DHL-REF-{tracking}",
            tracking_number=tracking,
            label_media_type="application/pdf",
            label_content=b"%PDF-1.4\n%Mock\n%%EOF\n",
            service_code="N",
            booked_at=datetime.now(UTC),
        )
    )
    return adapter


async def _paid_dhl_order(db_session, customer_user, vendor_user, admin_user, monkeypatch):
    cohort_seed = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")
    await _enable_dhl_checkout_settings(
        db_session, monkeypatch, cohort_seed=cohort_seed, actor_id=admin_user["user"].id
    )
    monkeypatch.setattr(
        "app.core.config.settings.DHL_REQUIRE_HUB_MEASURED_PARCEL", True, raising=False
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
    return order


@pytest.mark.asyncio
async def test_hub_measurement_repacks_estimated_parcel_and_unblocks_booking(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = {"Authorization": f"Bearer {admin_user['token']}"}
    order = await _paid_dhl_order(db_session, customer_user, vendor_user, admin_user, monkeypatch)

    # 1) Auto/admin prepare creates an *estimated* v1 that cannot be booked.
    prep = await client.post(f"/api/v1/admin/orders/{order.id}/dhl/prepare-package", headers=headers)
    assert prep.status_code == 200, prep.text
    v1 = prep.json()["dhl_operations"]["packages"][0]
    assert v1["parcel"]["measurement_source"] == "estimated"
    assert "parcel_not_measured" in v1["selection_blockers"]
    assert v1["selection_eligible"] is False

    adapter = _mock_adapter(f"77{uuid.uuid4().int % 10**8:08d}")
    with patch("app.services.dhl.shipments.create_shipment_adapter", return_value=adapter):
        blocked = await client.post(
            f"/api/v1/admin/orders/{order.id}/dhl/bookings",
            json={k: v1[k] for k in ("intent_id", "package_id", "package_version", "seal_id")}
            | {"idempotency_key": f"book-{uuid.uuid4().hex}"},
            headers=headers,
        )
    assert blocked.status_code == 400
    assert blocked.json()["detail"] == HUB_MEASUREMENT_REQUIRED_DETAIL
    adapter.book.assert_not_called()

    # 2) DHL-unacceptable measurements are rejected with reasons.
    too_heavy = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/parcel-measurement",
        json={"box_preset_code": "SS-M", "weight_kg": "75", "length_cm": 40, "width_cm": 30, "height_cm": 15},
        headers=headers,
    )
    assert too_heavy.status_code == 422
    assert any("70 kg" in e for e in too_heavy.json()["detail"]["errors"])
    unknown_box = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/parcel-measurement",
        json={"box_preset_code": "NOPE", "weight_kg": "1", "length_cm": 40, "width_cm": 30, "height_cm": 15},
        headers=headers,
    )
    assert unknown_box.status_code == 422

    # 3) Real scale reading + box: repack to an audited v2.
    measure_body = {"box_preset_code": "ss-m", "weight_kg": "2.137", "length_cm": "29.4", "width_cm": "39.2", "height_cm": "14.1"}
    measured = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/parcel-measurement", json=measure_body, headers=headers
    )
    assert measured.status_code == 200, measured.text
    v2 = measured.json()["dhl_operations"]["packages"][0]
    assert v2["package_id"] == v1["package_id"]
    assert v2["package_version"] == 2
    assert v2["intent_id"] != v1["intent_id"] and v2["seal_id"] != v1["seal_id"]
    assert v2["selection_eligible"] is True, v2["selection_blockers"]
    parcel = v2["parcel"]
    assert parcel["measurement_source"] == "hub_measured"
    assert parcel["box_preset_code"] == "SS-M"
    assert (Decimal(parcel["length_cm"]), Decimal(parcel["width_cm"]), Decimal(parcel["height_cm"])) == (40, 30, 15)
    assert Decimal(parcel["weight_kg"]) == Decimal("2.137")
    assert Decimal(parcel["billable_weight_kg"]) == Decimal("4.0")
    assert Decimal(parcel["estimated_contents_weight_kg"]) == Decimal(v1["parcel"]["weight_kg"])

    package_id = uuid.UUID(v1["package_id"])
    old_seal = await db_session.get(HubPackageSeal, uuid.UUID(v1["seal_id"]))
    await db_session.refresh(old_seal)
    assert old_seal.retired_at is not None and "Hub measured" in old_seal.retirement_reason
    invalidation = await db_session.scalar(
        select(OutboundShipmentIntentInvalidation).where(
            OutboundShipmentIntentInvalidation.intent_id == uuid.UUID(v1["intent_id"])
        )
    )
    assert invalidation is not None
    v2_row = await db_session.get(HubPackageVersion, (package_id, 2))
    assert v2_row.previous_version == 1 and v2_row.reason == "Hub measured parcel (SS-M)"

    # 4) Same reading again is an idempotent replay (no v3).
    replay = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/parcel-measurement", json=measure_body, headers=headers
    )
    assert replay.status_code == 200
    assert replay.json()["dhl_operations"]["packages"][0]["package_version"] == 2

    # 5) Booking now uses exactly the measured parcel.
    with patch("app.services.dhl.shipments.create_shipment_adapter", return_value=adapter):
        booked = await client.post(
            f"/api/v1/admin/orders/{order.id}/dhl/bookings",
            json={k: v2[k] for k in ("intent_id", "package_id", "package_version", "seal_id")}
            | {"idempotency_key": f"book-{uuid.uuid4().hex}"},
            headers=headers,
        )
    assert booked.status_code == 200, booked.text
    assert booked.json()["result_kind"] == "booked"
    sent = adapter.calls[-1]
    assert (sent.version, sent.measurement_source) == (2, "hub_measured")
    assert (Decimal(sent.weight_kg), Decimal(sent.length_cm)) == (Decimal("2.137"), Decimal("40"))

    # 6) A booked parcel cannot be silently re-measured.
    late = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/parcel-measurement",
        json=measure_body | {"weight_kg": "3.5"},
        headers=headers,
    )
    assert late.status_code == 409
    assert "already exists" in late.json()["detail"]


@pytest.mark.asyncio
async def test_hub_measurement_before_preparation_creates_measured_first_version(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = {"Authorization": f"Bearer {admin_user['token']}"}
    order = await _paid_dhl_order(db_session, customer_user, vendor_user, admin_user, monkeypatch)

    res = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/parcel-measurement",
        json={"weight_kg": "0.8", "length_cm": 35, "width_cm": 25, "height_cm": 4},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    package = res.json()["dhl_operations"]["packages"][0]
    assert package["package_version"] == 1
    assert package["parcel"]["measurement_source"] == "hub_measured"
    assert package["parcel"]["box_preset_code"] is None
    assert package["selection_eligible"] is True


@pytest.mark.asyncio
async def test_hub_measurement_requires_admin_and_paid_order(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user: dict,
    vendor_user: dict,
    admin_user: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = await _paid_dhl_order(db_session, customer_user, vendor_user, admin_user, monkeypatch)
    body = {"weight_kg": "1", "length_cm": 30, "width_cm": 20, "height_cm": 10}
    as_customer = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/parcel-measurement",
        json=body,
        headers={"Authorization": f"Bearer {customer_user['token']}"},
    )
    assert as_customer.status_code in (401, 403)

    order.payment_status = PaymentStatus.PENDING
    await db_session.commit()
    unpaid = await client.post(
        f"/api/v1/admin/orders/{order.id}/dhl/parcel-measurement",
        json=body,
        headers={"Authorization": f"Bearer {admin_user['token']}"},
    )
    assert unpaid.status_code == 409


@pytest.mark.asyncio
async def test_admin_can_read_and_replace_shipping_box_presets(
    client: AsyncClient, admin_user: dict, customer_user: dict
) -> None:
    headers = {"Authorization": f"Bearer {admin_user['token']}"}
    default = await client.get("/api/v1/settings/admin/shipping-boxes", headers=headers)
    assert default.status_code == 200
    assert default.json()["is_default"] is True

    saved = await client.put(
        "/api/v1/settings/admin/shipping-boxes",
        json={"presets": [{"code": "shopsoma-a", "name": "ShopSoma A", "length_cm": 32, "width_cm": 24, "height_cm": 9.2, "tare_weight_kg": 0.25}]},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["is_default"] is False
    assert body["presets"][0]["code"] == "SHOPSOMA-A"
    assert Decimal(str(body["presets"][0]["height_cm"])) == Decimal("10")

    oversize = await client.put(
        "/api/v1/settings/admin/shipping-boxes",
        json={"presets": [{"code": "BIG", "name": "Big", "length_cm": 150, "width_cm": 50, "height_cm": 50}]},
        headers=headers,
    )
    assert oversize.status_code == 422
    forbidden = await client.get(
        "/api/v1/settings/admin/shipping-boxes",
        headers={"Authorization": f"Bearer {customer_user['token']}"},
    )
    assert forbidden.status_code in (401, 403)
