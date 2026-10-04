"""add made-to-order ready-for-pickup tracking to vendor_pickups

Revision ID: z9a0b1c2d3e4
Revises: y8z9a0b1c2d3
Create Date: 2026-10-04 12:00:00.000000

Readiness is tracked per order item on the existing ``vendor_pickups`` row so a
multi-vendor customer order can have independent readiness/pickup per vendor
item. Both columns are nullable with no default, so the change is metadata-only
in PostgreSQL and safe to run online. Existing rows remain "not ready" (NULL)
and no backfill is required.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "z9a0b1c2d3e4"
down_revision = "y8z9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "vendor_pickups",
        sa.Column("ready_for_pickup_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "vendor_pickups",
        sa.Column(
            "ready_for_pickup_marked_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "vendor_pickups_ready_for_pickup_marked_by_fkey",
        "vendor_pickups",
        "users",
        ["ready_for_pickup_marked_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(
        "vendor_pickups_ready_for_pickup_marked_by_fkey",
        "vendor_pickups",
        type_="foreignkey",
    )
    op.drop_column("vendor_pickups", "ready_for_pickup_marked_by")
    op.drop_column("vendor_pickups", "ready_for_pickup_at")
