from app.models.checkout_prerequisite_ddl import M2_CHECKOUT_TRIGGER_DDL
from pathlib import Path


ROOT = Path(__file__).parents[1]
REPAIR_MIGRATION = ROOT / "alembic" / "versions" / "d5e6f7a8b9c0_repair_payment_bridge_canonical_gate.py"


def test_checkout_prerequisite_ddl_uses_replacement_aware_membership_validation() -> None:
    normalized = " ".join(M2_CHECKOUT_TRIGGER_DDL.split())
    assert "JOIN stock_reservations r ON r.id=ar.reservation_id" in normalized
    assert "JOIN stock_reservations sr ON sr.id=ar.reservation_id" in normalized
    assert "payment_attempt_reservations ar" in normalized
    assert "ar.membership_family='domestic_checkout_v1'" in normalized
    assert "r.expires_at>statement_timestamp()" in normalized
    assert "sr.expires_at>now_at" in normalized
    assert "coverage.reservation_id=ar.reservation_id" not in normalized
    assert "c.reservation_id=ar.reservation_id" not in normalized


def test_checkout_prerequisite_ddl_allows_call_started_to_expire_after_authorization_deadline() -> None:
    normalized = " ".join(M2_CHECKOUT_TRIGGER_DDL.split())
    assert "IF OLD.state='call_started' AND NEW.state='expired' THEN" in normalized
    assert "IF now_at<OLD.authorization_deadline_at THEN RAISE EXCEPTION 'payment authorization deadline has not elapsed'; END IF;" in normalized
    assert "NEW.lease_token:=NULL; NEW.call_started_at:=NULL; NEW.claim_expires_at:=NULL;" in normalized
    assert "NEW.terminal_evidence_id:=NULL; NEW.terminal_at:=now_at; NEW.updated_at:=now_at; RETURN NEW;" in normalized


def test_repair_migration_keeps_call_started_expiry_in_parity() -> None:
    normalized = " ".join(REPAIR_MIGRATION.read_text().split())
    assert "IF OLD.state='call_started' AND NEW.state='expired' THEN" in normalized
    assert "IF now_at<OLD.authorization_deadline_at THEN RAISE EXCEPTION 'payment authorization deadline has not elapsed'; END IF;" in normalized
    assert "NEW.lease_token:=NULL; NEW.call_started_at:=NULL; NEW.claim_expires_at:=NULL;" in normalized
    assert "NEW.terminal_evidence_id:=NULL; NEW.terminal_at:=now_at; NEW.updated_at:=now_at; RETURN NEW;" in normalized
