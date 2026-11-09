"""Customs declaration and HS-code builder for DHL Express international export shipments."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

DEFAULT_HS_CODE = "62044200"  # Women's/Girls' cotton dresses & apparel

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


def build_export_content_fields(
    *,
    order: Any,
    package_version: Any,
    planned_ship_date: date,
) -> dict[str, object]:
    """Build customs declaration fields for MyDHL `/shipments` content payload."""
    currency_raw = str(getattr(order, "currency", None) or "NGN").strip().upper()
    currency = currency_raw if currency_raw in {"NGN", "USD", "GBP", "EUR", "CAD"} else "NGN"

    total_weight_kg = max(float(getattr(package_version, "weight_kg", 1.0) or 1.0), 0.1)
    loaded_items = _safe_loaded_order_items(order)

    line_items: list[dict[str, object]] = []
    declared_total = Decimal("0.00")

    if loaded_items:
        item_count = len(loaded_items)
        per_line_weight = round(max(total_weight_kg / item_count, 0.05), 3)
        for index, item in enumerate(loaded_items, start=1):
            qty = max(int(getattr(item, "quantity", 1) or 1), 1)
            raw_unit_price = getattr(item, "unit_price", None)
            try:
                unit_price_dec = Decimal(str(raw_unit_price)) if raw_unit_price is not None else Decimal("0")
            except Exception:
                unit_price_dec = Decimal("0")
            if unit_price_dec <= 0:
                unit_price_dec = Decimal("50.00") if currency != "NGN" else Decimal("25000.00")
            unit_price = float(unit_price_dec.quantize(Decimal("0.01")))
            declared_total += (unit_price_dec * qty).quantize(Decimal("0.01"))

            raw_title = str(
                getattr(item, "product_title", None)
                or getattr(item, "title", None)
                or "Fashion apparel"
            ).strip()
            clean_description = (
                "".join(ch if ch.isprintable() else " " for ch in raw_title).strip()[:70]
                or "Fashion apparel"
            )
            hs_code = resolve_hs_code(*_extract_item_category_hints(item))

            line_items.append(
                {
                    "number": index,
                    "description": clean_description,
                    "price": unit_price,
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
                        "netValue": per_line_weight,
                        "grossValue": per_line_weight,
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
            fallback_price_dec = Decimal("50.00") if currency != "NGN" else Decimal("25000.00")
        declared_total = fallback_price_dec.quantize(Decimal("0.01"))
        rounded_weight = round(total_weight_kg, 3)
        line_items.append(
            {
                "number": 1,
                "description": "Fashion apparel and accessories",
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
