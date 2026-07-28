"""Deterministic, versioned and keyed identity for domestic rate requests."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

from app.services.shipping.contracts import DomesticRateRequest

CANONICAL_RATE_VERSION = "rate-canonical-v2"


def _decimal_string(value: Decimal) -> str:
    """Preserve the exact Decimal coefficient and scale without context rounding."""
    return str(value)


def _address(value: Any) -> dict[str, Any]:
    return {
        "city": value.city,
        "contact_name": value.contact_name,
        "country_code": value.country_code,
        "line1": value.line1,
        "line2": value.line2,
        "phone": value.phone,
        "postal_code": value.postal_code,
        "state": value.state,
    }


def _hub(value: Any) -> dict[str, Any]:
    return {
        "city": value.city,
        "contact_name": value.contact_name,
        "country_code": value.country_code,
        "hub_id": str(value.hub.id),
        "hub_version": value.hub_version,
        "intent_id": str(value.intent_id),
        "line1": value.line1,
        "line2": value.line2,
        "order_id": str(value.order_id),
        "package_id": str(value.package_id),
        "package_version": value.package_version,
        "phone": value.phone,
        "postal_code": value.postal_code,
        "seal_id": str(value.seal_id),
        "state": value.state,
    }


def canonical_rate_document(
    *,
    request: DomesticRateRequest,
    resolved_hub: Any,
    provider: str,
    environment: str,
    account_alias: str,
    adapter_version: str,
    schema_version: str,
    key_version: str,
) -> dict[str, Any]:
    """Build the complete canonical binding document (never log this value)."""
    if not isinstance(request, DomesticRateRequest):
        raise TypeError("request must be a DomesticRateRequest")
    package = request.package
    measurement = package.measurement
    composition = sorted(
        (
            {
                "cohort_id": str(item.cohort.id),
                "cohort_hub_id": str(item.cohort.hub.id),
                "order_item_id": str(item.order_item_id),
                "quantity": item.quantity,
            }
            for item in package.composition
        ),
        key=lambda item: (
            item["cohort_id"],
            item["order_item_id"],
            item["quantity"],
        ),
    )
    return {
        "account_alias": account_alias,
        "adapter_version": adapter_version,
        "canonicalization_version": CANONICAL_RATE_VERSION,
        "environment": environment,
        "fingerprint_key_version": key_version,
        "provider": provider,
        "request": {
            "content_type": request.content_type,
            "destination": _address(request.destination),
            "movement_direction": request.movement_direction,
            "origin_hub_id": str(request.origin.id),
            "package": {
                "composition": composition,
                "measurement": {
                    "height_cm": _decimal_string(measurement.height_cm),
                    "length_cm": _decimal_string(measurement.length_cm),
                    "weight_kg": _decimal_string(measurement.weight_kg),
                    "width_cm": _decimal_string(measurement.width_cm),
                },
                "package_id": str(package.package_id),
                "package_version": package.package_version,
                "seal_value": package.seal.value,
            },
            "planned_ship_date": request.planned_ship_date.isoformat(),
        },
        "resolved_hub": _hub(resolved_hub),
        "schema_version": schema_version,
    }


def canonical_rate_fingerprint(
    *,
    request: DomesticRateRequest,
    resolved_hub: Any,
    provider: str,
    environment: str,
    account_alias: str,
    adapter_version: str,
    schema_version: str,
    key_version: str,
    secret_key: bytes,
) -> str:
    """Return a SHA-256 HMAC over canonical UTF-8 JSON.

    The key is explicit by design. It is used only as HMAC key material and is
    never included in the canonical document, an exception, or a log record.
    """
    if not isinstance(secret_key, bytes):
        raise TypeError("secret key must be bytes")
    if not secret_key:
        raise ValueError("secret key must not be empty")
    document = canonical_rate_document(
        request=request,
        resolved_hub=resolved_hub,
        provider=provider,
        environment=environment,
        account_alias=account_alias,
        adapter_version=adapter_version,
        schema_version=schema_version,
        key_version=key_version,
    )
    canonical_json = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return hmac.new(secret_key, canonical_json, hashlib.sha256).hexdigest()
