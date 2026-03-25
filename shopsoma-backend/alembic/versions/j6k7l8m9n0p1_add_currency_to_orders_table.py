"""add currency to orders table

Revision ID: j6k7l8m9n0p1
Revises: i5j6k7l8m9n0
Create Date: 2026-03-25 14:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "j6k7l8m9n0p1"
down_revision = "i5j6k7l8m9n0"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade():
    if not _column_exists("orders", "currency"):
        op.add_column(
            "orders",
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="NGN"),
        )


def downgrade():
    if _column_exists("orders", "currency"):
        op.drop_column("orders", "currency")
