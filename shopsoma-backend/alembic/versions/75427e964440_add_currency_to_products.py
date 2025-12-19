"""add_currency_to_products

Revision ID: 75427e964440
Revises: cd3def809521
Create Date: 2025-12-18 16:25:35.609458

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '75427e964440'
down_revision: Union[str, None] = 'cd3def809521'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add currency column with default 'NGN'
    op.add_column('products', sa.Column('currency', sa.String(length=3), server_default='NGN', nullable=False))


def downgrade() -> None:
    # Remove currency column
    op.drop_column('products', 'currency')
