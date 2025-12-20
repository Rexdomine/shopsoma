"""Allow null variant_id on cart_items for products without variants.

Revision ID: b1c2d3e4f5g6
Revises: 66739681d75e
Create Date: 2025-12-19 18:12:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5g6"
down_revision = "66739681d75e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "cart_items",
        "variant_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "cart_items",
        "variant_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
