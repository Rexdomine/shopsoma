"""add durable variation price inheritance markers

Revision ID: a7b8c9d0e1f2
Revises: p2q3r4s5t6u7
Create Date: 2026-09-18 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "p2q3r4s5t6u7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "variations",
        sa.Column("inherits_price", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "variations",
        sa.Column("inherits_sale_price", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("variations", "inherits_sale_price")
    op.drop_column("variations", "inherits_price")
