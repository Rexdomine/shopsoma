"""add_wishlist_table

Revision ID: 5ec6095c2c06
Revises: c7ebcfc2223e
Create Date: 2025-11-21 08:02:46.366479

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ec6095c2c06'
down_revision: Union[str, None] = 'c7ebcfc2223e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create wishlists table
    op.create_table(
        'wishlists',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'product_id', name='uq_user_product_wishlist')
    )

    # Create indexes for better query performance
    op.create_index('ix_wishlists_user_id', 'wishlists', ['user_id'])
    op.create_index('ix_wishlists_product_id', 'wishlists', ['product_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_wishlists_product_id', table_name='wishlists')
    op.drop_index('ix_wishlists_user_id', table_name='wishlists')

    # Drop table
    op.drop_table('wishlists')
