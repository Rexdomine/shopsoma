"""Parcel measurement fallbacks for products whose vendors left dimensions blank."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.dhl import hub_preparation
from app.services.shipping.parcel_defaults import (
    GENERIC_UNIT_MEASUREMENT,
    default_unit_measurement,
    fill_missing_measurements,
)


def test_category_defaults_match_on_word_prefixes() -> None:
    assert default_unit_measurement("dresses", None) == default_unit_measurement("Silk Midi Dress")
    assert default_unit_measurement("Leather Tote Bag")[3] == Decimal("12")
    assert default_unit_measurement("Strappy Heels")[0] == Decimal("1.000")
    # "ring" must not match inside "layering"; unknown titles use the generic unit.
    assert default_unit_measurement("Layering Cardigan") == GENERIC_UNIT_MEASUREMENT
    assert default_unit_measurement(None, "", "Mystery Item") == GENERIC_UNIT_MEASUREMENT
    # A category hint wins over a later title hint.
    assert default_unit_measurement("accessories", "Silk Dress") == default_unit_measurement("necklace")


def test_vendor_values_win_and_only_missing_fields_are_estimated() -> None:
    values, estimated = fill_missing_measurements(
        (Decimal("2.5"), Decimal("40"), Decimal("30"), Decimal("10")), ("dress",)
    )
    assert values == (Decimal("2.5"), Decimal("40"), Decimal("30"), Decimal("10"))
    assert estimated is False

    values, estimated = fill_missing_measurements(
        (Decimal("2.5"), None, Decimal("0"), None), ("dress",)
    )
    default = default_unit_measurement("dress")
    assert values == (Decimal("2.5"), default[1], default[2], default[3])
    assert estimated is True

    values, estimated = fill_missing_measurements(None, ("shoes",))
    assert values == default_unit_measurement("shoes") and estimated is True
    assert all(value > 0 for value in values)


@pytest.mark.asyncio
async def test_hub_package_is_measured_like_the_checkout_quote(monkeypatch: pytest.MonkeyPatch) -> None:
    """Booked parcel = same per-item resolver + aggregation as the DHL rating path."""

    def _item(qty: int) -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), quantity=qty)

    async def fake_resolver(_db, order):  # noqa: ANN001
        return [
            (_item(2), None, None, (Decimal("0.800"), Decimal("35"), Decimal("28"), Decimal("6"))),
            (_item(1), None, None, (Decimal("1.000"), Decimal("33"), Decimal("22"), Decimal("13"))),
        ]

    monkeypatch.setattr(
        "app.services.checkout.estimates._authoritative_parcel_measurements", fake_resolver
    )
    weight, length, width, height = await hub_preparation._compute_parcel_measurements(
        object(), order=SimpleNamespace(id=uuid.uuid4())
    )
    assert weight == Decimal("2.600")  # 2 x 0.8 + 1 x 1.0
    assert length == Decimal("35.000") and width == Decimal("28.000")
    # volume = 2*35*28*6 + 33*22*13 = 11760 + 9438 = 21198 -> /(35*28) = 21.63 cm stacked
    assert height == Decimal("21.631")
