"""DHL v2: booking pickup columns and relaxed DHL lane constraints

Revision ID: d1e2f3a4b5c7
Revises: b9c0d1e2f3a4
Create Date: 2026-11-10 12:00:00.000000

The "DHL implementation v2" change originally appended these statements to the
already-released ``b9c0d1e2f3a4`` revision. Databases that had already applied
that revision (staging) never received them, so ``alembic upgrade heads`` was a
no-op while the ORM started selecting ``outbound_shipment_booking.pickup_*``.
Every ``select(OutboundShipmentBooking)`` then failed with UndefinedColumn,
which broke order cancellation (delivery-option change, delivery-address
change, currency change) and DHL tracking.

Every statement here is idempotent so it is safe on databases where the
columns/constraints were already applied manually or by the edited revision.
"""

from alembic import op


revision = "d1e2f3a4b5c7"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE outbound_shipment_booking
        ADD COLUMN IF NOT EXISTS pickup_confirmation_number VARCHAR(120),
        ADD COLUMN IF NOT EXISTS pickup_scheduled_for TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS pickup_requested_at TIMESTAMPTZ;

        ALTER TABLE outbound_shipment_intents
        DROP CONSTRAINT IF EXISTS ck_outbound_intents_country_ng;

        ALTER TABLE outbound_shipment_intents
        ADD CONSTRAINT ck_outbound_intents_country_ng
        CHECK (destination_country_code ~ '^[A-Z]{2}$');

        ALTER TABLE domestic_rate_attempts
        DROP CONSTRAINT IF EXISTS ck_domestic_rate_attempts_lane;

        ALTER TABLE domestic_rate_attempts
        ADD CONSTRAINT ck_domestic_rate_attempts_lane
        CHECK (
            provider = 'dhl'
            AND environment IN ('sandbox', 'production')
            AND destination_country_code ~ '^[A-Z]{2}$'
        );

        ALTER TABLE outbound_shipment_booking
        DROP CONSTRAINT IF EXISTS ck_outbound_shipment_bookings_lane;

        ALTER TABLE outbound_shipment_booking
        ADD CONSTRAINT ck_outbound_shipment_bookings_lane
        CHECK (provider = 'dhl' AND environment IN ('sandbox', 'production'));
        """
    )


def downgrade() -> None:
    # Restoring the strict constraints fails if non-NG / production rows exist;
    # that is intentional so a downgrade cannot silently drop evidence.
    op.execute(
        """
        ALTER TABLE outbound_shipment_booking
        DROP CONSTRAINT IF EXISTS ck_outbound_shipment_bookings_lane;

        ALTER TABLE outbound_shipment_booking
        ADD CONSTRAINT ck_outbound_shipment_bookings_lane
        CHECK (provider = 'dhl' AND environment = 'sandbox');

        ALTER TABLE domestic_rate_attempts
        DROP CONSTRAINT IF EXISTS ck_domestic_rate_attempts_lane;

        ALTER TABLE domestic_rate_attempts
        ADD CONSTRAINT ck_domestic_rate_attempts_lane
        CHECK (provider = 'dhl' AND environment = 'sandbox' AND destination_country_code = 'NG');

        ALTER TABLE outbound_shipment_intents
        DROP CONSTRAINT IF EXISTS ck_outbound_intents_country_ng;

        ALTER TABLE outbound_shipment_intents
        ADD CONSTRAINT ck_outbound_intents_country_ng
        CHECK (destination_country_code = 'NG');

        ALTER TABLE outbound_shipment_booking
        DROP COLUMN IF EXISTS pickup_requested_at,
        DROP COLUMN IF EXISTS pickup_scheduled_for,
        DROP COLUMN IF EXISTS pickup_confirmation_number;
        """
    )
