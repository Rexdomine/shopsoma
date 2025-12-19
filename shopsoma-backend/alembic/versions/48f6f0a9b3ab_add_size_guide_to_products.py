"""add size guide to products

Revision ID: 48f6f0a9b3ab
Revises: 3a9bcaf3fd5f
Create Date: 2025-03-07 12:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '48f6f0a9b3ab'
down_revision = '3a9bcaf3fd5f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('size_guide', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'size_guide')
