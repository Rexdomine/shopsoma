"""Hub-measured parcel provenance on package versions

Revision ID: e7f8a9b0c1d2
Revises: e2f3a4b5c6d8
Create Date: 2026-11-18 12:00:00.000000

Adds ``measurement_source`` ('estimated' | 'hub_measured') and
``box_preset_code`` to ``hub_package_versions`` so DHL bookings can require a
parcel the hub actually weighed and measured.

Additive and online-safe: existing rows become 'estimated' via a constant
default (no table rewrite on PostgreSQL 11+, and row triggers do not fire for
ALTER TABLE). Every statement is idempotent.
"""

from alembic import op


revision = "e7f8a9b0c1d2"
down_revision = "e2f3a4b5c6d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE hub_package_versions
        ADD COLUMN IF NOT EXISTS measurement_source VARCHAR(20) NOT NULL DEFAULT 'estimated',
        ADD COLUMN IF NOT EXISTS box_preset_code VARCHAR(50);

        ALTER TABLE hub_package_versions
        DROP CONSTRAINT IF EXISTS ck_hub_package_versions_measurement_source;

        ALTER TABLE hub_package_versions
        ADD CONSTRAINT ck_hub_package_versions_measurement_source
        CHECK (measurement_source IN ('estimated', 'hub_measured'));
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE hub_package_versions
        DROP CONSTRAINT IF EXISTS ck_hub_package_versions_measurement_source;

        ALTER TABLE hub_package_versions
        DROP COLUMN IF EXISTS box_preset_code,
        DROP COLUMN IF EXISTS measurement_source;
        """
    )
