from __future__ import annotations

import base64
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol, Sequence

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.dhl_shipment import (
    OutboundIntentShipmentGuard,
    OutboundShipmentBooking,
    OutboundShipmentTrackingSnapshot,
)
from app.models.order import FulfillmentStatus, Order
from app.models.package_custody import (
    CustodyEvent,
    CustodyStream,
    HubPackage,
    HubPackageSeal,
    OutboundShipmentIntent,
    OutboundShipmentIntentInvalidation,
)
from app.models.user import User
from app.services.admin_shadow_quote import (
    _planned_ship_date_for_shadow_quote,
)
from app.services.dhl.client import (
    DHLAPIError,
    DHLClient,
    DHLConfigurationError,
)

PROVIDER = "dhl"
ENVIRONMENT = "sandbox"
ACCOUNT_ALIAS = "dhl-ng-sandbox"
BOOKING_ADAPTER_VERSION = "mydhl-shipments-v1"
BOOKING_SCHEMA_VERSION = "domestic-booking-v1"
TRACKING_SCHEMA_VERSION = "domestic-tracking-v1"
CANONICALIZATION_VERSION = "shipment-c14n-v1"
CLAIM_TTL_SECONDS = 300


class ShipmentPhase4Error(Exception):
    pass


class ShipmentPhase4ConflictError(ShipmentPhase4Error):
    pass


class ShipmentPhase4ReconciliationRequiredError(ShipmentPhase4ConflictError):
    pass


class ShipmentPhase4UnknownOutcomeError(ShipmentPhase4Error):
    pass


@dataclass(frozen=True, slots=True)
class BookingCommand:
    order_id: uuid.UUID
    intent_id: uuid.UUID
    package_id: uuid.UUID
    package_version: int
    seal_id: uuid.UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class BookingResult:
    booking_id: uuid.UUID
    order_id: uuid.UUID
    intent_id: uuid.UUID
    result_kind: str
    outbound_state: str
    provider_reference: str | None
    tracking_number: str | None
    label_media_type: str | None
    label_sha256: str | None
    booked_at: datetime | None
    note: str | None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class HandoffCommand:
    booking_id: uuid.UUID
    occurred_at: datetime
    idempotency_key: str
    counterparty: str
    evidence_ref: str
    evidence_sha256: str


@dataclass(frozen=True, slots=True)
class HandoffResult:
    booking_id: uuid.UUID
    outbound_state: str
    occurred_at: datetime
    custody_event_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class TrackingRefreshCommand:
    booking_id: uuid.UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TrackingObservation:
    provider_status_code: str
    outbound_state: str
    customer_status: str
    detail: str
    observed_at: datetime
    exception_code: str | None = None


@dataclass(frozen=True, slots=True)
class TrackingRefreshResult:
    booking_id: uuid.UUID
    tracking_number: str
    outbound_state: str
    customer_status: str
    observations_recorded: int
    refreshed_at: datetime


@dataclass(frozen=True, slots=True)
class ShipmentLabel:
    booking_id: uuid.UUID
    media_type: str
    filename: str
    content: bytes
    sha256: str


@dataclass(frozen=True, slots=True)
class AdapterBookingResult:
    provider_reference: str
    tracking_number: str
    label_media_type: str | None
    label_content: bytes | None
    service_code: str | None
    booked_at: datetime | None


class ShipmentAdapter(Protocol):
    async def book(self, intent: OutboundShipmentIntent, order: Order) -> AdapterBookingResult: ...

    async def track(self, tracking_number: str) -> Sequence[TrackingObservation]: ...


class DHLShipmentAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = DHLClient(config=settings)

    async def book(self, intent: OutboundShipmentIntent, order: Order) -> AdapterBookingResult:
        payload = {
            "plannedShippingDateAndTime": _planned_ship_date_for_shadow_quote(intent.created_at).isoformat(),
            "pickup": {"isRequested": False},
            "productCode": "N",
            "accounts": [{"typeCode": "shipper", "number": "SANDBOX"}],
            "customerDetails": {
                "shipperDetails": {"postalAddress": {"countryCode": "NG"}},
                "receiverDetails": {
                    "postalAddress": {
                        "countryCode": intent.destination_country_code,
                        "postalCode": intent.destination_postal_code,
                        "cityName": intent.destination_city,
                        "provinceCode": intent.destination_state,
                        "addressLine1": intent.destination_address_line1,
                        "addressLine2": intent.destination_address_line2,
                    },
                    "contactInformation": {
                        "fullName": intent.destination_name,
                        "phone": intent.destination_phone,
                    },
                },
            },
            "outputImageProperties": {"printerDPI": 300, "encodingFormat": "pdf"},
            "content": {"packages": [{"weight": 1}]},
        }
        response = await self._client.request_json("POST", "/shipments", json=payload)
        documents = response.get("documents") or []
        label_media_type = None
        label_content = None
        for document in documents:
            content = document.get("content")
            if content:
                label_media_type = document.get("mimeType") or "application/pdf"
                label_content = base64.b64decode(content)
                break
        tracking = response.get("trackingNumber") or response.get("shipmentTrackingNumber")
        provider_reference = response.get("shipmentReference") or tracking
        if not tracking or not provider_reference:
            raise ShipmentPhase4UnknownOutcomeError(
                "booking response missing provider identifiers"
            )
        booked_at = _utc_or_none(response.get("timestamp"))
        return AdapterBookingResult(
            provider_reference=str(provider_reference),
            tracking_number=str(tracking),
            label_media_type=label_media_type,
            label_content=label_content,
            service_code=response.get("productCode"),
            booked_at=booked_at,
        )

    async def track(self, tracking_number: str) -> Sequence[TrackingObservation]:
        response = await self._client.request_json(
            "GET",
            f"/shipments/{tracking_number}/tracking",
        )
        checkpoints = response.get("checkpoints") or response.get("events") or []
        observations: list[TrackingObservation] = []
        for checkpoint in checkpoints:
            code = str(checkpoint.get("statusCode") or checkpoint.get("code") or "UNKNOWN").strip().upper()
            detail = str(checkpoint.get("description") or checkpoint.get("detail") or code).strip()
            observed_at = _utc_or_none(
                checkpoint.get("timestamp") or checkpoint.get("dateTime") or response.get("timestamp")
            ) or datetime.now(UTC)
            outbound_state, customer_status = _map_tracking_status(code)
            observations.append(
                TrackingObservation(
                    provider_status_code=code,
                    outbound_state=outbound_state,
                    customer_status=customer_status,
                    detail=detail,
                    observed_at=observed_at,
                    exception_code=code if outbound_state == "exception" else None,
                )
            )
        if not observations:
            observations.append(
                TrackingObservation(
                    provider_status_code="BOOKED",
                    outbound_state="booked",
                    customer_status="label_created",
                    detail="Shipment booked with no downstream checkpoints yet",
                    observed_at=datetime.now(UTC),
                )
            )
        return observations


def create_shipment_adapter(settings: Settings) -> ShipmentAdapter:
    return DHLShipmentAdapter(settings)


def _setting_bool(settings: object, upper_name: str, lower_name: str) -> bool:
    if hasattr(settings, upper_name):
        return bool(getattr(settings, upper_name))
    if hasattr(settings, lower_name):
        return bool(getattr(settings, lower_name))
    return False


def _utc_or_none(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _normalize_text(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized or not normalized.isascii() or any(ch.isspace() for ch in normalized):
        raise ShipmentPhase4Error(f"invalid {field}")
    return normalized


def _map_tracking_status(code: str) -> tuple[str, str]:
    if code in {"PICKUP_CONFIRMED", "COLLECTED"}:
        return "collected", "picked_up"
    if code in {"DEPARTED", "IN_TRANSIT", "ARRIVED_AT_SORT"}:
        return "in_transit", "in_transit"
    if code in {"OUT_FOR_DELIVERY"}:
        return "out_for_delivery", "out_for_delivery"
    if code in {"DELIVERED"}:
        return "delivered", "delivered"
    if code in {"EXCEPTION", "HOLD", "RETURNED"}:
        return "exception", "delivery_exception"
    return "booked", "label_created"


async def _load_authoritative_subject(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    command: BookingCommand,
) -> tuple[Order, HubPackage, HubPackageSeal, OutboundShipmentIntent]:
    order = await db.get(Order, order_id)
    if order is None:
        raise ShipmentPhase4Error("order not found")
    package_handoff_exists = (
        select(CustodyEvent.id)
        .where(
            CustodyEvent.package_id == HubPackage.id,
            CustodyEvent.package_version == HubPackage.current_version,
            CustodyEvent.event_type.in_(("released", "tendered", "provider_accepted")),
        )
        .exists()
    )
    package = (
        await db.execute(
            select(HubPackage).where(
                HubPackage.id == command.package_id,
                HubPackage.order_id == order_id,
                HubPackage.state == "ready",
                HubPackage.current_version == command.package_version,
                ~package_handoff_exists,
            )
        )
    ).scalar_one_or_none()
    if package is None:
        raise ShipmentPhase4Error("selected ready package not found for order")
    seal = (
        await db.execute(
            select(HubPackageSeal).where(
                HubPackageSeal.id == command.seal_id,
                HubPackageSeal.package_id == package.id,
                HubPackageSeal.package_version == package.current_version,
                HubPackageSeal.retired_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if seal is None:
        raise ShipmentPhase4Error("no active bound seal")
    intent = (
        await db.execute(
            select(OutboundShipmentIntent).where(
                OutboundShipmentIntent.id == command.intent_id,
                OutboundShipmentIntent.order_id == order_id,
                OutboundShipmentIntent.package_id == package.id,
                OutboundShipmentIntent.package_version == package.current_version,
                OutboundShipmentIntent.seal_id == seal.id,
                ~select(OutboundShipmentIntentInvalidation.id)
                .where(OutboundShipmentIntentInvalidation.intent_id == OutboundShipmentIntent.id)
                .exists(),
            )
        )
    ).scalar_one_or_none()
    if intent is None:
        raise ShipmentPhase4Error("no authoritative outbound shipment intent")
    return order, package, seal, intent


async def book_outbound_shipment(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    admin: User,
    settings: Settings,
    command: BookingCommand,
    adapter: ShipmentAdapter | None = None,
) -> BookingResult:
    if not _setting_bool(settings, "DHL_DOMESTIC_WORKFLOW_ENABLED", "dhl_domestic_workflow_enabled"):
        raise ShipmentPhase4Error("dhl domestic workflow disabled")
    if not _setting_bool(settings, "DHL_DOMESTIC_PROVIDER_CALLS_ENABLED", "dhl_domestic_provider_calls_enabled"):
        raise ShipmentPhase4Error("dhl domestic provider calls disabled")

    order, package, seal, intent = await _load_authoritative_subject(db, order_id=order_id, command=command)
    command = BookingCommand(
        order_id=order_id,
        intent_id=intent.id,
        package_id=package.id,
        package_version=package.current_version,
        seal_id=seal.id,
        idempotency_key=_normalize_text(command.idempotency_key, field="idempotency_key"),
    )

    request_fingerprint = hashlib.sha256(
        f"{intent.id}:{package.id}:{package.current_version}:{seal.id}".encode("utf-8")
    ).hexdigest()

    existing = (
        await db.execute(
            select(OutboundShipmentBooking).where(
                OutboundShipmentBooking.provider == PROVIDER,
                OutboundShipmentBooking.environment == ENVIRONMENT,
                OutboundShipmentBooking.account_alias == ACCOUNT_ALIAS,
                OutboundShipmentBooking.idempotency_key == command.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if (
            existing.order_id != order.id
            or existing.intent_id != intent.id
            or existing.package_id != package.id
            or existing.package_version != package.current_version
            or existing.seal_id != seal.id
            or existing.request_fingerprint != request_fingerprint
        ):
            raise ShipmentPhase4ConflictError(
                "idempotency key is already bound to a different shipment subject"
            )
        return _booking_result(existing, replayed=True)

    guard = await db.get(OutboundIntentShipmentGuard, intent.id)
    if guard is None:
        guard = OutboundIntentShipmentGuard(intent_id=intent.id)
        db.add(guard)
        await db.flush()
    elif guard.booking_blocked_reason == "unknown_outcome":
        raise ShipmentPhase4ReconciliationRequiredError(
            "booking outcome is unknown; reconcile before retry"
        )
    elif guard.active_booking_id is not None:
        active = await db.get(OutboundShipmentBooking, guard.active_booking_id)
        if active is not None:
            raise ShipmentPhase4ConflictError(
                f"booking already exists for intent in state {active.outbound_state}"
            )

    now = await db.scalar(text("SELECT clock_timestamp()"))
    assert now is not None
    planned_ship_date = _planned_ship_date_for_shadow_quote(intent.created_at)
    booking = OutboundShipmentBooking(
        intent_id=intent.id,
        order_id=order.id,
        package_id=package.id,
        package_version=package.current_version,
        seal_id=seal.id,
        origin_hub_id=intent.origin_hub_id,
        provider=PROVIDER,
        environment=ENVIRONMENT,
        account_alias=ACCOUNT_ALIAS,
        initiating_actor_type="admin",
        initiating_actor_id=str(admin.id),
        source_command="admin_dhl_booking",
        idempotency_key=command.idempotency_key,
        request_fingerprint=request_fingerprint,
        fingerprint_key_version="shipment-fingerprint-v1",
        planned_ship_date=planned_ship_date,
        adapter_version=BOOKING_ADAPTER_VERSION,
        schema_version=BOOKING_SCHEMA_VERSION,
        canonicalization_version=CANONICALIZATION_VERSION,
        claimed_at=now,
        claim_expires_at=now + timedelta(seconds=CLAIM_TTL_SECONDS),
        classification="pending",
        outbound_state="intent_created",
    )
    db.add(booking)
    await db.flush()
    guard.active_booking_id = booking.id

    adapter = adapter or create_shipment_adapter(settings)
    try:
        called_at = await db.scalar(text("SELECT clock_timestamp()"))
        booking.call_started_at = called_at
        await db.flush()
        adapter_result = await adapter.book(intent, order)
    except (DHLConfigurationError,) as exc:
        raise ShipmentPhase4Error(str(exc)) from exc
    except (DHLAPIError, TimeoutError) as exc:
        completed_at = await db.scalar(text("SELECT clock_timestamp()"))
        booking.result_recorded_at = completed_at
        booking.classification = "unknown"
        booking.failure_code = "unknown_outcome"
        booking.completion_txid = await db.scalar(text("SELECT txid_current()"))
        guard.booking_blocked_reason = "unknown_outcome"
        await db.flush()
        return _booking_result(booking, replayed=False, note=str(exc))
    except ShipmentPhase4UnknownOutcomeError as exc:
        completed_at = await db.scalar(text("SELECT clock_timestamp()"))
        booking.result_recorded_at = completed_at
        booking.classification = "unknown"
        booking.failure_code = "unknown_outcome"
        booking.completion_txid = await db.scalar(text("SELECT txid_current()"))
        guard.booking_blocked_reason = "unknown_outcome"
        await db.flush()
        return _booking_result(booking, replayed=False, note=str(exc))
    except ShipmentPhase4Error:
        raise
    except Exception as exc:
        completed_at = await db.scalar(text("SELECT clock_timestamp()"))
        booking.result_recorded_at = completed_at
        booking.classification = "failure"
        booking.failure_code = "adapter_failure"
        booking.completion_txid = await db.scalar(text("SELECT txid_current()"))
        guard.active_booking_id = None
        await db.flush()
        raise ShipmentPhase4Error("booking failed") from exc

    completed_at = await db.scalar(text("SELECT clock_timestamp()"))
    booked_at = adapter_result.booked_at or completed_at
    booking.result_recorded_at = completed_at
    booking.classification = "success"
    booking.provider_reference = adapter_result.provider_reference.strip()
    booking.tracking_number = adapter_result.tracking_number.strip()
    booking.service_code = adapter_result.service_code
    booking.label_media_type = adapter_result.label_media_type
    booking.label_content = adapter_result.label_content
    booking.label_sha256 = (
        hashlib.sha256(adapter_result.label_content).hexdigest()
        if adapter_result.label_content is not None
        else None
    )
    booking.label_received_at = booked_at if adapter_result.label_content is not None else None
    booking.outbound_state = "label_ready" if adapter_result.label_content is not None else "booked"
    booking.completion_txid = await db.scalar(text("SELECT txid_current()"))
    booking.last_tracking_refresh_at = completed_at
    order.delivery_provider = PROVIDER
    order.tracking_number = booking.tracking_number
    guard.booking_blocked_reason = None
    await db.flush()
    return _booking_result(booking, replayed=False)


async def get_shipment_label(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    booking_id: uuid.UUID,
) -> ShipmentLabel:
    booking = await _load_booking_for_order(db, order_id=order_id, booking_id=booking_id)
    if booking.label_content is None or booking.label_media_type is None or booking.label_sha256 is None:
        raise ShipmentPhase4Error("label not available for booking")
    filename = f"dhl-label-{booking.tracking_number or booking.id}.pdf"
    return ShipmentLabel(
        booking_id=booking.id,
        media_type=booking.label_media_type,
        filename=filename,
        content=booking.label_content,
        sha256=booking.label_sha256,
    )


async def record_collection_handoff(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    admin: User,
    command: HandoffCommand,
) -> HandoffResult:
    booking = await _load_booking_for_order(db, order_id=order_id, booking_id=command.booking_id)
    if booking.classification != "success":
        raise ShipmentPhase4Error("cannot hand off a non-booked shipment")
    if booking.outbound_state not in {"label_ready", "awaiting_collection", "collected"}:
        raise ShipmentPhase4ConflictError(
            f"booking cannot accept handoff in state {booking.outbound_state}"
        )
    if booking.handoff_recorded_at is not None:
        existing_event = (
            await db.execute(
                select(CustodyEvent).where(
                    CustodyEvent.package_id == booking.package_id,
                    CustodyEvent.package_version == booking.package_version,
                    CustodyEvent.idempotency_key == command.idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing_event is None:
            raise ShipmentPhase4ConflictError("handoff already recorded")
        return HandoffResult(
            booking_id=booking.id,
            outbound_state=booking.outbound_state,
            occurred_at=existing_event.occurred_at,
            custody_event_id=existing_event.id,
        )
    cohort_id, vendor_id = await _cohort_ref_from_booking(db, booking)
    stream = (
        await db.execute(
            select(CustodyStream).where(
                CustodyStream.package_id == booking.package_id,
                CustodyStream.package_version == booking.package_version,
            )
        )
    ).scalar_one()
    tip = (
        await db.execute(
            select(CustodyEvent)
            .where(CustodyEvent.stream_id == stream.id)
            .order_by(CustodyEvent.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    custody = CustodyEvent(
        id=uuid.uuid4(),
        stream_id=stream.id,
        version=stream.next_version,
        previous_event_id=(tip.id if tip else None),
        cohort_id=cohort_id,
        order_id=order_id,
        vendor_id=vendor_id,
        hub_id=booking.origin_hub_id,
        event_type="provider_accepted",
        actor_type="user",
        actor_id=str(admin.id),
        source_system="admin_dhl_handoff",
        source_command="admin_dhl_handoff",
        occurred_at=command.occurred_at,
        recorded_at=max(command.occurred_at, datetime.now(UTC)),
        location="hub_dispatch",
        idempotency_key=_normalize_text(command.idempotency_key, field="idempotency_key"),
        counterparty=command.counterparty.strip(),
        evidence_ref=command.evidence_ref.strip(),
        evidence_hash=command.evidence_sha256.lower(),
        package_id=booking.package_id,
        package_version=booking.package_version,
        seal_id=booking.seal_id,
    )
    db.add(custody)  # single ORM insert (consolidated from duplicate construction)
    booking.collection_counterparty = custody.counterparty
    booking.collection_evidence_ref = custody.evidence_ref
    booking.collection_evidence_hash = custody.evidence_hash
    booking.collection_scheduled_at = booking.collection_scheduled_at or custody.occurred_at
    booking.handoff_recorded_at = custody.recorded_at
    booking.outbound_state = "collected"
    order = await db.get(Order, order_id)
    if order is not None:
        order.fulfillment_status = FulfillmentStatus.PICKED_UP
    await db.flush()
    return HandoffResult(
        booking_id=booking.id,
        outbound_state=booking.outbound_state,
        occurred_at=custody.occurred_at,
        custody_event_id=custody.id,
    )


async def refresh_tracking(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    settings: Settings,
    command: TrackingRefreshCommand,
    adapter: ShipmentAdapter | None = None,
) -> TrackingRefreshResult:
    if not _setting_bool(settings, "DHL_DOMESTIC_WORKFLOW_ENABLED", "dhl_domestic_workflow_enabled"):
        raise ShipmentPhase4Error("dhl domestic workflow disabled")
    if not _setting_bool(settings, "DHL_DOMESTIC_PROVIDER_CALLS_ENABLED", "dhl_domestic_provider_calls_enabled"):
        raise ShipmentPhase4Error("dhl domestic provider calls disabled")
    booking = await _load_booking_for_order(db, order_id=order_id, booking_id=command.booking_id)
    if booking.tracking_number is None:
        raise ShipmentPhase4Error("tracking number unavailable")
    adapter = adapter or create_shipment_adapter(settings)
    observations = await adapter.track(booking.tracking_number)
    if not observations:
        raise ShipmentPhase4Error("tracking adapter returned no observations")
    inserted = 0
    latest = observations[-1]
    for position, observation in enumerate(observations):
        snapshot = OutboundShipmentTrackingSnapshot(
            booking_id=booking.id,
            order_id=booking.order_id,
            provider=PROVIDER,
            tracking_number=booking.tracking_number,
            provider_status_code=observation.provider_status_code,
            outbound_state=observation.outbound_state,
            customer_status=observation.customer_status,
            detail=observation.detail,
            observed_at=observation.observed_at,
            exception_code=observation.exception_code,
            idempotency_key=f"{command.idempotency_key}:{position}",
            source_command="admin_dhl_tracking_refresh",
        )
        try:
            async with db.begin_nested():
                db.add(snapshot)
                await db.flush()
        except IntegrityError:
            continue
        inserted += 1
        latest = observation
    completed_at = await db.scalar(text("SELECT clock_timestamp()"))
    booking.last_tracking_refresh_at = completed_at
    booking.outbound_state = latest.outbound_state
    if latest.outbound_state == "exception":
        booking.latest_exception_code = latest.exception_code
    order = await db.get(Order, order_id)
    if order is not None:
        order.delivery_provider = PROVIDER
        order.tracking_number = booking.tracking_number
        if latest.outbound_state in {"collected", "in_transit", "out_for_delivery"}:
            order.fulfillment_status = FulfillmentStatus.IN_TRANSIT
        elif latest.outbound_state == "delivered":
            order.fulfillment_status = FulfillmentStatus.DELIVERED
            order.delivered_at = latest.observed_at
        elif latest.outbound_state == "exception":
            order.fulfillment_status = FulfillmentStatus.DELIVERY_FAILED
    await db.flush()
    return TrackingRefreshResult(
        booking_id=booking.id,
        tracking_number=booking.tracking_number,
        outbound_state=latest.outbound_state,
        customer_status=latest.customer_status,
        observations_recorded=inserted,
        refreshed_at=completed_at,
    )


async def _load_booking_for_order(db: AsyncSession, *, order_id: uuid.UUID, booking_id: uuid.UUID) -> OutboundShipmentBooking:
    booking = (
        await db.execute(
            select(OutboundShipmentBooking).where(
                OutboundShipmentBooking.id == booking_id,
                OutboundShipmentBooking.order_id == order_id,
            )
        )
    ).scalar_one_or_none()
    if booking is None:
        raise ShipmentPhase4Error("booking not found for order")
    return booking


async def _hub_ref_from_booking(db: AsyncSession, booking: OutboundShipmentBooking):
    from app.models.fulfillment_hub import FulfillmentHub
    from app.services.fulfillment.contracts import HubRef

    hub = await db.get(FulfillmentHub, booking.origin_hub_id)
    if hub is None:
        raise ShipmentPhase4Error("origin hub not found")
    return HubRef(id=hub.id)


async def _cohort_ref_from_booking(db: AsyncSession, booking: OutboundShipmentBooking) -> tuple[uuid.UUID, uuid.UUID]:
    from app.models.package_custody import HubPackageItem

    row = (
        await db.execute(
            select(HubPackageItem.cohort_id, HubPackageItem.vendor_id)
            .where(
                HubPackageItem.package_id == booking.package_id,
                HubPackageItem.package_version == booking.package_version,
            )
            .limit(1)
        )
    ).first()
    if row is None:
        raise ShipmentPhase4Error("package cohort not found")
    cohort_id, vendor_id = row
    return cohort_id, vendor_id


def _booking_result(booking: OutboundShipmentBooking, *, replayed: bool, note: str | None = None) -> BookingResult:
    return BookingResult(
        booking_id=booking.id,
        order_id=booking.order_id,
        intent_id=booking.intent_id,
        result_kind=("booked" if booking.classification == "success" else booking.classification),
        outbound_state=booking.outbound_state,
        provider_reference=booking.provider_reference,
        tracking_number=booking.tracking_number,
        label_media_type=booking.label_media_type,
        label_sha256=booking.label_sha256,
        booked_at=booking.result_recorded_at,
        note=note,
        replayed=replayed,
    )
