"""add_brand_info_fields_to_vendors

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2025-12-05 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e1f2a3b4c5d6'
down_revision = 'd8e9f0a1b2c3'
branch_labels = None
depends_on = None


def upgrade():
    # Add new brand info fields to vendors table
    op.add_column('vendors', sa.Column('open_days', postgresql.ARRAY(sa.String(3)), nullable=True))
    op.add_column('vendors', sa.Column('open_hour', sa.String(5), nullable=True))
    op.add_column('vendors', sa.Column('close_hour', sa.String(5), nullable=True))
    op.add_column('vendors', sa.Column('returning_address', sa.Text(), nullable=True))
    op.add_column('vendors', sa.Column('secondary_contacts', postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column('vendors', 'secondary_contacts')
    op.drop_column('vendors', 'returning_address')
    op.drop_column('vendors', 'close_hour')
    op.drop_column('vendors', 'open_hour')
    op.drop_column('vendors', 'open_days')
