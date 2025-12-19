"""create_vendor_payment_methods_table

Revision ID: d8e9f0a1b2c3
Revises: abbae5384d63
Create Date: 2025-12-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd8e9f0a1b2c3'
down_revision = '92998e4016c5'
branch_labels = None
depends_on = None


def upgrade():
    # Create vendor_payment_methods table
    op.create_table(
        'vendor_payment_methods',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('vendor_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('account_type', sa.String(length=50), nullable=True),
        sa.Column('bank_name', sa.String(length=100), nullable=False),
        sa.Column('account_number', sa.String(length=50), nullable=False),
        sa.Column('account_holder', sa.String(length=255), nullable=False),
        sa.Column('tin', sa.String(length=50), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ondelete='CASCADE'),
    )

    # Create indexes
    op.create_index('ix_vendor_payment_methods_id', 'vendor_payment_methods', ['id'])
    op.create_index('ix_vendor_payment_methods_vendor_id', 'vendor_payment_methods', ['vendor_id'])
    op.create_index('ix_vendor_payment_methods_is_default', 'vendor_payment_methods', ['is_default'])


def downgrade():
    op.drop_index('ix_vendor_payment_methods_is_default', table_name='vendor_payment_methods')
    op.drop_index('ix_vendor_payment_methods_vendor_id', table_name='vendor_payment_methods')
    op.drop_index('ix_vendor_payment_methods_id', table_name='vendor_payment_methods')
    op.drop_table('vendor_payment_methods')
