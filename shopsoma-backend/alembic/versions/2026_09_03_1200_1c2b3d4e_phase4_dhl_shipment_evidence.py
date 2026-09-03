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
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_version", sa.Integer(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("recorded_by", sa.String(200), nullable=False),
        sa.UniqueConstraint(
            "intent_id",
            "package_id",
            "package_version",
            name="uq_shipment_guard_intent_package",
        ),
    )
    op.create_index(
        "ix_shipment_guard_intent_package",
        "outbound_intent_shipment_guard",
        ["intent_id", "package_id", "package_version"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # outbound_shipment_booking
    #   Immutable booking evidence: idempotent, captures label+tracking on
    #   success; records outcome_kind='unknown' on ambiguous DHL responses.
    # ------------------------------------------------------------------
    op.create_table(
        "outbound_shipment_booking",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("package_version", sa.Integer(), nullable=False),
        sa.Column("seal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outbound_state", sa.String(50), nullable=False, server_default="booked"),
        # Idempotency
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        # Deterministic request fingerprint for duplicate detection
        sa.Column(
            "request_fingerprint",
            sa.String(64),
            nullable=False,
            comment="SHA-256 of canonicalized booking request",
        ),
        # Outcome
        sa.Column(
            "outcome_kind",
            sa.String(20),
            nullable=False,
            server_default="success",
        ),
        # Provider reference (populated on success only)
        sa.Column("provider_reference", sa.String(100), nullable=True),
        sa.Column("tracking_number", sa.String(100), nullable=True),
        # Label (populated on success only; stored as binary, not base64)
        sa.Column("label_media_type", sa.String(100), nullable=True),
        sa.Column("label_sha256", sa.String(64), nullable=True),
        sa.Column("label_content", sa.LargeBinary(), nullable=True),
        # Failure note (populated on failure/unknown only)
        sa.Column("failure_note", sa.Text(), nullable=True),
        # Provider error context (populated on unknown only)
        sa.Column("provider_status_code", sa.Integer(), nullable=True),
        sa.Column("provider_request_id", sa.String(100), nullable=True),
        # Timestamps
        sa.Column(
            "booked_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When booking was accepted by DHL",
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Operator who initiated booking
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Constraints enforcing immutability rules
        sa.CheckConstraint(
            "outcome_kind IN ('success', 'failure', 'unknown')",
            name="ck_booking_outcome_kind",
        ),
        sa.CheckConstraint(
            "outcome_kind != 'success' "
            "OR (provider_reference IS NOT NULL AND tracking_number IS NOT NULL)",
            name="ck_success_requires_provider_refs",
        ),
        sa.CheckConstraint(
            "outcome_kind != 'success' "
            "OR (label_sha256 IS NOT NULL AND label_content IS NOT NULL AND label_media_type IS NOT NULL)",
            name="ck_success_requires_label",
        ),
        sa.CheckConstraint(
            "outcome_kind IN ('failure', 'unknown') "
            "OR failure_note IS NULL",
            name="ck_success_has_no_failure_note",
        ),
        # Request fingerprint must be a valid hex SHA-256
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_booking_fingerprint_format",
        ),
        # Label SHA256 must be valid hex when present
        sa.CheckConstraint(
            "label_sha256 IS NULL OR label_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_booking_label_sha256_format",
        ),
    )
    op.create_index(
        "ix_booking_order_intent",
        "outbound_shipment_booking",
        ["order_id", "intent_id"],
    )
    op.create_index(
        "ix_booking_intent_package",
        "outbound_shipment_booking",
        ["intent_id", "package_id", "package_version"],
    )

    # ------------------------------------------------------------------
    # outbound_shipment_tracking_snapshot
    #   Append-only tracking history per booking.  Each refresh call
    #   inserts a new row; rows are never updated or deleted.
    # ------------------------------------------------------------------
    op.create_table(
        "outbound_shipment_tracking_snapshot",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        # Tracking data from DHL
        sa.Column("tracking_number", sa.String(100), nullable=False),
        sa.Column("outbound_state", sa.String(50), nullable=False),
        sa.Column("customer_status", sa.String(50), nullable=False),
        sa.Column("raw_status", sa.Text(), nullable=True),
        sa.Column(
            "status_code",
            sa.String(20),
            nullable=True,
            comment="DHL event status code",
        ),
        sa.Column("status_description", sa.Text(), nullable=True),
        # Location
        sa.Column("location_description", sa.String(200), nullable=True),
        sa.Column("destination_country", sa.String(2), nullable=True),
        sa.Column("destination_city", sa.String(100), nullable=True),
        # Timestamps from DHL
        sa.Column(
            "event_occurred_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When DHL recorded the event",
        ),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # Operator who triggered the refresh
        sa.Column("operator_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.create_index(
        "ix_tracking_snapshot_booking",
        "outbound_shipment_tracking_snapshot",
        ["booking_id"],
    )


def downgrade() -> None:
    op.drop_table("outbound_shipment_tracking_snapshot")
    op.drop_table("outbound_shipment_booking")
    op.drop_table("outbound_intent_shipment_guard")
