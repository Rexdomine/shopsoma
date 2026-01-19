"""add men's category hierarchy

Revision ID: c2f9a1b4d7e8
Revises: 9a2b3c4d5e6f
Create Date: 2026-01-19 15:15:00.000000
"""
from alembic import op
import sqlalchemy as sa
import uuid


# revision identifiers, used by Alembic.
revision = "c2f9a1b4d7e8"
down_revision = "9a2b3c4d5e6f"
branch_labels = None
depends_on = None


def _get_category_id(conn, name: str, slug: str):
    return conn.execute(
        sa.text(
            """
            SELECT id FROM categories
            WHERE slug = :slug OR name = :name
            """
        ),
        {"slug": slug, "name": name},
    ).scalar()


def _ensure_category(conn, name: str, slug: str, parent_id, display_order: int):
    existing = _get_category_id(conn, name, slug)
    if existing:
        return existing
    new_id = uuid.uuid4()
    conn.execute(
        sa.text(
            """
            INSERT INTO categories (
                id, name, slug, parent_id, display_order, is_active, created_at, updated_at
            )
            VALUES (:id, :name, :slug, :parent_id, :display_order, TRUE, now(), now())
            """
        ),
        {
            "id": new_id,
            "name": name,
            "slug": slug,
            "parent_id": parent_id,
            "display_order": display_order,
        },
    )
    return new_id


def upgrade():
    conn = op.get_bind()

    men_id = _ensure_category(conn, "Men", "men", None, 1)
    shop_edits_id = _ensure_category(conn, "Shop Edits", "shop-edits", None, 4)

    subcategories = [
        {
            "name": "Tops",
            "slug": "men-tops",
            "display_order": 1,
            "children": [
                {"name": "T-Shirts", "slug": "men-tops-t-shirts", "display_order": 1},
                {"name": "Shirts", "slug": "men-tops-shirts", "display_order": 2},
            ],
        },
        {
            "name": "Bottoms",
            "slug": "men-bottoms",
            "display_order": 2,
            "children": [
                {"name": "Jeans", "slug": "men-bottoms-jeans", "display_order": 1},
                {"name": "Trousers", "slug": "men-bottoms-trousers", "display_order": 2},
                {"name": "Shorts", "slug": "men-bottoms-shorts", "display_order": 3},
            ],
        },
        {
            "name": "Activewear",
            "slug": "men-activewear",
            "display_order": 3,
            "children": [
                {"name": "Activewear Tops", "slug": "men-activewear-tops", "display_order": 1},
                {"name": "Activewear Bottoms", "slug": "men-activewear-bottoms", "display_order": 2},
            ],
        },
        {
            "name": "Co-ords",
            "slug": "men-co-ords",
            "display_order": 4,
            "children": [],
        },
        {
            "name": "Shoes",
            "slug": "men-shoes",
            "display_order": 5,
            "children": [
                {"name": "Casual Shoes", "slug": "men-shoes-casual", "display_order": 1},
                {"name": "Formal Shoes", "slug": "men-shoes-formal", "display_order": 2},
            ],
        },
        {
            "name": "Accessories",
            "slug": "men-accessories",
            "display_order": 6,
            "children": [
                {"name": "Watches/Jewellery", "slug": "men-accessories-watches-jewellery", "display_order": 1},
                {"name": "Wallets", "slug": "men-accessories-wallets", "display_order": 2},
                {"name": "Belts", "slug": "men-accessories-belts", "display_order": 3},
                {"name": "Sunglasses", "slug": "men-accessories-sunglasses", "display_order": 4},
                {"name": "Caps/Hats", "slug": "men-accessories-caps-hats", "display_order": 5},
            ],
        },
        {
            "name": "Outerwear",
            "slug": "men-outerwear",
            "display_order": 7,
            "children": [
                {"name": "Hoodies", "slug": "men-outerwear-hoodies", "display_order": 1},
            ],
        },
    ]

    for sub in subcategories:
        sub_id = _ensure_category(
            conn,
            sub["name"],
            sub["slug"],
            men_id,
            sub["display_order"],
        )
        for child in sub["children"]:
            _ensure_category(
                conn,
                child["name"],
                child["slug"],
                sub_id,
                child["display_order"],
            )

    shop_edits = [
        {
            "name": "Seasonal (Summer / Winter)",
            "slug": "shop-edits-seasonal",
            "display_order": 1,
            "children": [],
        },
        {
            "name": "Occasion Wear",
            "slug": "shop-edits-occasion-wear",
            "display_order": 2,
            "children": [
                {"name": "Casual", "slug": "shop-edits-occasion-wear-casual", "display_order": 1},
                {"name": "Workwear", "slug": "shop-edits-occasion-wear-workwear", "display_order": 2},
                {"name": "Party", "slug": "shop-edits-occasion-wear-party", "display_order": 3},
            ],
        },
        {
            "name": "Designer Picks",
            "slug": "shop-edits-designer-picks",
            "display_order": 3,
            "children": [],
        },
    ]

    for sub in shop_edits:
        sub_id = _ensure_category(
            conn,
            sub["name"],
            sub["slug"],
            shop_edits_id,
            sub["display_order"],
        )
        for child in sub["children"]:
            _ensure_category(
                conn,
                child["name"],
                child["slug"],
                sub_id,
                child["display_order"],
            )


def downgrade():
    # No-op to avoid removing categories that may now contain products.
    pass
