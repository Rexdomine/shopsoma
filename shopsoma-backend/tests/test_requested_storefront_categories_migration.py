import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND_ROOT / (
    "alembic/versions/y8z9a0b1c2d3_add_requested_storefront_categories.py"
)


def test_requested_category_migration_targets_current_head():
    source = MIGRATION.read_text()
    assert re.search(r'^revision = "y8z9a0b1c2d3"$', source, re.MULTILINE)
    assert re.search(r'^down_revision = "x7y8z9a0b1c2"$', source, re.MULTILINE)


def test_requested_category_slugs_and_names_are_present():
    source = MIGRATION.read_text()
    for slug in (
        "women-tops-bodysuit",
        "women-tops-tank-tops",
        "women-bottoms-shorts",
        "women-dresses-beach-dresses",
        "men-outerwear-jackets",
    ):
        assert slug in source
    assert '"Bodysuit"' in source
    assert '"Tank Tops"' in source
    assert '"Shorts"' in source
    assert '"Beach Dresses"' in source
    assert '"Jackets"' in source


def test_requested_category_migration_can_reupgrade_after_downgrade():
    source = MIGRATION.read_text()
    assert "DROP CONSTRAINT IF EXISTS categories_name_key" in source


def test_seed_categories_contains_requested_categories():
    seed_source = (BACKEND_ROOT / "seed_categories.py").read_text()
    for slug in (
        "women-tops-bodysuit",
        "women-tops-tank-tops",
        "women-bottoms-shorts",
        "women-dresses-beach-dresses",
        "men-outerwear-jackets",
    ):
        assert slug in seed_source
    assert '"Bodysuit"' in seed_source
    assert '"Tank Tops"' in seed_source
    assert '"Shorts"' in seed_source
    assert '"Beach Dresses"' in seed_source
    assert '"Jackets"' in seed_source
