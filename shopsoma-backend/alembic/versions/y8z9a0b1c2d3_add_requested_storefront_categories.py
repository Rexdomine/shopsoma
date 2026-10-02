"""add requested storefront product category hierarchy

Revision ID: y8z9a0b1c2d3
Revises: x7y8z9a0b1c2
Create Date: 2026-10-01 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
import uuid


revision = "y8z9a0b1c2d3"
down_revision = "x7y8z9a0b1c2"
branch_labels = None
depends_on = None


def _find_category(conn, name: str, slug: str, parent_id):
    category_id = conn.execute(
        sa.text("SELECT id FROM categories WHERE slug = :slug"),
        {"slug": slug},
    ).scalar()
    if category_id:
        return category_id

    return conn.execute(
        sa.text(
            """
            SELECT id FROM categories
            WHERE name = :name AND parent_id IS NOT DISTINCT FROM :parent_id
            LIMIT 1
            """
        ),
        {"name": name, "parent_id": parent_id},
    ).scalar()


def _ensure_category(conn, name: str, slug: str, parent_id, display_order: int, description: str = None):
    category_id = _find_category(conn, name, slug, parent_id)
    if category_id:
        conn.execute(
            sa.text(
                """
                UPDATE categories
                SET name = :name,
                    slug = :slug,
                    parent_id = :parent_id,
                    display_order = :display_order,
                    description = COALESCE(:description, description),
                    is_active = TRUE,
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "id": category_id,
                "name": name,
                "slug": slug,
                "parent_id": parent_id,
                "display_order": display_order,
                "description": description or name,
            },
        )
        return category_id

    category_id = uuid.uuid4()
    conn.execute(
        sa.text(
            """
            INSERT INTO categories
                (id, name, slug, parent_id, display_order, description, is_active, created_at, updated_at)
            VALUES (:id, :name, :slug, :parent_id, :display_order, :description, TRUE, now(), now())
            """
        ),
        {
            "id": category_id,
            "name": name,
            "slug": slug,
            "parent_id": parent_id,
            "display_order": display_order,
            "description": description or name,
        },
    )
    return category_id


def upgrade():
    conn = op.get_bind()

    op.execute("ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_name_key")

    men_id = _find_category(conn, "Men", "men", None)
    women_id = _find_category(conn, "Women", "women", None)
    if not men_id or not women_id:
        return

    # Women's Tops: Bodysuit, Tank Tops
    women_tops_id = _find_category(conn, "Women's Tops", "women-tops", women_id)
    if women_tops_id:
        _ensure_category(
            conn,
            "Bodysuit",
            "women-tops-bodysuit",
            women_tops_id,
            4,
            "Bodysuit",
        )
        _ensure_category(
            conn,
            "Tank Tops",
            "women-tops-tank-tops",
            women_tops_id,
            5,
            "Tank tops",
        )

    # Women's Bottoms: Shorts
    women_bottoms_id = _find_category(conn, "Women's Bottoms", "women-bottoms", women_id)
    if women_bottoms_id:
        _ensure_category(
            conn,
            "Shorts",
            "women-bottoms-shorts",
            women_bottoms_id,
            4,
            "Women's shorts",
        )

    # Women's Dresses: Beach Dresses
    women_dresses_id = _find_category(conn, "Women's Dresses", "women-dresses", women_id)
    if women_dresses_id:
        _ensure_category(
            conn,
            "Beach Dresses",
            "women-dresses-beach-dresses",
            women_dresses_id,
            4,
            "Beach dresses",
        )

    # Men's Outerwear: Jackets
    men_outerwear_id = _find_category(conn, "Outerwear", "men-outerwear", men_id)
    if men_outerwear_id:
        _ensure_category(
            conn,
            "Jackets",
            "men-outerwear-jackets",
            men_outerwear_id,
            2,
            "Men's jackets",
        )


def downgrade():
    pass
