"""create_vendor_applications_table

Revision ID: 92998e4016c5
Revises: 07fd66bddac5
Create Date: 2025-12-04 09:24:03.823554

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '92998e4016c5'
down_revision: Union[str, None] = '07fd66bddac5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'vendor_applications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('first_name', sa.String(100), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('phone_country_code', sa.String(10), nullable=False),
        sa.Column('phone_number', sa.String(20), nullable=False),
        sa.Column('business_name', sa.String(255), nullable=False),
        sa.Column('business_location', sa.Text, nullable=False),
        sa.Column('is_business_registered', sa.Text, nullable=True),
        sa.Column('product_categories', postgresql.ARRAY(sa.String), nullable=False),
        sa.Column('local_production_level', sa.String(100), nullable=False),
        sa.Column('years_in_business', sa.String(50), nullable=False),
        sa.Column('brand_story', sa.Text, nullable=True),
        sa.Column('website_link', sa.String(500), nullable=True),
        sa.Column('social_media_handles', postgresql.JSON, nullable=True),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending_review'),
        sa.Column('admin_notes', sa.Text, nullable=True),
        sa.Column('reviewed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('vendor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Create indexes
    op.create_index('ix_vendor_applications_id', 'vendor_applications', ['id'])
    op.create_index('ix_vendor_applications_email', 'vendor_applications', ['email'])
    op.create_index('ix_vendor_applications_status', 'vendor_applications', ['status'])
    op.create_index('ix_vendor_applications_vendor_id', 'vendor_applications', ['vendor_id'])


def downgrade() -> None:
    op.drop_index('ix_vendor_applications_vendor_id', table_name='vendor_applications')
    op.drop_index('ix_vendor_applications_status', table_name='vendor_applications')
    op.drop_index('ix_vendor_applications_email', table_name='vendor_applications')
    op.drop_index('ix_vendor_applications_id', table_name='vendor_applications')
    op.drop_table('vendor_applications')
