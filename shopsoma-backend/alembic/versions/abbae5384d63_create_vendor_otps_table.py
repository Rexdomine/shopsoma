"""create_vendor_otps_table

Revision ID: abbae5384d63
Revises: 3f110cfcb80f
Create Date: 2025-12-03 15:56:45.061571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abbae5384d63'
down_revision: Union[str, None] = '3f110cfcb80f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create vendor_otps table
    op.create_table(
        'vendor_otps',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('vendor_id', sa.UUID(), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('code_hash', sa.String(255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='5'),
        sa.Column('is_used', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_vendor_otps_vendor_id', 'vendor_otps', ['vendor_id'])
    op.create_index('ix_vendor_otps_email', 'vendor_otps', ['email'])

    # Create foreign key
    op.create_foreign_key(
        'fk_vendor_otps_vendor_id',
        'vendor_otps', 'vendors',
        ['vendor_id'], ['id'],
        ondelete='CASCADE'
    )


def downgrade() -> None:
    # Drop foreign key
    op.drop_constraint('fk_vendor_otps_vendor_id', 'vendor_otps', type_='foreignkey')

    # Drop indexes
    op.drop_index('ix_vendor_otps_email', 'vendor_otps')
    op.drop_index('ix_vendor_otps_vendor_id', 'vendor_otps')

    # Drop table
    op.drop_table('vendor_otps')
