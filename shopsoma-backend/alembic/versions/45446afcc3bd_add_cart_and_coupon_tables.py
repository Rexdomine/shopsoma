"""add cart and coupon tables

Revision ID: 45446afcc3bd
Revises: 48f6f0a9b3ab
Create Date: 2025-11-15 12:56:56.465565

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '45446afcc3bd'
down_revision: Union[str, None] = '48f6f0a9b3ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create cart_items table
    op.create_table(
        'cart_items',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('product_id', UUID(as_uuid=True), nullable=False),
        sa.Column('variant_id', sa.String(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cart_items_id'), 'cart_items', ['id'], unique=False)
    op.create_index(op.f('ix_cart_items_session_id'), 'cart_items', ['session_id'], unique=False)

    # Create coupons table
    op.create_table(
        'coupons',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('discount_type', sa.String(), nullable=False),
        sa.Column('discount_value', sa.Float(), nullable=False),
        sa.Column('min_purchase', sa.Float(), nullable=True),
        sa.Column('max_discount', sa.Float(), nullable=True),
        sa.Column('usage_limit', sa.Integer(), nullable=True),
        sa.Column('used_count', sa.Integer(), nullable=True),
        sa.Column('valid_from', sa.DateTime(), nullable=False),
        sa.Column('valid_until', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_coupons_code'), 'coupons', ['code'], unique=True)
    op.create_index(op.f('ix_coupons_id'), 'coupons', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_coupons_id'), table_name='coupons')
    op.drop_index(op.f('ix_coupons_code'), table_name='coupons')
    op.drop_table('coupons')
    op.drop_index(op.f('ix_cart_items_session_id'), table_name='cart_items')
    op.drop_index(op.f('ix_cart_items_id'), table_name='cart_items')
    op.drop_table('cart_items')
