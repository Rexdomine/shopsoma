"""Admin-only DHL sandbox shadow-quote wrapper (non-payment, UAT only).

Reuses the strict sandbox adapter (rating.py) and writes fresh
DomesticRateAttempt / Response / Offer evidence with admin attribution.
No customer-facing endpoint; checkout remains closed.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.domestic_rate_quote import (
    DomesticRateAttempt,
    DomesticRateOffer,
    DomesticRateResponse,
)
from app.models.package_custody import (
    HubPackage,
    HubPackageItem,
    HubPackageSeal,
    HubPackageVersion,
    OutboundShipmentIntent,
    OutboundShipmentIntentInvalidation,
)
from app.models.fulfillment_hub import FulfillmentHub
from app.models.order import Order
from app.models.user import User
from app.services.dhl.rating import (
    ACCOUNT_ALIAS,
    ADAPTER_VERSION,
    DHLRateAdapterError,
    DHLResolvedHub,
    DHLDomesticRateResult,
    SCHEMA_VERSION,
    MYDHL_TEST_BASE_URL,
    create_sandbox_domestic_rate_adapter,
)
from app.services.fulfillment.contracts import (
    HubRef,
    DomesticAddress,
    PackageRef,
    PackageItemRef,
    ParcelMeasurement,
    FulfillmentCohortRef,
    SealRef,
)
from app.services.shipping.contracts import DomesticRateRequest
from app.services.shipping.rate_identity import (
    CANONICAL_RATE_VERSION,
    canonical_rate_fingerprint,
)
from app.schemas.admin_order import ShadowQuoteResult


class ShadowQuoteError(Exception):
    pass


_LAGOS_TZ = ZoneInfo("Africa/Lagos")


def _normalize_lagos_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_LAGOS_TZ)
    return value.astimezone(_LAGOS_TZ)


def _planned_ship_date_for_shadow_quote(intent_created_at: datetime | None) -> date:
    current_time = _normalize_lagos_datetime(datetime.now(_LAGOS_TZ))
    planned_ship_date = current_time.date()
    if intent_created_at is not None:
        planned_ship_date = max(
            planned_ship_date,
            _normalize_lagos_datetime(intent_created_at).date(),
        )
    tender_at = datetime.combine(planned_ship_date, time(hour=12), tzinfo=_LAGOS_TZ)
    if tender_at <= current_time:
        planned_ship_date += timedelta(days=1)
    return planned_ship_date


async def run_admin_shadow_quote(
    db: AsyncSession,
    order_id: uuid.UUID,
    admin: User,
    settings: Settings,
    identity_key: bytes,
    identity_key_version: str,
    ready_package_id: uuid.UUID | None = None,
) -> ShadowQuoteResult:
    # Fail-closed sandbox gate check (before DB work)
    if settings.DHL_ENVIRONMENT != "sandbox":
        raise ShadowQuoteError("sandbox adapter requires DHL_ENVIRONMENT=sandbox")
    if settings.dhl_base_url != MYDHL_TEST_BASE_URL:
        raise ShadowQuoteError("sandbox adapter requires fixed MyDHL test base URL")
    if not settings.dhl_domestic_sandbox_cohort_ids:
        raise ShadowQuoteError("sandbox adapter requires restricted cohort set")

    order = await db.get(Order, order_id)
    if not order:
        raise ShadowQuoteError("order not found")

    # Authoritative ready package
    package_query = select(HubPackage).where(
        HubPackage.order_id == order_id,
        HubPackage.state == "ready",
    )
    if ready_package_id is not None:
        package_query = package_query.where(HubPackage.id == ready_package_id)
        pkg_res = await db.execute(package_query)
        package = pkg_res.scalar_one_or_none()
        if package is None:
            raise ShadowQuoteError("selected ready package not found for order")
    else:
        pkg_res = await db.execute(
            package_query.order_by(
                HubPackage.ready_at.desc(),
                HubPackage.row_version.desc(),
                HubPackage.created_at.desc(),
                HubPackage.id.desc(),
            )
        )
        packages = pkg_res.scalars().all()
        if not packages:
            raise ShadowQuoteError("no ready package for order")
        if len(packages) > 1:
            raise ShadowQuoteError(
                "multiple ready packages for order; package_id is required"
            )
        package = packages[0]

    # Active bound seal for package version
    seal_res = await db.execute(
        select(HubPackageSeal).where(
            HubPackageSeal.package_id == package.id,
            HubPackageSeal.package_version == package.current_version,
            HubPackageSeal.retired_at.is_(None),
        ).order_by(HubPackageSeal.applied_at.desc())
    )
    seal = seal_res.scalar_one_or_none()
    if seal is None:
        raise ShadowQuoteError("no active bound seal")

    # Authoritative outbound intent
    intent_res = await db.execute(
        select(OutboundShipmentIntent).where(
            OutboundShipmentIntent.order_id == order_id,
            OutboundShipmentIntent.package_id == package.id,
            OutboundShipmentIntent.package_version == package.current_version,
            ~select(OutboundShipmentIntentInvalidation.id)
            .where(OutboundShipmentIntentInvalidation.intent_id == OutboundShipmentIntent.id)
            .exists(),
        ).order_by(OutboundShipmentIntent.created_at.desc())
    )
    intent = intent_res.scalar_one_or_none()
    if intent is None:
        invalidated_intent_res = await db.execute(
            select(OutboundShipmentIntent.id).where(
                OutboundShipmentIntent.order_id == order_id,
                OutboundShipmentIntent.package_id == package.id,
                OutboundShipmentIntent.package_version == package.current_version,
                select(OutboundShipmentIntentInvalidation.id)
                .where(OutboundShipmentIntentInvalidation.intent_id == OutboundShipmentIntent.id)
                .exists(),
            )
        )
        if invalidated_intent_res.scalar_one_or_none() is not None:
            raise ShadowQuoteError(
                "selected ready package outbound intent has been invalidated"
            )
        raise ShadowQuoteError("no outbound shipment intent")

    # Active hub
    hub_res = await db.execute(
        select(FulfillmentHub).where(
            FulfillmentHub.id == package.hub_id, FulfillmentHub.is_active.is_(True)
        )
    )
    hub = hub_res.scalar_one_or_none()
    if hub is None:
        raise ShadowQuoteError("hub not active")

    # Load package version measurement
    pv_res = await db.execute(
        select(HubPackageVersion).where(
            HubPackageVersion.package_id == package.id,
            HubPackageVersion.version == package.current_version,
        )
    )
    pv = pv_res.scalar_one_or_none()
    if pv is None:
        raise ShadowQuoteError("missing package version measurement")

    # Derive contract objects from the authoritative package composition
    measurement = ParcelMeasurement(
        weight_kg=pv.weight_kg,
        length_cm=pv.length_cm,
        width_cm=pv.width_cm,
        height_cm=pv.height_cm,
    )
    items_res = await db.execute(
        select(HubPackageItem).where(
            HubPackageItem.package_id == package.id,
            HubPackageItem.package_version == package.current_version,
        )
    )
    package_items = items_res.scalars().all()
    if not package_items:
        raise ShadowQuoteError("ready package has no package items")
    cohort_ids = {item.cohort_id for item in package_items}
    if not cohort_ids <= settings.dhl_domestic_sandbox_cohort_ids:
        raise ShadowQuoteError("package composition is outside sandbox cohort allowlist")
    composition = tuple(
        PackageItemRef(
            cohort=FulfillmentCohortRef(
                id=item.cohort_id,
                hub=HubRef(id=hub.id),
            ),
            order_item_id=item.order_item_id,
            quantity=item.quantity,
        )
        for item in package_items
    )
    package_ref = PackageRef(
        package_id=package.id,
        package_version=package.current_version,
        composition=composition,
        measurement=measurement,
        seal=SealRef(value=seal.opaque_value),
    )

    destination_country_code = intent.destination_country_code
    destination = DomesticAddress(
        contact_name=intent.destination_name,
        phone=intent.destination_phone,
        line1=intent.destination_address_line1,
        line2=intent.destination_address_line2,
        city=intent.destination_city,
        state=intent.destination_state,
        postal_code=intent.destination_postal_code,
        country_code=destination_country_code,
    )

    hub_ref = HubRef(id=hub.id)

    resolved = DHLResolvedHub(
        hub=hub_ref,
        hub_version=hub.version,
        intent_id=intent.id,
        order_id=order.id,
        seal_id=seal.id,
        package_id=package.id,
        package_version=package.current_version,
        destination=destination,
        package=package_ref,
        contact_name=hub.contact_name,
        phone=hub.contact_phone,
        line1=hub.address_line1,
        line2=hub.address_line2,
        city=hub.city,
        state=hub.state,
        postal_code=hub.postal_code,
        country_code=hub.country_code,
    )

    planned_ship_date = _planned_ship_date_for_shadow_quote(intent.created_at)

    request = DomesticRateRequest(
        origin=hub_ref,
        destination=destination,
        package=package_ref,
        planned_ship_date=planned_ship_date,
    )

    fingerprint = canonical_rate_fingerprint(
        request=request,
        resolved_hub=resolved,
        provider="dhl",
        environment="sandbox",
        account_alias=ACCOUNT_ALIAS,
        adapter_version=ADAPTER_VERSION,
        schema_version=SCHEMA_VERSION,
        key_version=identity_key_version,
        secret_key=identity_key,
    )

    claimed_at = await db.scalar(text("SELECT clock_timestamp()"))
    idempotency_key = f"shadow-admin-{str(admin.id)}-{str(order.id)}-{uuid.uuid4().hex}"

    # Build pristine pending attempt; lifecycle completes via SQL update
    attempt = DomesticRateAttempt(
        id=uuid.uuid4(),
        intent_id=intent.id,
        order_id=order.id,
        package_id=package.id,
        package_version=package.current_version,
        seal_id=seal.id,
        origin_hub_id=hub.id,
        hub_version=hub.version,
        destination_country_code=destination_country_code,
        destination_snapshot_hash=intent.destination_snapshot_hash,
        provider="dhl",
        environment="sandbox",
        account_alias=ACCOUNT_ALIAS,
        initiating_actor_type="admin",
        initiating_actor_id=str(admin.id),
        source_command="admin_shadow_quote",
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        fingerprint_key_version=identity_key_version,
        planned_ship_date=request.planned_ship_date,
        adapter_version=ADAPTER_VERSION,
        schema_version=SCHEMA_VERSION,
        canonicalization_version=CANONICAL_RATE_VERSION,
        claimed_at=claimed_at,
        claim_ttl_seconds=300,
        classification="pending",
    )
    db.add(attempt)
    await db.flush()

    await db.execute(
        text(
            "UPDATE domestic_rate_attempts "
            "SET call_started_at=clock_timestamp() "
            "WHERE id=:attempt_id"
        ),
        {"attempt_id": attempt.id},
    )
    await db.refresh(attempt)
    call_started_at = attempt.call_started_at

    result: DHLDomesticRateResult | None = None
    adapter_error = None
    try:
        adapter = create_sandbox_domestic_rate_adapter(
            config=settings,
            transport=None,
            identity_key=identity_key,
            identity_key_version=identity_key_version,
        )
        result = await adapter.rate(resolved, request)
    except DHLRateAdapterError as exc:
        adapter_error = exc
    result_recorded_at = await db.scalar(text("SELECT clock_timestamp()"))
    terminal_classification = (
        "failure" if adapter_error is not None else (result.result_kind if result is not None else "no_service")
    )
    failure_code = "adapter_rate_failure" if adapter_error is not None else None
    await db.execute(
        text(
            "UPDATE domestic_rate_attempts "
            "SET result_recorded_at=:recorded, "
            "classification=:classification, failure_code=:failure_code "
            "WHERE id=:attempt_id"
        ),
        {
            "attempt_id": attempt.id,
            "recorded": result_recorded_at,
            "classification": terminal_classification,
            "failure_code": failure_code,
        },
    )
    await db.refresh(attempt)

    # Write response only for terminal success/no_service
    if adapter_error is None and result is not None:
        ttl_seconds = settings.DHL_DOMESTIC_QUOTE_TTL_SECONDS
        received_at = result_recorded_at
        expires_at = received_at + timedelta(seconds=ttl_seconds)
        response = DomesticRateResponse(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            result_kind=result.result_kind,
            received_at=received_at,
            ttl_seconds=ttl_seconds,
            expires_at=expires_at,
            completion_txid=attempt.completion_txid,
        )
        db.add(response)
        await db.flush()
        offers_redacted = []
        if result.result_kind == "success":
            for offer in result.offers:
                offer_row = DomesticRateOffer(
                    id=uuid.uuid4(),
                    response_id=response.id,
                    provider_product_code=offer.provider_product_code,
                    provider_service_code=offer.provider_service_code,
                    service_label=offer.service_label,
                    total_amount=offer.rate.total_amount,
                    currency=offer.rate.currency,
                    transit_days=offer.rate.carrier_transit_days,
                    delivery_date=offer.rate.estimated_carrier_delivery_date,
                    completion_txid=response.completion_txid,
                )
                db.add(offer_row)
                offers_redacted.append({
                    "provider_product_code": offer.provider_product_code,
                    "service_label": offer.service_label,
                    "currency": offer.rate.currency,
                    "total_amount": float(offer.rate.total_amount),
                })
        await db.flush()
    else:
        offers_redacted = []

    await db.commit()

    gate_status = {
        "sandbox_environment": settings.DHL_ENVIRONMENT == "sandbox",
        "base_url_fixed": settings.dhl_base_url == MYDHL_TEST_BASE_URL,
        "cohort_restricted": bool(settings.dhl_domestic_sandbox_cohort_ids),
        "provider_calls_enabled": settings.DHL_DOMESTIC_PROVIDER_CALLS_ENABLED,
        "adapter_version": ADAPTER_VERSION,
    }

    result_kind = (
        result.result_kind if adapter_error is None and result is not None else "failed"
    )

    return ShadowQuoteResult(
        order_id=order.id,
        shadow_quote_id=attempt.id,
        result_kind=result_kind,
        environment="sandbox",
        adapter_version=ADAPTER_VERSION,
        provider="dhl",
        offers_count=len(offers_redacted),
        offers_redacted=offers_redacted,
        gate_status=gate_status,
        quoted_at=result_recorded_at,
        note=(
            "admin shadow quote; checkout remains closed; no booking created"
            if adapter_error is None and result is not None
            else "adapter rate failed; evidence persisted with admin attribution"
        ),
    )
