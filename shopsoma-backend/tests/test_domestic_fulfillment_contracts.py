from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.services.fulfillment.contracts import (
    CustodyEvent,
    DomesticAddress,
    FulfillmentCohortRef,
    HubReceiptResult,
    HubRef,
    InboundTransferRef,
    OutboundShipmentIntent,
    ParcelMeasurement,
    QcDecision,
    SealRef,
)


HUB_ID = UUID("00000000-0000-0000-0000-000000000001")
TRANSFER_ID = UUID("00000000-0000-0000-0000-000000000002")
VENDOR_ID = UUID("00000000-0000-0000-0000-000000000003")
COHORT_ID = UUID("00000000-0000-0000-0000-000000000004")
ORDER_ID = UUID("00000000-0000-0000-0000-000000000005")
NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def make_address() -> DomesticAddress:
    return DomesticAddress(
        contact_name="Ada Okafor",
        phone="+2348000000000",
        line1="1 Marina Road",
        city="Lagos",
        state="Lagos",
        postal_code="100001",
    )


def make_parcel() -> ParcelMeasurement:
    return ParcelMeasurement(
        weight_kg=Decimal("1.25"),
        length_cm=Decimal("30"),
        width_cm=Decimal("20"),
        height_cm=Decimal("10"),
    )


def test_contracts_model_the_hub_fulfillment_topology() -> None:
    hub = HubRef(id=HUB_ID)
    transfer = InboundTransferRef(
        id=TRANSFER_ID,
        vendor_id=VENDOR_ID,
        destination_hub=hub,
    )
    cohort = FulfillmentCohortRef(id=COHORT_ID, hub=hub)
    receipt = HubReceiptResult(
        transfer=transfer,
        received_at=NOW,
        received_item_count=2,
    )
    custody = CustodyEvent(
        cohort=cohort,
        hub=hub,
        event="sealed",
        occurred_at=NOW,
        seal=SealRef("opaque/seal:42"),
    )
    outbound = OutboundShipmentIntent(
        order_id=ORDER_ID,
        cohort=cohort,
        origin_hub=hub,
        destination=make_address(),
        parcel=make_parcel(),
        seal=SealRef("opaque/seal:42"),
    )

    assert receipt.transfer.destination_hub == hub
    assert QcDecision.APPROVED.value == "approved"
    assert custody.seal == outbound.seal
    assert outbound.origin_hub == cohort.hub
    assert outbound.destination.country_code == "NG"


@pytest.mark.parametrize(
    "contract,attribute,new_value",
    [
        (HubRef(HUB_ID), "id", TRANSFER_ID),
        (make_address(), "city", "Abuja"),
        (SealRef("seal-1"), "value", "seal-2"),
        (make_parcel(), "weight_kg", Decimal("2")),
    ],
)
def test_contract_values_are_immutable(contract, attribute, new_value) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(contract, attribute, new_value)


def test_domestic_address_country_is_fixed_to_nigeria() -> None:
    assert make_address().country_code == "NG"

    with pytest.raises(ValueError, match="country_code must be NG"):
        DomesticAddress(
            contact_name="Ada Okafor",
            phone="+2348000000000",
            line1="1 Marina Road",
            city="Lagos",
            state="Lagos",
            country_code="US",
        )


@pytest.mark.parametrize("metric", ["weight_kg", "length_cm", "width_cm", "height_cm"])
@pytest.mark.parametrize(
    "invalid_value",
    [
        Decimal("0"),
        Decimal("-0.01"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_parcel_metrics_must_be_positive(metric, invalid_value) -> None:
    values = {
        "weight_kg": Decimal("1"),
        "length_cm": Decimal("1"),
        "width_cm": Decimal("1"),
        "height_cm": Decimal("1"),
    }
    values[metric] = invalid_value

    with pytest.raises(ValueError, match=f"{metric} must be positive"):
        ParcelMeasurement(**values)


def test_hub_refs_require_server_owned_uuid_identifiers() -> None:
    with pytest.raises(TypeError, match="HubRef id must be a UUID"):
        HubRef(id="client-supplied-hub")  # type: ignore[arg-type]


def test_seal_ids_are_opaque_but_non_empty() -> None:
    assert SealRef("not-a-provider-format/123").value == "not-a-provider-format/123"

    for value in ("", "   "):
        with pytest.raises(ValueError, match="seal value must not be empty"):
            SealRef(value)


def test_inbound_contracts_have_no_carrier_or_provider_fields() -> None:
    inbound_contracts = (HubRef, InboundTransferRef, HubReceiptResult)

    for contract_type in inbound_contracts:
        names = {field.name.lower() for field in fields(contract_type)}
        assert not names & {"carrier", "carrier_id", "provider", "provider_id"}


def test_outbound_intent_starts_at_a_hub_and_has_no_vendor_address() -> None:
    names = {field.name.lower() for field in fields(OutboundShipmentIntent)}

    assert "origin_hub" in names
    assert not any("vendor" in name and "address" in name for name in names)


def test_custody_event_rejects_non_hub_runtime_value() -> None:
    cohort = FulfillmentCohortRef(id=COHORT_ID, hub=HubRef(HUB_ID))

    with pytest.raises(TypeError, match="hub must be a HubRef"):
        CustodyEvent(
            cohort=cohort,
            hub=object(),  # type: ignore[arg-type]
            event="received",
            occurred_at=NOW,
        )


def test_outbound_intent_rejects_non_hub_runtime_value() -> None:
    cohort = FulfillmentCohortRef(id=COHORT_ID, hub=HubRef(HUB_ID))

    with pytest.raises(TypeError, match="origin_hub must be a HubRef"):
        OutboundShipmentIntent(
            order_id=ORDER_ID,
            cohort=cohort,
            origin_hub=object(),  # type: ignore[arg-type]
            destination=make_address(),
            parcel=make_parcel(),
            seal=SealRef("seal-1"),
        )
