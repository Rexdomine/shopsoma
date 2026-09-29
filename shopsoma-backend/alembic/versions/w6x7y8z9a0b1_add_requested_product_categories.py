"""add requested product category hierarchy

Revision ID: w6x7y8z9a0b1
Revises: f6a7b8c9d0e1
Create Date: 2026-09-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
import uuid


revision = "w6x7y8z9a0b1"
down_revision = "f6a7b8c9d0e1"
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


def _ensure_category(conn, name: str, slug: str, parent_id, display_order: int):
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
            },
        )
        return category_id

    category_id = uuid.uuid4()
    conn.execute(
        sa.text(
            """
            INSERT INTO categories
                (id, name, slug, parent_id, display_order, is_active, created_at, updated_at)
            VALUES (:id, :name, :slug, :parent_id, :display_order, TRUE, now(), now())
            """
        ),
        {
            "id": category_id,
            "name": name,
            "slug": slug,
            "parent_id": parent_id,
            "display_order": display_order,
        },
    )
    return category_id


def upgrade():
    conn = op.get_bind()

    # The original schema made names globally unique. Slugs are the stable
    # identifier, while the same display name can be valid in separate trees.
    # The downgrade intentionally leaves this constraint absent because the
    # requested hierarchy contains duplicate display names under separate
    # parents. Make re-upgrades safe after that downgrade path.
    op.execute("ALTER TABLE categories DROP CONSTRAINT IF EXISTS categories_name_key")

    men_id = _find_category(conn, "Men", "men", None)
    women_id = _find_category(conn, "Women", "women", None)
    if not men_id or not women_id:
        return

    men_activewear_id = _find_category(conn, "Activewear", "men-activewear", men_id)
    if men_activewear_id:
        _ensure_category(
            conn,
            "Activewear Accessories",
            "men-activewear-accessories",
            men_activewear_id,
            3,
        )

    women_activewear_id = _find_category(conn, "Women's Activewear", "women-activewear", women_id)
    if women_activewear_id:
        _ensure_category(
            conn,
            "Activewear Accessories",
            "women-activewear-accessories",
            women_activewear_id,
            3,
        )

    mens_sets_id = _ensure_category(conn, "Men's Sets", "men-sets", men_id, 4)
    _ensure_category(conn, "Trouser Sets", "men-sets-trouser-sets", mens_sets_id, 1)

    womens_sets_id = _ensure_category(conn, "Women's Sets", "women-sets", women_id, 10)
    _ensure_category(conn, "Trouser Sets", "women-sets-trouser-sets", womens_sets_id, 1)
    _ensure_category(conn, "Skirt Sets", "women-sets-skirt-sets", womens_sets_id, 2)


def downgrade():
    # Keep categories and products intact on downgrade. The name constraint is
    # intentionally not restored because valid duplicate names may remain.
    pass
