"""add durable legacy variant stock inheritance marker

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_variants",
        sa.Column("inherits_stock", sa.Boolean(), nullable=True),
    )
    # Existing rows are intentionally left unknown. Axis-less rows can be
    # explicitly stocked, so inferring inheritance would overwrite inventory.


def downgrade() -> None:
    op.drop_column("product_variants", "inherits_stock")
