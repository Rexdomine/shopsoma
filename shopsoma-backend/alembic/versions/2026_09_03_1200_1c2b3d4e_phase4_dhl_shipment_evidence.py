"""Phase 4 DHL shipment evidence: booking, tracking, custody guard.

Revision ID: 1c2b3d4e
Revises: e6f7a8b9c0d1  # repair_domestic_rate_custody_guards
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
down_revision: Union[str, None] = "e6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_prerequisite_phase4_tables() -> None:
    from app.core.base import Base
    import app.models.checkout_shipping_estimate  # noqa: F401
    import app.models.customer_shipping_quote  # noqa: F401
    import app.models.domestic_rate_quote  # noqa: F401
    import app.models.fulfillment_cohort  # noqa: F401
    import app.models.fulfillment_hub  # noqa: F401
    import app.models.hub_quality  # noqa: F401
    import app.models.inbound_transfer  # noqa: F401
    import app.models.order_guest_capability  # noqa: F401
    import app.models.package_custody  # noqa: F401

    bind = op.get_bind()
    table_names = [
        "fulfillment_hubs",
        "fulfillment_cohorts",
        "cohort_item_allocations",
        "inbound_transfers",
        "inbound_transfer_item_allocations",
        "hub_receipt_sessions",
        "hub_receipt_items",
        "hub_discrepancies",
        "hub_remediations",
        "hub_qc_sessions",
        "hub_qc_inspections",
        "hub_evidence",
        "hub_evidence_retention_events",
        "hub_packages",
        "hub_package_versions",
        "hub_package_items",
        "hub_package_seals",
        "custody_streams",
        "custody_events",
        "outbound_shipment_intents",
        "outbound_shipment_intent_invalidations",
        "outbound_intent_rate_guards",
        "domestic_rate_attempts",
        "domestic_rate_responses",
        "domestic_rate_offers",
        "customer_shipping_quotes",
        "customer_shipping_quote_options",
        "customer_shipping_quote_selections",
        "order_workflow_migration_runs",
        "order_workflow_classifications",
        "order_current_owners",
        "order_guest_capabilities",
        "checkout_shipping_estimates",
        "checkout_shipping_estimate_options",
        "checkout_shipping_estimate_selections",
        "order_inventory_coverage",
    ]
    for name in table_names:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)


def upgrade() -> None:
    _create_prerequisite_phase4_tables()
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
        sa.ForeignKeyConstraint(
            ["intent_id"], ["outbound_shipment_intents.id"],
            name="fk_outbound_intent_shipment_guard_intent",
            ondelete="CASCADE",
        ),
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
        sa.Column("reconciliation_resolution", sa.String(30), nullable=True),
        sa.Column("reconciliation_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciliation_actor_type", sa.String(30), nullable=True),
        sa.Column("reconciliation_actor_id", sa.String(200), nullable=True),
        sa.Column("reconciled_from_classification", sa.String(20), nullable=True),
        sa.Column("reconciled_from_failure_code", sa.String(100), nullable=True),
        sa.Column("reconciled_from_result_recorded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciled_from_completion_txid", sa.BigInteger(), nullable=True),
        sa.Column("reconciliation_evidence_ref", sa.String(200), nullable=True),
        sa.Column("reconciliation_evidence_sha256", sa.String(64), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["intent_id"], ["outbound_shipment_intents.id"],
            name="fk_outbound_shipment_bookings_intent",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"],
            name="fk_outbound_shipment_bookings_order",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["origin_hub_id"], ["fulfillment_hubs.id"],
            name="fk_outbound_shipment_bookings_origin_hub",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["package_id", "package_version"],
            ["hub_package_versions.package_id", "hub_package_versions.version"],
            name="fk_outbound_shipment_bookings_package_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["seal_id", "package_id", "package_version"],
            [
                "hub_package_seals.id",
                "hub_package_seals.package_id",
                "hub_package_seals.package_version",
            ],
            name="fk_outbound_shipment_bookings_seal_binding",
            ondelete="RESTRICT",
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
            "request_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND ((label_sha256 IS NULL AND label_content IS NULL AND label_media_type IS NULL AND label_received_at IS NULL) "
            "OR (label_sha256 ~ '^[0-9a-f]{64}$' AND label_content IS NOT NULL AND octet_length(label_content) > 0 "
            "AND label_media_type = btrim(label_media_type) AND length(label_media_type) > 0 AND label_received_at IS NOT NULL))",
            name="ck_outbound_shipment_bookings_label_privacy",
        ),
        sa.CheckConstraint(
            "account_alias ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'"
            " AND initiating_actor_type ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'"
            " AND initiating_actor_id ~ '^[!-~]+$'"
            " AND source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'"
            " AND idempotency_key ~ '^[!-~]+$'"
            " AND fingerprint_key_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'"
            " AND adapter_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'"
            " AND schema_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'"
            " AND canonicalization_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_outbound_shipment_bookings_identifiers",
        ),
        sa.CheckConstraint(
            "classification IN ('pending', 'success', 'failure', 'unknown')"
            " AND outbound_state IN ('intent_created', 'booked', 'label_ready', 'awaiting_collection', 'collected', 'in_transit', 'out_for_delivery', 'delivered', 'exception', 'cancelled')",
            name="ck_outbound_shipment_bookings_state_classification",
        ),
        sa.CheckConstraint(
            "claim_expires_at = claimed_at + claim_ttl_seconds * interval '1 second'"
            " AND (call_started_at IS NULL OR call_started_at >= claimed_at)"
            " AND (result_recorded_at IS NULL OR ((call_started_at IS NULL AND result_recorded_at >= claimed_at) OR (call_started_at IS NOT NULL AND result_recorded_at >= call_started_at)))"
            " AND ((classification = 'pending' AND result_recorded_at IS NULL AND completion_txid IS NULL AND failure_code IS NULL)"
            " OR (classification = 'success' AND result_recorded_at IS NOT NULL AND completion_txid IS NOT NULL AND failure_code IS NULL AND provider_reference IS NOT NULL AND tracking_number IS NOT NULL)"
            " OR (classification = 'failure' AND result_recorded_at IS NOT NULL AND completion_txid IS NOT NULL AND failure_code IS NOT NULL AND provider_reference IS NULL AND tracking_number IS NULL)"
            " OR (classification = 'unknown' AND result_recorded_at IS NOT NULL AND completion_txid IS NOT NULL AND failure_code = 'unknown_outcome'))",
            name="ck_outbound_shipment_bookings_lifecycle",
        ),
        sa.CheckConstraint(
            "((reconciliation_resolution IS NULL AND reconciliation_recorded_at IS NULL AND reconciliation_actor_type IS NULL AND reconciliation_actor_id IS NULL AND reconciled_from_classification IS NULL AND reconciled_from_failure_code IS NULL AND reconciled_from_result_recorded_at IS NULL AND reconciled_from_completion_txid IS NULL AND reconciliation_evidence_ref IS NULL AND reconciliation_evidence_sha256 IS NULL)"
            " OR (reconciliation_resolution = 'confirm_success' AND reconciliation_recorded_at IS NOT NULL AND reconciliation_actor_type ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND reconciliation_actor_id ~ '^[!-~]+$' AND reconciled_from_classification = 'unknown' AND reconciled_from_failure_code = 'unknown_outcome' AND reconciled_from_result_recorded_at IS NOT NULL AND reconciled_from_completion_txid IS NOT NULL AND reconciliation_evidence_ref IS NULL AND reconciliation_evidence_sha256 IS NULL)"
            " OR (reconciliation_resolution = 'confirm_failure' AND reconciliation_recorded_at IS NOT NULL AND reconciliation_actor_type ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND reconciliation_actor_id ~ '^[!-~]+$' AND reconciled_from_classification = 'unknown' AND reconciled_from_failure_code = 'unknown_outcome' AND reconciled_from_result_recorded_at IS NOT NULL AND reconciled_from_completion_txid IS NOT NULL AND reconciliation_evidence_ref = btrim(reconciliation_evidence_ref) AND length(reconciliation_evidence_ref) > 0 AND reconciliation_evidence_ref NOT LIKE '%://%' AND reconciliation_evidence_ref NOT LIKE '/%' AND reconciliation_evidence_ref NOT LIKE '%..%' AND reconciliation_evidence_sha256 ~ '^[0-9a-f]{64}$'))",
            name="ck_outbound_shipment_bookings_reconciliation_audit",
        ),
        sa.CheckConstraint(
            "(collection_evidence_ref IS NULL AND collection_evidence_hash IS NULL AND collection_counterparty IS NULL AND handoff_recorded_at IS NULL)"
            " OR (collection_evidence_ref IS NOT NULL AND collection_evidence_hash ~ '^[0-9a-f]{64}$'"
            " AND collection_evidence_ref = btrim(collection_evidence_ref) AND length(collection_evidence_ref) > 0"
            " AND collection_evidence_ref NOT LIKE '%://%' AND collection_evidence_ref NOT LIKE '/%' AND collection_evidence_ref NOT LIKE '%..%'"
            " AND collection_counterparty = btrim(collection_counterparty) AND length(collection_counterparty) > 0"
            " AND handoff_recorded_at IS NOT NULL)",
            name="ck_outbound_shipment_bookings_private_handoff_evidence",
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
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_outbound_shipment_booking_reconciliation_audit_update() RETURNS trigger AS $$
        BEGIN
            IF OLD.reconciliation_recorded_at IS NOT NULL AND (
                NEW.reconciliation_resolution IS DISTINCT FROM OLD.reconciliation_resolution
                OR NEW.reconciliation_recorded_at IS DISTINCT FROM OLD.reconciliation_recorded_at
                OR NEW.reconciliation_actor_type IS DISTINCT FROM OLD.reconciliation_actor_type
                OR NEW.reconciliation_actor_id IS DISTINCT FROM OLD.reconciliation_actor_id
                OR NEW.reconciled_from_classification IS DISTINCT FROM OLD.reconciled_from_classification
                OR NEW.reconciled_from_failure_code IS DISTINCT FROM OLD.reconciled_from_failure_code
                OR NEW.reconciled_from_result_recorded_at IS DISTINCT FROM OLD.reconciled_from_result_recorded_at
                OR NEW.reconciled_from_completion_txid IS DISTINCT FROM OLD.reconciled_from_completion_txid
                OR NEW.reconciliation_evidence_ref IS DISTINCT FROM OLD.reconciliation_evidence_ref
                OR NEW.reconciliation_evidence_sha256 IS DISTINCT FROM OLD.reconciliation_evidence_sha256
            ) THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'outbound shipment reconciliation audit is immutable';
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_outbound_shipment_bookings_reconciliation_audit_immutable
        BEFORE UPDATE ON outbound_shipment_booking
        FOR EACH ROW EXECUTE FUNCTION validate_outbound_shipment_booking_reconciliation_audit_update();
        """
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
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("statement_timestamp()")),
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
        sa.ForeignKeyConstraint(
            ["booking_id"], ["outbound_shipment_booking.id"],
            name="fk_outbound_shipment_tracking_snapshots_booking",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.id"],
            name="fk_outbound_shipment_tracking_snapshots_order",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "provider = 'dhl'"
            " AND provider_status_code = btrim(provider_status_code) AND length(provider_status_code) > 0"
            " AND outbound_state IN ('booked', 'label_ready', 'awaiting_collection', 'collected', 'in_transit', 'out_for_delivery', 'delivered', 'exception', 'cancelled')"
            " AND customer_status = btrim(customer_status) AND length(customer_status) > 0"
            " AND detail = btrim(detail) AND length(detail) > 0"
            " AND idempotency_key ~ '^[!-~]+$'"
            " AND source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_outbound_shipment_tracking_snapshots_canonical",
        ),
        sa.CheckConstraint(
            "recorded_at >= observed_at",
            name="ck_outbound_shipment_tracking_snapshots_recording_order",
        ),
    )
    op.create_index(
        "ix_outbound_shipment_tracking_snapshots_booking",
        "outbound_shipment_tracking_snapshot",
        ["booking_id", "observed_at"],
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_outbound_shipment_tracking_snapshot_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'outbound shipment tracking snapshot evidence is append-only';
        END; $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_outbound_shipment_tracking_snapshot_append_only_update
        BEFORE UPDATE ON outbound_shipment_tracking_snapshot
        FOR EACH ROW EXECUTE FUNCTION validate_outbound_shipment_tracking_snapshot_append_only();

        CREATE TRIGGER tr_outbound_shipment_tracking_snapshot_append_only_delete
        BEFORE DELETE ON outbound_shipment_tracking_snapshot
        FOR EACH ROW EXECUTE FUNCTION validate_outbound_shipment_tracking_snapshot_append_only();
        """
    )

    op.create_table(
        "outbound_shipment_tracking_refresh",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid4),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False, server_default="dhl"),
        sa.Column("tracking_number", sa.String(120), nullable=False),
        sa.Column("outbound_state", sa.String(30), nullable=False),
        sa.Column("customer_status", sa.String(60), nullable=False),
        sa.Column("observations_recorded", sa.Integer(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("source_command", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("statement_timestamp()")),
        sa.UniqueConstraint("booking_id", "idempotency_key", name="uq_outbound_shipment_tracking_refreshes_replay"),
        sa.ForeignKeyConstraint(["booking_id"], ["outbound_shipment_booking.id"], name="fk_outbound_shipment_tracking_refreshes_booking", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_outbound_shipment_tracking_refreshes_order", ondelete="RESTRICT"),
        sa.CheckConstraint(
            "provider = 'dhl'"
            " AND tracking_number = btrim(tracking_number) AND length(tracking_number) > 0"
            " AND outbound_state IN ('booked', 'label_ready', 'awaiting_collection', 'collected', 'in_transit', 'out_for_delivery', 'delivered', 'exception', 'cancelled')"
            " AND customer_status = btrim(customer_status) AND length(customer_status) > 0"
            " AND observations_recorded >= 0"
            " AND idempotency_key ~ '^[!-~]+$'"
            " AND source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_outbound_shipment_tracking_refreshes_canonical",
        ),
        sa.CheckConstraint(
            "created_at >= refreshed_at",
            name="ck_outbound_shipment_tracking_refreshes_time_order",
        ),
    )
    op.create_index(
        "ix_outbound_shipment_tracking_refreshes_booking",
        "outbound_shipment_tracking_refresh",
        ["booking_id", "refreshed_at"],
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS tr_outbound_shipment_tracking_snapshot_append_only_delete ON outbound_shipment_tracking_snapshot"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS tr_outbound_shipment_tracking_snapshot_append_only_update ON outbound_shipment_tracking_snapshot"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS validate_outbound_shipment_tracking_snapshot_append_only()"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS tr_outbound_shipment_bookings_reconciliation_audit_immutable ON outbound_shipment_booking"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS validate_outbound_shipment_booking_reconciliation_audit_update()"
    )
    op.drop_table("outbound_shipment_tracking_refresh")
    op.drop_table("outbound_shipment_tracking_snapshot")
    op.drop_table("outbound_shipment_booking")
    op.drop_table("outbound_intent_shipment_guard")
