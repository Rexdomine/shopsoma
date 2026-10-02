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

    # Men's Accessories: ensure linked to Men parent
    conn.execute(
        sa.text(
            """
            UPDATE categories
            SET parent_id = :men_id,
                display_order = 6,
                is_active = TRUE,
                updated_at = now()
            WHERE (slug = 'men-accessories' OR slug = 'accessories')
              AND parent_id IS NULL
            """
        ),
        {"men_id": men_id},
    )
    _ensure_category(
        conn,
        "Accessories",
        "men-accessories",
        men_id,
        6,
        "Men's accessories",
    )

    # Men's Activewear: Activewear Accessories
    men_activewear_id = _find_category(conn, "Activewear", "men-activewear", men_id)
    if men_activewear_id:
        _ensure_category(
            conn,
            "Activewear Accessories",
            "men-activewear-accessories",
            men_activewear_id,
            3,
            "Men's activewear accessories",
        )

    # Men's Sets
    mens_sets_id = _ensure_category(
        conn,
        "Men's Sets",
        "men-sets",
        men_id,
        4,
        "Men's matching sets and co-ords",
    )
    _ensure_category(
        conn,
        "Trouser Sets",
        "men-sets-trouser-sets",
        mens_sets_id,
        1,
        "Men's trouser sets",
    )
    _ensure_category(
        conn,
        "Shorts Sets",
        "men-sets-shorts-sets",
        mens_sets_id,
        2,
        "Men's shorts sets",
    )

    # Women's Activewear: Activewear Accessories
    women_activewear_id = _find_category(conn, "Women's Activewear", "women-activewear", women_id)
    if women_activewear_id:
        _ensure_category(
            conn,
            "Activewear Accessories",
            "women-activewear-accessories",
            women_activewear_id,
            3,
            "Women's activewear accessories",
        )

    # Women's Swimwear
    _ensure_category(
        conn,
        "Women's Swimwear",
        "women-swimwear",
        women_id,
        8,
        "Women's swimwear",
    )

    # Women's Lingerie/Pyjamas and subcategories
    women_lingerie_id = _ensure_category(
        conn,
        "Women's Lingerie/Pyjamas",
        "women-lingerie-pyjamas",
        women_id,
        9,
        "Women's lingerie and pyjamas",
    )
    _ensure_category(
        conn,
        "Shapewear",
        "women-lingerie-shapewear",
        women_lingerie_id,
        1,
        "Women's shapewear",
    )
    _ensure_category(
        conn,
        "Bras & Bralettes",
        "women-lingerie-bras-bralettes",
        women_lingerie_id,
        2,
        "Bras and bralettes",
    )
    _ensure_category(
        conn,
        "Panties & Briefs",
        "women-lingerie-panties-briefs",
        women_lingerie_id,
        3,
        "Panties and briefs",
    )
    _ensure_category(
        conn,
        "Pyjamas & Sleepwear",
        "women-lingerie-pyjamas-sleepwear",
        women_lingerie_id,
        4,
        "Pyjamas and sleepwear",
    )
    _ensure_category(
        conn,
        "Robes & Loungewear",
        "women-lingerie-robes-loungewear",
        women_lingerie_id,
        5,
        "Robes and loungewear",
    )
    _ensure_category(
        conn,
        "Lingerie Sets",
        "women-lingerie-sets",
        women_lingerie_id,
        6,
        "Lingerie sets",
    )

    # Women's Sets
    womens_sets_id = _ensure_category(
        conn,
        "Women's Sets",
        "women-sets",
        women_id,
        10,
        "Women's matching sets and co-ords",
    )
    _ensure_category(
        conn,
        "Trouser Sets",
        "women-sets-trouser-sets",
        womens_sets_id,
        1,
        "Women's trouser sets",
    )
    _ensure_category(
        conn,
        "Skirt Sets",
        "women-sets-skirt-sets",
        womens_sets_id,
        2,
        "Women's skirt sets",
    )
    _ensure_category(
        conn,
        "Shorts Sets",
        "women-sets-shorts-sets",
        womens_sets_id,
        3,
        "Women's shorts sets",
    )


def downgrade():
    pass
