import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND_ROOT / (
    "alembic/versions/y8z9a0b1c2d3_add_requested_storefront_categories.py"
)


def test_requested_category_migration_targets_current_head():
    source = MIGRATION.read_text(encoding="utf-8")
    assert re.search(r'^revision = "y8z9a0b1c2d3"$', source, re.MULTILINE)
    assert re.search(r'^down_revision = "x7y8z9a0b1c2"$', source, re.MULTILINE)


def test_requested_category_slugs_and_names_are_present():
    source = MIGRATION.read_text(encoding="utf-8")
    for slug in (
        "women-tops-bodysuit",
        "women-tops-tank-tops",
        "women-bottoms-shorts",
        "women-dresses-beach-dresses",
        "men-outerwear-jackets",
        "women-lingerie-pyjamas",
        "women-lingerie-shapewear",
        "women-lingerie-bras-bralettes",
        "women-lingerie-panties-briefs",
        "women-lingerie-pyjamas-sleepwear",
        "women-lingerie-robes-loungewear",
        "women-lingerie-sets",
        "women-sets",
        "women-sets-trouser-sets",
        "women-sets-skirt-sets",
        "women-sets-shorts-sets",
        "men-sets",
        "men-sets-trouser-sets",
        "men-sets-shorts-sets",
        "men-accessories",
        "men-activewear-accessories",
        "women-activewear-accessories",
    ):
        assert slug in source
    assert '"Bodysuit"' in source
    assert '"Tank Tops"' in source
    assert '"Shorts"' in source
    assert '"Beach Dresses"' in source
    assert '"Jackets"' in source
    assert '"Women\'s Lingerie/Pyjamas"' in source
    assert '"Shapewear"' in source
    assert '"Bras & Bralettes"' in source
    assert '"Panties & Briefs"' in source
    assert '"Pyjamas & Sleepwear"' in source
    assert '"Robes & Loungewear"' in source
    assert '"Lingerie Sets"' in source
    assert '"Women\'s Sets"' in source
    assert '"Men\'s Sets"' in source


def test_requested_category_migration_can_reupgrade_after_downgrade():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "DROP CONSTRAINT IF EXISTS categories_name_key" in source


def test_seed_categories_contains_requested_categories():
    seed_source = (BACKEND_ROOT / "seed_categories.py").read_text(encoding="utf-8")
    for slug in (
        "women-tops-bodysuit",
        "women-tops-tank-tops",
        "women-bottoms-shorts",
        "women-dresses-beach-dresses",
        "men-outerwear-jackets",
        "women-lingerie-pyjamas",
        "women-lingerie-shapewear",
        "women-lingerie-bras-bralettes",
        "women-lingerie-panties-briefs",
        "women-lingerie-pyjamas-sleepwear",
        "women-lingerie-robes-loungewear",
        "women-lingerie-sets",
        "women-sets",
        "women-sets-trouser-sets",
        "women-sets-skirt-sets",
        "women-sets-shorts-sets",
        "men-sets",
        "men-sets-trouser-sets",
        "men-sets-shorts-sets",
        "men-accessories",
        "men-activewear-accessories",
        "women-activewear-accessories",
    ):
        assert slug in seed_source
    assert '"Bodysuit"' in seed_source
    assert '"Tank Tops"' in seed_source
    assert '"Shorts"' in seed_source
    assert '"Beach Dresses"' in seed_source
    assert '"Jackets"' in seed_source
    assert '"Women\'s Lingerie/Pyjamas"' in seed_source
    assert '"Shapewear"' in seed_source
    assert '"Bras & Bralettes"' in seed_source
    assert '"Panties & Briefs"' in seed_source
    assert '"Pyjamas & Sleepwear"' in seed_source
    assert '"Robes & Loungewear"' in seed_source
    assert '"Lingerie Sets"' in seed_source
    assert '"Women\'s Sets"' in seed_source
    assert '"Men\'s Sets"' in seed_source
