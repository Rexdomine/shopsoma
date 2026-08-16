from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_migration_graph_has_exactly_one_head() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert heads == ["d5e6f7a8b9c0"]

    repair_revision = script.get_revision(heads[0])
    assert repair_revision is not None
    assert repair_revision.down_revision == "c4d5e6f7a8b9"

    free_shipping_revision = script.get_revision("c4d5e6f7a8b9")
    assert free_shipping_revision is not None
    assert free_shipping_revision.down_revision == "b3c4d5e6f7a8"

    outbox_revision = script.get_revision("b3c4d5e6f7a8")
    assert outbox_revision is not None
    assert outbox_revision.down_revision == "a2b3c4d5e6f7"

    stock_payment_revision = script.get_revision("a2b3c4d5e6f7")
    assert stock_payment_revision is not None
    assert stock_payment_revision.down_revision == "a1b2c3d4e5f6"

    classify_revision = script.get_revision("a1b2c3d4e5f6")
    assert classify_revision is not None
    assert classify_revision.down_revision == "a0b1c2d3e4f5"

    expand_revision = script.get_revision("a0b1c2d3e4f5")
    assert expand_revision is not None
    assert expand_revision.down_revision == "f9d1b3e5a7c9"

    predecessor_revision = script.get_revision("f9d1b3e5a7c9")
    assert predecessor_revision is not None
    assert predecessor_revision.down_revision == "e8c0a2d4f6b8"

    quote_revision = script.get_revision("e8c0a2d4f6b8")
    assert quote_revision is not None
    assert quote_revision.down_revision == "d7b9f1c3e5a8"

    rate_lease_revision = script.get_revision("d7b9f1c3e5a8")
    assert rate_lease_revision is not None
    assert rate_lease_revision.down_revision == "c6a8e0f2b4d7"

    rate_evidence_revision = script.get_revision("c6a8e0f2b4d7")
    assert rate_evidence_revision is not None
    assert rate_evidence_revision.down_revision == "b5f7d9a2c4e6"

    lane_3d_revision = script.get_revision("b5f7d9a2c4e6")
    assert lane_3d_revision is not None
    assert lane_3d_revision.down_revision == "a4e6c8f1b3d5"

    lane_3c_revision = script.get_revision("a4e6c8f1b3d5")
    assert lane_3c_revision is not None
    assert lane_3c_revision.down_revision == "9d3e5f7a1b2c"

    lane_3b_revision = script.get_revision("9d3e5f7a1b2c")
    assert lane_3b_revision is not None
    assert lane_3b_revision.down_revision == "8c2d4e6f7a9b"

    lane_3a_revision = script.get_revision("8c2d4e6f7a9b")
    assert lane_3a_revision is not None
    assert lane_3a_revision.down_revision == "7b87484b1b1f"

    merge_revision = script.get_revision("7b87484b1b1f")
    assert merge_revision is not None
    assert merge_revision.down_revision == (
        "f6a7b8c9d0e1",
        "j6k7l8m9n0p1",
    )
