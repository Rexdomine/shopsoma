from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_migration_graph_has_exactly_one_head() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert heads == ["b5f7d9a2c4e6"]

    lane_3d_revision = script.get_revision(heads[0])
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
