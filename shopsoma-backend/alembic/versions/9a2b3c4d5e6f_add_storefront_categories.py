"""add storefront categories for perfumes and bags/wallets

Revision ID: 9a2b3c4d5e6f
Revises: 8f7c9a1b2c3d
Create Date: 2025-12-28 12:50:00.000000
"""
from alembic import op
import sqlalchemy as sa
import uuid


# revision identifiers, used by Alembic.
revision = "9a2b3c4d5e6f"
down_revision = "8f7c9a1b2c3d"
branch_labels = None
depends_on = None


def _get_category_id(conn, name: str):
    return conn.execute(
        sa.text("SELECT id FROM categories WHERE name = :name"),
        {"name": name},
    ).scalar()


def _ensure_category(conn, name: str, slug: str, parent_id=None):
    existing = _get_category_id(conn, name)
    if existing:
        return existing
    new_id = uuid.uuid4()
    conn.execute(
        sa.text(
            """
            INSERT INTO categories (id, name, slug, parent_id, display_order, is_active, created_at, updated_at)
            VALUES (:id, :name, :slug, :parent_id, 0, TRUE, now(), now())
            """
        ),
        {"id": new_id, "name": name, "slug": slug, "parent_id": parent_id},
    )
    return new_id


def upgrade():
    conn = op.get_bind()

    beauty_id = _ensure_category(conn, "Beauty", "beauty")

    accessories_id = _get_category_id(conn, "Accessories")
    if not accessories_id:
        accessories_id = _get_category_id(conn, "Bags/Accessories")
    if not accessories_id:
        accessories_id = _ensure_category(conn, "Accessories", "accessories")

    _ensure_category(conn, "Perfumes", "perfumes", beauty_id)
    _ensure_category(conn, "Bags & Wallets", "bags-wallets", accessories_id)


def downgrade():
    # No-op to avoid removing categories that may now contain products.
    pass
