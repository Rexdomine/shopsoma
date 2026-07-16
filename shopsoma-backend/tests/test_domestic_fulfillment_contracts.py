from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.services.fulfillment.contracts import (
    CustodyActorType,
    CustodyEvent,
    DomesticAddress,
    FulfillmentCohortRef,
    HubReceiptResult,
    HubRef,
    InboundTransferRef,
    OutboundShipmentIntent,
    PackageItemRef,
    PackageRef,
    ParcelMeasurement,
    QcDecision,
    ReceiptRef,
    SealRef,
)


HUB_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_HUB_ID = UUID("00000000-0000-0000-0000-000000000010")
TRANSFER_ID = UUID("00000000-0000-0000-0000-000000000002")
VENDOR_ID = UUID("00000000-0000-0000-0000-000000000003")
COHORT_ID = UUID("00000000-0000-0000-0000-000000000004")
SECOND_COHORT_ID = UUID("00000000-0000-0000-0000-000000000014")
ORDER_ID = UUID("00000000-0000-0000-0000-000000000005")
ORDER_ITEM_ID = UUID("00000000-0000-0000-0000-000000000006")
SECOND_ORDER_ITEM_ID = UUID("00000000-0000-0000-0000-000000000016")
PACKAGE_ID = UUID("00000000-0000-0000-0000-000000000007")
EVENT_ID = UUID("00000000-0000-0000-0000-000000000008")
AGGREGATE_ID = UUID("00000000-0000-0000-0000-000000000009")
PREVIOUS_EVENT_ID = UUID("00000000-0000-0000-0000-000000000011")
NOW = datetime(2026, 7, 16, 12, tzinfo=UTC)


def make_address() -> DomesticAddress:
    return DomesticAddress(
        contact_name="Ada Okafor",
        phone="+234****0000",
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


def make_package(hub: HubRef | None = None) -> PackageRef:
    hub = hub or HubRef(HUB_ID)
    return PackageRef(
        package_id=PACKAGE_ID,
        package_version=3,
        composition=(
            PackageItemRef(
                cohort=FulfillmentCohortRef(COHORT_ID, hub),
                order_item_id=ORDER_ITEM_ID,
                quantity=1,
            ),
            PackageItemRef(
                cohort=FulfillmentCohortRef(SECOND_COHORT_ID, hub),
                order_item_id=SECOND_ORDER_ITEM_ID,
                quantity=2,
            ),
        ),
        measurement=make_parcel(),
        seal=SealRef("opaque/seal:42"),
    )


def make_custody(**overrides: object) -> CustodyEvent:
    hub = HubRef(HUB_ID)
    values = {
        "event_id": EVENT_ID,
        "aggregate_id": AGGREGATE_ID,
        "aggregate_version": 2,
        "cohort": FulfillmentCohortRef(COHORT_ID, hub),
        "hub": hub,
        "event": "sealed",
        "actor_type": CustodyActorType.HUB_OPERATOR,
        "actor_id": "operator-17",
        "source_system": "shopsoma-fulfillment",
        "occurred_at": NOW,
        "recorded_at": NOW + timedelta(seconds=1),
        "location": "Lagos Hub / packing station 4",
        "counterparty": "DHL handoff agent",
        "idempotency_key": "seal:cohort-4:v2",
        "previous_event_id": PREVIOUS_EVENT_ID,
        "evidence_ref": "object://custody/event-8.jpg",
        "evidence_hash": "a" * 64,
        "seal": SealRef("opaque/seal:42"),
    }
    values.update(overrides)
    return CustodyEvent(**values)


def test_contracts_model_the_hub_fulfillment_topology() -> None:
    hub = HubRef(id=HUB_ID)
    transfer = InboundTransferRef(
        id=TRANSFER_ID,
        vendor_id=VENDOR_ID,
        destination_hub=hub,
    )
    cohort = FulfillmentCohortRef(id=COHORT_ID, hub=hub)
    receipt = ReceiptRef(
        transfer=transfer,
        received_at=NOW,
        received_item_count=2,
    )
    custody = make_custody(cohort=cohort, hub=hub)
    package = make_package(hub)
    outbound = OutboundShipmentIntent(
        order_id=ORDER_ID,
        origin_hub=hub,
        destination=make_address(),
        package=package,
    )

    assert receipt.transfer.destination_hub == hub
    assert isinstance(receipt, HubReceiptResult)
    assert QcDecision.APPROVED.value == "approved"
    assert custody.seal == outbound.package.seal
    assert {item.cohort.id for item in outbound.package.composition} == {
        COHORT_ID,
        SECOND_COHORT_ID,
    }
    assert outbound.origin_hub == cohort.hub
    assert outbound.destination.country_code == "NG"


@pytest.mark.parametrize(
    "contract,attribute,new_value",
    [
        (HubRef(HUB_ID), "id", TRANSFER_ID),
        (make_address(), "city", "Abuja"),
        (SealRef("seal-1"), "value", "seal-2"),
        (make_parcel(), "weight_kg", Decimal("2")),
        (make_custody(), "aggregate_version", 3),
        (make_package(), "package_version", 4),
        (make_package().composition[0], "quantity", 4),
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
            phone="+234****0000",
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
    inbound_contracts = (HubRef, InboundTransferRef, ReceiptRef)

    for contract_type in inbound_contracts:
        names = {field.name.lower() for field in fields(contract_type)}
        assert not names & {"carrier", "carrier_id", "provider", "provider_id"}


def test_outbound_intent_binds_final_package_without_vendor_or_single_cohort() -> None:
    names = {field.name.lower() for field in fields(OutboundShipmentIntent)}

    assert names == {"order_id", "origin_hub", "destination", "package"}
    assert "cohort" not in names
    assert not any("vendor" in name and "address" in name for name in names)


def test_receipt_and_custody_timestamps_require_timezone_aware_utc() -> None:
    transfer = InboundTransferRef(TRANSFER_ID, VENDOR_ID, HubRef(HUB_ID))
    non_utc = datetime(2026, 7, 16, 13, tzinfo=timezone(timedelta(hours=1)))

    for invalid in (datetime(2026, 7, 16, 12), non_utc):
        with pytest.raises(ValueError, match="received_at must be timezone-aware UTC"):
            ReceiptRef(transfer, invalid, 1)
        with pytest.raises(ValueError, match="occurred_at must be timezone-aware UTC"):
            make_custody(occurred_at=invalid)
        with pytest.raises(ValueError, match="recorded_at must be timezone-aware UTC"):
            make_custody(recorded_at=invalid)


def test_custody_event_is_complete_append_only_audit_record() -> None:
    event = make_custody(counterparty="  DHL handoff agent  ", evidence_hash="A" * 64)

    assert event.counterparty == "DHL handoff agent"
    assert event.evidence_hash == "a" * 64
    assert event.recorded_at > event.occurred_at
    assert isinstance(event.actor_type, CustodyActorType)
    assert event.previous_event_id == PREVIOUS_EVENT_ID


@pytest.mark.parametrize(
    "field_name", ["actor_id", "source_system", "location", "idempotency_key"]
)
def test_custody_event_requires_nonempty_audit_strings(field_name: str) -> None:
    with pytest.raises(ValueError, match=f"{field_name} must not be empty"):
        make_custody(**{field_name: "  "})


@pytest.mark.parametrize("value", ["bad\nparty", "bad\x00party", "   "])
def test_custody_event_sanitizes_optional_counterparty(value: str) -> None:
    with pytest.raises(ValueError, match="counterparty"):
        make_custody(counterparty=value)


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [
        ("event_id", "event-8"),
        ("aggregate_id", "aggregate-9"),
        ("previous_event_id", "event-7"),
        ("actor_type", "hub_operator"),
    ],
)
def test_custody_event_rejects_wrong_audit_field_types(
    field_name: str, invalid: object
) -> None:
    with pytest.raises(TypeError, match=field_name):
        make_custody(**{field_name: invalid})


@pytest.mark.parametrize("version", [0, -1, True, 1.5])
def test_custody_aggregate_version_must_be_a_positive_integer(version: object) -> None:
    with pytest.raises((TypeError, ValueError), match="aggregate_version"):
        make_custody(aggregate_version=version)


def test_custody_recording_cannot_predate_occurrence() -> None:
    with pytest.raises(ValueError, match="recorded_at must not be before occurred_at"):
        make_custody(recorded_at=NOW - timedelta(microseconds=1))


def test_custody_previous_event_cannot_reference_self() -> None:
    with pytest.raises(ValueError, match="previous_event_id must not equal event_id"):
        make_custody(previous_event_id=EVENT_ID)


@pytest.mark.parametrize(
    ("evidence_ref", "evidence_hash"),
    [
        (None, "a" * 64),
        ("object://evidence", None),
        ("object://evidence", "not-sha256"),
    ],
)
def test_custody_evidence_reference_and_sha256_hash_are_paired(
    evidence_ref: str | None, evidence_hash: str | None
) -> None:
    with pytest.raises(ValueError, match="evidence"):
        make_custody(evidence_ref=evidence_ref, evidence_hash=evidence_hash)


def test_custody_event_rejects_non_hub_runtime_value() -> None:
    with pytest.raises(TypeError, match="hub must be a HubRef"):
        make_custody(hub=object())


def test_package_binds_multiple_cohorts_version_measurement_and_active_seal() -> None:
    package = make_package()

    assert package.package_id == PACKAGE_ID
    assert package.package_version == 3
    assert len(package.composition) == 2
    assert package.measurement == make_parcel()
    assert package.seal == SealRef("opaque/seal:42")
    assert isinstance(package.composition, tuple)


@pytest.mark.parametrize("value", [(), []])
def test_package_requires_nonempty_tuple_composition(value: object) -> None:
    values = {
        "package_id": PACKAGE_ID,
        "package_version": 1,
        "composition": value,
        "measurement": make_parcel(),
        "seal": SealRef("seal-1"),
    }
    with pytest.raises((TypeError, ValueError), match="composition"):
        PackageRef(**values)


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [
        ("package_id", "package-7"),
        ("package_version", True),
        ("package_version", 0),
        ("composition", (object(),)),
        ("measurement", object()),
        ("seal", "seal-1"),
    ],
)
def test_package_rejects_invalid_binding_fields(
    field_name: str, invalid: object
) -> None:
    package = make_package()
    values = {field.name: getattr(package, field.name) for field in fields(PackageRef)}
    values[field_name] = invalid

    with pytest.raises((TypeError, ValueError), match=field_name):
        PackageRef(**values)


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5])
def test_package_item_quantity_must_be_a_positive_integer(quantity: object) -> None:
    with pytest.raises((TypeError, ValueError), match="quantity"):
        PackageItemRef(
            FulfillmentCohortRef(COHORT_ID, HubRef(HUB_ID)),
            ORDER_ITEM_ID,
            quantity,
        )


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [("cohort", object()), ("order_item_id", "item-6")],
)
def test_package_item_rejects_wrong_runtime_types(
    field_name: str, invalid: object
) -> None:
    values = {
        "cohort": FulfillmentCohortRef(COHORT_ID, HubRef(HUB_ID)),
        "order_item_id": ORDER_ITEM_ID,
        "quantity": 1,
    }
    values[field_name] = invalid
    with pytest.raises(TypeError, match=field_name):
        PackageItemRef(**values)


def test_outbound_intent_rejects_package_cohort_from_wrong_hub() -> None:
    origin = HubRef(HUB_ID)
    wrong_package = make_package(HubRef(OTHER_HUB_ID))

    with pytest.raises(
        ValueError, match="every package cohort hub must match origin_hub"
    ):
        OutboundShipmentIntent(ORDER_ID, origin, make_address(), wrong_package)


@pytest.mark.parametrize(
    ("field_name", "invalid"),
    [
        ("order_id", "order-5"),
        ("origin_hub", object()),
        ("destination", object()),
        ("package", object()),
    ],
)
def test_outbound_intent_rejects_wrong_runtime_values(
    field_name: str, invalid: object
) -> None:
    values = {
        "order_id": ORDER_ID,
        "origin_hub": HubRef(HUB_ID),
        "destination": make_address(),
        "package": make_package(),
    }
    values[field_name] = invalid
    with pytest.raises(TypeError, match=field_name):
        OutboundShipmentIntent(**values)
