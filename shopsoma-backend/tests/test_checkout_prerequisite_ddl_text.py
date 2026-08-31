from app.models.checkout_prerequisite_ddl import M2_CHECKOUT_TRIGGER_DDL
from pathlib import Path


ROOT = Path(__file__).parents[1]
REPAIR_MIGRATION = ROOT / "alembic" / "versions" / "d5e6f7a8b9c0_repair_payment_bridge_canonical_gate.py"


def test_checkout_prerequisite_ddl_uses_active_reservation_truth_for_selection_completion() -> None:
    normalized = " ".join(M2_CHECKOUT_TRIGGER_DDL.split())
    assert "LEFT JOIN stock_reservations r ON r.id=c.reservation_id" in normalized
    assert "payment_attempt_reservations ar" in normalized
    assert "coverage.reservation_id=ar.reservation_id" not in normalized
    assert "c.reservation_id=ar.reservation_id" not in normalized
    assert (
        "validate_checkout_prerequisite_order(target_order_id uuid)"
        in normalized
    )


def test_checkout_prerequisite_ddl_allows_call_started_to_expire_after_authorization_deadline() -> None:
    normalized = " ".join(M2_CHECKOUT_TRIGGER_DDL.split())
    assert "IF OLD.state='call_started' AND NEW.state='expired' THEN" in normalized
    assert "IF now_at<OLD.authorization_deadline_at THEN RAISE EXCEPTION 'payment authorization deadline has not elapsed'; END IF;" in normalized
    assert "NEW.lease_token:=NULL; NEW.call_started_at:=NULL; NEW.claim_expires_at:=NULL;" in normalized
    assert "NEW.terminal_evidence_id:=NULL; NEW.terminal_at:=now_at; NEW.updated_at:=now_at; RETURN NEW;" in normalized


def test_checkout_prerequisite_ddl_uses_evidence_backed_late_capture_lease_exemption() -> None:
    normalized = " ".join(M2_CHECKOUT_TRIGGER_DDL.split())
    assert "AND OLD.supersedes_attempt_id IS NOT NULL" in normalized
    assert "FROM payment_attempt_evidence pe WHERE pe.id=NEW.terminal_evidence_id AND pe.attempt_id=OLD.id AND pe.evidence_type='payment_failed' AND pe.source='payment.success_reconciliation'" in normalized
    assert "NEW.terminal_reason='superseded_by_late_verified_capture'" not in normalized


def test_checkout_prerequisite_ddl_uses_selection_reservation_window_for_attempt_expiry() -> None:
    normalized = " ".join(M2_CHECKOUT_TRIGGER_DDL.split())
    assert "authoritative.estimate_expires_at<=now_at" not in normalized
    assert "s.selected_at AS selection_selected_at" in normalized
    assert "IF (NOT requires_stock_reservations) AND authoritative.selection_selected_at + NEW.payment_window_seconds*interval '1 second' <= now_at THEN RAISE EXCEPTION 'domestic payment attempt binding is invalid'; END IF;" in normalized
    assert "NEW.expires_at:=LEAST( now_at+NEW.payment_window_seconds*interval '1 second', COALESCE( earliest_reservation_expiry, authoritative.selection_selected_at + NEW.payment_window_seconds*interval '1 second'));" in normalized


def test_repair_migration_keeps_selection_reservation_window_for_attempt_expiry() -> None:
    normalized = " ".join(REPAIR_MIGRATION.read_text().split())
    assert "authoritative.estimate_expires_at<=now_at" not in normalized
    assert normalized.count("s.selected_at AS selection_selected_at") >= 2
    assert normalized.count("IF (NOT requires_stock_reservations) AND authoritative.selection_selected_at + NEW.payment_window_seconds*interval '1 second' <= now_at THEN RAISE EXCEPTION 'domestic payment attempt binding is invalid'; END IF;") >= 2
    assert normalized.count("COALESCE( earliest_reservation_expiry, authoritative.selection_selected_at + NEW.payment_window_seconds*interval '1 second'))") >= 2


def test_repair_migration_declares_requires_stock_reservations_in_both_trigger_copies() -> None:
    normalized = " ".join(REPAIR_MIGRATION.read_text().split())
    assert normalized.count("DECLARE requires_stock_reservations boolean;") >= 2


def test_repair_migration_keeps_call_started_expiry_in_parity() -> None:
    normalized = " ".join(REPAIR_MIGRATION.read_text().split())
    assert "IF OLD.state='call_started' AND NEW.state='expired' THEN" in normalized
    assert "IF now_at<OLD.authorization_deadline_at THEN RAISE EXCEPTION 'payment authorization deadline has not elapsed'; END IF;" in normalized
    assert "NEW.lease_token:=NULL; NEW.call_started_at:=NULL; NEW.claim_expires_at:=NULL;" in normalized
    assert "NEW.terminal_evidence_id:=NULL; NEW.terminal_at:=now_at; NEW.updated_at:=now_at; RETURN NEW;" in normalized
