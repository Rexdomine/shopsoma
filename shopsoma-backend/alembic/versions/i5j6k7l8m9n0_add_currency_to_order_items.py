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


def upgrade():
    op.add_column(
        "orders",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="NGN"),
    )
    op.add_column(
        "order_items",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="NGN"),
    )


def downgrade():
    op.drop_column("order_items", "currency")
    op.drop_column("orders", "currency")
