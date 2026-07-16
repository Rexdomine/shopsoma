from dataclasses import FrozenInstanceError, fields
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.services.fulfillment.contracts import (
    DomesticAddress,
    HubRef,
    ParcelMeasurement,
)
from app.services.shipping.contracts import DomesticRate, DomesticRateRequest


def hub() -> HubRef:
    return HubRef(uuid4())


def destination() -> DomesticAddress:
    return DomesticAddress(
        contact_name="Ada Customer",
        phone="+2348012345678",
        line1="1 Marina Road",
        city="Lagos",
        state="Lagos",
    )


def parcel(**overrides: object) -> ParcelMeasurement:
    values = {
        "weight_kg": Decimal("1.25"),
        "length_cm": Decimal("30"),
        "width_cm": Decimal("20"),
        "height_cm": Decimal("10"),
    }
    values.update(overrides)
    return ParcelMeasurement(**values)


def request(**overrides: object) -> DomesticRateRequest:
    values = {
        "origin": hub(),
        "destination": destination(),
        "parcels": (parcel(),),
        "planned_ship_date": date(2026, 7, 20),
    }
    values.update(overrides)
    return DomesticRateRequest(**values)


def rate(**overrides: object) -> DomesticRate:
    values = {
        "rate_id": "rate:opaque-123",
        "service_id": "service.standard_1",
        "total_amount": Decimal("12500.50"),
        "currency": "NGN",
        "carrier_transit_days": 2,
        "estimated_carrier_delivery_date": date(2026, 7, 22),
    }
    values.update(overrides)
    return DomesticRate(**values)


def test_request_fields_expose_only_hub_origin_and_no_vendor_origin_address() -> None:
    field_names = {field.name for field in fields(DomesticRateRequest)}

    assert field_names == {
        "origin",
        "destination",
        "parcels",
        "planned_ship_date",
        "content_type",
        "movement_direction",
    }
    assert not any("vendor" in name for name in field_names)
    assert "origin_address" not in field_names


def test_request_is_immutable_and_normalizes_parcels_to_tuple() -> None:
    first, second = parcel(), parcel(weight_kg="2.5")
    value = request(parcels=[first, second])

    assert value.parcels == (first, second)
    assert isinstance(value.parcels, tuple)
    with pytest.raises(FrozenInstanceError):
        value.origin = hub()  # type: ignore[misc]


def test_request_reuses_fulfillment_contract_types() -> None:
    value = request()

    assert isinstance(value.origin, HubRef)
    assert isinstance(value.destination, DomesticAddress)
    assert all(isinstance(item, ParcelMeasurement) for item in value.parcels)


@pytest.mark.parametrize(
    ("field_name", "invalid_value", "message"),
    [
        ("origin", "vendor warehouse", "origin must be a HubRef"),
        ("origin", destination(), "origin must be a HubRef"),
        ("destination", "Abuja", "destination must be a DomesticAddress"),
        ("destination", hub(), "destination must be a DomesticAddress"),
        ("parcels", (object(),), "parcels must contain only ParcelMeasurement"),
    ],
)
def test_request_rejects_wrong_runtime_nested_types(
    field_name: str, invalid_value: object, message: str
) -> None:
    with pytest.raises(TypeError, match=message):
        request(**{field_name: invalid_value})


def test_destination_contract_fails_closed_for_international_shipping() -> None:
    with pytest.raises(ValueError, match="country_code must be NG"):
        DomesticAddress(
            contact_name="Ada Customer",
            phone="+233201234567",
            line1="1 High Street",
            city="Accra",
            state="Greater Accra",
            country_code="GH",
        )


@pytest.mark.parametrize("parcels", [(), [], iter(())])
def test_request_requires_at_least_one_parcel(parcels: object) -> None:
    with pytest.raises(ValueError, match="at least one parcel"):
        request(parcels=parcels)


@pytest.mark.parametrize("content_type", ["document", "documents", "gift", ""])
def test_request_fails_closed_for_non_merchandise_content(content_type: str) -> None:
    with pytest.raises(ValueError, match="content_type must be merchandise"):
        request(content_type=content_type)


@pytest.mark.parametrize("direction", ["inbound", "import", "vendor_to_hub", ""])
def test_request_fails_closed_for_non_outbound_movement(direction: str) -> None:
    with pytest.raises(ValueError, match="movement_direction must be outbound"):
        request(movement_direction=direction)


def test_request_defaults_to_domestic_merchandise_outbound_semantics() -> None:
    value = request()

    assert value.content_type == "merchandise"
    assert value.movement_direction == "outbound"
    assert value.destination.country_code == "NG"


@pytest.mark.parametrize(
    "planned_ship_date", [datetime(2026, 7, 20, 10, 30), "2026-07-20", None]
)
def test_request_requires_a_date_and_rejects_datetime(
    planned_ship_date: object,
) -> None:
    with pytest.raises(TypeError, match="planned_ship_date must be a date"):
        request(planned_ship_date=planned_ship_date)


def test_metric_contract_normalizes_exact_values_to_decimal() -> None:
    value = parcel(weight_kg="1.250", length_cm=30, width_cm="20", height_cm=10)

    assert value.weight_kg == Decimal("1.250")
    assert all(
        isinstance(metric, Decimal)
        for metric in (
            value.weight_kg,
            value.length_cm,
            value.width_cm,
            value.height_cm,
        )
    )


@pytest.mark.parametrize("invalid", ["0", "-1", "NaN", "Infinity", "-Infinity"])
def test_metric_contract_rejects_nonpositive_and_nonfinite_values(invalid: str) -> None:
    with pytest.raises(ValueError, match="weight_kg must be positive"):
        parcel(weight_kg=invalid)


def test_rate_is_provider_neutral_immutable_and_normalizes_exact_money() -> None:
    value = rate(total_amount="12500.50", currency="ngn")

    assert value.total_amount == Decimal("12500.50")
    assert value.currency == "NGN"
    assert "dhl" not in repr(value).lower()
    with pytest.raises(FrozenInstanceError):
        value.currency = "USD"  # type: ignore[misc]


@pytest.mark.parametrize(
    "invalid_amount", [0, -1, "0", "-0.01", "NaN", "Infinity", "-Infinity"]
)
def test_rate_rejects_nonpositive_or_nonfinite_money(invalid_amount: object) -> None:
    with pytest.raises(ValueError, match="total_amount must be positive and finite"):
        rate(total_amount=invalid_amount)


@pytest.mark.parametrize("invalid_amount", [1.5, float("nan"), float("inf")])
def test_rate_rejects_float_money_to_preserve_decimal_precision(
    invalid_amount: float,
) -> None:
    with pytest.raises(TypeError, match="total_amount must not be a float"):
        rate(total_amount=invalid_amount)


@pytest.mark.parametrize("currency", ["NG", "NGNN", "N1N", "N G", "", 123])
def test_rate_rejects_malformed_currency(currency: object) -> None:
    with pytest.raises((TypeError, ValueError), match="currency"):
        rate(currency=currency)


@pytest.mark.parametrize(
    ("field_name", "identifier"),
    [
        ("rate_id", ""),
        ("rate_id", " rate-1"),
        ("rate_id", "rate 1"),
        ("rate_id", "rate/1"),
        ("rate_id", 123),
        ("service_id", ""),
        ("service_id", " service-1"),
        ("service_id", "service 1"),
        ("service_id", "service/1"),
        ("service_id", None),
    ],
)
def test_rate_rejects_malformed_opaque_identifiers(
    field_name: str, identifier: object
) -> None:
    with pytest.raises((TypeError, ValueError), match=field_name):
        rate(**{field_name: identifier})


@pytest.mark.parametrize("carrier_transit_days", [-1, 1.5, True, "2"])
def test_rate_validates_carrier_transit_days(carrier_transit_days: object) -> None:
    with pytest.raises((TypeError, ValueError), match="carrier_transit_days"):
        rate(carrier_transit_days=carrier_transit_days)


@pytest.mark.parametrize(
    "delivery_date", [datetime(2026, 7, 22, 12), "2026-07-22", 20260722]
)
def test_rate_requires_delivery_date_not_datetime(delivery_date: object) -> None:
    with pytest.raises(
        TypeError, match="estimated_carrier_delivery_date must be a date"
    ):
        rate(estimated_carrier_delivery_date=delivery_date)


def test_rate_allows_provider_to_omit_transit_estimates() -> None:
    value = rate(
        carrier_transit_days=None,
        estimated_carrier_delivery_date=None,
    )

    assert value.carrier_transit_days is None
    assert value.estimated_carrier_delivery_date is None


def test_rate_names_carrier_estimate_without_claiming_full_order_eta() -> None:
    field_names = {field.name for field in fields(DomesticRate)}

    assert "carrier_transit_days" in field_names
    assert "estimated_carrier_delivery_date" in field_names
    assert not any(
        term in field_name
        for field_name in field_names
        for term in ("vendor_preparation", "inbound", "quality_control", "order_eta")
    )
