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
    OutboundShipmentTrackingRefresh,
    OutboundShipmentTrackingSnapshot,
)
from app.models.order import FulfillmentStatus, Order
from app.models.package_custody import (
    CustodyEvent,
    CustodyStream,
    HubPackage,
    HubPackageItem,
    HubPackageSeal,
    HubPackageVersion,
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
from app.models.fulfillment_hub import FulfillmentHub

PROVIDER = "dhl"
ENVIRONMENT = "sandbox"
ACCOUNT_ALIAS = "dhl-ng-sandbox"
MYDHL_TEST_BASE_URL = "https://express.api.dhl.com/mydhlapi/test"
BOOKING_ADAPTER_VERSION = "mydhl-shipments-v1"
BOOKING_SCHEMA_VERSION = "domestic-booking-v1"
TRACKING_SCHEMA_VERSION = "domestic-tracking-v1"
CANONICALIZATION_VERSION = "shipment-c14n-v1"
CLAIM_TTL_SECONDS = 300
NO_CHECKPOINTS_DETAIL = "Shipment booked with no downstream checkpoints yet"


class ShipmentPhase4Error(Exception):
    pass


class ShipmentPhase4ConflictError(ShipmentPhase4Error):
    pass


class ShipmentPhase4ReconciliationRequiredError(ShipmentPhase4ConflictError):
    pass


class ShipmentPhase4UnknownOutcomeError(ShipmentPhase4Error):
    pass


def _is_unique_constraint_violation(
    exc: IntegrityError,
    *,
    constraint_name: str | None = None,
) -> bool:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate != "23505":
        return False
    if constraint_name is None:
        return True
    diag = getattr(orig, "diag", None)
    if getattr(diag, "constraint_name", None) == constraint_name:
        return True
    return constraint_name in str(orig)


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
    async def book(
        self,
        intent: OutboundShipmentIntent,
        order: Order,
        hub: FulfillmentHub,
        package_version: HubPackageVersion,
    ) -> AdapterBookingResult: ...

    async def track(self, tracking_number: str) -> Sequence[TrackingObservation]: ...


class DHLShipmentAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = DHLClient(config=settings)

    async def book(
        self,
        intent: OutboundShipmentIntent,
        order: Order,
        hub: FulfillmentHub,
        package_version: HubPackageVersion,
    ) -> AdapterBookingResult:
        planned_ship_date = _planned_ship_date_for_shadow_quote(intent.created_at)
        payload = {
            "plannedShippingDateAndTime": _mydhl_planned_shipping_timestamp(planned_ship_date),
            "pickup": {"isRequested": False},
            "productCode": "N",
            "accounts": [{
                "typeCode": "shipper",
                "number": self._settings.DHL_EXPORT_ACCOUNT_NUMBER.get_secret_value(),
            }],
            "customerDetails": {
                "shipperDetails": {
                    "postalAddress": {
                        "countryCode": hub.country_code,
                        "postalCode": hub.postal_code,
                        "cityName": hub.city,
                        "provinceCode": hub.state,
                        "addressLine1": hub.address_line1,
                        "addressLine2": hub.address_line2,
                    },
                    "contactInformation": {
                        "fullName": hub.contact_name,
                        "phone": hub.contact_phone,
                    },
                },
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
            "content": {
                "packages": [{
                    "weight": float(package_version.weight_kg),
                    "dimensions": {
                        "length": float(package_version.length_cm),
                        "width": float(package_version.width_cm),
                        "height": float(package_version.height_cm),
                    },
                }]
            },
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
        checkpoints = _tracking_checkpoints(response)
        observations: list[TrackingObservation] = []
        for shipment, checkpoint in checkpoints:
            codes = [
                str(raw).strip().upper()
                for raw in (
                    checkpoint.get("typeCode"),
                    checkpoint.get("statusCode"),
                    checkpoint.get("code"),
                )
                if raw is not None and str(raw).strip()
            ]
            primary_code = codes[0] if codes else "UNKNOWN"
            detail = str(
                checkpoint.get("description")
                or checkpoint.get("detail")
                or checkpoint.get("remark")
                or primary_code
            ).strip()
            observed_at = _tracking_observed_at(
                checkpoint=checkpoint,
                shipment=shipment,
                response=response,
            ) or datetime.now(UTC)
            outbound_state, customer_status = _map_tracking_status(*codes)
            observations.append(
                TrackingObservation(
                    provider_status_code=primary_code,
                    outbound_state=outbound_state,
                    customer_status=customer_status,
                    detail=detail,
                    observed_at=observed_at,
                    exception_code=primary_code if outbound_state == "exception" else None,
                )
            )
        if not observations:
            observations.append(
                TrackingObservation(
                    provider_status_code="BOOKED",
                    outbound_state="booked",
                    customer_status="label_created",
                    detail=NO_CHECKPOINTS_DETAIL,
                    observed_at=datetime.now(UTC),
                )
            )
        return observations


def create_shipment_adapter(settings: Settings) -> ShipmentAdapter:
    try:
        return DHLShipmentAdapter(settings)
    except DHLConfigurationError as exc:
        raise ShipmentPhase4Error(str(exc)) from exc


def _setting_bool(settings: object, upper_name: str, lower_name: str) -> bool:
    if hasattr(settings, upper_name):
        return bool(getattr(settings, upper_name))
    if hasattr(settings, lower_name):
        return bool(getattr(settings, lower_name))
    return False


def _cohort_allowlist(settings: Settings) -> frozenset[uuid.UUID]:
    return settings.dhl_domestic_sandbox_cohort_ids


def _mydhl_planned_shipping_timestamp(planned_ship_date: date) -> str:
    return f"{planned_ship_date.isoformat()}T12:00:00GMT+01:00"


def _derived_handoff_idempotency_key(base_key: str, suffix: str) -> str:
    candidate = f"{base_key}{suffix}"
    if len(candidate) <= 200:
        return candidate
    digest = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    prefix_budget = 200 - len(suffix) - 1 - len(digest)
    return f"{base_key[:prefix_budget]}:{digest}{suffix}"


def _state_rank(outbound_state: str) -> int:
    order = {
        "intent_created": 0,
        "booked": 1,
        "label_ready": 2,
        "awaiting_collection": 3,
        "collected": 4,
        "in_transit": 5,
        "out_for_delivery": 6,
        "delivered": 7,
    }
    return order.get(outbound_state, -1)


def _is_placeholder_booked_observation(observation: TrackingObservation) -> bool:
    return (
        observation.provider_status_code == "BOOKED"
        and observation.outbound_state == "booked"
        and observation.customer_status == "label_created"
        and observation.detail == NO_CHECKPOINTS_DETAIL
    )


def _customer_status_for_outbound_state(outbound_state: str, *, fallback: str) -> str:
    return {
        "intent_created": "label_created",
        "booked": "label_created",
        "label_ready": "label_created",
        "awaiting_collection": "label_created",
        "collected": "picked_up",
        "in_transit": "in_transit",
        "out_for_delivery": "out_for_delivery",
        "delivered": "delivered",
        "exception": "delivery_exception",
    }.get(outbound_state, fallback)


def _aggregate_order_shipment_state(states: Sequence[str]) -> str | None:
    active_states = [state for state in states if state and state != "cancelled"]
    if not active_states:
        return None
    if any(state == "exception" for state in active_states):
        return "exception"
    if all(state == "delivered" for state in active_states):
        return "delivered"
    if all(state in {"delivered", "out_for_delivery"} for state in active_states):
        return "out_for_delivery"
    if any(
        state in {"collected", "in_transit", "out_for_delivery", "delivered"}
        for state in active_states
    ):
        return "in_transit"
    return "booked"


async def _aggregate_order_outbound_state(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    fallback: str,
) -> str:
    packages = (
        await db.execute(
            select(HubPackage.id, HubPackage.current_version).where(
                HubPackage.order_id == order_id
            )
        )
    ).all()
    if not packages:
        return fallback

    bookings = (
        await db.execute(
            select(OutboundShipmentBooking)
            .where(
                OutboundShipmentBooking.order_id == order_id,
                OutboundShipmentBooking.classification == "success",
            )
            .order_by(
                OutboundShipmentBooking.package_id,
                OutboundShipmentBooking.package_version,
                OutboundShipmentBooking.result_recorded_at.desc(),
                OutboundShipmentBooking.created_at.desc(),
            )
        )
    ).scalars().all()
    latest_by_package: dict[tuple[uuid.UUID, int], str] = {
        (package_id, current_version): "booked"
        for package_id, current_version in packages
    }
    for candidate in bookings:
        key = (candidate.package_id, candidate.package_version)
        if key not in latest_by_package or candidate.outbound_state == "cancelled":
            continue
        if latest_by_package[key] != "booked":
            continue
        latest_by_package[key] = candidate.outbound_state
    aggregate_state = _aggregate_order_shipment_state(list(latest_by_package.values()))
    return aggregate_state or fallback


async def _project_order_tracking_number(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    fallback: str | None,
) -> str | None:
    packages = (
        await db.execute(
            select(HubPackage.id, HubPackage.current_version).where(
                HubPackage.order_id == order_id
            )
        )
    ).all()
    if not packages:
        return fallback

    bookings = (
        await db.execute(
            select(OutboundShipmentBooking)
            .where(
                OutboundShipmentBooking.order_id == order_id,
                OutboundShipmentBooking.classification == "success",
            )
            .order_by(
                OutboundShipmentBooking.package_id,
                OutboundShipmentBooking.package_version,
                OutboundShipmentBooking.result_recorded_at.desc(),
                OutboundShipmentBooking.created_at.desc(),
            )
        )
    ).scalars().all()
    latest_by_package: dict[tuple[uuid.UUID, int], str] = {}
    for candidate in bookings:
        key = (candidate.package_id, candidate.package_version)
        if key not in {(package_id, current_version) for package_id, current_version in packages}:
            continue
        if key in latest_by_package or candidate.outbound_state == "cancelled":
            continue
        tracking_number = candidate.tracking_number.strip() if candidate.tracking_number else None
        if tracking_number:
            latest_by_package[key] = tracking_number
    if not latest_by_package:
        return fallback

    projected: list[str] = []
    for tracking_number in latest_by_package.values():
        if tracking_number not in projected:
            projected.append(tracking_number)
    summary = ", ".join(projected)
    return summary if len(summary) <= 100 else fallback


def _ensure_sandbox_booking_allowed(
    settings: Settings,
    *,
    cohort_ids: frozenset[uuid.UUID],
) -> None:
    if settings.DHL_ENVIRONMENT != "sandbox":
        raise ShipmentPhase4Error("sandbox adapter requires DHL_ENVIRONMENT=sandbox")
    if settings.dhl_base_url != MYDHL_TEST_BASE_URL:
        raise ShipmentPhase4Error("sandbox adapter requires fixed MyDHL test base URL")
    allowed = _cohort_allowlist(settings)
    if not allowed:
        raise ShipmentPhase4Error("sandbox adapter requires restricted cohort set")
    if not cohort_ids <= allowed:
        raise ShipmentPhase4Error("package composition is outside sandbox cohort allowlist")


async def _package_cohort_ids(
    db: AsyncSession,
    *,
    package_id: uuid.UUID,
    package_version: int,
) -> frozenset[uuid.UUID]:
    rows = (
        await db.execute(
            select(HubPackageItem.cohort_id).where(
                HubPackageItem.package_id == package_id,
                HubPackageItem.package_version == package_version,
            )
        )
    ).scalars().all()
    return frozenset(rows)


async def _matching_replay(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    command: BookingCommand,
) -> OutboundShipmentBooking | None:
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
    if existing is None:
        return None
    if (
        existing.order_id != order_id
        or existing.intent_id != command.intent_id
        or existing.package_id != command.package_id
        or existing.package_version != command.package_version
        or existing.seal_id != command.seal_id
    ):
        raise ShipmentPhase4ConflictError(
            "idempotency key is already bound to a different shipment subject"
        )
    return existing


async def _reconcile_or_release_expired_claim(
    db: AsyncSession,
    *,
    guard: OutboundIntentShipmentGuard,
) -> None:
    if guard.active_booking_id is None:
        return
    active = await db.get(OutboundShipmentBooking, guard.active_booking_id)
    if active is None:
        guard.active_booking_id = None
        guard.booking_blocked_reason = None
        await db.flush()
        return
    now = await db.scalar(text("SELECT clock_timestamp()"))
    assert now is not None
    if active.claim_expires_at > now or active.classification != "pending":
        return
    if active.call_started_at is None:
        active.classification = "failure"
        active.failure_code = "claim_expired"
        active.call_started_at = active.claimed_at
        active.result_recorded_at = now
        active.completion_txid = await db.scalar(text("SELECT txid_current()"))
        guard.active_booking_id = None
        guard.booking_blocked_reason = None
    else:
        active.classification = "unknown"
        active.failure_code = "unknown_outcome"
        active.result_recorded_at = now
        active.completion_txid = await db.scalar(text("SELECT txid_current()"))
        guard.booking_blocked_reason = "unknown_outcome"
    await db.flush()


async def _matching_tracking_replay(
    db: AsyncSession,
    *,
    booking: OutboundShipmentBooking,
    idempotency_key: str,
) -> TrackingRefreshResult | None:
    refresh = (
        await db.execute(
            select(OutboundShipmentTrackingRefresh).where(
                OutboundShipmentTrackingRefresh.booking_id == booking.id,
                OutboundShipmentTrackingRefresh.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if refresh is None:
        return None
    return TrackingRefreshResult(
        booking_id=booking.id,
        tracking_number=refresh.tracking_number,
        outbound_state=refresh.outbound_state,
        customer_status=refresh.customer_status,
        observations_recorded=refresh.observations_recorded,
        refreshed_at=refresh.refreshed_at,
    )


async def _load_order(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    lock_for_update: bool = False,
) -> Order:
    query = select(Order).where(Order.id == order_id)
    if lock_for_update:
        query = query.with_for_update()
    order = (await db.execute(query)).scalar_one_or_none()
    if order is None:
        raise ShipmentPhase4Error("order not found")
    return order


def _ensure_order_not_cancelled(order: Order, *, action: str) -> None:
    if order.fulfillment_status == FulfillmentStatus.CANCELLED:
        raise ShipmentPhase4ConflictError(f"cannot {action} for cancelled order")


async def _matching_handoff_replay(
    db: AsyncSession,
    *,
    booking: OutboundShipmentBooking,
    command: HandoffCommand,
    normalized_idempotency: str,
) -> HandoffResult | None:
    existing_events = (
        await db.execute(
            select(CustodyEvent)
            .join(CustodyStream, CustodyStream.id == CustodyEvent.stream_id)
            .where(
                CustodyEvent.package_id == booking.package_id,
                CustodyEvent.package_version == booking.package_version,
                CustodyEvent.idempotency_key == normalized_idempotency,
            )
            .order_by(
                CustodyStream.cohort_id,
                CustodyStream.vendor_id,
                CustodyStream.id,
                CustodyEvent.version,
                CustodyEvent.id,
            )
        )
    ).scalars().all()
    if not existing_events:
        return None
    existing_event = existing_events[0]
    normalized_counterparty = command.counterparty.strip()
    if (
        booking.collection_scheduled_at != command.occurred_at
        or booking.collection_counterparty != normalized_counterparty
        or booking.collection_evidence_ref != command.evidence_ref.strip()
        or booking.collection_evidence_hash != command.evidence_sha256.lower()
    ):
        raise ShipmentPhase4ConflictError(
            "handoff idempotency key is already bound to different evidence"
        )
    return HandoffResult(
        booking_id=booking.id,
        outbound_state="collected",
        occurred_at=existing_event.occurred_at,
        custody_event_id=existing_event.id,
    )


async def _verified_carrier_acceptance_snapshot(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
) -> OutboundShipmentTrackingSnapshot:
    snapshot = (
        await db.execute(
            select(OutboundShipmentTrackingSnapshot)
            .where(
                OutboundShipmentTrackingSnapshot.booking_id == booking_id,
                OutboundShipmentTrackingSnapshot.provider == PROVIDER,
                OutboundShipmentTrackingSnapshot.outbound_state.in_(
                    ("collected", "in_transit", "out_for_delivery", "delivered")
                ),
            )
            .order_by(
                OutboundShipmentTrackingSnapshot.observed_at.asc(),
                OutboundShipmentTrackingSnapshot.id.asc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise ShipmentPhase4ConflictError(
            "verified DHL collection event required before carrier acceptance handoff"
        )
    return snapshot


async def _latest_tracking_snapshot_for_state(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
    outbound_state: str,
) -> OutboundShipmentTrackingSnapshot | None:
    return (
        await db.execute(
            select(OutboundShipmentTrackingSnapshot)
            .where(
                OutboundShipmentTrackingSnapshot.booking_id == booking_id,
                OutboundShipmentTrackingSnapshot.provider == PROVIDER,
                OutboundShipmentTrackingSnapshot.outbound_state == outbound_state,
            )
            .order_by(
                OutboundShipmentTrackingSnapshot.observed_at.desc(),
                OutboundShipmentTrackingSnapshot.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


def _utc_or_none(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _tracking_checkpoints(response: dict[str, object]) -> list[tuple[dict[str, object], dict[str, object]]]:
    shipments = response.get("shipments")
    if isinstance(shipments, list):
        nested: list[tuple[dict[str, object], dict[str, object]]] = []
        for shipment in shipments:
            if not isinstance(shipment, dict):
                continue
            events = shipment.get("events") or shipment.get("checkpoints") or []
            if not isinstance(events, list):
                continue
            for checkpoint in events:
                if isinstance(checkpoint, dict):
                    nested.append((shipment, checkpoint))
        if nested:
            return nested
    checkpoints = response.get("checkpoints") or response.get("events") or []
    if not isinstance(checkpoints, list):
        return []
    return [({}, checkpoint) for checkpoint in checkpoints if isinstance(checkpoint, dict)]


def _tracking_observed_at(
    *,
    checkpoint: dict[str, object],
    shipment: dict[str, object],
    response: dict[str, object],
) -> datetime | None:
    date_value = checkpoint.get("date")
    time_value = checkpoint.get("time")
    combined_datetime = None
    if date_value and time_value:
        combined_datetime = f"{str(date_value).strip()}T{str(time_value).strip()}"
    elif date_value:
        combined_datetime = f"{str(date_value).strip()}T00:00:00"
    for candidate in (
        checkpoint.get("timestamp"),
        checkpoint.get("dateTime"),
        combined_datetime,
        shipment.get("timestamp"),
        response.get("timestamp"),
    ):
        parsed = _utc_or_none(candidate)
        if parsed is not None:
            return parsed
    return None


def _normalize_text(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized or not normalized.isascii() or any(ch.isspace() for ch in normalized):
        raise ShipmentPhase4Error(f"invalid {field}")
    return normalized


def _map_tracking_status(*codes: str) -> tuple[str, str]:
    normalized_codes = {
        code.strip().upper()
        for code in codes
        if code is not None and code.strip()
    }
    if normalized_codes & {"PU", "PICKUP_CONFIRMED", "COLLECTED"}:
        return "collected", "picked_up"
    if normalized_codes & {"OK", "DELIVERED"}:
        return "delivered", "delivered"
    if normalized_codes & {"OOD", "OUT_FOR_DELIVERY"}:
        return "out_for_delivery", "out_for_delivery"
    if normalized_codes & {"DEPARTED", "IN_TRANSIT", "ARRIVED_AT_SORT", "TRANSIT"}:
        return "in_transit", "in_transit"
    if normalized_codes & {"EXCEPTION", "HOLD", "RETURNED", "FAILURE"}:
        return "exception", "delivery_exception"
    return "booked", "label_created"


async def _load_authoritative_subject(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    command: BookingCommand,
) -> tuple[Order, HubPackage, HubPackageSeal, OutboundShipmentIntent, HubPackageVersion, frozenset[uuid.UUID]]:
    order = await _load_order(db, order_id=order_id, lock_for_update=True)
    _ensure_order_not_cancelled(order, action="book shipment")
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
    package_version = (
        await db.execute(
            select(HubPackageVersion).where(
                HubPackageVersion.package_id == package.id,
                HubPackageVersion.version == package.current_version,
            )
        )
    ).scalar_one_or_none()
    if package_version is None:
        raise ShipmentPhase4Error("missing package version measurement")
    package_items = (
        await db.execute(
            select(HubPackageItem).where(
                HubPackageItem.package_id == package.id,
                HubPackageItem.package_version == package.current_version,
            )
        )
    ).scalars().all()
    if not package_items:
        raise ShipmentPhase4Error("ready package has no package items")
    return order, package, seal, intent, package_version, frozenset(item.cohort_id for item in package_items)


async def book_outbound_shipment(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    admin: User,
    settings: Settings,
    command: BookingCommand,
    adapter: ShipmentAdapter | None = None,
) -> BookingResult:
    command = BookingCommand(
        order_id=order_id,
        intent_id=command.intent_id,
        package_id=command.package_id,
        package_version=command.package_version,
        seal_id=command.seal_id,
        idempotency_key=_normalize_text(command.idempotency_key, field="idempotency_key"),
    )
    replay = await _matching_replay(db, order_id=order_id, command=command)
    if replay is not None:
        now = await db.scalar(text("SELECT clock_timestamp()"))
        assert now is not None
        if not (replay.classification == "pending" and replay.claim_expires_at <= now):
            return _booking_result(replay, replayed=True)

    order, package, seal, intent, package_version, cohort_ids = await _load_authoritative_subject(db, order_id=order_id, command=command)

    request_fingerprint = hashlib.sha256(
        f"{intent.id}:{package.id}:{package.current_version}:{seal.id}".encode("utf-8")
    ).hexdigest()

    guard = (
        await db.execute(
            select(OutboundIntentShipmentGuard)
            .where(OutboundIntentShipmentGuard.intent_id == intent.id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if guard is None:
        try:
            async with db.begin_nested():
                guard = OutboundIntentShipmentGuard(intent_id=intent.id)
                db.add(guard)
                await db.flush()
        except IntegrityError as exc:
            if not _is_unique_constraint_violation(exc):
                raise
            guard = (
                await db.execute(
                    select(OutboundIntentShipmentGuard)
                    .where(OutboundIntentShipmentGuard.intent_id == intent.id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if guard is None:
                raise
        else:
            guard = (
                await db.execute(
                    select(OutboundIntentShipmentGuard)
                    .where(OutboundIntentShipmentGuard.intent_id == intent.id)
                    .with_for_update()
                )
            ).scalar_one()
    await _reconcile_or_release_expired_claim(db, guard=guard)
    replay = await _matching_replay(db, order_id=order_id, command=command)
    if replay is not None:
        return _booking_result(replay, replayed=True)
    if guard.booking_blocked_reason == "unknown_outcome":
        raise ShipmentPhase4ReconciliationRequiredError(
            "booking outcome is unknown; reconcile before retry"
        )
    if guard.active_booking_id is not None:
        active = await db.get(OutboundShipmentBooking, guard.active_booking_id)
        if active is not None:
            raise ShipmentPhase4ConflictError(
                f"booking already exists for intent in state {active.outbound_state}"
            )

    if not _setting_bool(settings, "DHL_DOMESTIC_WORKFLOW_ENABLED", "dhl_domestic_workflow_enabled"):
        raise ShipmentPhase4Error("dhl domestic workflow disabled")
    if not _setting_bool(settings, "DHL_DOMESTIC_PROVIDER_CALLS_ENABLED", "dhl_domestic_provider_calls_enabled"):
        raise ShipmentPhase4Error("dhl domestic provider calls disabled")
    _ensure_sandbox_booking_allowed(settings, cohort_ids=cohort_ids)
    hub = await db.get(FulfillmentHub, intent.origin_hub_id)
    if hub is None:
        raise ShipmentPhase4Error("origin hub not found")
    adapter = adapter or create_shipment_adapter(settings)

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
    await db.commit()

    booking = await db.get(OutboundShipmentBooking, booking.id)
    guard = await db.get(OutboundIntentShipmentGuard, intent.id)
    assert booking is not None and guard is not None

    try:
        order = await _load_order(db, order_id=order_id, lock_for_update=True)
        _ensure_order_not_cancelled(order, action="book shipment")
        called_at = await db.scalar(text("SELECT clock_timestamp()"))
        booking.call_started_at = called_at
        await db.flush()
        adapter_result = await adapter.book(intent, order, hub, package_version)
    except (DHLAPIError, TimeoutError) as exc:
        completed_at = await db.scalar(text("SELECT clock_timestamp()"))
        booking.result_recorded_at = completed_at
        definitive_rejection = isinstance(exc, DHLAPIError) and (
            exc.status_code in {400, 401, 403}
        )
        booking.classification = "failure" if definitive_rejection else "unknown"
        booking.failure_code = (
            f"provider_rejected_{exc.status_code}"
            if definitive_rejection and isinstance(exc, DHLAPIError) and exc.status_code is not None
            else "unknown_outcome"
        )
        booking.completion_txid = await db.scalar(text("SELECT txid_current()"))
        guard.active_booking_id = None if definitive_rejection else guard.active_booking_id
        guard.booking_blocked_reason = None if definitive_rejection else "unknown_outcome"
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
        booking.classification = "unknown"
        booking.failure_code = "unknown_outcome"
        booking.completion_txid = await db.scalar(text("SELECT txid_current()"))
        guard.booking_blocked_reason = "unknown_outcome"
        await db.flush()
        return _booking_result(booking, replayed=False, note=str(exc))

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
    order.tracking_number = await _project_order_tracking_number(
        db,
        order_id=order.id,
        fallback=booking.tracking_number,
    )
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
    booking = await _load_booking_for_order(
        db,
        order_id=order_id,
        booking_id=command.booking_id,
        lock_for_update=True,
    )
    normalized_idempotency = _normalize_text(command.idempotency_key, field="idempotency_key")
    replay = await _matching_handoff_replay(
        db,
        booking=booking,
        command=command,
        normalized_idempotency=normalized_idempotency,
    )
    if replay is not None:
        return replay
    if booking.classification != "success":
        raise ShipmentPhase4Error("cannot hand off a non-booked shipment")
    if booking.outbound_state not in {"label_ready", "awaiting_collection", "collected"}:
        raise ShipmentPhase4ConflictError(
            f"booking cannot accept handoff in state {booking.outbound_state}"
        )
    if booking.handoff_recorded_at is not None:
        raise ShipmentPhase4ConflictError("handoff already recorded")
    order = await _load_order(db, order_id=order_id, lock_for_update=True)
    _ensure_order_not_cancelled(order, action="record handoff")
    database_now = await db.scalar(text("SELECT clock_timestamp()"))
    if command.occurred_at > database_now:
        raise ShipmentPhase4ConflictError("handoff occurred_at cannot be in the future")
    recorded_at = max(command.occurred_at, database_now)
    verified_acceptance = await _verified_carrier_acceptance_snapshot(
        db,
        booking_id=booking.id,
    )
    verified_acceptance_now = await db.scalar(text("SELECT clock_timestamp()"))
    assert verified_acceptance_now is not None
    if verified_acceptance.observed_at > verified_acceptance_now:
        raise ShipmentPhase4ConflictError(
            "verified carrier acceptance cannot be in the future"
        )
    tendered_idempotency_key = _derived_handoff_idempotency_key(
        normalized_idempotency,
        ":tendered",
    )
    streams = (
        await db.execute(
            select(CustodyStream)
            .where(
                CustodyStream.package_id == booking.package_id,
                CustodyStream.package_version == booking.package_version,
            )
            .order_by(CustodyStream.cohort_id, CustodyStream.vendor_id)
        )
    ).scalars().all()
    if not streams:
        raise ShipmentPhase4ConflictError("package custody streams not found")
    returned_event: CustodyEvent | None = None
    for stream in streams:
        tip = (
            await db.execute(
                select(CustodyEvent)
                .where(CustodyEvent.stream_id == stream.id)
                .order_by(CustodyEvent.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if tip is None:
            raise ShipmentPhase4ConflictError("custody stream has no releasable lifecycle tip")
        if command.occurred_at < tip.occurred_at:
            raise ShipmentPhase4ConflictError(
                "handoff occurred_at precedes current custody state"
            )
        previous = tip
        next_version = stream.next_version
        if tip.event_type == "released":
            if verified_acceptance.observed_at < tip.occurred_at:
                raise ShipmentPhase4ConflictError(
                    "verified carrier acceptance precedes current custody state"
                )
            tendered_occurred_at = max(
                min(command.occurred_at, verified_acceptance.observed_at),
                previous.occurred_at + timedelta(microseconds=1),
            )
            tendered_recorded_now = await db.scalar(text("SELECT clock_timestamp()"))
            assert tendered_recorded_now is not None
            tendered_recorded_at = max(
                tendered_occurred_at,
                previous.recorded_at,
                recorded_at,
                tendered_recorded_now,
            )
            tendered = CustodyEvent(
                id=uuid.uuid4(),
                stream_id=stream.id,
                version=next_version,
                previous_event_id=previous.id,
                cohort_id=stream.cohort_id,
                order_id=order_id,
                vendor_id=stream.vendor_id,
                hub_id=booking.origin_hub_id,
                event_type="tendered",
                actor_type="user",
                actor_id=str(admin.id),
                source_system="admin_dhl_handoff",
                source_command="admin_dhl_handoff",
                occurred_at=tendered_occurred_at,
                recorded_at=tendered_recorded_at,
                location="hub_dispatch",
                idempotency_key=tendered_idempotency_key,
                counterparty=command.counterparty.strip(),
                evidence_ref=command.evidence_ref.strip(),
                evidence_hash=command.evidence_sha256.lower(),
                package_id=booking.package_id,
                package_version=booking.package_version,
                seal_id=booking.seal_id,
            )
            db.add(tendered)
            await db.flush()
            previous = tendered
            next_version += 1
        elif tip.event_type != "tendered":
            raise ShipmentPhase4ConflictError(
                f"booking cannot accept handoff from custody state {tip.event_type}"
            )

        provider_accepted_occurred_at = max(
            verified_acceptance.observed_at,
            previous.occurred_at + timedelta(microseconds=1),
        )
        provider_accepted_recorded_now = await db.scalar(text("SELECT clock_timestamp()"))
        assert provider_accepted_recorded_now is not None
        provider_accepted_recorded_at = max(
            provider_accepted_occurred_at,
            previous.recorded_at,
            provider_accepted_recorded_now,
        )
        custody = CustodyEvent(
            id=uuid.uuid4(),
            stream_id=stream.id,
            version=next_version,
            previous_event_id=previous.id,
            cohort_id=stream.cohort_id,
            order_id=order_id,
            vendor_id=stream.vendor_id,
            hub_id=booking.origin_hub_id,
            event_type="provider_accepted",
            actor_type="carrier",
            actor_id=PROVIDER,
            source_system="admin_dhl_handoff",
            source_command="admin_dhl_handoff",
            occurred_at=provider_accepted_occurred_at,
            recorded_at=provider_accepted_recorded_at,
            location="hub_dispatch",
            idempotency_key=normalized_idempotency,
            counterparty=command.counterparty.strip(),
            evidence_ref=command.evidence_ref.strip(),
            evidence_hash=command.evidence_sha256.lower(),
            package_id=booking.package_id,
            package_version=booking.package_version,
            seal_id=booking.seal_id,
        )
        db.add(custody)
        returned_event = returned_event or custody
    assert returned_event is not None
    booking.collection_counterparty = returned_event.counterparty
    booking.collection_evidence_ref = returned_event.evidence_ref
    booking.collection_evidence_hash = returned_event.evidence_hash
    booking.collection_scheduled_at = command.occurred_at
    booking.handoff_recorded_at = max(recorded_at, returned_event.recorded_at)
    booking.outbound_state = "collected"
    order.fulfillment_status = FulfillmentStatus.PICKED_UP
    await db.flush()
    return HandoffResult(
        booking_id=booking.id,
        outbound_state=booking.outbound_state,
        occurred_at=returned_event.occurred_at,
        custody_event_id=returned_event.id,
    )


async def refresh_tracking(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    settings: Settings,
    command: TrackingRefreshCommand,
    adapter: ShipmentAdapter | None = None,
) -> TrackingRefreshResult:
    booking = await _load_booking_for_order(
        db,
        order_id=order_id,
        booking_id=command.booking_id,
        lock_for_update=True,
    )
    if booking.tracking_number is None:
        raise ShipmentPhase4Error("tracking number unavailable")
    normalized_idempotency = _normalize_text(command.idempotency_key, field="idempotency_key")
    replay = await _matching_tracking_replay(
        db,
        booking=booking,
        idempotency_key=normalized_idempotency,
    )
    if replay is not None:
        return replay
    if not _setting_bool(settings, "DHL_DOMESTIC_WORKFLOW_ENABLED", "dhl_domestic_workflow_enabled"):
        raise ShipmentPhase4Error("dhl domestic workflow disabled")
    cohort_ids = await _package_cohort_ids(
        db,
        package_id=booking.package_id,
        package_version=booking.package_version,
    )
    _ensure_sandbox_booking_allowed(settings, cohort_ids=cohort_ids)
    adapter = adapter or create_shipment_adapter(settings)
    try:
        observations = await adapter.track(booking.tracking_number)
    except (DHLAPIError, TimeoutError) as exc:
        raise ShipmentPhase4Error(str(exc)) from exc
    if not observations:
        raise ShipmentPhase4Error("tracking adapter returned no observations")
    inserted = 0
    latest = observations[-1]
    try:
        async with db.begin_nested():
            for position, observation in enumerate(observations):
                derived_idempotency_key = _derived_handoff_idempotency_key(
                    normalized_idempotency,
                    f":{position}",
                )
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
                    idempotency_key=derived_idempotency_key,
                    source_command="admin_dhl_tracking_refresh",
                )
                try:
                    async with db.begin_nested():
                        db.add(snapshot)
                        await db.flush()
                except IntegrityError as exc:
                    if not _is_unique_constraint_violation(
                        exc,
                        constraint_name="uq_outbound_shipment_tracking_snapshots_observation",
                    ):
                        raise
                    continue
                inserted += 1
            booking = await _load_booking_for_order(
                db,
                order_id=order_id,
                booking_id=command.booking_id,
                lock_for_update=True,
            )
            allow_carrier_movement = booking.handoff_recorded_at is not None
            current_state = booking.outbound_state
            current_state_snapshot = await _latest_tracking_snapshot_for_state(
                db,
                booking_id=booking.id,
                outbound_state=current_state,
            )
            current_state_observed_at = (
                current_state_snapshot.observed_at if current_state_snapshot is not None else None
            )
            completed_at = await db.scalar(text("SELECT clock_timestamp()"))
            booking.last_tracking_refresh_at = completed_at
            effective_state = current_state
            if allow_carrier_movement:
                if latest.outbound_state == "exception":
                    if current_state not in {"delivered", "cancelled"} and (
                        current_state_snapshot is None
                        or latest.observed_at >= current_state_snapshot.observed_at
                    ):
                        effective_state = "exception"
                elif current_state == "exception":
                    if latest.outbound_state in {
                        "collected",
                        "in_transit",
                        "out_for_delivery",
                        "delivered",
                        "cancelled",
                    } and not _is_placeholder_booked_observation(latest) and (
                        current_state_observed_at is None
                        or latest.observed_at >= current_state_observed_at
                    ):
                        effective_state = latest.outbound_state
                elif current_state != "cancelled" and (
                    _state_rank(latest.outbound_state) >= _state_rank(current_state)
                    and (
                        current_state_observed_at is None
                        or latest.observed_at >= current_state_observed_at
                    )
                ):
                    effective_state = latest.outbound_state
            else:
                if latest.outbound_state in {"booked", "label_ready", "awaiting_collection"}:
                    if _state_rank(latest.outbound_state) >= _state_rank(current_state):
                        effective_state = latest.outbound_state
            booking.outbound_state = effective_state
            if effective_state == "exception" and latest.outbound_state == "exception":
                booking.latest_exception_code = latest.exception_code
            effective_customer_status = _customer_status_for_outbound_state(
                effective_state,
                fallback=latest.customer_status,
            )
            aggregate_state = await _aggregate_order_outbound_state(
                db,
                order_id=booking.order_id,
                fallback=effective_state,
            )
            aggregate_tracking_number = await _project_order_tracking_number(
                db,
                order_id=booking.order_id,
                fallback=booking.tracking_number,
            )
            order = await _load_order(db, order_id=order_id, lock_for_update=True)
            if order is not None:
                order.delivery_provider = PROVIDER
                order.tracking_number = aggregate_tracking_number
                if order.fulfillment_status != FulfillmentStatus.CANCELLED:
                    if allow_carrier_movement and aggregate_state in {"collected", "in_transit"}:
                        order.fulfillment_status = FulfillmentStatus.IN_TRANSIT
                    elif allow_carrier_movement and aggregate_state == "out_for_delivery":
                        order.fulfillment_status = FulfillmentStatus.OUT_FOR_DELIVERY
                    elif allow_carrier_movement and aggregate_state == "delivered":
                        order.fulfillment_status = FulfillmentStatus.DELIVERED
                        if latest.outbound_state == "delivered" and (
                            current_state != "delivered" or order.delivered_at is None
                        ):
                            order.delivered_at = latest.observed_at
                    elif aggregate_state == "exception":
                        order.fulfillment_status = FulfillmentStatus.DELIVERY_FAILED
            refresh = OutboundShipmentTrackingRefresh(
                booking_id=booking.id,
                order_id=booking.order_id,
                provider=PROVIDER,
                tracking_number=booking.tracking_number,
                outbound_state=booking.outbound_state,
                customer_status=effective_customer_status,
                observations_recorded=inserted,
                refreshed_at=completed_at,
                idempotency_key=normalized_idempotency,
                source_command="admin_dhl_tracking_refresh",
            )
            db.add(refresh)
            await db.flush()
    except IntegrityError as exc:
        if not _is_unique_constraint_violation(
            exc,
            constraint_name="uq_outbound_shipment_tracking_refreshes_replay",
        ):
            raise
        replay = await _matching_tracking_replay(
            db,
            booking=booking,
            idempotency_key=normalized_idempotency,
        )
        if replay is not None:
            return replay
        raise
    return TrackingRefreshResult(
        booking_id=booking.id,
        tracking_number=booking.tracking_number,
        outbound_state=booking.outbound_state,
        customer_status=effective_customer_status,
        observations_recorded=inserted,
        refreshed_at=completed_at,
    )


async def _load_booking_for_order(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    booking_id: uuid.UUID,
    lock_for_update: bool = False,
) -> OutboundShipmentBooking:
    query = select(OutboundShipmentBooking).where(
        OutboundShipmentBooking.id == booking_id,
        OutboundShipmentBooking.order_id == order_id,
    )
    if lock_for_update:
        query = query.with_for_update()
    booking = (await db.execute(query)).scalar_one_or_none()
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
