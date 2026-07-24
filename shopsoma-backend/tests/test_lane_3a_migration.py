"""Migration graph and additive-scope contract for Lane 3A persistence."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REVISION = "8c2d4e6f7a9b"


def _scripts() -> ScriptDirectory:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_lane_3a_is_the_only_linear_alembic_head() -> None:
    scripts = _scripts()
    assert scripts.get_heads() == [REVISION]
    revision = scripts.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == "7b87484b1b1f"


def test_lane_3a_migration_is_narrow_additive_and_symmetric() -> None:
    revision = _scripts().get_revision(REVISION)
    assert revision is not None
    source = Path(revision.path).read_text()

    assert source.count("op.create_table(") == 2
    assert '"fulfillment_hubs"' in source
    assert '"product_logistics_profiles"' in source
    assert '"uq_product_variants_product_id_id"' in source
    assert "op.create_unique_constraint(" in source
    assert source.count("op.create_index(") == 2
    assert "postgresql_where" in source
    assert 'op.drop_table("product_logistics_profiles")' in source
    assert 'op.drop_table("fulfillment_hubs")' in source
    assert "op.drop_constraint(" in source
    assert "prevent_fulfillment_hub_activation_audit_mutation" in source
    assert "CREATE TRIGGER tr_fulfillment_hubs_activation_audit_immutable" in source
    assert (
        "DROP TRIGGER IF EXISTS tr_fulfillment_hubs_activation_audit_immutable"
        in source
    )
    assert "Oniru" not in source
    assert "dhl" not in source.lower()
    assert "credential" not in source.lower()
    assert "account_number" not in source.lower()
