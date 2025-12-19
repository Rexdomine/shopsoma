"""update_fulfillment_statuses_and_pickup_windows

Revision ID: b6ad33a51bb1
Revises: h4i5j6k7l8m9
Create Date: 2025-12-13 08:41:52.435058

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6ad33a51bb1'
down_revision: Union[str, None] = 'h4i5j6k7l8m9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new pickup window columns to vendor_pickups table
    op.add_column('vendor_pickups', sa.Column('pickup_window_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('vendor_pickups', sa.Column('pickup_window_end', sa.DateTime(timezone=True), nullable=True))
    op.add_column('vendor_pickups', sa.Column('courier_name', sa.String(length=100), nullable=True))
    op.add_column('vendor_pickups', sa.Column('rider_id', sa.String(length=100), nullable=True))

    # Update FulfillmentStatus enum
    # First, alter the enum type to include new values
    op.execute("""
        ALTER TYPE fulfillmentstatus RENAME TO fulfillmentstatus_old;
    """)

    op.execute("""
        CREATE TYPE fulfillmentstatus AS ENUM (
            'order_received',
            'preparing_for_pickup',
            'pickup_scheduled',
            'picked_up',
            'in_transit',
            'out_for_delivery',
            'delivered',
            'delivery_failed',
            'returned',
            'cancelled'
        );
    """)

    # Update orders table to use new enum with default migration
    op.execute("""
        ALTER TABLE orders
        ALTER COLUMN fulfillment_status TYPE fulfillmentstatus
        USING CASE
            WHEN fulfillment_status::text = 'pending' THEN 'order_received'::fulfillmentstatus
            WHEN fulfillment_status::text = 'processing' THEN 'preparing_for_pickup'::fulfillmentstatus
            WHEN fulfillment_status::text = 'shipped' THEN 'in_transit'::fulfillmentstatus
            WHEN fulfillment_status::text = 'delivered' THEN 'delivered'::fulfillmentstatus
            WHEN fulfillment_status::text = 'cancelled' THEN 'cancelled'::fulfillmentstatus
            ELSE 'order_received'::fulfillmentstatus
        END;
    """)

    # Update order_items table to use new enum
    op.execute("""
        ALTER TABLE order_items
        ALTER COLUMN fulfillment_status TYPE fulfillmentstatus
        USING CASE
            WHEN fulfillment_status::text = 'pending' THEN 'order_received'::fulfillmentstatus
            WHEN fulfillment_status::text = 'processing' THEN 'preparing_for_pickup'::fulfillmentstatus
            WHEN fulfillment_status::text = 'shipped' THEN 'in_transit'::fulfillmentstatus
            WHEN fulfillment_status::text = 'delivered' THEN 'delivered'::fulfillmentstatus
            WHEN fulfillment_status::text = 'cancelled' THEN 'cancelled'::fulfillmentstatus
            ELSE 'order_received'::fulfillmentstatus
        END;
    """)

    # Drop old enum
    op.execute("DROP TYPE fulfillmentstatus_old;")


def downgrade() -> None:
    # Remove new pickup columns
    op.drop_column('vendor_pickups', 'rider_id')
    op.drop_column('vendor_pickups', 'courier_name')
    op.drop_column('vendor_pickups', 'pickup_window_end')
    op.drop_column('vendor_pickups', 'pickup_window_start')

    # Revert enum changes
    op.execute("""
        ALTER TYPE fulfillmentstatus RENAME TO fulfillmentstatus_new;
    """)

    op.execute("""
        CREATE TYPE fulfillmentstatus AS ENUM (
            'pending',
            'processing',
            'shipped',
            'delivered',
            'cancelled'
        );
    """)

    # Revert orders table
    op.execute("""
        ALTER TABLE orders
        ALTER COLUMN fulfillment_status TYPE fulfillmentstatus
        USING CASE
            WHEN fulfillment_status::text = 'order_received' THEN 'pending'::fulfillmentstatus
            WHEN fulfillment_status::text = 'preparing_for_pickup' THEN 'processing'::fulfillmentstatus
            WHEN fulfillment_status::text = 'pickup_scheduled' THEN 'processing'::fulfillmentstatus
            WHEN fulfillment_status::text = 'picked_up' THEN 'shipped'::fulfillmentstatus
            WHEN fulfillment_status::text = 'in_transit' THEN 'shipped'::fulfillmentstatus
            WHEN fulfillment_status::text = 'out_for_delivery' THEN 'shipped'::fulfillmentstatus
            WHEN fulfillment_status::text = 'delivered' THEN 'delivered'::fulfillmentstatus
            WHEN fulfillment_status::text = 'delivery_failed' THEN 'processing'::fulfillmentstatus
            WHEN fulfillment_status::text = 'returned' THEN 'cancelled'::fulfillmentstatus
            WHEN fulfillment_status::text = 'cancelled' THEN 'cancelled'::fulfillmentstatus
            ELSE 'pending'::fulfillmentstatus
        END;
    """)

    # Revert order_items table
    op.execute("""
        ALTER TABLE order_items
        ALTER COLUMN fulfillment_status TYPE fulfillmentstatus
        USING CASE
            WHEN fulfillment_status::text = 'order_received' THEN 'pending'::fulfillmentstatus
            WHEN fulfillment_status::text = 'preparing_for_pickup' THEN 'processing'::fulfillmentstatus
            WHEN fulfillment_status::text = 'pickup_scheduled' THEN 'processing'::fulfillmentstatus
            WHEN fulfillment_status::text = 'picked_up' THEN 'shipped'::fulfillmentstatus
            WHEN fulfillment_status::text = 'in_transit' THEN 'shipped'::fulfillmentstatus
            WHEN fulfillment_status::text = 'out_for_delivery' THEN 'shipped'::fulfillmentstatus
            WHEN fulfillment_status::text = 'delivered' THEN 'delivered'::fulfillmentstatus
            WHEN fulfillment_status::text = 'delivery_failed' THEN 'processing'::fulfillmentstatus
            WHEN fulfillment_status::text = 'returned' THEN 'cancelled'::fulfillmentstatus
            WHEN fulfillment_status::text = 'cancelled' THEN 'cancelled'::fulfillmentstatus
            ELSE 'pending'::fulfillmentstatus
        END;
    """)

    # Drop new enum
    op.execute("DROP TYPE fulfillmentstatus_new;")
