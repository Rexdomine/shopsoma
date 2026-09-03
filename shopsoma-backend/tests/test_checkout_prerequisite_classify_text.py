from pathlib import Path


ROOT = Path(__file__).parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "a1b2c3d4e5f6_checkout_prerequisite_classify.py"


def _normalized_source() -> str:
    return " ".join(MIGRATION.read_text().split())


def test_compatibility_writer_preserves_post_cutover_domestic_truth() -> None:
    source = _normalized_source()
    assert "SELECT id,classification_cutover_at INTO active_run,cutover_at FROM order_workflow_migration_runs" in source
    assert (
        "IF cutover_at IS NOT NULL AND NEW.workflow_cohort='domestic_checkout_v1' "
        "AND NEW.workflow_policy_version='domestic_checkout_v1' "
        "AND NEW.checkout_access_mode IN ('authenticated','guest_capability') THEN RETURN NEW; END IF;"
    ) in source


def test_compatibility_writer_hash_uses_actual_order_truth() -> None:
    source = _normalized_source()
    assert (
        "NEW.id::text||'|'||NEW.workflow_cohort||'|'||NEW.workflow_policy_version||'|'||NEW.checkout_access_mode||'|positive_release_or_bridge_evidence|'||release_reference"
    ) in source
    assert (
        "NEW.id::text||'|legacy_pre_bridge|legacy_pre_bridge_v1|authenticated|positive_release_or_bridge_evidence|'||release_reference"
        not in source
    )
