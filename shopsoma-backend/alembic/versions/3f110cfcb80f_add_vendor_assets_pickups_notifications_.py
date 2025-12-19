"""add_vendor_assets_pickups_notifications_tables

Revision ID: 3f110cfcb80f
Revises: 7k8l9m0n1o2p
Create Date: 2025-12-02 14:36:19.912153

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3f110cfcb80f'
down_revision: Union[str, None] = '7k8l9m0n1o2p'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create vendor_assets table
    op.create_table(
        'vendor_assets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('vendor_id', sa.UUID(), nullable=False),
        sa.Column('asset_type', sa.String(50), nullable=False),
        sa.Column('file_url', sa.Text(), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('mime_type', sa.String(100), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('alt_text', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ondelete='CASCADE')
    )
    op.create_index('ix_vendor_assets_vendor_id', 'vendor_assets', ['vendor_id'])
    op.create_index('ix_vendor_assets_asset_type', 'vendor_assets', ['asset_type'])

    # Create vendor_pickups table
    op.create_table(
        'vendor_pickups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('vendor_id', sa.UUID(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('order_item_id', sa.UUID(), nullable=False),
        sa.Column('order_type', sa.Enum('RTW', 'MADE_TO_ORDER', 'CUSTOM', name='ordertype'), nullable=False, server_default='RTW'),
        sa.Column('estimated_production_days', sa.Integer(), nullable=True),
        sa.Column('scheduled_pickup_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('actual_pickup_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pickup_address', sa.Text(), nullable=True),
        sa.Column('pickup_contact_name', sa.String(255), nullable=True),
        sa.Column('pickup_contact_phone', sa.String(20), nullable=True),
        sa.Column('logistics_partner', sa.String(100), nullable=True),
        sa.Column('tracking_number', sa.String(100), nullable=True),
        sa.Column('driver_name', sa.String(255), nullable=True),
        sa.Column('driver_phone', sa.String(20), nullable=True),
        sa.Column('status', sa.Enum('SCHEDULED', 'IN_TRANSIT', 'DELIVERED_TO_QC', 'QC_APPROVED', 'QC_REJECTED', 'SHIPPED_TO_CUSTOMER', 'COMPLETED', 'CANCELLED', name='pickupstatus'), nullable=False, server_default='SCHEDULED'),
        sa.Column('qc_center_arrival_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('qc_approved_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('qc_rejected_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('qc_notes', sa.Text(), nullable=True),
        sa.Column('qc_approved_by', sa.UUID(), nullable=True),
        sa.Column('vendor_notes', sa.Text(), nullable=True),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancellation_reason', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['qc_approved_by'], ['users.id'], ondelete='SET NULL')
    )
    op.create_index('ix_vendor_pickups_vendor_id', 'vendor_pickups', ['vendor_id'])
    op.create_index('ix_vendor_pickups_order_id', 'vendor_pickups', ['order_id'])
    op.create_index('ix_vendor_pickups_order_item_id', 'vendor_pickups', ['order_item_id'])
    op.create_index('ix_vendor_pickups_status', 'vendor_pickups', ['status'])
    op.create_index('ix_vendor_pickups_tracking_number', 'vendor_pickups', ['tracking_number'])

    # Create vendor_notifications table
    op.create_table(
        'vendor_notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('vendor_id', sa.UUID(), nullable=False),
        sa.Column('notification_type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=True),
        sa.Column('pickup_id', sa.UUID(), nullable=True),
        sa.Column('payout_id', sa.UUID(), nullable=True),
        sa.Column('data', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('email_sent', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('email_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['vendor_id'], ['vendors.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['pickup_id'], ['vendor_pickups.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['payout_id'], ['payouts.id'], ondelete='SET NULL')
    )
    op.create_index('ix_vendor_notifications_vendor_id', 'vendor_notifications', ['vendor_id'])
    op.create_index('ix_vendor_notifications_notification_type', 'vendor_notifications', ['notification_type'])
    op.create_index('ix_vendor_notifications_is_read', 'vendor_notifications', ['is_read'])
    op.create_index('ix_vendor_notifications_created_at', 'vendor_notifications', ['created_at'])


def downgrade() -> None:
    # Drop vendor_notifications table
    op.drop_index('ix_vendor_notifications_created_at', 'vendor_notifications')
    op.drop_index('ix_vendor_notifications_is_read', 'vendor_notifications')
    op.drop_index('ix_vendor_notifications_notification_type', 'vendor_notifications')
    op.drop_index('ix_vendor_notifications_vendor_id', 'vendor_notifications')
    op.drop_table('vendor_notifications')

    # Drop vendor_pickups table
    op.drop_index('ix_vendor_pickups_tracking_number', 'vendor_pickups')
    op.drop_index('ix_vendor_pickups_status', 'vendor_pickups')
    op.drop_index('ix_vendor_pickups_order_item_id', 'vendor_pickups')
    op.drop_index('ix_vendor_pickups_order_id', 'vendor_pickups')
    op.drop_index('ix_vendor_pickups_vendor_id', 'vendor_pickups')
    op.drop_table('vendor_pickups')
    op.execute('DROP TYPE IF EXISTS pickupstatus')
    op.execute('DROP TYPE IF EXISTS ordertype')

    # Drop vendor_assets table
    op.drop_index('ix_vendor_assets_asset_type', 'vendor_assets')
    op.drop_index('ix_vendor_assets_vendor_id', 'vendor_assets')
    op.drop_table('vendor_assets')
