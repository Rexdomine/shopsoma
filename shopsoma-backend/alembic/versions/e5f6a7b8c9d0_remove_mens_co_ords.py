"""remove men's co-ords category

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c6
Create Date: 2026-01-19 16:05:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    co_ords_id = conn.execute(
        sa.text("SELECT id FROM categories WHERE slug = 'men-co-ords' LIMIT 1")
    ).scalar()
    if not co_ords_id:
        return

    conn.execute(
        sa.text(
            """
            UPDATE categories
            SET is_active = FALSE, updated_at = now()
            WHERE id = :category_id
            """
        ),
        {"category_id": co_ords_id},
    )


def downgrade():
    # No-op to avoid reactivating categories that may have been intentionally disabled.
    pass
