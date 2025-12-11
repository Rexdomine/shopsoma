"""create_collections_table

Revision ID: 94cb1a1d069d
Revises: 9965ca7f294b
Create Date: 2025-12-07 08:02:08.489729

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '94cb1a1d069d'
down_revision: Union[str, None] = '9965ca7f294b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create collections table
    op.create_table(
        'collections',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vendor_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ondelete='CASCADE')
    )

    # Create indexes
    op.create_index('ix_collections_vendor_id', 'collections', ['vendor_id'])
    op.create_index('ix_collections_slug', 'collections', ['slug'])

    # Add collection_id to products table
    op.add_column('products', sa.Column('collection_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_products_collection_id', 'products', ['collection_id'])
    op.create_foreign_key('fk_products_collection_id', 'products', 'collections', ['collection_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    # Remove collection_id from products table
    op.drop_constraint('fk_products_collection_id', 'products', type_='foreignkey')
    op.drop_index('ix_products_collection_id', 'products')
    op.drop_column('products', 'collection_id')

    # Drop collections table
    op.drop_index('ix_collections_slug', 'collections')
    op.drop_index('ix_collections_vendor_id', 'collections')
    op.drop_table('collections')
