"""Add ShipBubble shipping support

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-10-13 12:00:00.000000

Adds:
- 'shipbubble_live' to checkout_shipping_estimates source_kind check constraint
- provider_metadata JSONB column to checkout_shipping_estimate_options
- shipbubble_address_code BIGINT to fulfillment_hubs
- shipbubble_shipments table for booking tracking and audit
- shipbubble_webhook_events table for webhook idempotency and event storage
- updates validate_checkout_estimate_option_write trigger to validate shipbubble_live options
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Update checkout_shipping_estimates source_kind constraint
    op.execute(
        """
        ALTER TABLE checkout_shipping_estimates
        DROP CONSTRAINT IF EXISTS ck_checkout_shipping_estimates_kinds;

        ALTER TABLE checkout_shipping_estimates
        ADD CONSTRAINT ck_checkout_shipping_estimates_kinds
        CHECK(source_kind IN ('static_domestic_rate','sandbox_normalized','shipbubble_live')
              AND created_by_actor_type IN ('customer','guest_capability','staff'));
        """
    )

    # 2. Add provider_metadata to checkout_shipping_estimate_options
    op.add_column(
        "checkout_shipping_estimate_options",
        sa.Column("provider_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # 3. Add shipbubble_address_code to fulfillment_hubs
    op.add_column(
        "fulfillment_hubs",
        sa.Column("shipbubble_address_code", sa.BigInteger(), nullable=True),
    )

    # 4. Create shipbubble_shipments table
    op.create_table(
        "shipbubble_shipments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "estimate_option_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("checkout_shipping_estimate_options.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("request_token", sa.String(length=120), nullable=False),
        sa.Column("courier_id", sa.String(length=60), nullable=False),
        sa.Column("service_code", sa.String(length=60), nullable=False),
        sa.Column("courier_name", sa.String(length=100), nullable=False),
        sa.Column("shipbubble_order_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("tracking_code", sa.String(length=100), nullable=True),
        sa.Column("tracking_url", sa.String(length=255), nullable=True),
        sa.Column("waybill_document_url", sa.String(length=255), nullable=True),
        sa.Column("shipping_fee", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="NGN"),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
    )
    op.create_index(
        "ix_shipbubble_shipments_order_id",
        "shipbubble_shipments",
        ["order_id"],
    )
    op.create_index(
        "ix_shipbubble_shipments_status",
        "shipbubble_shipments",
        ["status"],
    )
    op.create_index(
        "ix_shipbubble_shipments_sb_order_id",
        "shipbubble_shipments",
        ["shipbubble_order_id"],
    )

    # 5. Create shipbubble_webhook_events table
    op.create_table(
        "shipbubble_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.String(length=100), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False, unique=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="received"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("statement_timestamp()"),
        ),
    )
    op.create_index(
        "ix_shipbubble_webhook_events_status",
        "shipbubble_webhook_events",
        ["status"],
    )
    op.create_index(
        "ix_shipbubble_webhook_events_payload_sha256",
        "shipbubble_webhook_events",
        ["payload_sha256"],
    )

    # 6. Update option validation trigger to handle shipbubble_live
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION validate_checkout_estimate_option_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE estimate record;
BEGIN
 IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'checkout estimate option is immutable audit'; END IF;
 SELECT currency,source_kind,creation_txid INTO estimate
 FROM checkout_shipping_estimates WHERE id=NEW.estimate_id FOR UPDATE;
 IF NOT FOUND OR estimate.currency IS DISTINCT FROM NEW.currency
    OR estimate.creation_txid IS DISTINCT FROM txid_current()
    OR (estimate.source_kind='static_domestic_rate' AND NEW.source_rate_id IS NULL)
    OR (estimate.source_kind IN ('sandbox_normalized','shipbubble_live') AND NEW.source_rate_id IS NOT NULL) THEN
  RAISE EXCEPTION 'checkout estimate option truth is invalid';
 END IF;
 RETURN NEW;
END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        r"""
CREATE OR REPLACE FUNCTION validate_checkout_estimate_option_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE estimate record;
BEGIN
 IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'checkout estimate option is immutable audit'; END IF;
 SELECT currency,source_kind,creation_txid INTO estimate
 FROM checkout_shipping_estimates WHERE id=NEW.estimate_id FOR UPDATE;
 IF NOT FOUND OR estimate.currency IS DISTINCT FROM NEW.currency
    OR estimate.creation_txid IS DISTINCT FROM txid_current()
    OR (estimate.source_kind='static_domestic_rate' AND NEW.source_rate_id IS NULL)
    OR (estimate.source_kind='sandbox_normalized' AND NEW.source_rate_id IS NOT NULL) THEN
  RAISE EXCEPTION 'checkout estimate option truth is invalid';
 END IF;
 RETURN NEW;
END $$;
        """
    )
    op.drop_table("shipbubble_webhook_events")
    op.drop_table("shipbubble_shipments")
    op.drop_column("fulfillment_hubs", "shipbubble_address_code")
    op.drop_column("checkout_shipping_estimate_options", "provider_metadata")
    op.execute(
        """
        ALTER TABLE checkout_shipping_estimates
        DROP CONSTRAINT IF EXISTS ck_checkout_shipping_estimates_kinds;

        ALTER TABLE checkout_shipping_estimates
        ADD CONSTRAINT ck_checkout_shipping_estimates_kinds
        CHECK(source_kind IN ('static_domestic_rate','sandbox_normalized')
              AND created_by_actor_type IN ('customer','guest_capability','staff'));
        """
    )
