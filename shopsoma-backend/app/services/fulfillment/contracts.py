"""Pure, provider-neutral values for domestic hub fulfillment."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from uuid import UUID


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_uuid(value: UUID, field_name: str) -> None:
    if not isinstance(value, UUID):
        raise TypeError(f"{field_name} must be a UUID")


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
class HubReceiptResult:
    """Result of ShopSoma taking custody of an inbound transfer."""

    transfer: InboundTransferRef
    received_at: datetime
    received_item_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.transfer, InboundTransferRef):
            raise TypeError("transfer must be an InboundTransferRef")
        if not isinstance(self.received_at, datetime):
            raise TypeError("received_at must be a datetime")
        if (
            not isinstance(self.received_item_count, int)
            or isinstance(self.received_item_count, bool)
            or self.received_item_count < 0
        ):
            raise ValueError("received_item_count must be a non-negative integer")


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
    """Opaque identifier applied after ShopSoma packs a parcel."""

    value: str

    def __post_init__(self) -> None:
        _require_non_empty(self.value, "seal value")


@dataclass(frozen=True, slots=True)
class CustodyEvent:
    """ShopSoma hub custody event for a fulfillment cohort."""

    cohort: FulfillmentCohortRef
    hub: HubRef
    event: str
    occurred_at: datetime
    seal: SealRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cohort, FulfillmentCohortRef):
            raise TypeError("cohort must be a FulfillmentCohortRef")
        if not isinstance(self.hub, HubRef):
            raise TypeError("hub must be a HubRef")
        if self.hub != self.cohort.hub:
            raise ValueError("custody hub must match the cohort hub")
        _require_non_empty(self.event, "event")
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be a datetime")
        if self.seal is not None and not isinstance(self.seal, SealRef):
            raise TypeError("seal must be a SealRef")


@dataclass(frozen=True, slots=True)
class OutboundShipmentIntent:
    """Last-mile intent originating only at a ShopSoma hub."""

    order_id: UUID
    cohort: FulfillmentCohortRef
    origin_hub: HubRef
    destination: DomesticAddress
    parcel: ParcelMeasurement
    seal: SealRef

    def __post_init__(self) -> None:
        _require_uuid(self.order_id, "order_id")
        if not isinstance(self.cohort, FulfillmentCohortRef):
            raise TypeError("cohort must be a FulfillmentCohortRef")
        if not isinstance(self.origin_hub, HubRef):
            raise TypeError("origin_hub must be a HubRef")
        if self.origin_hub != self.cohort.hub:
            raise ValueError("origin_hub must match the cohort hub")
        if not isinstance(self.destination, DomesticAddress):
            raise TypeError("destination must be a DomesticAddress")
        if not isinstance(self.parcel, ParcelMeasurement):
            raise TypeError("parcel must be a ParcelMeasurement")
        if not isinstance(self.seal, SealRef):
            raise TypeError("seal must be a SealRef")
