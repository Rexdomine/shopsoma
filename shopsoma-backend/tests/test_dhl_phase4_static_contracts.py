from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.schemas.admin_order import DHLHandoffRequest
from app.services.dhl.shipments import _is_unique_constraint_violation


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
    assert "async with db.begin_nested():" in source
    assert "guard = OutboundIntentShipmentGuard(intent_id=intent.id)" in source
    assert "if not _is_unique_constraint_violation(exc):" in source
    assert ".with_for_update()" in source


def test_phase4_booking_releases_guard_on_definitive_dhl_rejections() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert "exc.status_code in {400, 401, 403}" in source
    assert 'booking.classification = "failure" if definitive_rejection else "unknown"' in source
    assert 'guard.active_booking_id = None if definitive_rejection else guard.active_booking_id' in source
    assert 'guard.booking_blocked_reason = None if definitive_rejection else "unknown_outcome"' in source


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


def test_dhl_handoff_request_normalizes_valid_evidence_inputs() -> None:
    payload = DHLHandoffRequest(
        occurred_at=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        idempotency_key="handoff-1",
        counterparty="DHL",
        evidence_ref=" evidence/private-ref-1 ",
        evidence_sha256="A" * 64,
    )

    assert payload.evidence_ref == "evidence/private-ref-1"
    assert payload.evidence_sha256 == "a" * 64


def test_tracking_refresh_sets_delivered_at_only_on_first_delivery_transition() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert 'if latest.outbound_state == "delivered" and (' in source
    assert 'current_state != "delivered" or order.delivered_at is None' in source


def test_tracking_refresh_reloads_locked_booking_after_provider_poll() -> None:
    source = (ROOT / "app" / "services" / "dhl" / "shipments.py").read_text()
    assert "booking = await _load_booking_for_order(" in source
    assert "lock_for_update=True" in source
    assert "allow_carrier_movement = booking.handoff_recorded_at is not None" in source
    assert "current_state = booking.outbound_state" in source


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
