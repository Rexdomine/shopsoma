"""add durable legacy variant price inheritance marker

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-23 17:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_variants",
        sa.Column("inherits_price", sa.Boolean(), nullable=True),
    )
    # Existing generic rows cannot be classified safely from equal prices:
    # equality also represents a legitimate explicit price. Mark them
    # conservative/explicit so future parent edits cannot overwrite them.
    op.execute(
        sa.text(
            "UPDATE product_variants SET inherits_price = FALSE "
            "WHERE size IS NULL AND color IS NULL AND inherits_price IS NULL"
        )
    )


def downgrade() -> None:
    op.drop_column("product_variants", "inherits_price")
