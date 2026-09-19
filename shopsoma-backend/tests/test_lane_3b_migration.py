"""Migration graph and scope contract for Lane 2A-3B persistence."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REVISION = "9d3e5f7a1b2c"
PARENT = "8c2d4e6f7a9b"


def _scripts() -> ScriptDirectory:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_lane_3b_remains_in_the_single_linear_alembic_chain() -> None:
    scripts = _scripts()
    assert len(scripts.get_heads()) == 1
    assert REVISION in {revision.revision for revision in scripts.walk_revisions()}
    revision = scripts.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PARENT


def test_lane_3b_migration_is_narrow_additive_and_symmetric() -> None:
    revision = _scripts().get_revision(REVISION)
    assert revision is not None
    source = Path(revision.path).read_text()

    for table in (
        "fulfillment_cohorts",
        "cohort_item_allocations",
        "inbound_transfers",
        "inbound_transfer_item_allocations",
    ):
        assert f'"{table}"' in source
        assert f'op.drop_table("{table}")' in source
    assert source.count("op.create_table(") == 4
    assert '"uq_order_items_id_order_vendor"' in source
    assert "validate_cohort_item_allocation_quantity" in source
    assert "validate_inbound_transfer_item_quantity" in source
    assert "FOR UPDATE" in source
    assert "CREATE TRIGGER" in source
    assert "DROP TRIGGER IF EXISTS" in source
    assert "Oniru" not in source
    assert "dhl" not in source.lower()
    assert "credential" not in source.lower()
    assert "account_number" not in source.lower()
    assert "origin_address" not in source.lower()
    assert "vendor_address" not in source.lower()


def test_lane_3b_quantity_trigger_events_match_model_metadata() -> None:
    migration = Path(_scripts().get_revision(REVISION).path).read_text()
    cohort_model = (
        BACKEND_ROOT / "app" / "models" / "fulfillment_cohort.py"
    ).read_text()
    inbound_model = (
        BACKEND_ROOT / "app" / "models" / "inbound_transfer.py"
    ).read_text()

    cohort_event = "BEFORE INSERT ON cohort_item_allocations"
    inbound_event = "BEFORE INSERT ON inbound_transfer_item_allocations"
    assert cohort_event in migration and cohort_event in cohort_model
    assert inbound_event in migration and inbound_event in inbound_model
    assert "BEFORE INSERT OR UPDATE ON cohort_item_allocations" not in cohort_model
    assert (
        "BEFORE INSERT OR UPDATE ON inbound_transfer_item_allocations"
        not in inbound_model
    )
