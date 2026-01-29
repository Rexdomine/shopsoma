"""add return order item details

Revision ID: b9f1c2d3e4f5
Revises: h4i5j6k7l8m9
Create Date: 2026-01-26 13:12:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'b9f1c2d3e4f5'
down_revision = 'g3h4i5j6k7l8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('returns', sa.Column('order_item_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('returns', sa.Column('request_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key(
        'fk_returns_order_item_id',
        'returns',
        'order_items',
        ['order_item_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    op.create_index('ix_returns_order_item_id', 'returns', ['order_item_id'])


def downgrade():
    op.drop_index('ix_returns_order_item_id', table_name='returns')
    op.drop_constraint('fk_returns_order_item_id', 'returns', type_='foreignkey')
    op.drop_column('returns', 'request_details')
    op.drop_column('returns', 'order_item_id')
