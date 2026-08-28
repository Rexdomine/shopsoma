from app.models.checkout_prerequisite_ddl import M2_CHECKOUT_TRIGGER_DDL


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
