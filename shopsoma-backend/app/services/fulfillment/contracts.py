"""Pure, provider-neutral values for domestic hub fulfillment."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from uuid import UUID

_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_uuid(value: UUID, field_name: str) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")


def _require_positive_int(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be a positive integer")
    if value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")


def _require_utc_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")


@dataclass(frozen=True, slots=True)
class HubRef:
    """Server-owned identifier for a ShopSoma fulfillment hub."""

    id: UUID

    def __post_init__(self) -> None:
        _require_uuid(self.id, "HubRef id")


@dataclass(frozen=True, slots=True)
class DomesticAddress:
    """Nigerian delivery address independent of any carrier schema."""

    contact_name: str
    phone: str
    line1: str
    city: str
    state: str
    postal_code: str | None = None
    country_code: str = "NG"

    def __post_init__(self) -> None:
        for name in ("contact_name", "phone", "line1", "city", "state"):
            _require_non_empty(getattr(self, name), name)
        if self.postal_code is not None:
            _require_non_empty(self.postal_code, "postal_code")
        if self.country_code != "NG":
            raise ValueError("country_code must be NG")


@dataclass(frozen=True, slots=True)
class InboundTransferRef:
    """Independent vendor-to-ShopSoma transfer ending at a hub."""

    id: UUID
    vendor_id: UUID
    destination_hub: HubRef

    def __post_init__(self) -> None:
        _require_uuid(self.id, "InboundTransferRef id")
        _require_uuid(self.vendor_id, "vendor_id")
        if not isinstance(self.destination_hub, HubRef):
            raise TypeError("destination_hub must be a HubRef")


@dataclass(frozen=True, slots=True)
class FulfillmentCohortRef:
    """Items grouped for QC, packing, and sealing at one ShopSoma hub."""

    id: UUID
    hub: HubRef

    def __post_init__(self) -> None:
        _require_uuid(self.id, "FulfillmentCohortRef id")
        if not isinstance(self.hub, HubRef):
            raise TypeError("hub must be a HubRef")


@dataclass(frozen=True, slots=True)
class ReceiptRef:
    """Result of ShopSoma taking custody of an inbound transfer."""

    transfer: InboundTransferRef
    received_at: datetime
    received_item_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.transfer, InboundTransferRef):
            raise TypeError("transfer must be an InboundTransferRef")
        _require_utc_datetime(self.received_at, "received_at")
        if (
            not isinstance(self.received_item_count, int)
            or isinstance(self.received_item_count, bool)
            or self.received_item_count < 0
        ):
            raise ValueError("received_item_count must be a non-negative integer")


# Compatibility for the original Lane 2A public name.
HubReceiptResult = ReceiptRef


class QcDecision(str, Enum):
    """Provider-neutral outcome of ShopSoma hub quality control."""

    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ParcelMeasurement:
    """Positive metric measurements of a packed parcel."""

    weight_kg: Decimal
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal

    def __post_init__(self) -> None:
        for name in ("weight_kg", "length_cm", "width_cm", "height_cm"):
            raw_value = getattr(self, name)
            try:
                value = Decimal(str(raw_value))
            except (InvalidOperation, ValueError):
                raise ValueError(f"{name} must be positive") from None
            if not value.is_finite() or value <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class SealRef:
    """Opaque identifier for the active seal on a packed parcel."""

    value: str

    def __post_init__(self) -> None:
        _require_non_empty(self.value, "seal value")


class CustodyActorType(str, Enum):
    """Explicit identity category responsible for a custody event."""

    HUB_OPERATOR = "hub_operator"
    SYSTEM = "system"
    VENDOR = "vendor"
    CARRIER = "carrier"


@dataclass(frozen=True, slots=True)
class CustodyEvent:
    """Immutable, append-only audit event for custody of a cohort at a hub."""

    event_id: UUID
    aggregate_id: UUID
    aggregate_version: int
    cohort: FulfillmentCohortRef
    hub: HubRef
    event: str
    actor_type: CustodyActorType
    actor_id: str
    source_system: str
    occurred_at: datetime
    recorded_at: datetime
    location: str
    idempotency_key: str
    previous_event_id: UUID | None = None
    counterparty: str | None = None
    evidence_ref: str | None = None
    evidence_hash: str | None = None
    seal: SealRef | None = None

    def __post_init__(self) -> None:
        _require_uuid(self.event_id, "event_id")
        _require_uuid(self.aggregate_id, "aggregate_id")
        _require_positive_int(self.aggregate_version, "aggregate_version")
        if not isinstance(self.cohort, FulfillmentCohortRef):
            raise TypeError("cohort must be a FulfillmentCohortRef")
        if not isinstance(self.hub, HubRef):
            raise TypeError("hub must be a HubRef")
        if self.hub != self.cohort.hub:
            raise ValueError("custody hub must match the cohort hub")
        _require_non_empty(self.event, "event")
        if not isinstance(self.actor_type, CustodyActorType):
            raise TypeError("actor_type must be a CustodyActorType")
        for name in ("actor_id", "source_system", "location", "idempotency_key"):
            _require_non_empty(getattr(self, name), name)
        _require_utc_datetime(self.occurred_at, "occurred_at")
        _require_utc_datetime(self.recorded_at, "recorded_at")
        if self.recorded_at < self.occurred_at:
            raise ValueError("recorded_at must not be before occurred_at")
        if self.previous_event_id is not None:
            _require_uuid(self.previous_event_id, "previous_event_id")
            if self.previous_event_id == self.event_id:
                raise ValueError("previous_event_id must not equal event_id")
        if self.counterparty is not None:
            _require_non_empty(self.counterparty, "counterparty")
            counterparty = self.counterparty.strip()
            if not counterparty.isprintable():
                raise ValueError("counterparty must not contain control characters")
            object.__setattr__(self, "counterparty", counterparty)
        if (self.evidence_ref is None) != (self.evidence_hash is None):
            raise ValueError("evidence_ref and evidence_hash must be provided together")
        if self.evidence_ref is not None:
            _require_non_empty(self.evidence_ref, "evidence_ref")
            if (
                not isinstance(self.evidence_hash, str)
                or _SHA256_PATTERN.fullmatch(self.evidence_hash) is None
            ):
                raise ValueError("evidence_hash must be a SHA-256 hex digest")
            object.__setattr__(self, "evidence_hash", self.evidence_hash.lower())
        if self.seal is not None and not isinstance(self.seal, SealRef):
            raise TypeError("seal must be a SealRef")


@dataclass(frozen=True, slots=True)
class PackageItemRef:
    """An order-item quantity contributed by one fulfillment cohort."""

    cohort: FulfillmentCohortRef
    order_item_id: UUID
    quantity: int

    def __post_init__(self) -> None:
        if not isinstance(self.cohort, FulfillmentCohortRef):
            raise TypeError("cohort must be a FulfillmentCohortRef")
        _require_uuid(self.order_item_id, "order_item_id")
        _require_positive_int(self.quantity, "quantity")


@dataclass(frozen=True, slots=True)
class PackageRef:
    """Versioned final package binding composition, dimensions, and active seal."""

    package_id: UUID
    package_version: int
    composition: tuple[PackageItemRef, ...]
    measurement: ParcelMeasurement
    seal: SealRef

    def __post_init__(self) -> None:
        _require_uuid(self.package_id, "package_id")
        _require_positive_int(self.package_version, "package_version")
        if not isinstance(self.composition, tuple):
            raise TypeError("composition must be a tuple of PackageItemRef values")
        if not self.composition:
            raise ValueError("composition must contain at least one PackageItemRef")
        if not all(isinstance(item, PackageItemRef) for item in self.composition):
            raise TypeError("composition must contain only PackageItemRef values")
        if not isinstance(self.measurement, ParcelMeasurement):
            raise TypeError("measurement must be a ParcelMeasurement")
        if not isinstance(self.seal, SealRef):
            raise TypeError("seal must be a SealRef")


@dataclass(frozen=True, slots=True)
class OutboundShipmentIntent:
    """Last-mile intent bound to one immutable final package from a hub."""

    order_id: UUID
    origin_hub: HubRef
    destination: DomesticAddress
    package: PackageRef

    def __post_init__(self) -> None:
        _require_uuid(self.order_id, "order_id")
        if not isinstance(self.origin_hub, HubRef):
            raise TypeError("origin_hub must be a HubRef")
        if not isinstance(self.destination, DomesticAddress):
            raise TypeError("destination must be a DomesticAddress")
        if not isinstance(self.package, PackageRef):
            raise TypeError("package must be a PackageRef")
        if any(item.cohort.hub != self.origin_hub for item in self.package.composition):
            raise ValueError("every package cohort hub must match origin_hub")
