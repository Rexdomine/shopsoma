"""Additive normalized evidence for DHL outbound booking, labels, handoff, and tracking.

This aggregate preserves the immutable shipment intent while storing only normalized,
operator-safe provider outcomes needed for replay, duplicate prevention, label access,
and manual tracking refresh. Raw provider payloads, credentials, and public label URLs
must never be stored here.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.base import Base

_UUID = UUID(as_uuid=True)
_NOW = func.statement_timestamp()


def _id_column():
    return Column(_UUID, primary_key=True, default=uuid.uuid4)


class OutboundIntentShipmentGuard(Base):
    """Mutable serialization guard ensuring one bounded active booking per intent."""

    __tablename__ = "outbound_intent_shipment_guard"

    intent_id = Column(
        _UUID,
        ForeignKey("outbound_shipment_intents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    active_booking_id = Column(_UUID)
    booking_blocked_reason = Column(String(40))


class OutboundShipmentBooking(Base):
    """One normalized booking attempt for one exact outbound intent subject."""

    __tablename__ = "outbound_shipment_booking"

    id = _id_column()
    intent_id = Column(
        _UUID,
        ForeignKey("outbound_shipment_intents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    order_id = Column(_UUID, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    package_id = Column(_UUID, nullable=False)
    package_version = Column(Integer, nullable=False)
    seal_id = Column(_UUID, nullable=False)
    origin_hub_id = Column(
        _UUID, ForeignKey("fulfillment_hubs.id", ondelete="RESTRICT"), nullable=False
    )
    provider = Column(String(20), nullable=False)
    environment = Column(String(20), nullable=False)
    account_alias = Column(String(100), nullable=False)
    initiating_actor_type = Column(String(30), nullable=False)
    initiating_actor_id = Column(String(200), nullable=False)
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    fingerprint_key_version = Column(String(50), nullable=False)
    planned_ship_date = Column(Date, nullable=False)
    adapter_version = Column(String(50), nullable=False)
    schema_version = Column(String(50), nullable=False)
    canonicalization_version = Column(String(50), nullable=False)
    claimed_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)
    claim_ttl_seconds = Column(Integer, nullable=False, server_default="300")
    claim_expires_at = Column(DateTime(timezone=True), nullable=False)
    call_started_at = Column(DateTime(timezone=True))
    result_recorded_at = Column(DateTime(timezone=True))
    classification = Column(String(20), nullable=False)
    outbound_state = Column(String(30), nullable=False)
    failure_code = Column(String(100))
    provider_reference = Column(String(120))
    tracking_number = Column(String(120))
    service_code = Column(String(60))
    label_media_type = Column(String(80))
    label_content = Column(LargeBinary)
    label_sha256 = Column(String(64))
    label_received_at = Column(DateTime(timezone=True))
    collection_scheduled_at = Column(DateTime(timezone=True))
    collection_counterparty = Column(String(120))
    collection_evidence_ref = Column(String(200))
    collection_evidence_hash = Column(String(64))
    handoff_recorded_at = Column(DateTime(timezone=True))
    last_tracking_refresh_at = Column(DateTime(timezone=True))
    latest_exception_code = Column(String(100))
    completion_txid = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        ForeignKeyConstraint(
            ["package_id", "package_version"],
            ["hub_package_versions.package_id", "hub_package_versions.version"],
            name="fk_outbound_shipment_bookings_package_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["seal_id", "package_id", "package_version"],
            [
                "hub_package_seals.id",
                "hub_package_seals.package_id",
                "hub_package_seals.package_version",
            ],
            name="fk_outbound_shipment_bookings_seal_binding",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "provider = 'dhl' AND environment = 'sandbox'",
            name="ck_outbound_shipment_bookings_lane",
        ),
        CheckConstraint(
            "package_version > 0 AND claim_ttl_seconds BETWEEN 1 AND 900",
            name="ck_outbound_shipment_bookings_versions_ttl",
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$' "
            "AND ((label_sha256 IS NULL AND label_content IS NULL AND label_media_type IS NULL AND label_received_at IS NULL) "
            "OR (label_sha256 ~ '^[0-9a-f]{64}$' AND label_content IS NOT NULL AND octet_length(label_content) > 0 "
            "AND label_media_type = btrim(label_media_type) AND length(label_media_type) > 0 AND label_received_at IS NOT NULL))",
            name="ck_outbound_shipment_bookings_label_privacy",
        ),
        CheckConstraint(
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
        CheckConstraint(
            "classification IN ('pending', 'success', 'failure', 'unknown')"
            " AND outbound_state IN ('intent_created', 'booked', 'label_ready', 'awaiting_collection', 'collected', 'in_transit', 'out_for_delivery', 'delivered', 'exception', 'cancelled')",
            name="ck_outbound_shipment_bookings_state_classification",
        ),
        CheckConstraint(
            "claim_expires_at = claimed_at + claim_ttl_seconds * interval '1 second'"
            " AND (call_started_at IS NULL OR call_started_at >= claimed_at)"
            " AND (result_recorded_at IS NULL OR ((call_started_at IS NULL AND result_recorded_at >= claimed_at) OR (call_started_at IS NOT NULL AND result_recorded_at >= call_started_at)))"
            " AND ((classification = 'pending' AND result_recorded_at IS NULL AND completion_txid IS NULL AND failure_code IS NULL)"
            " OR (classification = 'success' AND result_recorded_at IS NOT NULL AND completion_txid IS NOT NULL AND failure_code IS NULL AND provider_reference IS NOT NULL AND tracking_number IS NOT NULL)"
            " OR (classification = 'failure' AND result_recorded_at IS NOT NULL AND completion_txid IS NOT NULL AND failure_code IS NOT NULL AND provider_reference IS NULL AND tracking_number IS NULL)"
            " OR (classification = 'unknown' AND result_recorded_at IS NOT NULL AND completion_txid IS NOT NULL AND failure_code = 'unknown_outcome'))",
            name="ck_outbound_shipment_bookings_lifecycle",
        ),
        CheckConstraint(
            "(collection_evidence_ref IS NULL AND collection_evidence_hash IS NULL AND collection_counterparty IS NULL AND handoff_recorded_at IS NULL)"
            " OR (collection_evidence_ref IS NOT NULL AND collection_evidence_hash ~ '^[0-9a-f]{64}$'"
            " AND collection_evidence_ref = btrim(collection_evidence_ref) AND length(collection_evidence_ref) > 0"
            " AND collection_evidence_ref NOT LIKE '%://%' AND collection_evidence_ref NOT LIKE '/%' AND collection_evidence_ref NOT LIKE '%..%'"
            " AND collection_counterparty = btrim(collection_counterparty) AND length(collection_counterparty) > 0"
            " AND handoff_recorded_at IS NOT NULL)",
            name="ck_outbound_shipment_bookings_private_handoff_evidence",
        ),
        UniqueConstraint(
            "provider", "environment", "account_alias", "idempotency_key",
            name="uq_outbound_shipment_bookings_idempotency",
        ),
        UniqueConstraint("provider", "environment", "provider_reference", name="uq_outbound_shipment_bookings_provider_reference"),
        UniqueConstraint("provider", "environment", "tracking_number", name="uq_outbound_shipment_bookings_tracking"),
        Index("ix_outbound_shipment_bookings_subject", "intent_id", "package_id", "package_version"),
        Index("ix_outbound_shipment_bookings_state", "outbound_state"),
    )


class OutboundShipmentTrackingSnapshot(Base):
    """Append-only normalized tracking observations for one booking."""

    __tablename__ = "outbound_shipment_tracking_snapshot"

    id = _id_column()
    booking_id = Column(
        _UUID,
        ForeignKey("outbound_shipment_booking.id", ondelete="RESTRICT"),
        nullable=False,
    )
    order_id = Column(_UUID, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False)
    provider = Column(String(20), nullable=False)
    tracking_number = Column(String(120), nullable=False)
    provider_status_code = Column(String(60), nullable=False)
    outbound_state = Column(String(30), nullable=False)
    customer_status = Column(String(60), nullable=False)
    detail = Column(String(240), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)
    exception_code = Column(String(100))
    idempotency_key = Column(String(200), nullable=False)
    source_command = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "provider = 'dhl'"
            " AND provider_status_code = btrim(provider_status_code) AND length(provider_status_code) > 0"
            " AND outbound_state IN ('booked', 'label_ready', 'awaiting_collection', 'collected', 'in_transit', 'out_for_delivery', 'delivered', 'exception', 'cancelled')"
            " AND customer_status = btrim(customer_status) AND length(customer_status) > 0"
            " AND detail = btrim(detail) AND length(detail) > 0"
            " AND idempotency_key ~ '^[!-~]+$'"
            " AND source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_outbound_shipment_tracking_snapshots_canonical",
        ),
        CheckConstraint(
            "recorded_at >= observed_at",
            name="ck_outbound_shipment_tracking_snapshots_recording_order",
        ),
        UniqueConstraint(
            "booking_id", "provider_status_code", "observed_at",
            name="uq_outbound_shipment_tracking_snapshots_observation",
        ),
        UniqueConstraint(
            "booking_id", "idempotency_key",
            name="uq_outbound_shipment_tracking_snapshots_replay",
        ),
        Index("ix_outbound_shipment_tracking_snapshots_booking", "booking_id", "observed_at"),
    )
