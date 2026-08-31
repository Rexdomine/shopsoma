from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "a2b3c4d5e6f7_checkout_prerequisite_validate.py"


def _normalized_source() -> str:
    return " ".join(MIGRATION.read_text().split())


def test_validation_accepts_post_cutover_live_writer_rows() -> None:
    source = _normalized_source()
    assert "run_row.classified_row_count<>(SELECT count(*) FROM orders)" not in source
    assert (
        "run_row.classified_row_count<>(SELECT count(*) FROM order_workflow_classifications)"
        not in source
    )
    assert (
        "LEFT JOIN order_workflow_classifications c ON c.order_id=o.id "
        "LEFT JOIN order_current_owners owner ON owner.order_id=o.id "
        "WHERE c.order_id IS NULL OR owner.order_id IS NULL"
    ) in source
    assert (
        "WHERE (o.created_at,o.id)<=(run_row.high_watermark_created_at, "
        "run_row.high_watermark_order_id) AND c.order_id IS NULL"
    ) in source


def test_validation_uses_replacement_aware_membership_for_exact_inventory_coverage() -> None:
    source = _normalized_source()
    assert "payment_attempt_reservations ar" in source
    assert "JOIN stock_reservations r ON r.id=ar.reservation_id" in source
    assert "ar.membership_family='domestic_checkout_v1'" in source
    assert "r.expires_at>statement_timestamp()" in source
    assert "LEFT JOIN stock_reservations r ON r.id=c.reservation_id" not in source
