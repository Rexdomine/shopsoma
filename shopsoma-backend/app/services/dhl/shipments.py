from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Protocol, Sequence
from urllib.parse import quote

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.customer_shipping_quote import (
    CustomerShippingQuote,
    CustomerShippingQuoteOption,
    CustomerShippingQuoteSelection,
)
from app.models.domestic_rate_quote import (
    DomesticRateAttempt,
    DomesticRateOffer,
    DomesticRateResponse,
)
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
    _blank_optional_text_to_none,
    _planned_ship_date_for_shadow_quote,
)
from app.services.dhl.client import (
    DHLAPIError,
    DHLClient,
    DHLConfigurationError,
)
from app.services.dhl.rating import DHLDomesticRateAdapter
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
MAX_BOOKING_PROVIDER_REFERENCE_LENGTH = 120
MAX_BOOKING_TRACKING_NUMBER_LENGTH = 120
MAX_ORDER_TRACKING_NUMBER_LENGTH = 100
MAX_BOOKING_SERVICE_CODE_LENGTH = 60
MAX_BOOKING_LABEL_MEDIA_TYPE_LENGTH = 80
MAX_TRACKING_STATUS_CODE_LENGTH = 60
MAX_TRACKING_EXCEPTION_CODE_LENGTH = 100
MAX_TRACKING_DETAIL_LENGTH = 240
EXPECTED_LABEL_MEDIA_TYPE = "application/pdf"
PDF_SIGNATURE = b"%PDF-"
DEFINITIVE_DHL_BOOKING_REJECTION_STATUSES = frozenset({400, 401, 403, 422})
TERMINAL_TRACKING_EXCEPTION_CODES = frozenset({"FAILURE", "RETURNED"})
CARRIER_CONTROLLED_FULFILLMENT_STATUSES = frozenset(
    {
        FulfillmentStatus.PICKED_UP,
        FulfillmentStatus.IN_TRANSIT,
        FulfillmentStatus.OUT_FOR_DELIVERY,
        FulfillmentStatus.DELIVERED,
        FulfillmentStatus.DELIVERY_FAILED,
        FulfillmentStatus.RETURNED,
    }
)


class ShipmentPhase4Error(Exception):
    pass


class ShipmentPhase4ConflictError(ShipmentPhase4Error):
    pass


class ShipmentPhase4ReconciliationRequiredError(ShipmentPhase4ConflictError):
    pass


class ShipmentPhase4UnknownOutcomeError(ShipmentPhase4Error):
    pass


@dataclass(frozen=True)
class EffectiveTrackingResolution:
    snapshot: OutboundShipmentTrackingSnapshot
    resolved_observed_at: datetime


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


def _is_definitive_booking_rejection(exc: DHLAPIError) -> bool:
    return (
        exc.status_code in DEFINITIVE_DHL_BOOKING_REJECTION_STATUSES
        and not exc.retryable
    )


def _is_booking_success_persistence_conflict(exc: IntegrityError) -> bool:
    return _is_unique_constraint_violation(
        exc,
        constraint_name="uq_outbound_shipment_bookings_provider_reference",
    ) or _is_unique_constraint_violation(
        exc,
        constraint_name="uq_outbound_shipment_bookings_tracking",
    )


@dataclass(frozen=True, slots=True)
class BookingCommand:
    order_id: uuid.UUID
    intent_id: uuid.UUID
    package_id: uuid.UUID
    package_version: int
    seal_id: uuid.UUID
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class BookingReconciliationCommand:
    booking_id: uuid.UUID
    resolution: str
    provider_reference: str | None = None
    tracking_number: str | None = None
    label_media_type: str | None = None
    label_content_base64: str | None = None
    provider_absence_evidence_ref: str | None = None
    provider_absence_evidence_sha256: str | None = None


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


@dataclass(frozen=True, slots=True)
class QuotedShipmentService:
    product_code: str
    service_code: str
    hub_version: int
    planned_ship_date: date


class ShipmentAdapter(Protocol):
    def prepare_booking_payload(
        self,
        intent: OutboundShipmentIntent,
        order: Order,
        hub: FulfillmentHub,
        package_version: HubPackageVersion,
        quoted_service: QuotedShipmentService,
    ) -> dict[str, object]: ...

    async def book(
        self,
        intent: OutboundShipmentIntent,
        order: Order,
        hub: FulfillmentHub,
        package_version: HubPackageVersion,
        quoted_service: QuotedShipmentService,
        prepared_payload: dict[str, object] | None = None,
    ) -> AdapterBookingResult: ...

    async def track(self, tracking_number: str) -> Sequence[TrackingObservation]: ...


class DHLShipmentAdapter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = DHLClient(config=settings)

    def prepare_booking_payload(
        self,
        intent: OutboundShipmentIntent,
        order: Order,
        hub: FulfillmentHub,
        package_version: HubPackageVersion,
        quoted_service: QuotedShipmentService,
    ) -> dict[str, object]:
        quoted_hub_version = getattr(quoted_service, "hub_version", None)
        current_hub_version = getattr(hub, "version", None)
        if (
            quoted_hub_version is not None
            and current_hub_version is not None
            and quoted_hub_version != current_hub_version
        ):
            raise ShipmentPhase4Error(
                "selected dhl quote hub version changed; refresh quote before booking"
            )
        minimum_planned_ship_date = _planned_ship_date_for_shadow_quote(intent.created_at)
        planned_ship_date = quoted_service.planned_ship_date
        if planned_ship_date < minimum_planned_ship_date:
            raise ShipmentPhase4Error(
                "selected dhl quote ship date expired; refresh quote before booking"
            )
        shipper = _provider_safe_booking_party(
            line1=hub.address_line1,
            line2=hub.address_line2,
            city=hub.city,
            state=hub.state,
            postal_code=hub.postal_code,
            country_code=hub.country_code,
        )
        receiver = _provider_safe_booking_party(
            line1=intent.destination_address_line1,
            line2=intent.destination_address_line2,
            city=intent.destination_city,
            state=intent.destination_state,
            postal_code=intent.destination_postal_code,
            country_code=intent.destination_country_code,
        )
        return {
            "plannedShippingDateAndTime": _mydhl_planned_shipping_timestamp(planned_ship_date),
            "pickup": {"isRequested": False},
            "productCode": quoted_service.product_code,
            "accounts": [{
                "typeCode": "shipper",
                "number": self._settings.DHL_EXPORT_ACCOUNT_NUMBER.get_secret_value(),
            }],
            "customerDetails": {
                "shipperDetails": {
                    "postalAddress": shipper,
                    "contactInformation": {
                        "fullName": hub.contact_name,
                        "phone": hub.contact_phone,
                    },
                },
                "receiverDetails": {
                    "postalAddress": receiver,
                    "contactInformation": {
                        "fullName": intent.destination_name,
                        "phone": intent.destination_phone,
                    },
                },
            },
            "outputImageProperties": {"printerDPI": 300, "encodingFormat": "pdf"},
            "content": {
                "unitOfMeasurement": "metric",
                "isCustomsDeclarable": False,
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

    async def book(
        self,
        intent: OutboundShipmentIntent,
        order: Order,
        hub: FulfillmentHub,
        package_version: HubPackageVersion,
        quoted_service: QuotedShipmentService,
        prepared_payload: dict[str, object] | None = None,
    ) -> AdapterBookingResult:
        payload = prepared_payload or self.prepare_booking_payload(
            intent,
            order,
            hub,
            package_version,
            quoted_service,
        )
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
            f"/shipments/{quote(tracking_number, safe='')}/tracking",
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
            primary_code = _bounded_tracking_code(
                codes[0] if codes else "UNKNOWN",
                field="provider_status_code",
                max_length=MAX_TRACKING_STATUS_CODE_LENGTH,
            )
            detail = _bounded_tracking_detail(
                checkpoint.get("description")
                or checkpoint.get("detail")
                or checkpoint.get("remark")
                or primary_code
            )
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
                    exception_code=_tracking_exception_code(
                        codes,
                        outbound_state=outbound_state,
                    ),
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


def _provider_safe_booking_party(
    *,
    line1: object,
    line2: object,
    city: object,
    state: object,
    postal_code: object,
    country_code: object,
) -> dict[str, object]:
    normalized_line2 = (
        _blank_optional_text_to_none(line2)
        if line2 is None or isinstance(line2, str)
        else line2
    )
    try:
        return DHLDomesticRateAdapter._party(
            SimpleNamespace(
                line1=line1,
                line2=normalized_line2,
                city=city,
                state=state,
                postal_code=postal_code,
                country_code=country_code,
            )
        )
    except (TypeError, ValueError):
        raise ShipmentPhase4Error("invalid booking party address") from None


def _tracking_exception_code(
    codes: Sequence[str],
    *,
    outbound_state: str,
) -> str | None:
    if outbound_state != "exception":
        return None
    normalized_codes = [str(code).strip().upper() for code in codes if str(code).strip()]
    terminal_code = next(
        (
            code
            for code in normalized_codes
            if code in TERMINAL_TRACKING_EXCEPTION_CODES
        ),
        None,
    )
    candidate = terminal_code or (normalized_codes[0] if normalized_codes else None)
    if candidate is None:
        return None
    return _bounded_tracking_code(
        candidate,
        field="exception_code",
        max_length=MAX_TRACKING_EXCEPTION_CODE_LENGTH,
    )


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


def _tracking_snapshot_fold_sort_key(
    snapshot: OutboundShipmentTrackingSnapshot,
) -> tuple[datetime, int, int, str, str, str]:
    provider_status_code = str(getattr(snapshot, "provider_status_code", ""))
    detail = str(getattr(snapshot, "detail", ""))
    if snapshot.outbound_state == "exception":
        return (
            snapshot.observed_at,
            1,
            1 if _is_terminal_tracking_exception(snapshot) else 0,
            (snapshot.exception_code or "").strip().upper(),
            provider_status_code,
            detail,
        )
    return (
        snapshot.observed_at,
        0,
        _state_rank(snapshot.outbound_state),
        "",
        provider_status_code,
        detail,
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
    return min(active_states, key=_state_rank)


def _highest_effective_tracking_snapshot_for_handoff(
    snapshots: Sequence[OutboundShipmentTrackingSnapshot],
) -> EffectiveTrackingResolution | None:
    effective_snapshot: OutboundShipmentTrackingSnapshot | None = None
    highest_progress_snapshot: OutboundShipmentTrackingSnapshot | None = None
    resolved_observed_at: datetime | None = None
    for snapshot in sorted(snapshots, key=_tracking_snapshot_fold_sort_key):
        snapshot_state = snapshot.outbound_state
        if snapshot_state != "exception" and (
            highest_progress_snapshot is None
            or _state_rank(snapshot_state)
            >= _state_rank(highest_progress_snapshot.outbound_state)
        ):
            highest_progress_snapshot = snapshot
        if effective_snapshot is None:
            effective_snapshot = snapshot
            resolved_observed_at = snapshot.observed_at
            continue
        effective_state = effective_snapshot.outbound_state
        if snapshot_state == "exception":
            if _is_terminal_tracking_exception(snapshot):
                effective_snapshot = snapshot
                resolved_observed_at = snapshot.observed_at
                continue
            if effective_state == "exception" and _is_terminal_tracking_exception(
                effective_snapshot
            ):
                continue
            effective_snapshot = snapshot
            resolved_observed_at = snapshot.observed_at
            continue
        if effective_state == "exception" and _is_terminal_tracking_exception(
            effective_snapshot
        ):
            continue
        if effective_state == "exception":
            if highest_progress_snapshot is not None and _state_rank(
                highest_progress_snapshot.outbound_state
            ) >= _state_rank(snapshot_state):
                effective_snapshot = highest_progress_snapshot
                resolved_observed_at = snapshot.observed_at
                continue
            effective_snapshot = snapshot
            resolved_observed_at = snapshot.observed_at
            continue
        if _state_rank(snapshot_state) >= _state_rank(effective_state):
            effective_snapshot = snapshot
            resolved_observed_at = snapshot.observed_at
    if effective_snapshot is None:
        return None
    return EffectiveTrackingResolution(
        snapshot=effective_snapshot,
        resolved_observed_at=resolved_observed_at or effective_snapshot.observed_at,
    )


def _is_terminal_tracking_exception(
    snapshot: OutboundShipmentTrackingSnapshot,
) -> bool:
    if snapshot.outbound_state != "exception":
        return False
    exception_code = snapshot.exception_code
    if not isinstance(exception_code, str):
        return False
    return exception_code.strip().upper() in TERMINAL_TRACKING_EXCEPTION_CODES


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
    if len(summary) > MAX_ORDER_TRACKING_NUMBER_LENGTH:
        fallback = fallback.strip() if fallback else None
        if fallback and len(fallback) <= MAX_ORDER_TRACKING_NUMBER_LENGTH:
            return fallback
        return None
    return summary


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
) -> bool:
    changed = False
    if guard.active_booking_id is None:
        return changed
    active = (
        await db.execute(
            select(OutboundShipmentBooking)
            .where(OutboundShipmentBooking.id == guard.active_booking_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if active is None:
        guard.active_booking_id = None
        guard.booking_blocked_reason = None
        await db.flush()
        return True
    now = await db.scalar(text("SELECT clock_timestamp()"))
    assert now is not None
    if active.claim_expires_at > now or active.classification != "pending":
        return changed
    if active.call_started_at is None:
        active.classification = "failure"
        active.failure_code = "claim_expired"
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
    changed = True
    await db.flush()
    return changed


async def _load_or_create_guard(
    db: AsyncSession,
    *,
    intent_id: uuid.UUID,
) -> OutboundIntentShipmentGuard:
    guard = (
        await db.execute(
            select(OutboundIntentShipmentGuard)
            .where(OutboundIntentShipmentGuard.intent_id == intent_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if guard is None:
        try:
            async with db.begin_nested():
                guard = OutboundIntentShipmentGuard(intent_id=intent_id)
                db.add(guard)
                await db.flush()
        except IntegrityError as exc:
            if not _is_unique_constraint_violation(exc):
                raise
            guard = (
                await db.execute(
                    select(OutboundIntentShipmentGuard)
                    .where(OutboundIntentShipmentGuard.intent_id == intent_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if guard is None:
                raise
        else:
            guard = (
                await db.execute(
                    select(OutboundIntentShipmentGuard)
                    .where(OutboundIntentShipmentGuard.intent_id == intent_id)
                    .with_for_update()
                )
            ).scalar_one()
    return guard


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


async def ensure_order_cancellation_allowed(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
) -> None:
    blocking_booking = (
        await db.execute(
            select(OutboundShipmentBooking)
            .where(
                OutboundShipmentBooking.order_id == order_id,
                OutboundShipmentBooking.outbound_state != "cancelled",
                OutboundShipmentBooking.classification.in_(("pending", "unknown", "success")),
            )
            .order_by(
                OutboundShipmentBooking.claimed_at.desc(),
                OutboundShipmentBooking.created_at.desc(),
            )
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if blocking_booking is not None:
        raise ShipmentPhase4ConflictError(
            "cannot cancel order while shipment booking outcome remains unresolved or active"
        )


async def ensure_order_manual_dhl_status_write_allowed(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    new_status: FulfillmentStatus,
) -> None:
    if new_status not in CARRIER_CONTROLLED_FULFILLMENT_STATUSES:
        return
    blocking_booking = (
        await db.execute(
            select(OutboundShipmentBooking)
            .where(
                OutboundShipmentBooking.order_id == order_id,
                OutboundShipmentBooking.outbound_state != "cancelled",
                OutboundShipmentBooking.classification.in_(("pending", "unknown", "success")),
            )
            .order_by(
                OutboundShipmentBooking.claimed_at.desc(),
                OutboundShipmentBooking.created_at.desc(),
            )
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if blocking_booking is not None:
        raise ShipmentPhase4ConflictError(
            "cannot manually set DHL carrier-tracked order status; use verified DHL handoff or tracking evidence"
        )


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
        outbound_state=booking.outbound_state,
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


async def _latest_tracking_snapshot(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
) -> OutboundShipmentTrackingSnapshot | None:
    return (
        await db.execute(
            select(OutboundShipmentTrackingSnapshot)
            .where(
                OutboundShipmentTrackingSnapshot.booking_id == booking_id,
                OutboundShipmentTrackingSnapshot.provider == PROVIDER,
            )
            .order_by(
                OutboundShipmentTrackingSnapshot.observed_at.desc(),
                OutboundShipmentTrackingSnapshot.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def _latest_effective_tracking_snapshot_for_handoff(
    db: AsyncSession,
    *,
    booking_id: uuid.UUID,
) -> EffectiveTrackingResolution | None:
    snapshots = (
        await db.execute(
            select(OutboundShipmentTrackingSnapshot).where(
                OutboundShipmentTrackingSnapshot.booking_id == booking_id,
                OutboundShipmentTrackingSnapshot.provider == PROVIDER,
                OutboundShipmentTrackingSnapshot.outbound_state.in_(
                    (
                        "collected",
                        "in_transit",
                        "out_for_delivery",
                        "delivered",
                        "exception",
                    )
                ),
            )
        )
    ).scalars().all()
    return _highest_effective_tracking_snapshot_for_handoff(snapshots)


def _utc_or_none(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
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


def _normalize_bounded_text(value: str | None, *, field: str, max_length: int) -> str:
    normalized = _normalize_nonempty_text(value, field=field)
    if len(normalized) > max_length:
        raise ShipmentPhase4Error(f"invalid {field}")
    return normalized


def _bounded_tracking_code(value: object, *, field: str, max_length: int) -> str:
    normalized = str(value).strip().upper()
    if not normalized or len(normalized) > max_length:
        raise ShipmentPhase4Error(f"invalid {field}")
    return normalized


def _bounded_tracking_detail(value: object) -> str:
    detail = str(value).strip()
    if not detail:
        detail = NO_CHECKPOINTS_DETAIL
    if len(detail) <= MAX_TRACKING_DETAIL_LENGTH:
        return detail
    return detail[: MAX_TRACKING_DETAIL_LENGTH - 1].rstrip() + "…"


def _validated_pdf_label_media_type(value: str | None) -> str:
    media_type = _normalize_bounded_text(
        value.lower() if isinstance(value, str) else value,
        field="label_media_type",
        max_length=MAX_BOOKING_LABEL_MEDIA_TYPE_LENGTH,
    )
    if media_type != EXPECTED_LABEL_MEDIA_TYPE:
        raise ShipmentPhase4Error("invalid label_media_type")
    return media_type


def _validate_pdf_label_content(value: bytes) -> None:
    if not value.startswith(PDF_SIGNATURE):
        raise ShipmentPhase4Error("invalid label_content")


def _decoded_reconciled_pdf_label_content(value: str | None) -> bytes:
    normalized = _normalize_nonempty_text(value, field="label_content_base64")
    try:
        decoded = base64.b64decode(normalized, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ShipmentPhase4Error("invalid label_content") from exc
    if not decoded:
        raise ShipmentPhase4Error("invalid label_content")
    _validate_pdf_label_content(decoded)
    return decoded


def _map_tracking_status(*codes: str) -> tuple[str, str]:
    normalized_codes = {
        code.strip().upper()
        for code in codes
        if code is not None and code.strip()
    }
    if normalized_codes & TERMINAL_TRACKING_EXCEPTION_CODES:
        return "exception", "delivery_exception"
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
    populate_existing: bool = False,
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
            select(HubPackage)
            .where(
                HubPackage.id == command.package_id,
                HubPackage.order_id == order_id,
                HubPackage.state == "ready",
                HubPackage.current_version == command.package_version,
                ~package_handoff_exists,
            )
            .execution_options(populate_existing=populate_existing)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if package is None:
        raise ShipmentPhase4Error("selected ready package not found for order")
    seal = (
        await db.execute(
            select(HubPackageSeal)
            .where(
                HubPackageSeal.id == command.seal_id,
                HubPackageSeal.package_id == package.id,
                HubPackageSeal.package_version == package.current_version,
                HubPackageSeal.retired_at.is_(None),
            )
            .execution_options(populate_existing=populate_existing)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if seal is None:
        raise ShipmentPhase4Error("no active bound seal")
    intent = (
        await db.execute(
            select(OutboundShipmentIntent)
            .where(
                OutboundShipmentIntent.id == command.intent_id,
                OutboundShipmentIntent.order_id == order_id,
                OutboundShipmentIntent.package_id == package.id,
                OutboundShipmentIntent.package_version == package.current_version,
                OutboundShipmentIntent.seal_id == seal.id,
                ~select(OutboundShipmentIntentInvalidation.id)
                .where(OutboundShipmentIntentInvalidation.intent_id == OutboundShipmentIntent.id)
                .exists(),
            )
            .execution_options(populate_existing=populate_existing)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if intent is None:
        raise ShipmentPhase4Error("no authoritative outbound shipment intent")
    package_version = (
        await db.execute(
            select(HubPackageVersion)
            .where(
                HubPackageVersion.package_id == package.id,
                HubPackageVersion.version == package.current_version,
            )
            .execution_options(populate_existing=populate_existing)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if package_version is None:
        raise ShipmentPhase4Error("missing package version measurement")
    package_items = (
        await db.execute(
            select(HubPackageItem)
            .where(
                HubPackageItem.package_id == package.id,
                HubPackageItem.package_version == package.current_version,
            )
            .execution_options(populate_existing=populate_existing)
            .with_for_update()
        )
    ).scalars().all()
    if not package_items:
        raise ShipmentPhase4Error("ready package has no package items")
    return order, package, seal, intent, package_version, frozenset(item.cohort_id for item in package_items)


async def _load_persisted_booking_intent(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    command: BookingCommand,
) -> OutboundShipmentIntent:
    intent = (
        await db.execute(
            select(OutboundShipmentIntent).where(
                OutboundShipmentIntent.id == command.intent_id,
                OutboundShipmentIntent.order_id == order_id,
                OutboundShipmentIntent.package_id == command.package_id,
                OutboundShipmentIntent.package_version == command.package_version,
                OutboundShipmentIntent.seal_id == command.seal_id,
            )
        )
    ).scalar_one_or_none()
    if intent is None:
        raise ShipmentPhase4Error("no persisted outbound shipment intent")
    return intent


async def _load_persisted_quoted_service(
    db: AsyncSession,
    *,
    intent_id: uuid.UUID,
) -> QuotedShipmentService:
    row = (
        await db.execute(
            select(CustomerShippingQuoteOption, DomesticRateAttempt)
            .join(
                CustomerShippingQuoteSelection,
                CustomerShippingQuoteSelection.option_id == CustomerShippingQuoteOption.id,
            )
            .join(
                CustomerShippingQuote,
                CustomerShippingQuote.id == CustomerShippingQuoteSelection.quote_id,
            )
            .join(
                DomesticRateResponse,
                DomesticRateResponse.id == CustomerShippingQuote.source_rate_response_id,
            )
            .join(
                DomesticRateAttempt,
                DomesticRateAttempt.id == DomesticRateResponse.attempt_id,
            )
            .where(
                CustomerShippingQuoteSelection.intent_id == intent_id,
                CustomerShippingQuoteSelection.quote_id == CustomerShippingQuoteOption.quote_id,
                CustomerShippingQuoteOption.provider == PROVIDER,
            )
        )
    ).one_or_none()
    if row is None:
        raise ShipmentPhase4Error("no persisted selected dhl shipping quote for outbound intent")
    option, attempt = row
    return QuotedShipmentService(
        product_code=_normalize_nonempty_text(option.product_code, field="product_code"),
        service_code=_normalize_bounded_text(
            option.service_code,
            field="service_code",
            max_length=MAX_BOOKING_SERVICE_CODE_LENGTH,
        ),
        hub_version=attempt.hub_version,
        planned_ship_date=attempt.planned_ship_date,
    )


async def _load_shadow_quote_recovery_service(
    db: AsyncSession,
    *,
    intent_id: uuid.UUID,
    selected_service: QuotedShipmentService,
    hub_version: int | None,
    minimum_planned_ship_date: date,
) -> QuotedShipmentService | None:
    row = (
        await db.execute(
            select(DomesticRateOffer, DomesticRateAttempt)
            .join(DomesticRateResponse, DomesticRateResponse.id == DomesticRateOffer.response_id)
            .join(DomesticRateAttempt, DomesticRateAttempt.id == DomesticRateResponse.attempt_id)
            .where(
                DomesticRateAttempt.intent_id == intent_id,
                DomesticRateAttempt.provider == PROVIDER,
                DomesticRateAttempt.source_command == "admin_shadow_quote",
                DomesticRateAttempt.classification == "success",
                DomesticRateResponse.result_kind == "success",
                DomesticRateOffer.provider_product_code == selected_service.product_code,
                DomesticRateOffer.provider_service_code == selected_service.service_code,
                DomesticRateAttempt.planned_ship_date >= minimum_planned_ship_date,
            )
            .order_by(
                DomesticRateAttempt.planned_ship_date.desc(),
                DomesticRateResponse.received_at.desc(),
                DomesticRateOffer.created_at.desc(),
            )
        )
    ).first()
    if row is None:
        return None
    offer, attempt = row
    if hub_version is not None and attempt.hub_version != hub_version:
        return None
    return QuotedShipmentService(
        product_code=_normalize_nonempty_text(
            offer.provider_product_code,
            field="product_code",
        ),
        service_code=_normalize_bounded_text(
            offer.provider_service_code,
            field="service_code",
            max_length=MAX_BOOKING_SERVICE_CODE_LENGTH,
        ),
        hub_version=attempt.hub_version,
        planned_ship_date=attempt.planned_ship_date,
    )


def _selected_quote_requires_recovery(
    *,
    quoted_service: QuotedShipmentService,
    hub_version: int | None,
    minimum_planned_ship_date: date,
) -> bool:
    quoted_hub_version = getattr(quoted_service, "hub_version", None)
    return (
        quoted_service.planned_ship_date < minimum_planned_ship_date
        or hub_version is not None
        and quoted_hub_version is not None
        and quoted_hub_version != hub_version
    )


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

    persisted_intent = await _load_persisted_booking_intent(
        db,
        order_id=order_id,
        command=command,
    )

    guard = await _load_or_create_guard(db, intent_id=persisted_intent.id)
    reconciliation_changed = await _reconcile_or_release_expired_claim(db, guard=guard)
    if reconciliation_changed:
        await db.commit()
        persisted_intent = await _load_persisted_booking_intent(
            db,
            order_id=order_id,
            command=command,
        )
        guard = await _load_or_create_guard(db, intent_id=persisted_intent.id)
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

    order, package, seal, intent, package_version, cohort_ids = await _load_authoritative_subject(
        db,
        order_id=order_id,
        command=command,
    )
    quoted_service = await _load_persisted_quoted_service(db, intent_id=intent.id)

    request_fingerprint = hashlib.sha256(
        f"{intent.id}:{package.id}:{package.current_version}:{seal.id}".encode("utf-8")
    ).hexdigest()

    if not _setting_bool(settings, "DHL_DOMESTIC_WORKFLOW_ENABLED", "dhl_domestic_workflow_enabled"):
        raise ShipmentPhase4Error("dhl domestic workflow disabled")
    if not _setting_bool(settings, "DHL_DOMESTIC_PROVIDER_CALLS_ENABLED", "dhl_domestic_provider_calls_enabled"):
        raise ShipmentPhase4Error("dhl domestic provider calls disabled")
    _ensure_sandbox_booking_allowed(settings, cohort_ids=cohort_ids)
    adapter = adapter or create_shipment_adapter(settings)

    now = await db.scalar(text("SELECT clock_timestamp()"))
    assert now is not None
    planned_ship_date = quoted_service.planned_ship_date
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
        order, package, seal, intent, package_version, _ = await _load_authoritative_subject(
            db,
            order_id=order_id,
            command=command,
            populate_existing=True,
        )
        hub = (
            await db.execute(
                select(FulfillmentHub)
                .where(FulfillmentHub.id == intent.origin_hub_id)
                .execution_options(populate_existing=True)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if hub is None:
            raise ShipmentPhase4Error("origin hub not found")
        minimum_planned_ship_date = _planned_ship_date_for_shadow_quote(
            intent.created_at
        )
        current_hub_version = getattr(hub, "version", None)
        if _selected_quote_requires_recovery(
            quoted_service=quoted_service,
            hub_version=current_hub_version,
            minimum_planned_ship_date=minimum_planned_ship_date,
        ):
            recovered_service = await _load_shadow_quote_recovery_service(
                db,
                intent_id=intent.id,
                selected_service=quoted_service,
                hub_version=current_hub_version,
                minimum_planned_ship_date=minimum_planned_ship_date,
            )
            if recovered_service is not None:
                quoted_service = recovered_service
        prepared_payload = adapter.prepare_booking_payload(
            intent,
            order,
            hub,
            package_version,
            quoted_service,
        )
    except ShipmentPhase4Error as exc:
        booking = await _load_booking_for_order(
            db,
            order_id=order_id,
            booking_id=booking.id,
            lock_for_update=True,
        )
        guard = await db.get(OutboundIntentShipmentGuard, intent.id)
        assert guard is not None
        await _mark_booking_failure(
            db,
            booking=booking,
            guard=guard,
            failure_code="local_preflight_failed",
        )
        return _booking_result(booking, replayed=False, note=str(exc))

    try:
        called_at = await db.scalar(text("SELECT clock_timestamp()"))
        booking.call_started_at = called_at
        await db.flush()
        await db.commit()
        adapter_result = await adapter.book(
            intent,
            order,
            hub,
            package_version,
            quoted_service,
            prepared_payload=prepared_payload,
        )
    except (DHLAPIError, TimeoutError) as exc:
        booking = await _load_booking_for_order(
            db,
            order_id=order_id,
            booking_id=booking.id,
            lock_for_update=True,
        )
        guard = await db.get(OutboundIntentShipmentGuard, intent.id)
        assert guard is not None
        completed_at = await db.scalar(text("SELECT clock_timestamp()"))
        definitive_rejection = isinstance(exc, DHLAPIError) and _is_definitive_booking_rejection(exc)
        booking.result_recorded_at = completed_at
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
        booking = await _load_booking_for_order(
            db,
            order_id=order_id,
            booking_id=booking.id,
            lock_for_update=True,
        )
        guard = await db.get(OutboundIntentShipmentGuard, intent.id)
        assert guard is not None
        await _mark_booking_unknown_outcome(db, booking=booking, guard=guard)
        return _booking_result(booking, replayed=False, note=str(exc))
    except ShipmentPhase4Error as exc:
        booking = await _load_booking_for_order(
            db,
            order_id=order_id,
            booking_id=booking.id,
            lock_for_update=True,
        )
        guard = await db.get(OutboundIntentShipmentGuard, intent.id)
        assert guard is not None
        await _mark_booking_failure(
            db,
            booking=booking,
            guard=guard,
            failure_code="local_preflight_failed",
        )
        return _booking_result(booking, replayed=False, note=str(exc))
    except Exception as exc:
        booking = await _load_booking_for_order(
            db,
            order_id=order_id,
            booking_id=booking.id,
            lock_for_update=True,
        )
        guard = await db.get(OutboundIntentShipmentGuard, intent.id)
        assert guard is not None
        await _mark_booking_unknown_outcome(db, booking=booking, guard=guard)
        return _booking_result(booking, replayed=False, note=str(exc))

    booking = (
        await db.execute(
            select(OutboundShipmentBooking)
            .where(
                OutboundShipmentBooking.id == booking.id,
                OutboundShipmentBooking.order_id == order_id,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one()
    guard = (
        await db.execute(
            select(OutboundIntentShipmentGuard)
            .where(OutboundIntentShipmentGuard.intent_id == intent.id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )
    ).scalar_one()
    if (
        booking.classification != "pending"
        or guard.active_booking_id != booking.id
        or guard.booking_blocked_reason is not None
    ):
        return _booking_result(
            booking,
            replayed=False,
            note="stale provider result ignored after booking ownership changed",
        )
    order = await _load_order(db, order_id=order_id, lock_for_update=True)
    completed_at = await db.scalar(text("SELECT clock_timestamp()"))
    booked_at = adapter_result.booked_at or completed_at
    try:
        if adapter_result.label_content is None:
            raise ShipmentPhase4Error("invalid label_content")
        provider_reference = _normalize_bounded_text(
            adapter_result.provider_reference,
            field="provider_reference",
            max_length=MAX_BOOKING_PROVIDER_REFERENCE_LENGTH,
        )
        tracking_number = _normalize_bounded_text(
            adapter_result.tracking_number,
            field="tracking_number",
            max_length=MAX_BOOKING_TRACKING_NUMBER_LENGTH,
        )
        if not adapter_result.label_content:
            raise ShipmentPhase4Error("invalid label_content")
        _validate_pdf_label_content(adapter_result.label_content)
        label_media_type = _validated_pdf_label_media_type(
            adapter_result.label_media_type
        )
    except ShipmentPhase4Error as exc:
        await _mark_booking_unknown_outcome(
            db,
            booking=booking,
            guard=guard,
            completed_at=completed_at,
        )
        return _booking_result(booking, replayed=False, note=str(exc))
    booking.result_recorded_at = completed_at
    booking.classification = "success"
    booking.provider_reference = provider_reference
    booking.tracking_number = tracking_number
    booking.service_code = quoted_service.service_code
    booking.label_media_type = label_media_type
    booking.label_content = adapter_result.label_content
    booking.label_sha256 = (
        hashlib.sha256(adapter_result.label_content).hexdigest()
        if adapter_result.label_content is not None
        else None
    )
    booking.label_received_at = booked_at if adapter_result.label_content is not None else None
    booking.outbound_state = "label_ready" if booking.label_content is not None else "awaiting_collection"
    booking.completion_txid = await db.scalar(text("SELECT txid_current()"))
    booking.last_tracking_refresh_at = completed_at
    order.delivery_provider = PROVIDER
    guard.booking_blocked_reason = None
    try:
        await db.flush()
    except IntegrityError as exc:
        if not _is_booking_success_persistence_conflict(exc):
            raise
        await db.rollback()
        booking = await _load_booking_for_order(
            db,
            order_id=order_id,
            booking_id=booking.id,
            lock_for_update=True,
        )
        guard = await db.get(OutboundIntentShipmentGuard, intent.id)
        assert guard is not None
        await _mark_booking_unknown_outcome(db, booking=booking, guard=guard)
        return _booking_result(
            booking,
            replayed=False,
            note="provider success persistence conflict",
        )
    order.tracking_number = await _project_order_tracking_number(
        db,
        order_id=order.id,
        fallback=booking.tracking_number,
    )
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
    filename = f"dhl-label-{booking.id}.pdf"
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
    order = await _load_order(db, order_id=order_id, lock_for_update=True)
    _ensure_order_not_cancelled(order, action="record handoff")
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
    latest_tracking = await _latest_effective_tracking_snapshot_for_handoff(
        db,
        booking_id=booking.id,
    )
    latest_tracking_snapshot = latest_tracking.snapshot if latest_tracking is not None else None
    if latest_tracking_snapshot is not None and latest_tracking_snapshot.outbound_state in {
        "collected",
        "in_transit",
        "out_for_delivery",
        "delivered",
        "exception",
    }:
        booking.outbound_state = latest_tracking_snapshot.outbound_state
        if latest_tracking_snapshot.outbound_state == "exception":
            booking.latest_exception_code = latest_tracking_snapshot.exception_code
    else:
        booking.outbound_state = "collected"
    aggregate_state = await _aggregate_order_outbound_state(
        db,
        order_id=booking.order_id,
        fallback=booking.outbound_state,
    )
    if order.fulfillment_status != FulfillmentStatus.CANCELLED:
        if aggregate_state == "collected":
            order.fulfillment_status = FulfillmentStatus.PICKED_UP
        elif aggregate_state == "in_transit":
            order.fulfillment_status = FulfillmentStatus.IN_TRANSIT
        elif aggregate_state == "out_for_delivery":
            order.fulfillment_status = FulfillmentStatus.OUT_FOR_DELIVERY
        elif aggregate_state == "delivered":
            order.fulfillment_status = FulfillmentStatus.DELIVERED
            if (
                latest_tracking_snapshot is not None
                and latest_tracking_snapshot.outbound_state == "delivered"
                and (
                    order.delivered_at is None
                    or latest_tracking_snapshot.observed_at > order.delivered_at
                )
            ):
                order.delivered_at = latest_tracking_snapshot.observed_at
        elif aggregate_state == "exception":
            order.fulfillment_status = FulfillmentStatus.DELIVERY_FAILED
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
    order = await _load_order(db, order_id=order_id, lock_for_update=True)
    _ensure_order_not_cancelled(order, action="refresh tracking")
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
        observations = list(await adapter.track(booking.tracking_number))
    except (DHLAPIError, TimeoutError) as exc:
        raise ShipmentPhase4Error(str(exc)) from exc
    if not observations:
        raise ShipmentPhase4Error("tracking adapter returned no observations")
    placeholder_observed_at = (
        booking.result_recorded_at or booking.label_received_at or booking.claimed_at
    )
    observations = [
        TrackingObservation(
            provider_status_code=observation.provider_status_code,
            outbound_state=observation.outbound_state,
            customer_status=observation.customer_status,
            detail=observation.detail,
            observed_at=placeholder_observed_at,
            exception_code=observation.exception_code,
        )
        if _is_placeholder_booked_observation(observation)
        else observation
        for observation in observations
    ]
    inserted = 0
    latest = max(
        observations,
        key=lambda observation: observation.observed_at,
    )
    try:
        async with db.begin_nested():
            for position, observation in enumerate(observations):
                derived_idempotency_key = _derived_handoff_idempotency_key(
                    normalized_idempotency,
                    f":{position}",
                )
                observed_at = observation.observed_at
                recorded_at = await db.scalar(text("SELECT clock_timestamp()"))
                assert recorded_at is not None
                if observed_at > recorded_at:
                    raise ShipmentPhase4ConflictError(
                        "carrier observation timestamp cannot be in the future"
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
                    observed_at=observed_at,
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
            effective_tracking = (
                await _latest_effective_tracking_snapshot_for_handoff(
                    db,
                    booking_id=booking.id,
                )
                if allow_carrier_movement
                else None
            )
            effective_tracking_snapshot = (
                effective_tracking.snapshot if effective_tracking is not None else None
            )
            effective_tracking_observed_at = (
                effective_tracking.resolved_observed_at
                if effective_tracking is not None
                else None
            )
            completed_at = await db.scalar(text("SELECT clock_timestamp()"))
            booking.last_tracking_refresh_at = completed_at
            effective_state = current_state
            if allow_carrier_movement:
                if (
                    effective_tracking_snapshot is not None
                    and current_state != "cancelled"
                    and (
                        current_state_observed_at is None
                        or effective_tracking_observed_at is not None
                        and effective_tracking_observed_at >= current_state_observed_at
                    )
                ):
                    effective_state = effective_tracking_snapshot.outbound_state
            else:
                if latest.outbound_state in {"booked", "label_ready", "awaiting_collection"}:
                    if _state_rank(latest.outbound_state) >= _state_rank(current_state):
                        effective_state = latest.outbound_state
            booking.outbound_state = effective_state
            if effective_state == "exception" and effective_tracking_snapshot is not None:
                booking.latest_exception_code = effective_tracking_snapshot.exception_code
            effective_customer_status = _customer_status_for_outbound_state(
                effective_state,
                fallback=(
                    effective_tracking_snapshot.customer_status
                    if effective_tracking_snapshot is not None
                    else latest.customer_status
                ),
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
            if order is not None:
                order.delivery_provider = PROVIDER
                order.tracking_number = aggregate_tracking_number
                if order.fulfillment_status != FulfillmentStatus.CANCELLED:
                    if allow_carrier_movement and aggregate_state == "collected":
                        order.fulfillment_status = FulfillmentStatus.PICKED_UP
                    elif allow_carrier_movement and aggregate_state == "in_transit":
                        order.fulfillment_status = FulfillmentStatus.IN_TRANSIT
                    elif allow_carrier_movement and aggregate_state == "out_for_delivery":
                        order.fulfillment_status = FulfillmentStatus.OUT_FOR_DELIVERY
                    elif allow_carrier_movement and aggregate_state == "delivered":
                        order.fulfillment_status = FulfillmentStatus.DELIVERED
                        if effective_tracking_snapshot is not None and (
                            effective_tracking_snapshot.outbound_state == "delivered"
                            and (
                                current_state != "delivered" or order.delivered_at is None
                            )
                        ):
                            order.delivered_at = effective_tracking_snapshot.observed_at
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


async def reconcile_unknown_booking_outcome(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    admin: User,
    command: BookingReconciliationCommand,
) -> BookingResult:
    provider_reference: str | None = None
    tracking_number: str | None = None
    recovered_label_content: bytes | None = None
    recovered_label_media_type: str | None = None
    provider_absence_evidence_ref: str | None = None
    provider_absence_evidence_sha256: str | None = None
    order = await _load_order(db, order_id=order_id, lock_for_update=True)
    _ensure_order_not_cancelled(order, action="reconcile booking")
    booking = await _load_booking_for_order(
        db,
        order_id=order_id,
        booking_id=command.booking_id,
    )
    guard = await _load_or_create_guard(db, intent_id=booking.intent_id)
    booking = await _load_booking_for_order(
        db,
        order_id=order_id,
        booking_id=command.booking_id,
        lock_for_update=True,
    )

    if command.resolution == "confirm_success":
        provider_reference = _normalize_nonempty_text(
            command.provider_reference,
            field="provider_reference",
        )
        tracking_number = _normalize_nonempty_text(
            command.tracking_number,
            field="tracking_number",
        )
        recovered_label_content = _decoded_reconciled_pdf_label_content(
            command.label_content_base64
        )
        recovered_label_media_type = _validated_pdf_label_media_type(
            command.label_media_type
        )
    else:
        provider_absence_evidence_ref = _normalize_private_reference(
            command.provider_absence_evidence_ref,
            field="provider_absence_evidence_ref",
        )
        provider_absence_evidence_sha256 = _normalize_sha256_hex(
            command.provider_absence_evidence_sha256,
            field="provider_absence_evidence_sha256",
        )

    if booking.classification != "unknown" or booking.failure_code != "unknown_outcome":
        if command.resolution == "confirm_success" and booking.classification == "success":
            if (
                booking.provider_reference != provider_reference
                or booking.tracking_number != tracking_number
            ):
                raise ShipmentPhase4ConflictError(
                    "booking reconciliation does not match existing provider identifiers"
                )
            return _booking_result(booking, replayed=True)
        if command.resolution == "confirm_failure" and booking.classification == "failure":
            if booking.failure_code != "reconciled_provider_absent":
                raise ShipmentPhase4ConflictError("booking is not awaiting reconciliation")
            if (
                booking.reconciliation_evidence_ref != provider_absence_evidence_ref
                or booking.reconciliation_evidence_sha256
                != provider_absence_evidence_sha256
            ):
                raise ShipmentPhase4ConflictError(
                    "booking reconciliation does not match existing provider-absence evidence"
                )
            return _booking_result(booking, replayed=True)
        raise ShipmentPhase4ConflictError("booking is not awaiting reconciliation")

    completed_at = await db.scalar(text("SELECT clock_timestamp()"))
    assert completed_at is not None
    try:
        async with db.begin_nested():
            booking.reconciliation_resolution = command.resolution
            booking.reconciliation_recorded_at = completed_at
            booking.reconciliation_actor_type = "admin"
            booking.reconciliation_actor_id = str(admin.id)
            booking.reconciled_from_classification = booking.classification
            booking.reconciled_from_failure_code = booking.failure_code
            booking.reconciled_from_result_recorded_at = booking.result_recorded_at
            booking.reconciled_from_completion_txid = booking.completion_txid
            booking.result_recorded_at = completed_at
            booking.completion_txid = await db.scalar(text("SELECT txid_current()"))
            if command.resolution == "confirm_success":
                assert provider_reference is not None
                assert tracking_number is not None
                assert recovered_label_content is not None
                assert recovered_label_media_type is not None
                booking.reconciliation_evidence_ref = None
                booking.reconciliation_evidence_sha256 = None
                guard.booking_blocked_reason = None

                booking.classification = "success"
                booking.failure_code = None
                booking.provider_reference = provider_reference
                booking.tracking_number = tracking_number
                booking.label_media_type = recovered_label_media_type
                booking.label_content = recovered_label_content
                booking.label_sha256 = hashlib.sha256(recovered_label_content).hexdigest()
                booking.label_received_at = completed_at
                booking.outbound_state = "label_ready"
                booking.last_tracking_refresh_at = completed_at
                guard.active_booking_id = booking.id
                order.delivery_provider = PROVIDER
            else:
                booking.reconciliation_evidence_ref = provider_absence_evidence_ref
                booking.reconciliation_evidence_sha256 = provider_absence_evidence_sha256
                booking.classification = "failure"
                booking.failure_code = "reconciled_provider_absent"
                booking.provider_reference = None
                booking.tracking_number = None
                booking.label_media_type = None
                booking.label_content = None
                booking.label_sha256 = None
                booking.label_received_at = None
                guard.active_booking_id = None
                guard.booking_blocked_reason = None
            await db.flush()
    except IntegrityError as exc:
        if not _is_booking_success_persistence_conflict(exc):
            raise
        raise ShipmentPhase4ConflictError(
            "booking reconciliation conflicts with existing provider identifiers"
        ) from exc
    if command.resolution == "confirm_success":
        order.tracking_number = await _project_order_tracking_number(
            db,
            order_id=order.id,
            fallback=booking.tracking_number,
        )

    await db.flush()
    return _booking_result(
        booking,
        replayed=False,
        note=f"reconciled {command.resolution} by admin {admin.id}",
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


async def _mark_booking_unknown_outcome(
    db: AsyncSession,
    *,
    booking: OutboundShipmentBooking,
    guard: OutboundIntentShipmentGuard,
    completed_at: datetime | None = None,
) -> None:
    if completed_at is None:
        completed_at = await db.scalar(text("SELECT clock_timestamp()"))
    booking.result_recorded_at = completed_at
    booking.classification = "unknown"
    booking.failure_code = "unknown_outcome"
    booking.completion_txid = await db.scalar(text("SELECT txid_current()"))
    guard.booking_blocked_reason = "unknown_outcome"
    await db.flush()


async def _mark_booking_failure(
    db: AsyncSession,
    *,
    booking: OutboundShipmentBooking,
    guard: OutboundIntentShipmentGuard,
    failure_code: str,
    completed_at: datetime | None = None,
) -> None:
    if completed_at is None:
        completed_at = await db.scalar(text("SELECT clock_timestamp()"))
    booking.result_recorded_at = completed_at
    booking.classification = "failure"
    booking.failure_code = failure_code
    booking.completion_txid = await db.scalar(text("SELECT txid_current()"))
    guard.active_booking_id = None
    guard.booking_blocked_reason = None
    await db.flush()


def _normalize_nonempty_text(value: str | None, *, field: str) -> str:
    if value is None:
        raise ShipmentPhase4Error(f"invalid {field}")
    normalized = value.strip()
    if not normalized:
        raise ShipmentPhase4Error(f"invalid {field}")
    return normalized


def _normalize_private_reference(value: str | None, *, field: str) -> str:
    normalized = _normalize_nonempty_text(value, field=field)
    if "://" in normalized or normalized.startswith("/") or ".." in normalized:
        raise ShipmentPhase4Error(f"invalid {field}")
    return normalized


def _normalize_sha256_hex(value: str | None, *, field: str) -> str:
    normalized = _normalize_nonempty_text(value, field=field).lower()
    if len(normalized) != 64:
        raise ShipmentPhase4Error(f"invalid {field}")
    try:
        bytes.fromhex(normalized)
    except ValueError as exc:
        raise ShipmentPhase4Error(f"invalid {field}") from exc
    return normalized
