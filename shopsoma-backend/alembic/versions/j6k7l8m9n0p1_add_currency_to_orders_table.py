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


def upgrade():
    op.add_column(
        "orders",
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="NGN"),
    )


def downgrade():
    op.drop_column("orders", "currency")
