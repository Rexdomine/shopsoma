"""Keep homepage Shop Edits definitions identical across initialization paths."""

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_LEAVES = [
    ("Casual", "shop-edits-occasion-wear-casual", 1),
    ("Evening", "shop-edits-occasion-wear-evening", 2),
    ("Party", "shop-edits-occasion-wear-party", 3),
    ("Workwear", "shop-edits-occasion-wear-workwear", 4),
]


def _occasion_wear_children_from_seed():
    tree = ast.parse((ROOT / "seed_categories.py").read_text())
    categories_data = next(
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "categories_data" for target in node.targets)
    )
    categories = ast.literal_eval(categories_data)
    shop_edits = next(category for category in categories if category["slug"] == "shop-edits")
    occasion_wear = next(category for category in shop_edits["subcategories"] if category["slug"] == "shop-edits-occasion-wear")
    return [
        (child["name"], child["slug"], child["display_order"])
        for child in occasion_wear["children"]
    ]


def _leaves_from_migration():
    source = (ROOT / "alembic/versions/p2q3r4s5t6u7_ensure_homepage_edit_categories.py").read_text()
    match = re.search(r"for name, slug, order in \(\s*(.*?)\s*\):", source, re.DOTALL)
    assert match, "canonical homepage leaf migration loop is missing"
    return ast.literal_eval(f"[{match.group(1)}]")


def _homepage_slugs():
    source = (ROOT.parent / "shopsoma-frontend/src/pages/Home.tsx").read_text()
    return re.findall(r"slug:\s*'(shop-edits-occasion-wear-(?:casual|evening|party|workwear))'", source)


def test_shop_edit_seed_migration_and_homepage_leaf_contract_match():
    """Fresh seeds, migrations, and homepage cards share one ordered leaf contract."""
    assert _occasion_wear_children_from_seed() == CANONICAL_LEAVES
    assert _leaves_from_migration() == CANONICAL_LEAVES
    assert _homepage_slugs() == [slug for _, slug, _ in CANONICAL_LEAVES]
