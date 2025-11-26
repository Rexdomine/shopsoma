"""fix_cart_item_id_to_uuid

Revision ID: 66739681d75e
Revises: 6426a9fb711d
Create Date: 2025-11-25 20:48:30.829524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '66739681d75e'
down_revision: Union[str, None] = '6426a9fb711d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Since cart_items is transient data (shopping carts), we can safely truncate
    # existing data to avoid complex data migration
    op.execute('TRUNCATE TABLE cart_items CASCADE')

    # Drop the old String id column and create new UUID id column
    op.drop_column('cart_items', 'id')
    op.add_column('cart_items', sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')))
    op.create_primary_key('cart_items_pkey', 'cart_items', ['id'])
    op.create_index(op.f('ix_cart_items_id'), 'cart_items', ['id'], unique=False)

    # Convert variant_id from String to UUID
    op.drop_column('cart_items', 'variant_id')
    op.add_column('cart_items', sa.Column('variant_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False))


def downgrade() -> None:
    # Revert variant_id back to String
    op.drop_column('cart_items', 'variant_id')
    op.add_column('cart_items', sa.Column('variant_id', sa.String(), nullable=False))

    # Revert id back to String
    op.drop_index(op.f('ix_cart_items_id'), table_name='cart_items')
    op.execute('ALTER TABLE cart_items DROP CONSTRAINT cart_items_pkey')
    op.drop_column('cart_items', 'id')
    op.add_column('cart_items', sa.Column('id', sa.String(), nullable=False))
    op.create_primary_key('cart_items_pkey', 'cart_items', ['id'])
    op.create_index(op.f('ix_cart_items_id'), 'cart_items', ['id'], unique=False)
