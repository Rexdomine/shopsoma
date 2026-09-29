import re
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND_ROOT / (
    "alembic/versions/w6x7y8z9a0b1_add_requested_product_categories.py"
)


def test_requested_category_migration_targets_current_category_head():
    source = MIGRATION.read_text()
    assert re.search(r'^revision = "w6x7y8z9a0b1"$', source, re.MULTILINE)
    assert re.search(r'^down_revision = "f6a7b8c9d0e1"$', source, re.MULTILINE)


def test_requested_category_slugs_and_parent_relationships_are_present():
    source = MIGRATION.read_text()
    for slug in (
        "men-activewear-accessories",
        "men-sets",
        "men-sets-trouser-sets",
        "women-sets",
        "women-sets-trouser-sets",
        "women-sets-skirt-sets",
    ):
        assert slug in source
    assert '"Men\'s Sets"' in source
    assert '"Women\'s Sets"' in source
    assert '"Trouser Sets"' in source
    assert '"Skirt Sets"' in source


def test_category_model_allows_duplicate_display_names():
    source = (BACKEND_ROOT / "app/models/category.py").read_text()
    assert 'name = Column(String(100), nullable=False)' in source
    assert 'name = Column(String(100), unique=True' not in source
