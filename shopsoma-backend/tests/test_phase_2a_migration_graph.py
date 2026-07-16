from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_migration_graph_has_exactly_one_head() -> None:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()

    assert heads == ["7b87484b1b1f"]

    merge_revision = script.get_revision(heads[0])
    assert merge_revision is not None
    assert merge_revision.down_revision == (
        "f6a7b8c9d0e1",
        "j6k7l8m9n0p1",
    )
