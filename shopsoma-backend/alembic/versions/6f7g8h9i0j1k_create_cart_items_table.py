"""create cart_items table

Revision ID: 6f7g8h9i0j1k
Revises: 5a1b2c3d4e5f
Create Date: 2025-11-26 15:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = '6f7g8h9i0j1k'
down_revision: Union[str, None] = '5a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create cart_items table"""
    op.create_table(
        'cart_items',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('product_id', UUID(as_uuid=True), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('variant_id', UUID(as_uuid=True), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    # Create indexes
    op.create_index('ix_cart_items_id', 'cart_items', ['id'])
    op.create_index('ix_cart_items_session_id', 'cart_items', ['session_id'])


def downgrade() -> None:
    """Drop cart_items table"""
    op.drop_index('ix_cart_items_session_id', table_name='cart_items')
    op.drop_index('ix_cart_items_id', table_name='cart_items')
    op.drop_table('cart_items')
