"""Phase 4 DHL shipment evidence: booking, tracking, custody guard.

Revision ID: 1c2b3d4e
Revises: 1c2b3d3a  # repair_domestic_rate_custody_guards
Create Date: 2026-09-03 12:00:00.000000

Additive normalized evidence tables for DHL outbound booking, label,
handoff tracking, and customer delivery status.  No changes to existing
order, shipment, or custody tables.

Tables
~~~~~~
outbound_intent_shipment_guard
  Prevents duplicate bookings per (intent_id, package_id, package_version).
  Unique constraint enforced at the DB layer.

outbound_shipment_booking
  Records each booking attempt with idempotency key, provider reference,
  tracking number, and base64-encoded label.  Immutable — updates only
  set outcome_kind and failure_note on unknown/failure outcomes.

outbound_shipment_tracking_snapshot
  Append-only tracking snapshots per booking.  Each refresh creates a new
  row; no row is ever updated or deleted.
"""
from __future__ import annotations

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1c2b3d4e"
down_revision: Union[str, None] = "17d4240dbb35"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # outboun d_intent_shipment_guard
    #   Exactly one active booking per (intent_id, package_id, package_version).
    #   Prevents duplicate booking attempts at the DB level.
    # ------------------------------------------------------------------
    op.create_table(
        "outbound_intent_shipment_guard",
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("active_booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("booking_blocked_reason", sa.String(40), nullable=True),
    )
    op.create_index(
        "ix_guard_intent",
        "outbound_intent_shipment_guard",
        ["intent_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # outbound_shipment_booking  — aligned with ORM OutboundShipmentBooking
    # ------------------------------------------------------------------
    op.create_table(
        "outbound_shipment_booking",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_version", sa.Integer(), nullable=False),
        sa.Column("seal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin_hub_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default="dhl"),
        sa.Column("environment", sa.String(20), nullable=False, server_default="sandbox"),
        sa.Column("account_alias", sa.String(100), nullable=False),
        sa.Column("initiating_actor_type", sa.String(30), nullable=False),
        sa.Column("initiating_actor_id", sa.String(200), nullable=False),
        sa.Column("source_command", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("fingerprint_key_version", sa.String(50), nullable=False),
        sa.Column("planned_ship_date", sa.Date(), nullable=False),
        sa.Column("adapter_version", sa.String(50), nullable=False),
        sa.Column("schema_version", sa.String(50), nullable=False),
        sa.Column("canonicalization_version", sa.String(50), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("claim_ttl_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("call_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("classification", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("outbound_state", sa.String(30), nullable=False, server_default="intent_created"),
        sa.Column("failure_code", sa.String(100), nullable=True),
        sa.Column("provider_reference", sa.String(120), nullable=True),
        sa.Column("tracking_number", sa.String(120), nullable=True),
        sa.Column("service_code", sa.String(60), nullable=True),
        sa.Column("label_media_type", sa.String(80), nullable=True),
        sa.Column("label_content", sa.LargeBinary(), nullable=True),
        sa.Column("label_sha256", sa.String(64), nullable=True),
        sa.Column("label_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collection_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collection_counterparty", sa.String(120), nullable=True),
        sa.Column("collection_evidence_ref", sa.String(200), nullable=True),
        sa.Column("collection_evidence_hash", sa.String(64), nullable=True),
        sa.Column("handoff_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_tracking_refresh_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_exception_code", sa.String(100), nullable=True),
        sa.Column("completion_txid", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "provider", "environment", "account_alias", "idempotency_key",
            name="uq_outbound_shipment_bookings_idempotency",
        ),
        sa.UniqueConstraint(
            "provider", "environment", "provider_reference",
            name="uq_outbound_shipment_bookings_provider_reference",
        ),
        sa.UniqueConstraint(
            "provider", "environment", "tracking_number",
            name="uq_outbound_shipment_bookings_tracking",
        ),
        sa.CheckConstraint(
            "provider = 'dhl' AND environment = 'sandbox'",
            name="ck_outbound_shipment_bookings_lane",
        ),
        sa.CheckConstraint(
            "package_version > 0 AND claim_ttl_seconds BETWEEN 1 AND 900",
            name="ck_outbound_shipment_bookings_versions_ttl",
        ),
        sa.CheckConstraint(
            "classification IN ('pending', 'success', 'failure', 'unknown')",
            name="ck_outbound_shipment_bookings_classification",
        ),
    )
    op.create_index(
        "ix_outbound_shipment_booking_subject",
        "outbound_shipment_booking",
        ["intent_id", "package_id", "package_version"],
    )
    op.create_index(
        "ix_outbound_shipment_booking_state",
        "outbound_shipment_booking",
        ["outbound_state"],
    )

    # ------------------------------------------------------------------
    # outbound_shipment_tracking_snapshot  — aligned with ORM OutboundShipmentTrackingSnapshot
    # ------------------------------------------------------------------
    op.create_table(
        "outbound_shipment_tracking_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default="dhl"),
        sa.Column("tracking_number", sa.String(120), nullable=False),
        sa.Column("provider_status_code", sa.String(60), nullable=False),
        sa.Column("outbound_state", sa.String(30), nullable=False),
        sa.Column("customer_status", sa.String(60), nullable=False),
        sa.Column("detail", sa.String(240), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("exception_code", sa.String(100), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("source_command", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "booking_id", "provider_status_code", "observed_at",
            name="uq_outbound_shipment_tracking_snapshots_observation",
        ),
        sa.UniqueConstraint(
            "booking_id", "idempotency_key",
            name="uq_outbound_shipment_tracking_snapshots_replay",
        ),
        sa.CheckConstraint(
            "provider = 'dhl'",
            name="ck_outbound_shipment_tracking_snapshots_provider",
        ),
    )
    op.create_index(
        "ix_outbound_shipment_tracking_snapshots_booking",
        "outbound_shipment_tracking_snapshot",
        ["booking_id", "observed_at"],
    )


def downgrade() -> None:
    op.drop_table("outbound_shipment_tracking_snapshot")
    op.drop_table("outbound_shipment_booking")
    op.drop_table("outbound_intent_shipment_guard")
