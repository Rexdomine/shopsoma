"""add_logo_to_vendors

Revision ID: f2g3h4i5j6k7
Revises: e1f2a3b4c5d6
Create Date: 2025-12-05 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f2g3h4i5j6k7'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    # Add logo_url field to vendors table
    op.add_column('vendors', sa.Column('logo_url', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('vendors', 'logo_url')
