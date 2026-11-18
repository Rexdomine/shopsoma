"""DHL Express single-piece parcel rules: validation, normalization, billable weight.

Values here mirror DHL Express standard piece acceptance so a label booked with
these measurements is not rejected or re-billed for oversize:

* actual weight 0.01 - 70 kg per piece (heavier pieces need DHL freight handling)
* longest side <= 120 cm, other two sides <= 80 cm (beyond = non-standard piece)
* dimensions are sent as whole centimetres, rounded **up**, because DHL measures
  and bills on full centimetres
* volumetric weight = L x W x H / 5000; DHL bills the greater of actual and
  volumetric weight, rounded up to the next 0.5 kg
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation

DHL_MIN_PIECE_WEIGHT_KG = Decimal("0.01")
DHL_MAX_PIECE_WEIGHT_KG = Decimal("70")
DHL_MAX_LONGEST_SIDE_CM = Decimal("120")
DHL_MAX_OTHER_SIDE_CM = Decimal("80")
DHL_VOLUMETRIC_DIVISOR = Decimal("5000")
DHL_BILLING_INCREMENT_KG = Decimal("0.5")


class ParcelValidationError(ValueError):
    """Raised with human-readable reasons when a parcel is not DHL-acceptable."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass(frozen=True, slots=True)
class DhlParcel:
    weight_kg: Decimal
    length_cm: Decimal
    width_cm: Decimal
    height_cm: Decimal

    @property
    def volumetric_weight_kg(self) -> Decimal:
        return volumetric_weight_kg(self.length_cm, self.width_cm, self.height_cm)

    @property
    def billable_weight_kg(self) -> Decimal:
        return billable_weight_kg(self.weight_kg, self.length_cm, self.width_cm, self.height_cm)


def _decimal(value: object, field: str, errors: list[str]) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors.append(f"{field} must be a number")
        return None
    if not parsed.is_finite():
        errors.append(f"{field} must be a number")
        return None
    return parsed


def volumetric_weight_kg(length_cm: object, width_cm: object, height_cm: object) -> Decimal:
    volume = Decimal(str(length_cm)) * Decimal(str(width_cm)) * Decimal(str(height_cm))
    return (volume / DHL_VOLUMETRIC_DIVISOR).quantize(Decimal("0.01"), rounding=ROUND_CEILING)


def billable_weight_kg(weight_kg: object, length_cm: object, width_cm: object, height_cm: object) -> Decimal:
    heavier = max(Decimal(str(weight_kg)), volumetric_weight_kg(length_cm, width_cm, height_cm))
    steps = (heavier / DHL_BILLING_INCREMENT_KG).to_integral_value(rounding=ROUND_CEILING)
    return max(steps, Decimal("1")) * DHL_BILLING_INCREMENT_KG


def normalize_dhl_parcel(
    weight_kg: object, length_cm: object, width_cm: object, height_cm: object
) -> DhlParcel:
    """Validate and normalize one physical piece for DHL Express booking.

    Dimensions are rounded up to whole centimetres and ordered longest-first so
    the per-side limits are applied consistently regardless of entry order.
    """
    errors: list[str] = []
    weight = _decimal(weight_kg, "Weight", errors)
    raw_dims = [
        _decimal(length_cm, "Length", errors),
        _decimal(width_cm, "Width", errors),
        _decimal(height_cm, "Height", errors),
    ]
    if errors:
        raise ParcelValidationError(errors)
    assert weight is not None
    if weight < DHL_MIN_PIECE_WEIGHT_KG:
        errors.append(f"Weight must be at least {DHL_MIN_PIECE_WEIGHT_KG} kg")
    if weight > DHL_MAX_PIECE_WEIGHT_KG:
        errors.append(
            f"Weight exceeds the DHL Express {DHL_MAX_PIECE_WEIGHT_KG} kg per-piece limit; split the order into smaller parcels"
        )
    dims: list[Decimal] = []
    for value, label in zip(raw_dims, ("Length", "Width", "Height")):
        assert value is not None
        if value <= 0:
            errors.append(f"{label} must be greater than 0 cm")
            continue
        dims.append(value.to_integral_value(rounding=ROUND_CEILING))
    if errors:
        raise ParcelValidationError(errors)
    longest, middle, shortest = sorted(dims, reverse=True)
    if longest > DHL_MAX_LONGEST_SIDE_CM:
        errors.append(
            f"Longest side {longest} cm exceeds the DHL Express {DHL_MAX_LONGEST_SIDE_CM} cm limit"
        )
    if middle > DHL_MAX_OTHER_SIDE_CM:
        errors.append(
            f"Second side {middle} cm exceeds the DHL Express {DHL_MAX_OTHER_SIDE_CM} cm limit"
        )
    if errors:
        raise ParcelValidationError(errors)
    return DhlParcel(
        weight_kg=weight.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP),
        length_cm=longest,
        width_cm=middle,
        height_cm=shortest,
    )
