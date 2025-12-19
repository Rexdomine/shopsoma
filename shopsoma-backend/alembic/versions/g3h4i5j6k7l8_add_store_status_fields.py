"""add_store_status_fields

Revision ID: g3h4i5j6k7l8
Revises: f2g3h4i5j6k7
Create Date: 2025-12-05 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'g3h4i5j6k7l8'
down_revision = 'f2g3h4i5j6k7'
branch_labels = None
depends_on = None


def upgrade():
    # Add store status fields to vendors table
    op.add_column('vendors', sa.Column('store_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('vendors', sa.Column('store_paused_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('vendors', sa.Column('store_deleted_at', sa.DateTime(timezone=True), nullable=True))

    # Add indexes
    op.create_index('ix_vendors_store_active', 'vendors', ['store_active'])


def downgrade():
    op.drop_index('ix_vendors_store_active', table_name='vendors')
    op.drop_column('vendors', 'store_deleted_at')
    op.drop_column('vendors', 'store_paused_at')
    op.drop_column('vendors', 'store_active')
