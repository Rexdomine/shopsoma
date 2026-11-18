"""Category-based parcel measurement estimates for products without vendor measurements.

Vendors may leave weight/length/width/height blank when creating a product. DHL
rating and hub package preparation still need a positive measurement, so each
missing value is filled from a conservative per-unit estimate for the product's
category (folded/packed garment sizes). Vendor-supplied values always win.

The hub is expected to weigh and measure the real packed parcel; these defaults
only keep checkout rating and package preparation working until then.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Iterable, Sequence

_WORD_RE = re.compile(r"[a-z]+")

# (weight_kg, length_cm, width_cm, height_cm) per single unit, packed.
Measurement = tuple[Decimal, Decimal, Decimal, Decimal]


def _m(weight: str, length: str, width: str, height: str) -> Measurement:
    return (Decimal(weight), Decimal(length), Decimal(width), Decimal(height))


# Same per-unit estimate hub preparation has always used for unmeasured items.
GENERIC_UNIT_MEASUREMENT: Measurement = _m("0.600", "35", "25", "5")

# Ordered: first matching keyword group wins (more specific groups first).
CATEGORY_UNIT_MEASUREMENTS: tuple[tuple[tuple[str, ...], Measurement], ...] = (
    (("agbada", "kaftan", "bubu", "boubou", "native", "aso", "senator", "adire", "ankara", "trad", "coat", "jacket", "windbreaker", "blazer"), _m("1.200", "40", "30", "8")),
    (("dress", "gown", "jumpsuit", "romper"), _m("0.800", "35", "28", "6")),
    (("shoe", "sandal", "heel", "sneaker", "boot", "footwear", "slipper", "loafer", "mule"), _m("1.000", "33", "22", "13")),
    (("bag", "handbag", "clutch", "tote", "purse", "backpack"), _m("0.900", "38", "28", "12")),
    (("jewelry", "jewellery", "earring", "necklace", "bracelet", "ring", "brooch", "accessor", "belt"), _m("0.150", "15", "12", "5")),
    (("gele", "headwrap", "scarf", "shawl", "turban", "legging", "tee", "top", "shirt", "blouse", "crop"), _m("0.300", "30", "25", "3")),
    (("trouser", "pant", "short", "jean", "skirt", "yoga"), _m("0.500", "32", "25", "5")),
)


def default_unit_measurement(*hints: str | None) -> Measurement:
    """Estimate one packed unit from category slug/name or product title hints.

    Keywords match on word prefixes ("dress" matches "dresses"; "ring" does not
    match "layering").
    """
    for raw in hints:
        if not raw or not isinstance(raw, str):
            continue
        tokens = _WORD_RE.findall(raw.lower())
        if not tokens:
            continue
        for keywords, measurement in CATEGORY_UNIT_MEASUREMENTS:
            if any(token.startswith(keyword) for token in tokens for keyword in keywords):
                return measurement
    return GENERIC_UNIT_MEASUREMENT


def _is_positive(value: object) -> bool:
    try:
        return value is not None and Decimal(str(value)) > 0
    except Exception:
        return False


def fill_missing_measurements(
    values: Sequence[object] | None,
    hints: Iterable[str | None] = (),
) -> tuple[Measurement, bool]:
    """Return ``(measurement, estimated)`` with missing/non-positive fields estimated.

    ``estimated`` is True when at least one field came from the category default.
    """
    defaults = default_unit_measurement(*hints)
    supplied = list(values) if values is not None else [None, None, None, None]
    supplied += [None] * (4 - len(supplied))
    estimated = False
    resolved: list[Decimal] = []
    for supplied_value, default in zip(supplied[:4], defaults):
        if _is_positive(supplied_value):
            resolved.append(Decimal(str(supplied_value)))
        else:
            resolved.append(default)
            estimated = True
    return (resolved[0], resolved[1], resolved[2], resolved[3]), estimated
