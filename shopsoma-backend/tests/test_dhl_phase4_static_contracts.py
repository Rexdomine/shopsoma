import base64
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.schemas.admin_order import DHLHandoffRequest
from app.schemas.admin_order import DHLBookingReconciliationRequest
from app.services.dhl.client import DHLAPIError, DHLConfigurationError
from app.services.dhl.shipments import (
    _is_definitive_booking_rejection,
    _is_unique_constraint_violation,
    create_shipment_adapter,
    ShipmentPhase4Error,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "alembic"
    / "versions"
    / "2026_09_03_1200_1c2b3d4e_phase4_dhl_shipment_evidence.py"
)
DUPLICATE_CLIENT = ROOT / "app" / "services" / "dhl" / "dhl_client.py"


def _integrity_error(sqlstate: str, constraint_name: str | None) -> IntegrityError:
    diag = SimpleNamespace(constraint_name=constraint_name)
    orig = SimpleNamespace(sqlstate=sqlstate, pgcode=sqlstate, diag=diag)
    return IntegrityError("INSERT", {}, orig)


def test_phase4_unique_violation_helper_matches_only_named_constraint() -> None:
    assert _is_unique_constraint_violation(
        _integrity_error(
            "23505",
            "uq_outbound_shipment_tracking_snapshots_observation",
        ),
        constraint_name="uq_outbound_shipment_tracking_snapshots_observation",
    )
    assert _is_unique_constraint_violation(
        IntegrityError(
            "INSERT",
            {},
            type(
                "Orig",
                (),
                {
                    "sqlstate": "23505",
                    "diag": None,
                    "__str__": lambda self: 'duplicate key value violates unique constraint "uq_outbound_shipment_tracking_snapshots_observation"',
                },
            )(),
        ),
        constraint_name="uq_outbound_shipment_tracking_snapshots_observation",
    )
    assert not _is_unique_constraint_violation(
        _integrity_error(
            "23505",
            "uq_outbound_shipment_tracking_refreshes_replay",
        ),
        constraint_name="uq_outbound_shipment_tracking_snapshots_observation",
    )
    assert not _is_unique_constraint_violation(
        _integrity_error(
            "23514",
            "uq_outbound_shipment_tracking_snapshots_observation",
        ),
        constraint_name="uq_outbound_shipment_tracking_snapshots_observation",
    )


def test_phase4_migration_uses_statement_timestamp_and_preserves_predecessors() -> None:
    source = MIGRATION.read_text()
    assert 'sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("statement_timestamp()"))' in source
    assert '"booking_id", "provider_status_code", "observed_at", "exception_code"' in source
    assert 'postgresql_nulls_not_distinct=True' in source
    assert "_drop_prerequisite_phase4_tables" not in source
    assert "Base.metadata.create_all" not in source
    assert "Base.metadata.tables[name].create(bind=bind, checkfirst=True)" in source


def test_phase4_booking_guard_creation_recovers_uniqueness_races() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert "async def _load_or_create_guard(" in source
    assert "async with db.begin_nested():" in source
    assert "guard = OutboundIntentShipmentGuard(intent_id=intent_id)" in source
    assert "if not _is_unique_constraint_violation(exc):" in source
    assert ".with_for_update()" in source


def test_phase4_booking_releases_guard_on_definitive_dhl_rejections() -> None:
    definitive_400 = DHLAPIError("DHL API request was rejected", status_code=400, retryable=False)
    definitive_401 = DHLAPIError("DHL API authentication failed", status_code=401, retryable=False)
    definitive_403 = DHLAPIError("DHL API authorization failed", status_code=403, retryable=False)
    definitive_422 = DHLAPIError("DHL API request was rejected", status_code=422, retryable=False)
    ambiguous_408 = DHLAPIError("DHL API request was rejected", status_code=408, retryable=False)
    ambiguous_409 = DHLAPIError("DHL API request was rejected", status_code=409, retryable=False)
    retryable_429 = DHLAPIError("DHL API rate limit exceeded", status_code=429, retryable=True)
    retryable_503 = DHLAPIError("DHL API is unavailable", status_code=503, retryable=True)

    assert _is_definitive_booking_rejection(definitive_400) is True
    assert _is_definitive_booking_rejection(definitive_401) is True
    assert _is_definitive_booking_rejection(definitive_403) is True
    assert _is_definitive_booking_rejection(definitive_422) is True
    assert _is_definitive_booking_rejection(ambiguous_408) is False
    assert _is_definitive_booking_rejection(ambiguous_409) is False
    assert _is_definitive_booking_rejection(retryable_429) is False
    assert _is_definitive_booking_rejection(retryable_503) is False

    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'DEFINITIVE_DHL_BOOKING_REJECTION_STATUSES = frozenset({400, 401, 403, 422})' in source
    assert 'booking.classification = "failure" if definitive_rejection else "unknown"' in source
    assert 'guard.active_booking_id = None if definitive_rejection else guard.active_booking_id' in source
    assert 'guard.booking_blocked_reason = None if definitive_rejection else "unknown_outcome"' in source


def test_phase4_booking_locks_and_rejects_cancelled_orders_before_provider_call() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    adapter_call = 'adapter_result = await adapter.book('
    assert 'order = await _load_order(db, order_id=order_id, lock_for_update=True)' in source
    assert '_ensure_order_not_cancelled(order, action="book shipment")' in source
    assert 'prepared_payload = adapter.prepare_booking_payload(' in source
    assert 'booking.call_started_at = called_at' in source
    assert adapter_call in source
    assert source.index('prepared_payload = adapter.prepare_booking_payload(') < source.index('booking.call_started_at = called_at')
    segment = source.split('booking.call_started_at = called_at', 1)[1].split(
        adapter_call,
        1,
    )[0]
    assert 'await db.commit()' in segment
    assert 'from app.services.admin_shadow_quote import (' in source
    assert '_blank_optional_text_to_none,' in source
    assert 'def _provider_safe_booking_party(' in source
    assert 'normalized_line2 = (' in source
    assert '_blank_optional_text_to_none(line2)' in source
    assert 'line2=normalized_line2,' in source
    assert 'return DHLDomesticRateAdapter._party(' in source
    assert 'raise ShipmentPhase4Error("invalid booking party address") from None' in source
    assert '"unitOfMeasurement": "metric"' in source.split('"content": {', 1)[1]
    assert '"isCustomsDeclarable": False' in source.split('"content": {', 1)[1]
    assert 'await _mark_booking_failure(' in source
    assert 'failure_code="local_preflight_failed"' in source
    assert 'booking.classification = "failure"' in source
    assert 'guard.active_booking_id = None' in source
    assert 'guard.booking_blocked_reason = None' in source


def test_phase4_tracking_preserves_terminal_exception_marker_from_all_codes() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'def _tracking_exception_code(' in source
    assert 'if code in TERMINAL_TRACKING_EXCEPTION_CODES' in source
    assert 'exception_code=_tracking_exception_code(' in source


def test_phase4_tracking_snapshot_uniqueness_deduplicates_null_exception_codes() -> None:
    model_source = (ROOT / "app" / "models" / "dhl_shipment.py").read_text()
    migration_source = MIGRATION.read_text()
    assert 'name="uq_outbound_shipment_tracking_snapshots_observation"' in model_source
    assert 'postgresql_nulls_not_distinct=True' in model_source
    assert 'name="uq_outbound_shipment_tracking_snapshots_observation"' in migration_source
    assert 'postgresql_nulls_not_distinct=True' in migration_source


def test_phase4_tracking_status_prioritizes_terminal_exception_codes_over_movement() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    segment = source.split('def _map_tracking_status(*codes: str) -> tuple[str, str]:', 1)[1].split(
        'async def _load_authoritative_subject(',
        1,
    )[0]
    assert 'if normalized_codes & TERMINAL_TRACKING_EXCEPTION_CODES:' in segment
    assert segment.index('if normalized_codes & TERMINAL_TRACKING_EXCEPTION_CODES:') < segment.index('if normalized_codes & {"PU", "PICKUP_CONFIRMED", "COLLECTED"}:')
    assert segment.index('if normalized_codes & TERMINAL_TRACKING_EXCEPTION_CODES:') < segment.index('if normalized_codes & {"OK", "DELIVERED"}:')


def test_order_cancellation_blocks_inflight_dhl_bookings_after_call_start() -> None:
    service_source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    customer_source = (ROOT / "app" / "api" / "v1" / "orders.py").read_text()
    admin_source = (ROOT / "app" / "api" / "v1" / "admin_orders.py").read_text()
    legacy_admin_source = (ROOT / "app" / "api" / "v1" / "admin.py").read_text()

    assert 'async def ensure_order_cancellation_allowed(' in service_source
    assert 'OutboundShipmentBooking.outbound_state != "cancelled"' in service_source
    assert 'OutboundShipmentBooking.classification.in_(("pending", "unknown", "success"))' in service_source
    assert 'cannot cancel order while shipment booking outcome remains unresolved or active' in service_source

    assert 'await ensure_order_cancellation_allowed(db, order_id=order.id)' in customer_source
    assert 'ShipmentPhase4ConflictError' in customer_source
    assert 'status_code=status.HTTP_409_CONFLICT' in customer_source

    assert 'select(Order).where(Order.id == order_id).with_for_update()' in admin_source
    assert 'await ensure_order_cancellation_allowed(db, order_id=order.id)' in admin_source
    assert 'status_code=status.HTTP_409_CONFLICT' in admin_source
    assert 'if new_status == FulfillmentStatus.CANCELLED:' in admin_source
    assert 'if update_data.fulfillment_status == FulfillmentStatus.CANCELLED:' in admin_source
    assert 'select(Order).where(Order.id.in_(update_data.order_ids)).with_for_update()' in admin_source

    legacy_status_route = legacy_admin_source.split('@router.put("/orders/{order_id}/status")', 1)[1].split(
        '@router.post("/orders/{order_id}/cancel")',
        1,
    )[0]
    assert '.with_for_update()' in legacy_status_route
    assert 'await ensure_order_cancellation_allowed(db, order_id=order.id)' in legacy_status_route
    assert 'if status == FulfillmentStatus.CANCELLED.value:' in legacy_status_route

    legacy_cancel_route = legacy_admin_source.split('@router.post("/orders/{order_id}/cancel")', 1)[1].split(
        '@router.put("/orders/{order_id}/notes")',
        1,
    )[0]
    assert '.with_for_update()' in legacy_cancel_route
    assert 'await ensure_order_cancellation_allowed(db, order_id=order.id)' in legacy_cancel_route
    assert 'ShipmentPhase4ConflictError' in legacy_cancel_route


def test_order_status_routes_block_manual_dhl_carrier_transitions() -> None:
    service_source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    admin_source = (ROOT / "app" / "api" / "v1" / "admin_orders.py").read_text()
    legacy_admin_source = (ROOT / "app" / "api" / "v1" / "admin.py").read_text()

    assert 'CARRIER_CONTROLLED_FULFILLMENT_STATUSES = frozenset(' in service_source
    assert 'async def ensure_order_manual_dhl_status_write_allowed(' in service_source
    assert 'FulfillmentStatus.DELIVERED' in service_source
    assert 'FulfillmentStatus.DELIVERY_FAILED' in service_source
    assert 'FulfillmentStatus.RETURNED' in service_source
    assert 'cannot manually set DHL carrier-tracked order status; use verified DHL handoff or tracking evidence' in service_source

    assert 'await ensure_order_manual_dhl_status_write_allowed(' in admin_source
    assert 'if new_status in {' in admin_source
    assert 'if update_data.fulfillment_status in {' in admin_source
    assert 'FulfillmentStatus.DELIVERED' in admin_source
    assert 'FulfillmentStatus.DELIVERY_FAILED' in admin_source
    assert 'FulfillmentStatus.RETURNED' in admin_source

    legacy_status_route = legacy_admin_source.split('@router.put("/orders/{order_id}/status")', 1)[1].split(
        '@router.post("/orders/{order_id}/cancel")',
        1,
    )[0]
    assert 'await ensure_order_manual_dhl_status_write_allowed(' in legacy_status_route
    assert 'new_status=FulfillmentStatus(status)' in legacy_status_route
    assert 'FulfillmentStatus.DELIVERED.value' in legacy_status_route
    assert 'FulfillmentStatus.DELIVERY_FAILED.value' in legacy_status_route
    assert 'FulfillmentStatus.RETURNED.value' in legacy_status_route


def test_phase4_booking_persists_unknown_outcome_when_success_flush_hits_unique_provider_conflict() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    adapter_call = 'adapter_result = await adapter.book('
    assert 'def _is_booking_success_persistence_conflict(exc: IntegrityError) -> bool:' in source
    assert 'constraint_name="uq_outbound_shipment_bookings_provider_reference"' in source
    assert 'constraint_name="uq_outbound_shipment_bookings_tracking"' in source
    assert 'booking.call_started_at = called_at' in source
    assert 'await db.commit()' in source[source.index('booking.call_started_at = called_at'):source.index(adapter_call)]
    success_reacquire = source[source.index('order = await _load_order(db, order_id=order_id, lock_for_update=True)'):source.index('completed_at = await db.scalar(text("SELECT clock_timestamp()"))')]
    assert success_reacquire.index('order = await _load_order(db, order_id=order_id, lock_for_update=True)') < success_reacquire.index('booking = await _load_booking_for_order(')
    success_tail = source[source.index('booking.classification = "success"'):]
    assert 'except IntegrityError as exc:' in success_tail
    assert 'if not _is_booking_success_persistence_conflict(exc):' in success_tail
    assert 'await db.rollback()' in success_tail
    assert 'await _mark_booking_unknown_outcome(db, booking=booking, guard=guard)' in success_tail
    assert 'note="provider success persistence conflict"' in success_tail


def test_phase4_dhl_mutations_preserve_order_before_booking_locking() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()

    handoff = source[source.index('async def record_collection_handoff('):source.index('async def download_label(') if 'async def download_label(' in source else source.index('async def _load_booking_for_order(')]
    assert handoff.index('order = await _load_order(db, order_id=order_id, lock_for_update=True)') < handoff.index('booking = await _load_booking_for_order(')
    assert '_ensure_order_not_cancelled(order, action="record handoff")' in handoff

    refresh = source[source.index('async def refresh_tracking('):source.index('async def reconcile_unknown_booking_outcome(')]
    assert refresh.index('order = await _load_order(db, order_id=order_id, lock_for_update=True)') < refresh.index('booking = await _load_booking_for_order(')
    assert '_ensure_order_not_cancelled(order, action="refresh tracking")' in refresh

    reconcile = source[source.index('async def reconcile_unknown_booking_outcome('):source.index('async def _load_booking_for_order(')]
    assert reconcile.index('order = await _load_order(db, order_id=order_id, lock_for_update=True)') < reconcile.index('booking = await _load_booking_for_order(')
    assert '_ensure_order_not_cancelled(order, action="reconcile booking")' in reconcile


def test_phase4_handoff_preserves_advanced_tracking_state_and_collection_projection() -> None:
    service_source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    orders_source = (ROOT / "app" / "api" / "v1" / "orders.py").read_text()
    frontend_tracking_source = (ROOT.parent / "shopsoma-frontend" / "src" / "services" / "orderService.ts").read_text()
    frontend_page_source = (ROOT.parent / "shopsoma-frontend" / "src" / "pages" / "orders" / "OrderTracking.tsx").read_text()

    handoff = service_source[service_source.index('async def record_collection_handoff('):service_source.index('async def refresh_tracking(')]
    assert 'async def _latest_effective_tracking_snapshot_for_handoff(' in service_source
    assert 'def _highest_effective_tracking_snapshot_for_handoff(' in service_source
    assert 'OutboundShipmentTrackingSnapshot.outbound_state.in_(' in service_source
    assert '.order_by(' in service_source
    assert 'OutboundShipmentTrackingSnapshot.observed_at.asc()' in service_source
    assert 'return _highest_effective_tracking_snapshot_for_handoff(snapshots)' in service_source
    assert 'latest_tracking = await _latest_effective_tracking_snapshot_for_handoff(' in handoff
    assert 'latest_tracking_snapshot = latest_tracking.snapshot if latest_tracking is not None else None' in handoff
    assert 'booking.outbound_state = latest_tracking_snapshot.outbound_state' in handoff
    assert 'booking.outbound_state = "collected"' in handoff
    assert 'if aggregate_state == "collected":' in handoff
    assert 'order.fulfillment_status = FulfillmentStatus.PICKED_UP' in handoff
    assert 'elif aggregate_state == "in_transit":' in handoff
    assert 'order.fulfillment_status = FulfillmentStatus.IN_TRANSIT' in handoff

    assert 'FulfillmentStatus.PICKED_UP: "picked_up"' in orders_source
    assert '"status": "picked_up"' in orders_source
    assert '"description": "Order has been collected by the courier"' in orders_source

    assert "| 'picked_up'" in frontend_tracking_source
    assert "{ key: 'picked_up', label: 'Picked Up' }" in frontend_page_source
    assert "currentStatus = 'picked_up';" in frontend_page_source


def test_phase4_booking_gets_header_safe_label_filename() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'filename = f"dhl-label-{booking.id}.pdf"' in source
    assert 'filename = f"dhl-label-{booking.tracking_number or booking.id}.pdf"' not in source


def test_phase4_booking_binds_provider_product_to_persisted_selected_quote() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'class QuotedShipmentService:' in source
    assert 'async def _load_persisted_quoted_service(' in source
    assert 'CustomerShippingQuoteSelection.intent_id == intent_id' in source
    assert 'CustomerShippingQuoteOption.provider == PROVIDER' in source
    assert 'quoted_service = await _load_persisted_quoted_service(db, intent_id=intent.id)' in source
    assert '"productCode": quoted_service.product_code' in source
    assert 'booking.service_code = quoted_service.service_code' in source


def test_phase4_booking_rejects_selected_service_codes_that_exceed_booking_width() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'MAX_BOOKING_SERVICE_CODE_LENGTH = 60' in source
    assert 'service_code=_normalize_bounded_text(' in source
    assert 'max_length=MAX_BOOKING_SERVICE_CODE_LENGTH' in source


def test_phase4_booking_rejects_empty_decoded_labels_before_success_flush() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'if adapter_result.label_content is None:' in source
    assert 'if not adapter_result.label_content:' in source
    assert 'raise ShipmentPhase4Error("invalid label_content")' in source
    assert source.index('if adapter_result.label_content is None:') < source.index('booking.classification = "success"')
    assert source.index('raise ShipmentPhase4Error("invalid label_content")') < source.index('booking.classification = "success"')
    assert 'booking.failure_code = "unknown_outcome"' in source


def test_phase4_booking_requires_label_document_before_success_flush() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    success_window = source[source.index('completed_at = await db.scalar(text("SELECT clock_timestamp()"))'):source.index('booking.classification = "success"')]
    assert 'if adapter_result.label_content is None:' in success_window
    assert 'raise ShipmentPhase4Error("invalid label_content")' in success_window
    assert 'booking.outbound_state = "label_ready" if booking.label_content is not None else "awaiting_collection"' in source


def test_phase4_booking_validates_pdf_label_contract_before_success_flush() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'EXPECTED_LABEL_MEDIA_TYPE = "application/pdf"' in source
    assert 'PDF_SIGNATURE = b"%PDF-"' in source
    assert 'def _validated_pdf_label_media_type(value: str | None) -> str:' in source
    assert 'def _validate_pdf_label_content(value: bytes) -> None:' in source
    assert 'if media_type != EXPECTED_LABEL_MEDIA_TYPE:' in source
    assert 'if not value.startswith(PDF_SIGNATURE):' in source
    assert source.index('_validate_pdf_label_content(adapter_result.label_content)') < source.index('booking.classification = "success"')
    assert source.index('_validated_pdf_label_media_type(') < source.index('booking.classification = "success"')


def test_phase4_booking_makes_label_less_successes_handoff_eligible() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'booking.outbound_state = "label_ready" if booking.label_content is not None else "awaiting_collection"' in source
    handoff_source = source[source.index('async def record_collection_handoff('):]
    assert 'if booking.outbound_state not in {"label_ready", "awaiting_collection", "collected"}:' in handoff_source


def test_phase4_booking_validates_provider_success_identifiers_before_success_flush() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'MAX_BOOKING_PROVIDER_REFERENCE_LENGTH = 120' in source
    assert 'MAX_BOOKING_TRACKING_NUMBER_LENGTH = 120' in source
    assert 'MAX_BOOKING_LABEL_MEDIA_TYPE_LENGTH = 80' in source
    assert 'provider_reference = _normalize_bounded_text(' in source
    assert 'tracking_number = _normalize_bounded_text(' in source
    assert 'booking.classification = "unknown"' in source
    assert 'guard.booking_blocked_reason = "unknown_outcome"' in source
    assert source.index('provider_reference = _normalize_bounded_text(') < source.index('booking.classification = "success"')


def test_phase4_reconciliation_preserves_append_only_audit_fields() -> None:
    service_source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    model_source = (ROOT / "app" / "models" / "dhl_shipment.py").read_text()
    migration_source = MIGRATION.read_text()
    assert 'booking.reconciliation_resolution = command.resolution' in service_source
    assert 'booking.reconciliation_recorded_at = completed_at' in service_source
    assert 'booking.reconciliation_actor_type = "admin"' in service_source
    assert 'booking.reconciliation_actor_id = str(admin.id)' in service_source
    assert 'booking.reconciled_from_classification = booking.classification' in service_source
    assert 'booking.reconciled_from_failure_code = booking.failure_code' in service_source
    assert 'booking.reconciled_from_result_recorded_at = booking.result_recorded_at' in service_source
    assert 'booking.reconciled_from_completion_txid = booking.completion_txid' in service_source
    assert 'booking.reconciliation_evidence_ref = provider_absence_evidence_ref' in service_source
    assert 'booking.reconciliation_evidence_sha256 = provider_absence_evidence_sha256' in service_source
    for field in (
        'reconciliation_resolution',
        'reconciliation_recorded_at',
        'reconciliation_actor_type',
        'reconciliation_actor_id',
        'reconciled_from_classification',
        'reconciled_from_failure_code',
        'reconciled_from_result_recorded_at',
        'reconciled_from_completion_txid',
        'reconciliation_evidence_ref',
        'reconciliation_evidence_sha256',
        "reconciliation_resolution = 'confirm_failure'",
        'ck_outbound_shipment_bookings_reconciliation_audit',
        'validate_outbound_shipment_booking_reconciliation_audit_update',
        'tr_outbound_shipment_bookings_reconciliation_audit_immutable',
        'tr_outbound_shipment_bookings_reconciliation_audit_immutable_delete',
        'outbound shipment reconciliation audit is immutable',
        "IF TG_OP = 'DELETE' AND OLD.reconciliation_recorded_at IS NOT NULL THEN",
    ):
        assert field in model_source
        assert field in migration_source

    assert (
        'DROP TRIGGER IF EXISTS tr_outbound_shipment_bookings_reconciliation_audit_immutable_delete ON outbound_shipment_booking'
        in migration_source
    )


def test_phase4_booking_behavioural_helper_now_seeds_selected_dhl_quote() -> None:
    source = (ROOT / "tests" / "test_dhl_phase4_booking.py").read_text()
    assert 'async def _seed_selected_dhl_quote(' in source
    assert 'CustomerShippingQuoteSelection(' in source
    assert 'provider="dhl"' in source
    assert 'product_code="N"' in source
    assert 'service_code="DOM-N"' in source
    assert 'await PHASE4._seed_selected_dhl_quote(db_session, graph, package, seal, intent, customer)' in source


def test_tracking_refresh_translates_transport_failures_into_service_errors() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    refresh_source = source[source.index("async def refresh_tracking"):]
    assert 'except (DHLAPIError, TimeoutError) as exc:' in refresh_source
    assert 'raise ShipmentPhase4Error(str(exc)) from exc' in refresh_source


def test_tracking_refresh_bounds_checkpoint_detail_before_persistence() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'MAX_TRACKING_DETAIL_LENGTH = 240' in source
    assert 'def _bounded_tracking_detail(value: object) -> str:' in source
    assert 'detail = _bounded_tracking_detail(' in source
    assert 'detail=observation.detail' in source


def test_tracking_refresh_bounds_provider_codes_before_persistence() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'MAX_TRACKING_STATUS_CODE_LENGTH = 60' in source
    assert 'MAX_TRACKING_EXCEPTION_CODE_LENGTH = 100' in source
    assert 'def _bounded_tracking_code(value: object, *, field: str, max_length: int) -> str:' in source
    assert 'field="provider_status_code"' in source
    assert 'field="exception_code"' in source
    assert 'provider_status_code=primary_code' in source
    assert 'exception_code=_tracking_exception_code(' in source


def test_phase4_tracking_snapshot_uniqueness_preserves_same_timestamp_exception_variants() -> None:
    model_source = (ROOT / "app" / "models" / "dhl_shipment.py").read_text()
    migration_source = MIGRATION.read_text()
    expected = '"booking_id", "provider_status_code", "observed_at", "exception_code"'
    assert expected in model_source
    assert expected in migration_source


def test_tracking_refresh_rejects_future_provider_observation_timestamps_before_insert() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    refresh = source[source.index('async def refresh_tracking('):source.index('async def reconcile_unknown_booking_outcome(')]
    assert 'observed_at = observation.observed_at' in refresh
    assert 'recorded_at = await db.scalar(text("SELECT clock_timestamp()"))' in refresh
    assert 'if observed_at > recorded_at:' in refresh
    assert 'raise ShipmentPhase4ConflictError(' in refresh
    assert '"carrier observation timestamp cannot be in the future"' in refresh
    assert refresh.index('if observed_at > recorded_at:') < refresh.index('snapshot = OutboundShipmentTrackingSnapshot(')


def test_tracking_refresh_aggregates_order_status_across_package_bookings() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'def _aggregate_order_shipment_state(states: Sequence[str]) -> str | None:' in source
    assert 'aggregate_state = await _aggregate_order_outbound_state(' in source
    assert 'select(HubPackage.id, HubPackage.current_version).where(' in source
    assert 'HubPackage.order_id == order_id' in source
    assert '(package_id, current_version): "booked"' in source
    assert 'if key not in latest_by_package or candidate.outbound_state == "cancelled":' in source
    assert 'return min(active_states, key=_state_rank)' in source


def test_tracking_refresh_folds_all_checkpoints_before_advancing_state() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    refresh = source[source.index('async def refresh_tracking('):source.index('async def reconcile_unknown_booking_outcome(')]
    assert 'effective_tracking = (' in refresh
    assert 'await _latest_effective_tracking_snapshot_for_handoff(' in refresh
    assert 'effective_tracking_snapshot = (' in refresh
    assert 'effective_state = effective_tracking_snapshot.outbound_state' in refresh
    assert 'key=lambda observation: observation.observed_at' not in refresh[refresh.index('effective_tracking = ('):refresh.index('booking.outbound_state = effective_state')]


def test_handoff_persists_delivered_at_when_delivery_is_preserved() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    handoff = source[source.index('async def record_collection_handoff('):source.index('async def refresh_tracking(')]
    assert 'order.fulfillment_status = FulfillmentStatus.DELIVERED' in handoff
    assert 'latest_tracking_snapshot.outbound_state == "delivered"' in handoff
    assert 'order.delivered_at = latest_tracking_snapshot.observed_at' in handoff


def test_effective_handoff_tracking_allows_newer_exception_to_supersede_delivery() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    helper = source[source.index('def _highest_effective_tracking_snapshot_for_handoff('):source.index('async def _aggregate_order_outbound_state(')]
    assert '@dataclass(frozen=True)' in source
    assert 'class EffectiveTrackingResolution:' in source
    assert 'resolved_observed_at: datetime' in source
    assert 'highest_progress_snapshot: OutboundShipmentTrackingSnapshot | None = None' in helper
    assert 'resolved_observed_at: datetime | None = None' in helper
    assert 'if snapshot_state == "exception":' in helper
    assert 'if _is_terminal_tracking_exception(snapshot):' in helper
    assert 'if effective_state == "exception" and _is_terminal_tracking_exception(' in helper
    assert 'if highest_progress_snapshot is not None and _state_rank(' in helper
    assert 'effective_snapshot = highest_progress_snapshot' in helper
    assert 'resolved_observed_at = snapshot.observed_at' in helper
    assert 'return EffectiveTrackingResolution(' in helper
    assert 'if snapshot_state == "exception" or effective_state == "exception":' not in helper
    assert 'if effective_state != "delivered"' not in helper


def test_order_tracking_keeps_prepickup_statuses_before_picked_up_milestone() -> None:
    orders_source = (ROOT / "app" / "api" / "v1" / "orders.py").read_text()
    frontend_page_source = (ROOT.parent / "shopsoma-frontend" / "src" / "pages" / "orders" / "OrderTracking.tsx").read_text()
    assert 'FulfillmentStatus.PREPARING_FOR_PICKUP: "order_placed"' in orders_source
    assert 'FulfillmentStatus.PICKUP_SCHEDULED: "order_placed"' in orders_source
    assert "fulfillmentStatus === 'preparing_for_pickup'" in frontend_page_source
    assert "fulfillmentStatus === 'pickup_scheduled'" in frontend_page_source
    assert "currentStatus = 'order_placed';" in frontend_page_source


def test_phase4_handoff_replay_returns_persisted_booking_state() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    handoff_replay = source[source.index('async def _matching_handoff_replay('):source.index('async def _verified_carrier_acceptance_snapshot(')]
    assert 'outbound_state=booking.outbound_state' in handoff_replay
    assert 'outbound_state="collected"' not in handoff_replay


def test_tracking_refresh_keeps_collected_state_at_picked_up_milestone() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    refresh = source[source.index('async def refresh_tracking('):source.index('async def reconcile_unknown_booking_outcome(')]
    assert 'if allow_carrier_movement and aggregate_state == "collected":' in refresh
    assert 'order.fulfillment_status = FulfillmentStatus.PICKED_UP' in refresh
    assert 'elif allow_carrier_movement and aggregate_state == "in_transit":' in refresh
    assert 'order.fulfillment_status = FulfillmentStatus.IN_TRANSIT' in refresh


def test_phase4_tracking_snapshots_are_db_enforced_append_only() -> None:
    model_source = (ROOT / "app" / "models" / "dhl_shipment.py").read_text()
    migration_source = MIGRATION.read_text()
    for field in (
        'validate_outbound_shipment_tracking_snapshot_append_only',
        'tr_outbound_shipment_tracking_snapshot_append_only_update',
        'tr_outbound_shipment_tracking_snapshot_append_only_delete',
        'outbound shipment tracking snapshot evidence is append-only',
    ):
        assert field in model_source
        assert field in migration_source
    assert 'OutboundShipmentTrackingSnapshot.__table__' in model_source


def test_no_duplicate_dhl_client_module_remains() -> None:
    assert not DUPLICATE_CLIENT.exists()


def test_dhl_handoff_request_rejects_invalid_evidence_inputs() -> None:
    with pytest.raises(ValidationError):
        DHLHandoffRequest(
            occurred_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            idempotency_key="handoff-1",
            counterparty="DHL",
            evidence_ref="https://example.test/evidence",
            evidence_sha256="z" * 64,
        )


def test_dhl_handoff_request_rejects_blank_counterparty() -> None:
    with pytest.raises(ValidationError, match="counterparty must not be empty"):
        DHLHandoffRequest(
            occurred_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
            idempotency_key="handoff-1",
            counterparty="   ",
            evidence_ref="evidence/private-ref-1",
            evidence_sha256="a" * 64,
        )


def test_dhl_handoff_request_normalizes_valid_evidence_inputs() -> None:
    payload = DHLHandoffRequest(
        occurred_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        idempotency_key="handoff-1",
        counterparty=" DHL ",
        evidence_ref=" evidence/private-ref-1 ",
        evidence_sha256="A" * 64,
    )

    assert payload.counterparty == "DHL"
    assert payload.evidence_ref == "evidence/private-ref-1"
    assert payload.evidence_sha256 == "a" * 64


def test_dhl_handoff_request_rejects_naive_occurred_at() -> None:
    with pytest.raises(ValidationError, match="occurred_at must be timezone-aware"):
        DHLHandoffRequest(
            occurred_at=datetime(2026, 9, 3, 12, 0),
            idempotency_key="handoff-1",
            counterparty="DHL",
            evidence_ref="evidence/private-ref-1",
            evidence_sha256="a" * 64,
        )


def test_dhl_handoff_request_normalizes_occurred_at_to_utc() -> None:
    payload = DHLHandoffRequest(
        occurred_at=datetime(2026, 9, 3, 13, 0, tzinfo=timezone(timedelta(hours=1))),
        idempotency_key="handoff-1",
        counterparty="DHL",
        evidence_ref="evidence/private-ref-1",
        evidence_sha256="a" * 64,
    )

    assert payload.occurred_at.tzinfo == UTC


def test_dhl_booking_reconciliation_request_requires_provider_identifiers_for_success() -> None:
    with pytest.raises(
        ValidationError,
        match="provider_reference, tracking_number, label_media_type, and label_content_base64 are required for confirm_success",
    ):
        DHLBookingReconciliationRequest(
            resolution="confirm_success",
            provider_reference=None,
            tracking_number=None,
        )


def test_dhl_booking_reconciliation_request_rejects_identifiers_for_confirm_failure() -> None:
    with pytest.raises(
        ValidationError,
        match="confirm_failure must not include provider_reference, tracking_number, label_media_type, or label_content_base64",
    ):
        DHLBookingReconciliationRequest(
            resolution="confirm_failure",
            provider_absence_evidence_ref="evidence/dhl/no-shipment-check.txt",
            provider_absence_evidence_sha256="a" * 64,
            provider_reference=" DHL-REF ",
            tracking_number=" TRACK-1 ",
            label_media_type=" application/pdf ",
            label_content_base64=" JVBERi0xLjQK ",
        )


def test_dhl_booking_reconciliation_request_requires_provider_absence_evidence_for_failure() -> None:
    with pytest.raises(
        ValidationError,
        match="provider_absence_evidence_ref and provider_absence_evidence_sha256 are required for confirm_failure",
    ):
        DHLBookingReconciliationRequest(
            resolution="confirm_failure",
            provider_reference=None,
            tracking_number=None,
            label_media_type=None,
            label_content_base64=None,
            provider_absence_evidence_ref=None,
            provider_absence_evidence_sha256=None,
        )


def test_dhl_booking_reconciliation_request_normalizes_failure_evidence() -> None:
    payload = DHLBookingReconciliationRequest(
        resolution="confirm_failure",
        provider_reference=None,
        tracking_number=None,
        label_media_type=None,
        label_content_base64=None,
        provider_absence_evidence_ref=" evidence/dhl/no-shipment-check.txt ",
        provider_absence_evidence_sha256="A" * 64,
    )

    assert payload.provider_absence_evidence_ref == "evidence/dhl/no-shipment-check.txt"
    assert payload.provider_absence_evidence_sha256 == "a" * 64


def test_dhl_booking_reconciliation_request_normalizes_success_identifiers() -> None:
    label_base64 = base64.b64encode(b"%PDF-1.4\nreconciled label\n").decode()
    payload = DHLBookingReconciliationRequest(
        resolution="confirm_success",
        provider_reference=" DHL-REF ",
        tracking_number=" TRACK-1 ",
        label_media_type=" application/pdf ",
        label_content_base64=f" {label_base64} ",
    )

    assert payload.provider_reference == "DHL-REF"
    assert payload.tracking_number == "TRACK-1"
    assert payload.label_media_type == "application/pdf"
    assert payload.label_content_base64 == label_base64


def test_dhl_reconciliation_flushes_success_before_projecting_tracking_and_translates_identifier_conflicts() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    reconcile = source[source.index('async def reconcile_unknown_booking_outcome('):source.index('async def _load_booking_for_order(')]
    assert 'async with db.begin_nested():' in reconcile
    assert 'booking.classification = "success"' in reconcile
    assert 'await db.flush()' in reconcile
    assert 'if not _is_booking_success_persistence_conflict(exc):' in reconcile
    assert '"booking reconciliation conflicts with existing provider identifiers"' in reconcile
    assert reconcile.index('await db.flush()') < reconcile.index('order.tracking_number = await _project_order_tracking_number(')


def test_tracking_refresh_sets_delivered_at_only_on_first_delivery_transition() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'if effective_tracking_snapshot is not None and (' in source
    assert 'effective_tracking_snapshot.outbound_state == "delivered"' in source
    assert 'current_state != "delivered" or order.delivered_at is None' in source


def test_booking_replay_runs_before_provider_call_gates() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert source.index("replay = await _matching_replay") < source.index(
        'raise ShipmentPhase4Error("dhl domestic provider calls disabled")'
    )
    assert source.index("await _reconcile_or_release_expired_claim") < source.index(
        'raise ShipmentPhase4Error("dhl domestic provider calls disabled")'
    )


def test_booking_reconciles_expired_claims_before_authoritative_subject_validation() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    booking_source = source[source.index("async def book_outbound_shipment"):]
    assert "persisted_intent = await _load_persisted_booking_intent(" in booking_source
    assert booking_source.index("persisted_intent = await _load_persisted_booking_intent(") < booking_source.index(
        "await _reconcile_or_release_expired_claim"
    )
    assert booking_source.index("await _reconcile_or_release_expired_claim") < booking_source.index(
        "await db.commit()"
    )
    assert booking_source.index("await db.commit()") < booking_source.index(
        "order, package, seal, intent, package_version, cohort_ids = await _load_authoritative_subject"
    )


def test_booking_expiry_reconciliation_preserves_no_call_boundary_marker() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    claim_source = source[source.index("async def _reconcile_or_release_expired_claim"):source.index("async def _load_or_create_guard")]
    assert 'select(OutboundShipmentBooking)' in claim_source
    assert '.execution_options(populate_existing=True)' in claim_source
    assert '.with_for_update()' in claim_source
    assert 'active.classification = "failure"' in claim_source
    assert 'active.failure_code = "claim_expired"' in claim_source
    assert 'active.call_started_at = active.claimed_at' not in claim_source


def test_booking_unknown_outcome_reconciliation_route_and_service_exist() -> None:
    schema_source = (ROOT / "app" / "schemas" / "admin_order.py").read_text()
    api_source = (ROOT / "app" / "api" / "v1" / "admin_orders.py").read_text()
    service_source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()

    assert 'class DHLBookingReconciliationRequest(BaseModel):' in schema_source
    assert 'resolution: str = Field(..., pattern="^(confirm_failure|confirm_success)$")' in schema_source
    assert 'provider_reference, tracking_number, label_media_type, and label_content_base64 are required for confirm_success' in schema_source
    assert 'provider_absence_evidence_ref and provider_absence_evidence_sha256 are required for confirm_failure' in schema_source
    assert 'confirm_failure must not include provider_reference, tracking_number, label_media_type, or label_content_base64' in schema_source
    assert 'confirm_success must not include provider_absence_evidence_ref or provider_absence_evidence_sha256' in schema_source
    assert '@router.post("/{order_id}/dhl/bookings/{booking_id}/reconcile", response_model=DHLBookingResult)' in api_source
    assert 'result = await reconcile_unknown_booking_outcome(' in api_source
    assert 'class BookingReconciliationCommand:' in service_source
    assert 'async def reconcile_unknown_booking_outcome(' in service_source
    assert 'provider_absence_evidence_ref: str | None = None' in service_source
    assert 'provider_absence_evidence_sha256: str | None = None' in service_source
    assert 'booking.classification = "success"' in service_source
    assert 'booking.failure_code = "reconciled_provider_absent"' in service_source
    assert 'guard.active_booking_id = None' in service_source.split('async def reconcile_unknown_booking_outcome(', 1)[1].split('async def _load_booking_for_order(', 1)[0]
    assert 'booking.tracking_number = tracking_number' in service_source
    assert 'label_media_type=payload.label_media_type' in api_source
    assert 'label_content_base64=payload.label_content_base64' in api_source
    assert 'provider_absence_evidence_ref=payload.provider_absence_evidence_ref' in api_source
    assert 'provider_absence_evidence_sha256=payload.provider_absence_evidence_sha256' in api_source
    assert 'label_media_type: str | None = None' in service_source
    assert 'label_content_base64: str | None = None' in service_source
    assert 'booking.reconciliation_evidence_ref = provider_absence_evidence_ref' in service_source
    assert 'booking.reconciliation_evidence_sha256 = provider_absence_evidence_sha256' in service_source
    assert 'recovered_label_content = _decoded_reconciled_pdf_label_content(' in service_source
    assert 'recovered_label_media_type = _validated_pdf_label_media_type(' in service_source
    assert 'booking.label_sha256 = hashlib.sha256(recovered_label_content).hexdigest()' in service_source
    assert 'booking.outbound_state = "label_ready"' in service_source


def test_phase4_booking_binds_selected_quote_to_source_hub_version_before_provider_call() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'select(CustomerShippingQuoteOption, DomesticRateAttempt)' in source
    assert 'CustomerShippingQuote.id == CustomerShippingQuoteSelection.quote_id' in source
    assert 'DomesticRateResponse.id == CustomerShippingQuote.source_rate_response_id' in source
    assert 'DomesticRateAttempt.id == DomesticRateResponse.attempt_id' in source
    assert 'hub_version=attempt.hub_version' in source
    assert 'quoted_hub_version = getattr(quoted_service, "hub_version", None)' in source
    assert 'current_hub_version = getattr(hub, "version", None)' in source
    assert 'quoted_hub_version != current_hub_version' in source
    assert 'selected dhl quote hub version changed; refresh quote before booking' in source
    booking_source = source[source.index('async def book_outbound_shipment('):]
    assert '.execution_options(populate_existing=True)' in booking_source
    assert 'select(FulfillmentHub)' in booking_source
    assert 'FulfillmentHub.id == intent.origin_hub_id' in booking_source
    assert '.with_for_update()' in booking_source
    assert booking_source.index('select(FulfillmentHub)') < booking_source.index('prepared_payload = adapter.prepare_booking_payload(')
    assert booking_source.index('prepared_payload = adapter.prepare_booking_payload(') < booking_source.index('booking.call_started_at = called_at')


def test_order_tracking_returns_persisted_carrier_number_on_initial_http_load() -> None:
    orders_source = (ROOT / 'app' / 'api' / 'v1' / 'orders.py').read_text()
    frontend_tracking_source = (ROOT.parent / 'shopsoma-frontend' / 'src' / 'services' / 'orderService.ts').read_text()
    assert 'tracking_id = order.tracking_number or f"GB{order.order_number.replace(\'-\', \'\')[-8:]}"' in orders_source
    assert '"tracking_number": order.tracking_number,' in orders_source
    assert 'tracking_number?: string | null;' in frontend_tracking_source
    assert 'tracking_number: trackingId,' in frontend_tracking_source


def test_booking_reconciliation_acquires_guard_before_locking_booking_row() -> None:
    service_source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    reconcile = service_source.split('async def reconcile_unknown_booking_outcome(', 1)[1].split('async def _load_booking_for_order(', 1)[0]
    assert 'guard = await _load_or_create_guard(db, intent_id=booking.intent_id)' in reconcile
    assert reconcile.index('guard = await _load_or_create_guard(db, intent_id=booking.intent_id)') < reconcile.rindex('lock_for_update=True')


def test_phase4_reconciliation_success_requires_a_valid_pdf_label() -> None:
    service_source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'def _decoded_reconciled_pdf_label_content(value: str | None) -> bytes:' in service_source
    assert '_normalize_nonempty_text(value, field="label_content_base64")' in service_source
    assert 'base64.b64decode(normalized, validate=True)' in service_source
    assert '_validate_pdf_label_content(decoded)' in service_source
    assert 'booking.label_media_type = recovered_label_media_type' in service_source
    assert 'booking.label_content = recovered_label_content' in service_source
    assert 'booking.label_received_at = completed_at' in service_source


def test_tracking_refresh_replay_runs_before_workflow_gate_and_skips_provider_calls_gate() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    refresh_source = source[source.index("async def refresh_tracking"):]
    assert refresh_source.index("replay = await _matching_tracking_replay") < refresh_source.index(
        'raise ShipmentPhase4Error("dhl domestic workflow disabled")'
    )
    assert 'raise ShipmentPhase4Error("dhl domestic provider calls disabled")' not in refresh_source


def test_tracking_refresh_reloads_locked_booking_after_provider_poll() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    refresh_source = source[source.index("async def refresh_tracking"):]
    assert "booking = await _load_booking_for_order(" in refresh_source
    assert "lock_for_update=True" in refresh_source
    assert "observations = await adapter.track(booking.tracking_number)" in refresh_source
    assert refresh_source.index("lock_for_update=True") < refresh_source.index(
        "observations = await adapter.track(booking.tracking_number)"
    )
    assert "allow_carrier_movement = booking.handoff_recorded_at is not None" in refresh_source
    assert "current_state = booking.outbound_state" in refresh_source


def test_tracking_refresh_keeps_provider_terminal_observation_as_latest() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'latest = max(' in source
    assert 'key=lambda observation: observation.observed_at' in source
    assert 'latest = observations[-1]' not in source


def test_tracking_refresh_preserves_cancelled_order_status() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert "if order.fulfillment_status != FulfillmentStatus.CANCELLED:" in source


def test_handoff_locks_booking_before_replay_check() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert "record_collection_handoff" in source
    assert "lock_for_update=True" in source


def test_handoff_replays_before_state_validation_and_rejects_mismatched_evidence() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert "replay = await _matching_handoff_replay(" in source
    assert "if replay is not None:" in source
    assert "return replay" in source
    assert 'outbound_state=booking.outbound_state' in source
    assert 'booking.collection_scheduled_at != command.occurred_at' in source
    assert 'booking.collection_counterparty != normalized_counterparty' in source
    assert 'booking.collection_evidence_ref != command.evidence_ref.strip()' in source
    assert 'booking.collection_evidence_hash != command.evidence_sha256.lower()' in source


def test_handoff_rejects_cancelled_orders_and_invalid_chronology_before_custody_insert() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert '_ensure_order_not_cancelled(order, action="record handoff")' in source
    assert 'database_now = await db.scalar(text("SELECT clock_timestamp()"))' in source
    assert 'if command.occurred_at > database_now:' in source
    assert 'recorded_at = max(command.occurred_at, database_now)' in source
    assert '"handoff occurred_at cannot be in the future"' in source
    assert 'verified_acceptance_now = await db.scalar(text("SELECT clock_timestamp()"))' in source
    assert 'if verified_acceptance.observed_at > verified_acceptance_now:' in source
    assert '"verified carrier acceptance cannot be in the future"' in source
    assert 'if command.occurred_at < tip.occurred_at:' in source
    assert '"handoff occurred_at precedes current custody state"' in source
    assert 'if verified_acceptance.observed_at < tip.occurred_at:' in source
    assert '"verified carrier acceptance precedes current custody state"' in source
    assert 'tendered_occurred_at = max(' in source
    assert 'min(command.occurred_at, verified_acceptance.observed_at)' in source
    assert 'tendered_recorded_at = max(' in source
    assert 'tendered_recorded_now = await db.scalar(text("SELECT clock_timestamp()"))' in source
    assert 'previous.recorded_at,' in source
    assert 'provider_accepted_occurred_at = max(' in source
    assert 'previous.occurred_at + timedelta(microseconds=1)' in source
    assert 'provider_accepted_recorded_now = await db.scalar(text("SELECT clock_timestamp()"))' in source
    assert 'provider_accepted_recorded_at = max(' in source
    assert 'booking.collection_scheduled_at = command.occurred_at' in source
    assert 'booking.handoff_recorded_at = max(recorded_at, returned_event.recorded_at)' in source


def test_tracking_refresh_uses_effective_customer_status_and_locks_order() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'effective_customer_status = _customer_status_for_outbound_state(' in source
    assert 'order = await _load_order(db, order_id=order_id, lock_for_update=True)' in source
    assert 'customer_status=effective_customer_status' in source


def test_order_tracking_projection_aggregates_latest_package_bookings() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'async def _project_order_tracking_number(' in source
    assert 'MAX_ORDER_TRACKING_NUMBER_LENGTH = 100' in source
    assert 'summary = ", ".join(projected)' in source
    assert 'order.tracking_number = await _project_order_tracking_number(' in source
    assert 'order.tracking_number = aggregate_tracking_number' in source
    assert 'if len(summary) > MAX_ORDER_TRACKING_NUMBER_LENGTH:' in source
    assert 'if fallback and len(fallback) <= MAX_ORDER_TRACKING_NUMBER_LENGTH:' in source
    assert 'return None' in source
    assert 'note="provider success persistence conflict",\n        )\n    order.tracking_number = await _project_order_tracking_number(' in source
    assert '    )\n    await db.flush()\n    return _booking_result(booking, replayed=False)' in source
    assert 'order.tracking_number = booking.tracking_number' not in source


def test_tracking_refresh_ignores_stale_exception_checkpoints() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'current_state_snapshot = await _latest_tracking_snapshot_for_state(' in source
    assert 'effective_tracking = (' in source
    assert 'effective_tracking_snapshot = (' in source
    assert 'effective_tracking_observed_at = (' in source
    assert 'effective_tracking_observed_at >= current_state_observed_at' in source


def test_tracking_refresh_requires_fresh_timestamps_for_state_advancement() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'current_state_observed_at = (' in source
    assert 'effective_tracking = (' in source
    assert 'current_state_observed_at is None' in source
    assert 'or effective_tracking_observed_at is not None' in source
    assert 'and effective_tracking_observed_at >= current_state_observed_at' in source
    assert 'effective_state = effective_tracking_snapshot.outbound_state' in source


def test_tracking_refresh_uses_resolving_observation_time_when_transient_exception_clears() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    helper = source[source.index('def _highest_effective_tracking_snapshot_for_handoff('):source.index('async def _aggregate_order_outbound_state(')]
    refresh = source[source.index('async def refresh_tracking('):source.index('async def reconcile_unknown_booking_outcome(')]
    assert 'resolved_observed_at = snapshot.observed_at' in helper
    assert 'resolved_observed_at=resolved_observed_at or effective_snapshot.observed_at' in helper
    assert 'effective_tracking_observed_at = (' in refresh
    assert 'effective_tracking.resolved_observed_at' in refresh
    assert 'effective_state = effective_tracking_snapshot.outbound_state' in refresh


def test_create_shipment_adapter_translates_dhl_configuration_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_: object) -> None:
        raise DHLConfigurationError('DHL integration is disabled')

    monkeypatch.setattr('app.services.dhl.shipments.DHLShipmentAdapter', _boom)

    with pytest.raises(ShipmentPhase4Error, match='DHL integration is disabled'):
        create_shipment_adapter(cast(Any, object()))
