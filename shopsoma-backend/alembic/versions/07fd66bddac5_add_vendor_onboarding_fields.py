"""add_vendor_onboarding_fields

Revision ID: 07fd66bddac5
Revises: abbae5384d63
Create Date: 2025-12-03 19:33:21.977910

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '07fd66bddac5'
down_revision: Union[str, None] = 'abbae5384d63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add onboarding fields to vendors table
    op.add_column('vendors', sa.Column('is_onboarding', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('vendors', sa.Column('brand_info_completed', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('vendors', sa.Column('payout_info_completed', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('vendors', sa.Column('onboarding_completed_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Remove onboarding fields from vendors table
    op.drop_column('vendors', 'onboarding_completed_at')
    op.drop_column('vendors', 'payout_info_completed')
    op.drop_column('vendors', 'brand_info_completed')
    op.drop_column('vendors', 'is_onboarding')
