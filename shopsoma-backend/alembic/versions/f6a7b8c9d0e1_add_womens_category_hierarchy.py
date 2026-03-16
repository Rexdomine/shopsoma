"""add women's category hierarchy

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-01-19 16:30:00.000000
"""
from alembic import op
import sqlalchemy as sa
import uuid


# revision identifiers, used by Alembic.
revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
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


def _upsert_category(conn, name: str, slug: str, parent_id, display_order: int):
    existing = _get_category_id(conn, name, slug)
    if existing:
        conn.execute(
            sa.text(
                """
                UPDATE categories
                SET name = :name,
                    slug = :slug,
                    parent_id = :parent_id,
                    display_order = :display_order,
                    is_active = TRUE,
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "id": existing,
                "name": name,
                "slug": slug,
                "parent_id": parent_id,
                "display_order": display_order,
            },
        )
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

    women_id = _upsert_category(conn, "Women", "women", None, 2)

    subcategories = [
        {
            "name": "Women's Tops",
            "slug": "women-tops",
            "display_order": 1,
            "children": [
                {"name": "Women's T-Shirts", "slug": "women-tops-t-shirts", "display_order": 1},
                {"name": "Women's Shirts", "slug": "women-tops-shirts", "display_order": 2},
                {"name": "Women's Blouses", "slug": "women-tops-blouses", "display_order": 3},
            ],
        },
        {
            "name": "Women's Dresses",
            "slug": "women-dresses",
            "display_order": 2,
            "children": [
                {"name": "Casual Dresses", "slug": "women-dresses-casual", "display_order": 1},
                {"name": "Party Dresses", "slug": "women-dresses-party", "display_order": 2},
                {"name": "Formal Dresses", "slug": "women-dresses-formal", "display_order": 3},
            ],
        },
        {
            "name": "Women's Bottoms",
            "slug": "women-bottoms",
            "display_order": 3,
            "children": [
                {"name": "Women's Jeans", "slug": "women-bottoms-jeans", "display_order": 1},
                {"name": "Women's Skirts", "slug": "women-bottoms-skirts", "display_order": 2},
                {"name": "Women's Trousers", "slug": "women-bottoms-trousers", "display_order": 3},
            ],
        },
        {
            "name": "Women's Accessories",
            "slug": "women-accessories",
            "display_order": 4,
            "children": [
                {"name": "Women's Jewellery", "slug": "women-accessories-jewellery", "display_order": 1},
                {"name": "Women's Bracelets", "slug": "women-accessories-bracelets", "display_order": 2},
                {"name": "Women's Earrings", "slug": "women-accessories-earrings", "display_order": 3},
                {"name": "Women's Necklace", "slug": "women-accessories-necklace", "display_order": 4},
                {"name": "Women's Rings", "slug": "women-accessories-rings", "display_order": 5},
                {"name": "Women's Watches", "slug": "women-accessories-watches", "display_order": 6},
                {"name": "Women's Anklets", "slug": "women-accessories-anklets", "display_order": 7},
                {"name": "Women's Body Jewellery", "slug": "women-accessories-body-jewellery", "display_order": 8},
                {"name": "Women's Brooches", "slug": "women-accessories-brooches", "display_order": 9},
                {"name": "Women's Bags", "slug": "women-accessories-bags", "display_order": 10},
                {"name": "Women's Belts", "slug": "women-accessories-belts", "display_order": 11},
                {"name": "Women's Sunglasses", "slug": "women-accessories-sunglasses", "display_order": 12},
            ],
        },
        {
            "name": "Women's Shoes",
            "slug": "women-shoes",
            "display_order": 5,
            "children": [
                {"name": "Women's Flats", "slug": "women-shoes-flats", "display_order": 1},
                {"name": "Women's Heels", "slug": "women-shoes-heels", "display_order": 2},
            ],
        },
        {
            "name": "Women's Activewear",
            "slug": "women-activewear",
            "display_order": 6,
            "children": [
                {"name": "Women's Activewear Tops", "slug": "women-activewear-tops", "display_order": 1},
                {"name": "Women's Activewear Bottoms", "slug": "women-activewear-bottoms", "display_order": 2},
            ],
        },
        {
            "name": "Women's Outerwear",
            "slug": "women-outerwear",
            "display_order": 7,
            "children": [
                {"name": "Women's Jackets", "slug": "women-outerwear-jackets", "display_order": 1},
                {"name": "Women's Kaftan", "slug": "women-outerwear-kaftan", "display_order": 2},
                {"name": "Women's Kimonos", "slug": "women-outerwear-kimonos", "display_order": 3},
                {"name": "Women's Ponchos", "slug": "women-outerwear-ponchos", "display_order": 4},
                {"name": "Women's Hoodies/Sweatshirts", "slug": "women-outerwear-hoodies-sweatshirts", "display_order": 5},
            ],
        },
        {
            "name": "Women's Swimwear",
            "slug": "women-swimwear",
            "display_order": 8,
            "children": [],
        },
        {
            "name": "Women's Lingerie/Pyjamas",
            "slug": "women-lingerie-pyjamas",
            "display_order": 9,
            "children": [],
        },
    ]

    allowed_sub_slugs = []
    allowed_child_slugs = []

    for sub in subcategories:
        sub_id = _upsert_category(
            conn,
            sub["name"],
            sub["slug"],
            women_id,
            sub["display_order"],
        )
        allowed_sub_slugs.append(sub["slug"])
        for child in sub["children"]:
            _upsert_category(
                conn,
                child["name"],
                child["slug"],
                sub_id,
                child["display_order"],
            )
            allowed_child_slugs.append(child["slug"])

    conn.execute(
        sa.text(
            """
            UPDATE categories
            SET is_active = FALSE, updated_at = now()
            WHERE parent_id = :women_id
              AND slug NOT IN :allowed_slugs
            """
        ),
        {"women_id": women_id, "allowed_slugs": tuple(allowed_sub_slugs)},
    )

    if allowed_child_slugs:
        conn.execute(
            sa.text(
                """
                UPDATE categories
                SET is_active = FALSE, updated_at = now()
                WHERE parent_id IN (
                    SELECT id FROM categories WHERE parent_id = :women_id
                )
                  AND slug NOT IN :allowed_child_slugs
                """
            ),
            {"women_id": women_id, "allowed_child_slugs": tuple(allowed_child_slugs)},
        )


def downgrade():
    # No-op to avoid removing categories that may now contain products.
    pass
