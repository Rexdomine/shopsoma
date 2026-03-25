"""add currency to orders and order items

Revision ID: i5j6k7l8m9n0
Revises: c1d2e3f4g5h6
Create Date: 2026-03-25 13:55:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "i5j6k7l8m9n0"
down_revision = "c1d2e3f4g5h6"
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
    if not _column_exists("order_items", "currency"):
        op.add_column(
            "order_items",
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="NGN"),
        )


def downgrade():
    if _column_exists("order_items", "currency"):
        op.drop_column("order_items", "currency")
    if _column_exists("orders", "currency"):
        op.drop_column("orders", "currency")
