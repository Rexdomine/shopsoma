"""Customs declaration and HS-code builder for DHL Express international export shipments."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Any, Iterable, Mapping

DEFAULT_HS_CODE = "62044200"  # Women's/Girls' cotton dresses & apparel
GENERIC_CONTENT_DESCRIPTION = "Fashion apparel and accessories"
# MyDHL `/shipments` content.description is limited to 70 characters.
MAX_CONTENT_DESCRIPTION_LENGTH = 70
MAX_LINE_ITEM_DESCRIPTION_LENGTH = 70

CATEGORY_HS_CODE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("dress", "dresses", "gown", "gowns"), "62044200"),
    (("shirt", "shirts", "top", "tops", "blouse", "blouses", "tee", "t-shirt"), "62052000"),
    (("trouser", "trousers", "pant", "pants", "short", "shorts", "jean", "jeans", "skirt", "skirts"), "62034200"),
    (("native", "agbada", "kaftan", "bubu", "boubou", "adire", "ankara", "aso", "senator", "trad"), "62114200"),
    (("bag", "bags", "handbag", "handbags", "clutch", "tote", "purse", "pouch"), "42022200"),
    (("shoe", "shoes", "footwear", "sandal", "sandals", "heel", "heels", "mule", "mules", "slipper", "loafers"), "64039900"),
    (("jewelry", "jewellery", "accessory", "accessories", "earring", "earrings", "necklace", "bracelet", "ring", "brooch"), "71171900"),
    (("headwrap", "headwraps", "gele", "scarf", "scarves", "shawl", "turban"), "62149000"),
)


def resolve_hs_code(*hints: str | None) -> str:
    """Resolve an 8-digit HS commodity code from category slug/name or product title."""
    for raw in hints:
        if not raw or not isinstance(raw, str):
            continue
        lower = raw.strip().lower()
        if not lower:
            continue
        for keywords, hs_code in CATEGORY_HS_CODE_KEYWORDS:
            if any(keyword in lower for keyword in keywords):
                return hs_code
    return DEFAULT_HS_CODE


def _safe_loaded_order_items(order: Any) -> list[Any]:
    """Return loaded order items without triggering lazy-load greenlet errors."""
    if order is None:
        return []
    raw_dict = getattr(order, "__dict__", None)
    if isinstance(raw_dict, dict) and "items" in raw_dict:
        items = raw_dict.get("items")
        return list(items) if items else []
    try:
        items = getattr(order, "items", None)
        return list(items) if items else []
    except Exception:
        return []


def _extract_item_category_hints(item: Any) -> tuple[str | None, ...]:
    hints: list[str | None] = []
    title = getattr(item, "product_title", None) or getattr(item, "title", None)
    product = getattr(item, "__dict__", {}).get("product") if hasattr(item, "__dict__") else None
    if product is not None:
        cat = getattr(product, "__dict__", {}).get("category") if hasattr(product, "__dict__") else None
        if cat is not None:
            hints.append(getattr(cat, "slug", None))
            hints.append(getattr(cat, "name", None))
        hints.append(getattr(product, "category_slug", None))
        hints.append(getattr(product, "category_name", None))
        if not title:
            title = getattr(product, "title", None) or getattr(product, "name", None)
    hints.append(title)
    return tuple(hints)


@dataclass(frozen=True, slots=True)
class ShipmentContentLine:
    """One product line physically packed inside a DHL shipment."""

    title: str
    quantity: int
    unit_price: Decimal | None = None
    variant_label: str | None = None
    hs_hints: tuple[str | None, ...] = ()


def _clean_text(value: object) -> str:
    """Return printable, whitespace-collapsed text that DHL documents can render."""
    if not isinstance(value, str):
        return ""
    folded = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    text = folded if folded.strip() else value
    return " ".join("".join(ch if ch.isprintable() else " " for ch in text).split())


def _variant_label(variant_details: object) -> str | None:
    if not isinstance(variant_details, Mapping):
        return None
    parts: list[str] = []
    size = _clean_text(str(variant_details.get("size") or ""))
    color = _clean_text(str(variant_details.get("color") or ""))
    if size:
        parts.append(f"Size {size}")
    if color:
        parts.append(color)
    return ", ".join(parts) or None


def content_line_from_order_item(item: Any, *, quantity: int | None = None) -> ShipmentContentLine:
    """Snapshot an order item (optionally with a package-specific quantity) as a content line."""
    title = _clean_text(
        getattr(item, "product_title", None) or getattr(item, "title", None) or ""
    ) or "Fashion item"
    raw_quantity = quantity if quantity is not None else getattr(item, "quantity", 1)
    try:
        qty = max(int(raw_quantity or 1), 1)
    except (TypeError, ValueError):
        qty = 1
    raw_price = getattr(item, "unit_price", None)
    try:
        unit_price = Decimal(str(raw_price)) if raw_price is not None else None
    except Exception:
        unit_price = None
    return ShipmentContentLine(
        title=title,
        quantity=qty,
        unit_price=unit_price,
        variant_label=_variant_label(getattr(item, "variant_details", None)),
        hs_hints=_extract_item_category_hints(item),
    )


def content_lines_from_order(order: Any) -> list[ShipmentContentLine]:
    """Build content lines from already-loaded order items (never lazy-loads)."""
    return [content_line_from_order_item(item) for item in _safe_loaded_order_items(order)]


def _line_label(line: ShipmentContentLine, *, with_variant: bool) -> str:
    name = line.title
    if with_variant and line.variant_label:
        name = f"{name} ({line.variant_label})"
    return f"{line.quantity}x {name}"


def _more_suffix(lines: Iterable[ShipmentContentLine]) -> str:
    units = sum(line.quantity for line in lines)
    return f" +{units} more item{'s' if units != 1 else ''}" if units else ""


def build_content_description(
    lines: Iterable[ShipmentContentLine],
    *,
    max_length: int = MAX_CONTENT_DESCRIPTION_LENGTH,
) -> str:
    """Summarize packed items (name + quantity) for the DHL label `Content:` field.

    Example: ``"2x Aifo skirt (Size 8, Black), 1x Eyo layered skirt"``. Falls back
    to dropping variant details, then to ``"... +N more items"`` so the result
    always fits DHL's 70-character limit.
    """
    packed = [line for line in lines if line.quantity > 0 and line.title]
    if not packed:
        return GENERIC_CONTENT_DESCRIPTION
    for with_variant in (True, False):
        joined = ", ".join(_line_label(line, with_variant=with_variant) for line in packed)
        if len(joined) <= max_length:
            return joined
    labels = [_line_label(line, with_variant=False) for line in packed]
    for keep in range(len(labels) - 1, 0, -1):
        head = ", ".join(labels[:keep])
        suffix = _more_suffix(packed[keep:])
        if len(head) + len(suffix) <= max_length:
            return head + suffix
    suffix = _more_suffix(packed[1:])
    room = max(max_length - len(suffix) - 3, 1)
    return labels[0][:room].rstrip() + "..." + suffix


def _fallback_unit_price(currency: str) -> Decimal:
    return Decimal("50.00") if currency != "NGN" else Decimal("25000.00")


def build_export_content_fields(
    *,
    order: Any,
    package_version: Any,
    planned_ship_date: date,
    content_lines: Iterable[ShipmentContentLine] | None = None,
) -> dict[str, object]:
    """Build customs declaration fields for MyDHL `/shipments` content payload.

    ``content_lines`` should describe exactly what is inside the package. When not
    supplied, already-loaded ``order.items`` are used; if nothing is available a
    single generic line valued at the order subtotal is declared.
    """
    currency_raw = str(getattr(order, "currency", None) or "NGN").strip().upper()
    currency = currency_raw if currency_raw in {"NGN", "USD", "GBP", "EUR", "CAD"} else "NGN"

    total_weight_kg = max(float(getattr(package_version, "weight_kg", 1.0) or 1.0), 0.1)
    lines = list(content_lines) if content_lines is not None else content_lines_from_order(order)

    line_items: list[dict[str, object]] = []
    declared_total = Decimal("0.00")

    if lines:
        total_units = sum(line.quantity for line in lines) or 1
        for index, line in enumerate(lines, start=1):
            qty = max(int(line.quantity or 1), 1)
            unit_price_dec = line.unit_price if line.unit_price is not None else Decimal("0")
            if unit_price_dec <= 0:
                unit_price_dec = _fallback_unit_price(currency)
            unit_price_dec = unit_price_dec.quantize(Decimal("0.01"))
            declared_total += (unit_price_dec * qty).quantize(Decimal("0.01"))
            line_weight = float(
                max(
                    (Decimal(str(total_weight_kg)) * qty / total_units).quantize(
                        Decimal("0.001"), rounding=ROUND_DOWN
                    ),
                    Decimal("0.010"),
                )
            )

            description = line.title
            if line.variant_label:
                description = f"{description} - {line.variant_label}"
            description = description[:MAX_LINE_ITEM_DESCRIPTION_LENGTH].strip() or "Fashion apparel"
            hs_code = resolve_hs_code(*line.hs_hints, line.title)

            line_items.append(
                {
                    "number": index,
                    "description": description,
                    "price": float(unit_price_dec),
                    "quantity": {
                        "value": qty,
                        "unitOfMeasurement": "PCS",
                    },
                    "commodityCodes": [
                        {"typeCode": "outbound", "value": hs_code},
                        {"typeCode": "inbound", "value": hs_code},
                    ],
                    "exportReasonType": "permanent",
                    "manufacturerCountry": "NG",
                    "weight": {
                        "netValue": line_weight,
                        "grossValue": line_weight,
                    },
                    "isTaxesPaid": False,
                }
            )
    else:
        raw_subtotal = getattr(order, "subtotal", None) or getattr(order, "total_amount", None)
        try:
            fallback_price_dec = Decimal(str(raw_subtotal)) if raw_subtotal is not None else Decimal("0")
        except Exception:
            fallback_price_dec = Decimal("0")
        if fallback_price_dec <= 0:
            fallback_price_dec = _fallback_unit_price(currency)
        declared_total = fallback_price_dec.quantize(Decimal("0.01"))
        rounded_weight = round(total_weight_kg, 3)
        line_items.append(
            {
                "number": 1,
                "description": GENERIC_CONTENT_DESCRIPTION,
                "price": float(declared_total),
                "quantity": {
                    "value": 1,
                    "unitOfMeasurement": "PCS",
                },
                "commodityCodes": [
                    {"typeCode": "outbound", "value": DEFAULT_HS_CODE},
                    {"typeCode": "inbound", "value": DEFAULT_HS_CODE},
                ],
                "exportReasonType": "permanent",
                "manufacturerCountry": "NG",
                "weight": {
                    "netValue": rounded_weight,
                    "grossValue": rounded_weight,
                },
                "isTaxesPaid": False,
            }
        )

    order_number_raw = str(
        getattr(order, "order_number", None)
        or getattr(order, "id", None)
        or "SHOPSOMA"
    ).strip()
    invoice_number = f"INV-{order_number_raw}"[:35]

    return {
        "isCustomsDeclarable": True,
        "declaredValue": float(declared_total),
        "declaredValueCurrency": currency,
        "incoterm": "DAP",
        "exportDeclaration": {
            "lineItems": line_items,
            "invoice": {
                "number": invoice_number,
                "date": planned_ship_date.isoformat(),
                "function": "both",
                "totalNetWeight": round(total_weight_kg, 3),
                "totalGrossWeight": round(total_weight_kg, 3),
            },
            "exportReason": "Permanent",
            "exportReasonType": "permanent",
            "placeOfIncoterm": "LAGOS",
            "shipmentType": "commercial",
        },
    }
