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
    definitive_404 = DHLAPIError("DHL API request was rejected", status_code=404, retryable=False)
    definitive_422 = DHLAPIError("DHL API request was rejected", status_code=422, retryable=False)
    retryable_429 = DHLAPIError("DHL API rate limit exceeded", status_code=429, retryable=True)
    retryable_503 = DHLAPIError("DHL API is unavailable", status_code=503, retryable=True)

    assert _is_definitive_booking_rejection(definitive_404) is True
    assert _is_definitive_booking_rejection(definitive_422) is True
    assert _is_definitive_booking_rejection(retryable_429) is False
    assert _is_definitive_booking_rejection(retryable_503) is False

    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'booking.classification = "failure" if definitive_rejection else "unknown"' in source
    assert 'guard.active_booking_id = None if definitive_rejection else guard.active_booking_id' in source
    assert 'guard.booking_blocked_reason = None if definitive_rejection else "unknown_outcome"' in source


def test_phase4_booking_locks_and_rejects_cancelled_orders_before_provider_call() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'order = await _load_order(db, order_id=order_id, lock_for_update=True)' in source
    assert '_ensure_order_not_cancelled(order, action="book shipment")' in source
    assert 'booking.call_started_at = called_at' in source
    assert 'adapter_result = await adapter.book(intent, order, hub, package_version, quoted_service)' in source
    segment = source.split('booking.call_started_at = called_at', 1)[1].split(
        'adapter_result = await adapter.book(intent, order, hub, package_version, quoted_service)',
        1,
    )[0]
    assert 'await db.commit()' in segment


def test_phase4_booking_persists_unknown_outcome_when_success_flush_hits_unique_provider_conflict() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'def _is_booking_success_persistence_conflict(exc: IntegrityError) -> bool:' in source
    assert 'constraint_name="uq_outbound_shipment_bookings_provider_reference"' in source
    assert 'constraint_name="uq_outbound_shipment_bookings_tracking"' in source
    assert 'booking.call_started_at = called_at' in source
    assert 'await db.commit()' in source[source.index('booking.call_started_at = called_at'):source.index('adapter_result = await adapter.book(intent, order, hub, package_version, quoted_service)')]
    success_tail = source[source.index('booking.classification = "success"'):]
    assert 'except IntegrityError as exc:' in success_tail
    assert 'if not _is_booking_success_persistence_conflict(exc):' in success_tail
    assert 'await db.rollback()' in success_tail
    assert 'await _mark_booking_unknown_outcome(db, booking=booking, guard=guard)' in success_tail
    assert 'note="provider success persistence conflict"' in success_tail


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
    assert 'if not adapter_result.label_content:' in source
    assert 'raise ShipmentPhase4Error("invalid label_content")' in source
    assert source.index('raise ShipmentPhase4Error("invalid label_content")') < source.index('booking.classification = "success"')
    assert 'booking.failure_code = "unknown_outcome"' in source


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
    assert 'field="label_media_type"' in source
    assert 'booking.classification = "unknown"' in source
    assert 'guard.booking_blocked_reason = "unknown_outcome"' in source
    assert source.index('provider_reference = _normalize_bounded_text(') < source.index('booking.classification = "success"')


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
    assert 'exception_code=(' in source


def test_tracking_refresh_aggregates_order_status_across_package_bookings() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'def _aggregate_order_shipment_state(states: Sequence[str]) -> str | None:' in source
    assert 'aggregate_state = await _aggregate_order_outbound_state(' in source
    assert 'select(HubPackage.id, HubPackage.current_version).where(' in source
    assert 'HubPackage.order_id == order_id' in source
    assert '(package_id, current_version): "booked"' in source
    assert 'if key not in latest_by_package or candidate.outbound_state == "cancelled":' in source
    assert 'if all(state == "delivered" for state in active_states):' in source
    assert 'if all(state in {"delivered", "out_for_delivery"} for state in active_states):' in source


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
    with pytest.raises(ValidationError, match="provider_reference and tracking_number are required for confirm_success"):
        DHLBookingReconciliationRequest(
            resolution="confirm_success",
            provider_reference=None,
            tracking_number=None,
        )


def test_dhl_booking_reconciliation_request_rejects_identifiers_for_confirm_failure() -> None:
    with pytest.raises(ValidationError, match="confirm_failure must not include provider_reference or tracking_number"):
        DHLBookingReconciliationRequest(
            resolution="confirm_failure",
            provider_reference=" DHL-REF ",
            tracking_number=" TRACK-1 ",
        )


def test_dhl_booking_reconciliation_request_normalizes_success_identifiers() -> None:
    payload = DHLBookingReconciliationRequest(
        resolution="confirm_success",
        provider_reference=" DHL-REF ",
        tracking_number=" TRACK-1 ",
    )

    assert payload.provider_reference == "DHL-REF"
    assert payload.tracking_number == "TRACK-1"


def test_tracking_refresh_sets_delivered_at_only_on_first_delivery_transition() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'if latest.outbound_state == "delivered" and (' in source
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
    assert 'active.classification = "failure"' in claim_source
    assert 'active.failure_code = "claim_expired"' in claim_source
    assert 'active.call_started_at = active.claimed_at' not in claim_source


def test_booking_unknown_outcome_reconciliation_route_and_service_exist() -> None:
    schema_source = (ROOT / "app" / "schemas" / "admin_order.py").read_text()
    api_source = (ROOT / "app" / "api" / "v1" / "admin_orders.py").read_text()
    service_source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()

    assert 'class DHLBookingReconciliationRequest(BaseModel):' in schema_source
    assert 'resolution: str = Field(..., pattern="^(confirm_failure|confirm_success)$")' in schema_source
    assert 'provider_reference and tracking_number are required for confirm_success' in schema_source
    assert 'confirm_failure must not include provider_reference or tracking_number' in schema_source
    assert '@router.post("/{order_id}/dhl/bookings/{booking_id}/reconcile", response_model=DHLBookingResult)' in api_source
    assert 'result = await reconcile_unknown_booking_outcome(' in api_source
    assert 'class BookingReconciliationCommand:' in service_source
    assert 'async def reconcile_unknown_booking_outcome(' in service_source
    assert 'definitive provider-absence evidence required before releasing unknown booking' in service_source
    assert 'booking.classification = "success"' in service_source
    assert 'booking.failure_code = "reconciled_provider_absent"' not in service_source
    assert 'guard.active_booking_id = None' not in service_source.split('async def reconcile_unknown_booking_outcome(', 1)[1].split('async def _load_booking_for_order(', 1)[0]
    assert 'booking.tracking_number = tracking_number' in service_source
    assert 'booking.outbound_state = "label_ready" if booking.label_content is not None else "awaiting_collection"' in service_source


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
    assert "latest = observations[-1]" in source
    assert "\n                latest = observation\n" not in source


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
    assert 'outbound_state="collected"' in source
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
    assert 'summary = ", ".join(projected)' in source
    assert 'order.tracking_number = await _project_order_tracking_number(' in source
    assert 'order.tracking_number = aggregate_tracking_number' in source
    assert 'order.tracking_number = booking.tracking_number' not in source


def test_tracking_refresh_ignores_stale_exception_checkpoints() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'current_state_snapshot = await _latest_tracking_snapshot_for_state(' in source
    assert 'latest.observed_at >= current_state_snapshot.observed_at' in source


def test_tracking_refresh_requires_fresh_timestamps_for_state_advancement() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'current_state_observed_at = (' in source
    assert 'latest.outbound_state in {' in source
    assert 'current_state_observed_at is None' in source
    assert 'or latest.observed_at >= current_state_observed_at' in source
    assert '_state_rank(latest.outbound_state) >= _state_rank(current_state)' in source


def test_create_shipment_adapter_translates_dhl_configuration_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_: object) -> None:
        raise DHLConfigurationError('DHL integration is disabled')

    monkeypatch.setattr('app.services.dhl.shipments.DHLShipmentAdapter', _boom)

    with pytest.raises(ShipmentPhase4Error, match='DHL integration is disabled'):
        create_shipment_adapter(cast(Any, object()))
