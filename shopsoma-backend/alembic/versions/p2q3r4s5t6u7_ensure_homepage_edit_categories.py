"""ensure homepage edit categories exist

Revision ID: p2q3r4s5t6u7
Revises: 3d4e5f6a7b8c
Create Date: 2026-09-17 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
import uuid

revision = "p2q3r4s5t6u7"
down_revision = "3d4e5f6a7b8c"
branch_labels = None
depends_on = None


def _find_id(conn, slug: str, name: str | None = None):
    # Prefer the canonical slug, then fall back to a same-name legacy row.
    # If both identities exist on different rows, merge references into the
    # slug owner before applying canonical values to avoid unique-key failure.
    slug_id = conn.execute(
        sa.text("SELECT id FROM categories WHERE slug = :slug"),
        {"slug": slug},
    ).scalar()
    if name is None:
        return slug_id
    name_id = conn.execute(
        sa.text("SELECT id FROM categories WHERE name = :name"),
        {"name": name},
    ).scalar()
    if not slug_id or slug_id == name_id:
        return slug_id or name_id

    conn.execute(
        sa.text(
            "UPDATE products SET category_id = :slug_id "
            "WHERE category_id = :name_id"
        ),
        {"slug_id": slug_id, "name_id": name_id},
    )
    conn.execute(
        sa.text(
            "UPDATE categories SET parent_id = "
            "(SELECT parent_id FROM categories WHERE id = :name_id) "
            "WHERE id = :slug_id AND parent_id = :name_id"
        ),
        {"slug_id": slug_id, "name_id": name_id},
    )
    conn.execute(
        sa.text(
            "UPDATE categories SET parent_id = :slug_id "
            "WHERE parent_id = :name_id AND id <> :slug_id"
        ),
        {"slug_id": slug_id, "name_id": name_id},
    )
    conn.execute(
        sa.text("DELETE FROM categories WHERE id = :name_id"),
        {"name_id": name_id},
    )
    return slug_id


def _ensure_category(conn, *, name: str, slug: str, parent_id, description: str, display_order: int):
    existing_id = _find_id(conn, slug, name)
    if existing_id:
        conn.execute(
            sa.text(
                """
                UPDATE categories
                SET name = :name, slug = :slug, parent_id = :parent_id,
                    description = :description, display_order = :display_order,
                    is_active = TRUE, updated_at = now()
                WHERE id = :id
                """
            ),
            {
                "id": existing_id,
                "name": name,
                "slug": slug,
                "parent_id": parent_id,
                "description": description,
                "display_order": display_order,
            },
        )
        return existing_id

    category_id = uuid.uuid4()
    conn.execute(
        sa.text(
            """
            INSERT INTO categories
              (id, name, slug, description, parent_id, display_order, is_active, created_at, updated_at)
            VALUES
              (:id, :name, :slug, :description, :parent_id, :display_order, TRUE, now(), now())
            """
        ),
        {
            "id": category_id,
            "name": name,
            "slug": slug,
            "description": description,
            "parent_id": parent_id,
            "display_order": display_order,
        },
    )
    return category_id


def upgrade():
    conn = op.get_bind()
    shop_edits_id = _find_id(conn, "shop-edits", "Shop Edits")
    if not shop_edits_id:
        shop_edits_id = _ensure_category(
            conn,
            name="Shop Edits",
            slug="shop-edits",
            parent_id=None,
            description="Curated edits and seasonal picks",
            display_order=4,
        )

    occasion_wear_id = _find_id(
        conn, "shop-edits-occasion-wear", "Occasion Wear"
    )
    if not occasion_wear_id:
        occasion_wear_id = _ensure_category(
            conn,
            name="Occasion Wear",
            slug="shop-edits-occasion-wear",
            parent_id=shop_edits_id,
            description="Occasion wear edits",
            display_order=2,
        )

    for name, slug, order in (
        ("Casual", "shop-edits-occasion-wear-casual", 1),
        ("Evening", "shop-edits-occasion-wear-evening", 2),
        ("Party", "shop-edits-occasion-wear-party", 3),
        ("Workwear", "shop-edits-occasion-wear-workwear", 4),
    ):
        _ensure_category(
            conn,
            name=name,
            slug=slug,
            parent_id=occasion_wear_id,
            description=f"{name} edits",
            display_order=order,
        )


def downgrade():
    # This migration may reuse categories that predate it or already contain
    # products. Leave all rows in place so rollback cannot uncategorize data.
    pass
