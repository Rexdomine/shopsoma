"""Provider-neutral contracts for Nigerian hub-to-customer rate shopping."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.services.fulfillment.contracts import (
    DomesticAddress,
    HubRef,
    PackageRef,
)

_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")


def _require_identifier(value: object, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if _IDENTIFIER_PATTERN.fullmatch(value) is None:
        raise ValueError(f"{field_name} is malformed")


def _require_date(value: object, field_name: str) -> None:
    # datetime is a date subclass, but silently discarding its time is unsafe.
    if not isinstance(value, date) or isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a date, not a datetime")


def _decimal_money(value: object) -> Decimal:
    if isinstance(value, float):
        raise TypeError("total_amount must not be a float")
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, str)):
        raise TypeError("total_amount must be a Decimal-compatible exact value")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError("total_amount must be positive and finite") from None
    if not amount.is_finite() or amount <= 0:
        raise ValueError("total_amount must be positive and finite")
    return amount


@dataclass(frozen=True, slots=True)
class DomesticRateRequest:
    """Rate request for sealed merchandise leaving a server-selected ShopSoma hub.

    This contract represents only Nigerian domestic outbound movement. It cannot
    represent a vendor origin, vendor-to-hub inbound transfer, import, or document
    shipment.
    """

    origin: HubRef
    destination: DomesticAddress
    package: PackageRef
    planned_ship_date: date
    content_type: str = "merchandise"
    movement_direction: str = "outbound"

    def __post_init__(self) -> None:
        if not isinstance(self.origin, HubRef):
            raise TypeError("origin must be a HubRef")
        if not isinstance(self.destination, DomesticAddress):
            raise TypeError("destination must be a DomesticAddress")

        if not isinstance(self.package, PackageRef):
            raise TypeError("package must be a PackageRef")
        if any(item.cohort.hub != self.origin for item in self.package.composition):
            raise ValueError("every package cohort hub must match origin")

        _require_date(self.planned_ship_date, "planned_ship_date")
        if self.content_type != "merchandise":
            raise ValueError("content_type must be merchandise")
        if self.movement_direction != "outbound":
            raise ValueError("movement_direction must be outbound")


@dataclass(frozen=True, slots=True)
class DomesticRate:
    """Provider-neutral carrier rate and carrier-only delivery estimate.

    Transit fields begin when the packed shipment leaves the ShopSoma hub. They
    deliberately exclude vendor preparation, inbound transfer, hub QC, and packing,
    and therefore are not a full order ETA.
    """

    rate_id: str
    service_id: str
    package: PackageRef
    total_amount: Decimal
    currency: str
    carrier_transit_days: int | None = None
    estimated_carrier_delivery_date: date | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.rate_id, "rate_id")
        _require_identifier(self.service_id, "service_id")
        if not isinstance(self.package, PackageRef):
            raise TypeError("package must be a PackageRef")
        object.__setattr__(self, "total_amount", _decimal_money(self.total_amount))

        if not isinstance(self.currency, str):
            raise TypeError("currency must be a string")
        currency = self.currency.upper()
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise ValueError("currency must be a three-letter currency code")
        object.__setattr__(self, "currency", currency)

        if self.carrier_transit_days is not None:
            if not isinstance(self.carrier_transit_days, int) or isinstance(
                self.carrier_transit_days, bool
            ):
                raise TypeError("carrier_transit_days must be a non-negative integer")
            if self.carrier_transit_days < 0:
                raise ValueError("carrier_transit_days must be a non-negative integer")
        if self.estimated_carrier_delivery_date is not None:
            _require_date(
                self.estimated_carrier_delivery_date,
                "estimated_carrier_delivery_date",
            )
