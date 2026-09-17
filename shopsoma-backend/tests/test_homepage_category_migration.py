import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND_ROOT / "alembic/versions/p2q3r4s5t6u7_ensure_homepage_edit_categories.py"


def _revision_metadata() -> tuple[str, str]:
    source = MIGRATION.read_text()
    revision = re.search(r'^revision = "([^"]+)"$', source, re.MULTILINE)
    down_revision = re.search(r'^down_revision = "([^"]+)"$', source, re.MULTILINE)
    assert revision and down_revision
    return revision.group(1), down_revision.group(1)


def test_homepage_category_migration_extends_canonical_head() -> None:
    revision, down_revision = _revision_metadata()
    assert revision == "p2q3r4s5t6u7"
    assert down_revision == "3d4e5f6a7b8c"


def test_homepage_edit_categories_remain_under_occasion_wear() -> None:
    source = MIGRATION.read_text()
    assert '"shop-edits-occasion-wear"' in source
    assert "occasion_wear_id = _find_id" in source
    assert "parent_id=occasion_wear_id" in source
    assert "parent_id=shop_edits_id" in source
    assert source.index("occasion_wear_id = _find_id") < source.index(
        "parent_id=occasion_wear_id"
    )


def test_homepage_category_downgrade_is_non_destructive() -> None:
    source = MIGRATION.read_text()
    assert "def downgrade():" in source
    downgrade = source.split("def downgrade():", 1)[1]
    assert "DELETE FROM categories" not in downgrade
    assert "pass" in downgrade


def test_name_reuse_repairs_the_requested_slug_deterministically() -> None:
    source = MIGRATION.read_text()
    assert 'SELECT id FROM categories WHERE slug = :slug' in source
    assert 'SELECT id FROM categories WHERE name = :name' in source
    assert "SET name = :name, slug = :slug" in source
