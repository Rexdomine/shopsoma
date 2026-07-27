"""Package, seal, custody, and inert outbound-intent persistence.

Lane 2A-3D is deliberately persistence-only.  The database owns aggregate
chronology, append-only audit history, quantity safety, replay identity, and
root-first serialization; no provider operation is represented here.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    DDL,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.base import Base

_UUID = UUID(as_uuid=True)
_NOW = func.statement_timestamp()


def _id_column():
    return Column(_UUID, primary_key=True, default=uuid.uuid4)


class HubPackage(Base):
    """Stable logical package aggregate; physical revisions live separately."""

    __tablename__ = "hub_packages"

    id = _id_column()
    order_id = Column(
        _UUID, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    hub_id = Column(
        _UUID, ForeignKey("fulfillment_hubs.id", ondelete="RESTRICT"), nullable=False
    )
    state = Column(
        String(20), nullable=False, default="packing", server_default="packing"
    )
    current_version = Column(Integer, nullable=False, default=1, server_default="1")
    row_version = Column(Integer, nullable=False, default=1, server_default="1")
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    created_by_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)
    sealed_at = Column(DateTime(timezone=True))
    ready_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "state IN ('packing', 'sealed', 'ready')", name="ck_hub_packages_state"
        ),
        CheckConstraint(
            "current_version > 0 AND row_version > 0",
            name="ck_hub_packages_versions_positive",
        ),
        CheckConstraint(
            "(state = 'packing' AND sealed_at IS NULL AND ready_at IS NULL) OR "
            "(state = 'sealed' AND sealed_at IS NOT NULL AND ready_at IS NULL) OR "
            "(state = 'ready' AND sealed_at IS NOT NULL AND ready_at IS NOT NULL "
            "AND ready_at >= sealed_at)",
            name="ck_hub_packages_state_times",
        ),
        CheckConstraint(
            "source_command = btrim(source_command) AND length(source_command) > 0 "
            "AND idempotency_key = btrim(idempotency_key) "
            "AND length(idempotency_key) > 0",
            name="ck_hub_packages_command_canonical",
        ),
        UniqueConstraint(
            "order_id", "hub_id", "idempotency_key", name="uq_hub_packages_replay"
        ),
        UniqueConstraint("id", "order_id", "hub_id", name="uq_hub_packages_identity"),
    )


class HubPackageVersion(Base):
    """Immutable measurements and lineage for one physical package revision."""

    __tablename__ = "hub_package_versions"

    package_id = Column(_UUID, primary_key=True)
    version = Column(Integer, primary_key=True)
    order_id = Column(_UUID, nullable=False)
    hub_id = Column(_UUID, nullable=False)
    previous_version = Column(Integer)
    weight_kg = Column(Numeric(10, 3), nullable=False)
    length_cm = Column(Numeric(10, 3), nullable=False)
    width_cm = Column(Numeric(10, 3), nullable=False)
    height_cm = Column(Numeric(10, 3), nullable=False)
    packed_by_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    packed_at = Column(DateTime(timezone=True), nullable=False)
    reason = Column(String(200))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        ForeignKeyConstraint(
            ["package_id", "order_id", "hub_id"],
            ["hub_packages.id", "hub_packages.order_id", "hub_packages.hub_id"],
            name="fk_hub_package_versions_package_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "version > 0 AND ((version = 1 AND previous_version IS NULL) OR "
            "(version > 1 AND previous_version = version - 1))",
            name="ck_hub_package_versions_lineage",
        ),
        CheckConstraint(
            "weight_kg > 0 AND weight_kg <= 9999999.999 "
            "AND length_cm > 0 AND length_cm <= 9999999.999 "
            "AND width_cm > 0 AND width_cm <= 9999999.999 "
            "AND height_cm > 0 AND height_cm <= 9999999.999",
            name="ck_hub_package_versions_measurements",
        ),
        CheckConstraint(
            "(version = 1 AND reason IS NULL) OR "
            "(version > 1 AND reason IS NOT NULL AND reason = btrim(reason) "
            "AND length(reason) > 0)",
            name="ck_hub_package_versions_reason",
        ),
        UniqueConstraint(
            "package_id",
            "version",
            "order_id",
            "hub_id",
            name="uq_hub_package_versions_identity",
        ),
    )


class HubPackageItem(Base):
    """Immutable item quantity assigned to one exact package version."""

    __tablename__ = "hub_package_items"

    id = _id_column()
    package_id = Column(_UUID, nullable=False)
    package_version = Column(Integer, nullable=False)
    order_id = Column(_UUID, nullable=False)
    hub_id = Column(_UUID, nullable=False)
    cohort_id = Column(_UUID, nullable=False)
    vendor_id = Column(_UUID, nullable=False)
    order_item_id = Column(_UUID, nullable=False)
    quantity = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        ForeignKeyConstraint(
            ["package_id", "package_version", "order_id", "hub_id"],
            [
                "hub_package_versions.package_id",
                "hub_package_versions.version",
                "hub_package_versions.order_id",
                "hub_package_versions.hub_id",
            ],
            name="fk_hub_package_items_version_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["cohort_id", "order_item_id", "order_id", "vendor_id"],
            [
                "cohort_item_allocations.cohort_id",
                "cohort_item_allocations.order_item_id",
                "cohort_item_allocations.order_id",
                "cohort_item_allocations.vendor_id",
            ],
            name="fk_hub_package_items_allocation_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="ck_hub_package_items_quantity"),
        UniqueConstraint(
            "package_id",
            "package_version",
            "cohort_id",
            "vendor_id",
            "order_item_id",
            name="uq_hub_package_items_composition",
        ),
    )


class HubPackageSeal(Base):
    """Append-preserved seal application with one atomic retirement mutation."""

    __tablename__ = "hub_package_seals"

    id = _id_column()
    package_id = Column(_UUID, nullable=False)
    package_version = Column(Integer, nullable=False)
    opaque_value = Column(String(200), nullable=False)
    applied_by_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    applied_at = Column(DateTime(timezone=True), nullable=False)
    retired_at = Column(DateTime(timezone=True))
    retired_by_id = Column(_UUID, ForeignKey("users.id", ondelete="RESTRICT"))
    retirement_reason = Column(String(200))

    __table_args__ = (
        ForeignKeyConstraint(
            ["package_id", "package_version"],
            ["hub_package_versions.package_id", "hub_package_versions.version"],
            name="fk_hub_package_seals_version",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "opaque_value = btrim(opaque_value) AND length(opaque_value) > 0",
            name="ck_hub_package_seals_value",
        ),
        CheckConstraint(
            "(retired_at IS NULL AND retired_by_id IS NULL AND retirement_reason IS NULL) "
            "OR (retired_at IS NOT NULL AND retired_by_id IS NOT NULL "
            "AND retirement_reason = btrim(retirement_reason) "
            "AND length(retirement_reason) > 0 AND retired_at >= applied_at)",
            name="ck_hub_package_seals_retirement",
        ),
        UniqueConstraint("opaque_value", name="uq_hub_package_seals_opaque_value"),
        UniqueConstraint(
            "id", "package_id", "package_version", name="uq_hub_package_seals_binding"
        ),
        Index(
            "uq_hub_package_seals_active",
            "package_id",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
        ),
    )


class CustodyStream(Base):
    """Stable serialization anchor for one physical package-version custody chain."""

    __tablename__ = "custody_streams"

    id = _id_column()
    cohort_id = Column(_UUID, nullable=False)
    order_id = Column(_UUID, nullable=False)
    vendor_id = Column(_UUID, nullable=False)
    hub_id = Column(
        _UUID, ForeignKey("fulfillment_hubs.id", ondelete="RESTRICT"), nullable=False
    )
    package_id = Column(_UUID, nullable=False)
    package_version = Column(Integer, nullable=False)
    next_version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        ForeignKeyConstraint(
            ["cohort_id", "order_id", "vendor_id"],
            [
                "fulfillment_cohorts.id",
                "fulfillment_cohorts.order_id",
                "fulfillment_cohorts.vendor_id",
            ],
            name="fk_custody_streams_cohort_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["package_id", "package_version", "order_id", "hub_id"],
            [
                "hub_package_versions.package_id",
                "hub_package_versions.version",
                "hub_package_versions.order_id",
                "hub_package_versions.hub_id",
            ],
            name="fk_custody_streams_package_version_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint("next_version > 0", name="ck_custody_streams_next"),
        UniqueConstraint(
            "cohort_id",
            "order_id",
            "vendor_id",
            "hub_id",
            "package_id",
            "package_version",
            name="uq_custody_streams_subject",
        ),
        UniqueConstraint(
            "id",
            "cohort_id",
            "order_id",
            "vendor_id",
            "hub_id",
            "package_id",
            "package_version",
            name="uq_custody_streams_identity",
        ),
    )


class CustodyEvent(Base):
    """Append-only, linearly chained physical-custody evidence."""

    __tablename__ = "custody_events"

    id = _id_column()
    stream_id = Column(_UUID, nullable=False)
    version = Column(Integer, nullable=False)
    previous_event_id = Column(
        _UUID, ForeignKey("custody_events.id", ondelete="RESTRICT")
    )
    cohort_id = Column(_UUID, nullable=False)
    order_id = Column(_UUID, nullable=False)
    vendor_id = Column(_UUID, nullable=False)
    hub_id = Column(_UUID, nullable=False)
    event_type = Column(String(50), nullable=False)
    actor_type = Column(String(30), nullable=False)
    actor_id = Column(String(200), nullable=False)
    source_system = Column(String(100), nullable=False)
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    recorded_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)
    location = Column(String(200), nullable=False)
    counterparty = Column(String(200))
    correction_reason = Column(String(300))
    evidence_ref = Column(String(500))
    evidence_hash = Column(String(64))
    package_id = Column(_UUID)
    package_version = Column(Integer)
    seal_id = Column(_UUID)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        ForeignKeyConstraint(
            [
                "stream_id",
                "cohort_id",
                "order_id",
                "vendor_id",
                "hub_id",
                "package_id",
                "package_version",
            ],
            [
                "custody_streams.id",
                "custody_streams.cohort_id",
                "custody_streams.order_id",
                "custody_streams.vendor_id",
                "custody_streams.hub_id",
                "custody_streams.package_id",
                "custody_streams.package_version",
            ],
            name="fk_custody_events_stream_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["seal_id", "package_id", "package_version"],
            [
                "hub_package_seals.id",
                "hub_package_seals.package_id",
                "hub_package_seals.package_version",
            ],
            name="fk_custody_events_seal_binding",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "event_type IN ('packed', 'sealed', 'staged', 'released', 'tendered', "
            "'provider_accepted', 'correction')",
            name="ck_custody_events_type",
        ),
        CheckConstraint(
            "actor_type IN ('user', 'system', 'carrier')",
            name="ck_custody_events_actor_type",
        ),
        CheckConstraint(
            "version > 0 AND ((version = 1 AND previous_event_id IS NULL) OR "
            "(version > 1 AND previous_event_id IS NOT NULL))",
            name="ck_custody_events_chain",
        ),
        CheckConstraint(
            "recorded_at >= occurred_at", name="ck_custody_events_recording_order"
        ),
        CheckConstraint(
            "event_type = btrim(event_type) AND actor_id = btrim(actor_id) "
            "AND length(actor_id) > 0 AND source_system = btrim(source_system) "
            "AND length(source_system) > 0 AND source_command = btrim(source_command) "
            "AND length(source_command) > 0 AND idempotency_key = btrim(idempotency_key) "
            "AND length(idempotency_key) > 0 "
            "AND location = btrim(location) AND length(location) > 0 "
            "AND (counterparty IS NULL OR (counterparty = btrim(counterparty) "
            "AND length(counterparty) > 0))",
            name="ck_custody_events_canonical",
        ),
        CheckConstraint(
            "(event_type = 'correction' AND correction_reason IS NOT NULL "
            "AND correction_reason = btrim(correction_reason) "
            "AND length(correction_reason) > 0) OR "
            "(event_type <> 'correction' AND correction_reason IS NULL)",
            name="ck_custody_events_correction",
        ),
        CheckConstraint(
            "(evidence_ref IS NULL AND evidence_hash IS NULL) OR "
            "(evidence_ref IS NOT NULL AND evidence_hash IS NOT NULL "
            "AND evidence_ref = btrim(evidence_ref) AND length(evidence_ref) > 0 "
            "AND evidence_ref NOT LIKE '%://%' AND evidence_ref NOT LIKE '/%' "
            "AND evidence_ref NOT LIKE '%..%' AND evidence_hash ~ '^[0-9a-f]{64}$')",
            name="ck_custody_events_private_evidence",
        ),
        CheckConstraint(
            "package_id IS NOT NULL AND package_version IS NOT NULL AND "
            "((event_type = 'packed' AND seal_id IS NULL) OR "
            "(event_type <> 'packed' AND seal_id IS NOT NULL))",
            name="ck_custody_events_package_binding",
        ),
        UniqueConstraint("stream_id", "version", name="uq_custody_events_version"),
        UniqueConstraint(
            "stream_id", "idempotency_key", name="uq_custody_events_replay"
        ),
        UniqueConstraint(
            "id", "stream_id", "version", name="uq_custody_events_identity"
        ),
    )


class OutboundShipmentIntent(Base):
    """Immutable, provider-neutral intent tied to exact ready package truth."""

    __tablename__ = "outbound_shipment_intents"

    id = _id_column()
    package_id = Column(_UUID, nullable=False)
    package_version = Column(Integer, nullable=False)
    seal_id = Column(_UUID, nullable=False)
    order_id = Column(_UUID, nullable=False)
    origin_hub_id = Column(_UUID, nullable=False)
    destination_name = Column(String(200), nullable=False)
    destination_phone = Column(String(40), nullable=False)
    destination_address_line1 = Column(String(300), nullable=False)
    destination_address_line2 = Column(String(300))
    destination_city = Column(String(120), nullable=False)
    destination_state = Column(String(120), nullable=False)
    destination_postal_code = Column(String(20), nullable=False)
    destination_country_code = Column(String(2), nullable=False, server_default="NG")
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    created_by_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        ForeignKeyConstraint(
            ["seal_id", "package_id", "package_version"],
            [
                "hub_package_seals.id",
                "hub_package_seals.package_id",
                "hub_package_seals.package_version",
            ],
            name="fk_outbound_intents_seal_binding",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["package_id", "order_id", "origin_hub_id"],
            ["hub_packages.id", "hub_packages.order_id", "hub_packages.hub_id"],
            name="fk_outbound_intents_package_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "destination_country_code = 'NG'",
            name="ck_outbound_intents_country_ng",
        ),
        CheckConstraint(
            "destination_name = btrim(destination_name) AND length(destination_name) > 0 "
            "AND destination_phone = btrim(destination_phone) AND length(destination_phone) > 0 "
            "AND destination_address_line1 = btrim(destination_address_line1) "
            "AND length(destination_address_line1) > 0 "
            "AND destination_city = btrim(destination_city) AND length(destination_city) > 0 "
            "AND destination_state = btrim(destination_state) AND length(destination_state) > 0 "
            "AND destination_postal_code = btrim(destination_postal_code) "
            "AND length(destination_postal_code) > 0",
            name="ck_outbound_intents_destination",
        ),
        CheckConstraint(
            "source_command = btrim(source_command) AND length(source_command) > 0 "
            "AND idempotency_key = btrim(idempotency_key) "
            "AND length(idempotency_key) > 0",
            name="ck_outbound_intents_canonical",
        ),
        UniqueConstraint(
            "package_id", "idempotency_key", name="uq_outbound_intents_replay"
        ),
        UniqueConstraint("id", "package_id", name="uq_outbound_intents_identity"),
        Index(
            "uq_outbound_shipment_intents_active",
            "package_id",
            "package_version",
            unique=True,
        ),
    )


class OutboundShipmentIntentInvalidation(Base):
    """Append-only invalidation permitting a later repack; intent remains intact."""

    __tablename__ = "outbound_shipment_intent_invalidations"

    id = _id_column()
    intent_id = Column(
        _UUID,
        ForeignKey("outbound_shipment_intents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reason = Column(String(200), nullable=False)
    actor_type = Column(String(30), nullable=False)
    actor_id = Column(String(200), nullable=False)
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    invalidated_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('user', 'system')",
            name="ck_outbound_invalidations_actor_type",
        ),
        CheckConstraint(
            "reason = btrim(reason) AND length(reason) > 0 "
            "AND actor_id = btrim(actor_id) AND length(actor_id) > 0 "
            "AND source_command = btrim(source_command) AND length(source_command) > 0 "
            "AND idempotency_key = btrim(idempotency_key) "
            "AND length(idempotency_key) > 0",
            name="ck_outbound_invalidations_canonical",
        ),
        UniqueConstraint("intent_id", name="uq_outbound_invalidations_intent"),
        UniqueConstraint("idempotency_key", name="uq_outbound_invalidations_replay"),
    )


PACKAGE_CUSTODY_TRIGGER_DDLS = (
    """
CREATE FUNCTION validate_hub_package_write() RETURNS trigger AS $$
DECLARE active_seals integer; item_count integer; version_count integer; prerequisite_time timestamptz;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='packages are audit records and cannot be deleted';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'packing' OR NEW.current_version <> 1 OR NEW.row_version <> 1
           OR NEW.sealed_at IS NOT NULL OR NEW.ready_at IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='packages must start packing at version one';
        END IF;
        SELECT max(s.completed_at) INTO prerequisite_time FROM hub_qc_sessions s
         WHERE s.order_id=NEW.order_id AND s.hub_id=NEW.hub_id AND s.state='qc_passed'
           AND NOT EXISTS (SELECT 1 FROM hub_qc_sessions newer WHERE newer.previous_session_id=s.id);
        IF prerequisite_time IS NULL OR NEW.created_at < prerequisite_time
           OR NEW.created_at > clock_timestamp() THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package creation must follow terminal QC truth';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.order_id IS DISTINCT FROM OLD.order_id
       OR NEW.hub_id IS DISTINCT FROM OLD.hub_id
       OR NEW.source_command IS DISTINCT FROM OLD.source_command
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package replay identity is immutable';
    END IF;
    IF NEW.row_version <> OLD.row_version + 1 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package row version must advance exactly once';
    END IF;
    IF OLD.state = 'packing' AND NEW.state = 'sealed' THEN
        IF NEW.current_version <> OLD.current_version OR NEW.sealed_at IS NULL
           OR NEW.ready_at IS NOT NULL OR NEW.sealed_at < OLD.created_at
           OR NEW.sealed_at > clock_timestamp() THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='invalid package sealing chronology';
        END IF;
        SELECT count(*) INTO active_seals FROM hub_package_seals
         WHERE package_id=OLD.id AND package_version=OLD.current_version AND retired_at IS NULL;
        SELECT count(*) INTO item_count FROM hub_package_items
         WHERE package_id=OLD.id AND package_version=OLD.current_version;
        SELECT count(*) INTO version_count FROM hub_package_versions
         WHERE package_id=OLD.id AND version=OLD.current_version;
        SELECT GREATEST(
            v.packed_at,
            COALESCE((SELECT max(i.created_at) FROM hub_package_items i
                       WHERE i.package_id=OLD.id AND i.package_version=OLD.current_version), v.packed_at),
            COALESCE((SELECT max(s.applied_at) FROM hub_package_seals s
                       WHERE s.package_id=OLD.id AND s.package_version=OLD.current_version
                         AND s.retired_at IS NULL), v.packed_at)
        ) INTO prerequisite_time FROM hub_package_versions v
         WHERE v.package_id=OLD.id AND v.version=OLD.current_version;
        IF active_seals <> 1 OR item_count = 0 OR version_count <> 1 THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='sealing requires one version, composition, and one active seal';
        END IF;
        IF NEW.sealed_at < prerequisite_time THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='sealing must follow package version, composition, and seal';
        END IF;
    ELSIF OLD.state = 'sealed' AND NEW.state = 'ready' THEN
        IF NEW.current_version <> OLD.current_version OR NEW.sealed_at IS DISTINCT FROM OLD.sealed_at
           OR NEW.ready_at IS NULL OR NEW.ready_at < OLD.sealed_at OR NEW.ready_at > clock_timestamp() THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='invalid package readiness chronology';
        END IF;
        SELECT count(*) INTO active_seals FROM hub_package_seals
         WHERE package_id=OLD.id AND package_version=OLD.current_version AND retired_at IS NULL;
        IF active_seals <> 1 THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='ready package requires one active current seal';
        END IF;
    ELSIF OLD.state IN ('sealed','ready') AND NEW.state = 'packing' THEN
        IF NEW.current_version <> OLD.current_version + 1 OR NEW.sealed_at IS NOT NULL
           OR NEW.ready_at IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='repack must advance exactly one version and clear terminal times';
        END IF;
        IF EXISTS (SELECT 1 FROM hub_package_seals WHERE package_id=OLD.id AND retired_at IS NULL) THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='active seal must retire before repack';
        END IF;
        IF EXISTS (
            SELECT 1 FROM outbound_shipment_intents i
             WHERE i.package_id=OLD.id
               AND NOT EXISTS (SELECT 1 FROM outbound_shipment_intent_invalidations x WHERE x.intent_id=i.id)
        ) THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='active outbound intent must be invalidated before repack';
        END IF;
        IF EXISTS (
            SELECT 1 FROM custody_events e
             WHERE e.package_id=OLD.id AND e.package_version=OLD.current_version
               AND e.event_type IN ('released','tendered','provider_accepted')
        ) THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package cannot repack after custody handoff';
        END IF;
    ELSE
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='illegal package state transition';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_hub_packages_write
BEFORE INSERT OR UPDATE OR DELETE ON hub_packages
FOR EACH ROW EXECUTE FUNCTION validate_hub_package_write()
    """,
    """
CREATE FUNCTION validate_hub_package_version_insert() RETURNS trigger AS $$
DECLARE package hub_packages%%ROWTYPE; qc_completed timestamptz; predecessor_boundary timestamptz;
BEGIN
    SELECT * INTO package FROM hub_packages WHERE id=NEW.package_id FOR UPDATE;
    IF NOT FOUND OR package.order_id<>NEW.order_id OR package.hub_id<>NEW.hub_id
       OR package.state<>'packing' OR package.current_version<>NEW.version THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package version must bind the current packing aggregate';
    END IF;
    SELECT max(s.completed_at) INTO qc_completed FROM hub_qc_sessions s
     WHERE s.order_id=NEW.order_id AND s.hub_id=NEW.hub_id AND s.state='qc_passed'
       AND NOT EXISTS (SELECT 1 FROM hub_qc_sessions newer WHERE newer.previous_session_id=s.id);
    IF qc_completed IS NULL OR NEW.packed_at < qc_completed
       OR NEW.packed_at < package.created_at OR NEW.packed_at > clock_timestamp()
       OR NEW.created_at < NEW.packed_at OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package version timestamps violate subject chronology';
    END IF;
    IF NEW.version=1 THEN
        IF EXISTS (SELECT 1 FROM hub_package_versions WHERE package_id=NEW.package_id) THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='initial package version already exists';
        END IF;
    ELSIF NOT EXISTS (
        SELECT 1 FROM hub_package_versions
         WHERE package_id=NEW.package_id AND version=NEW.version-1
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package version predecessor is missing';
    ELSE
        SELECT GREATEST(
            predecessor.packed_at,
            predecessor.created_at,
            COALESCE((SELECT max(seal.retired_at) FROM hub_package_seals seal
                       WHERE seal.package_id=NEW.package_id
                         AND seal.package_version=NEW.version-1), predecessor.created_at)
        ) INTO predecessor_boundary FROM hub_package_versions predecessor
         WHERE predecessor.package_id=NEW.package_id AND predecessor.version=NEW.version-1;
        IF NEW.packed_at < predecessor_boundary THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='successor package version must follow predecessor closeout';
        END IF;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_hub_package_versions_insert
BEFORE INSERT ON hub_package_versions
FOR EACH ROW EXECUTE FUNCTION validate_hub_package_version_insert()
    """,
    """
CREATE FUNCTION reject_package_immutable_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE='23503', MESSAGE=TG_TABLE_NAME || ' rows are immutable audit records';
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_hub_package_versions_immutable
BEFORE UPDATE OR DELETE ON hub_package_versions
FOR EACH ROW EXECUTE FUNCTION reject_package_immutable_mutation()
    """,
    """
CREATE FUNCTION validate_hub_package_item_insert() RETURNS trigger AS $$
DECLARE package hub_packages%%ROWTYPE; packed_at_value timestamptz; qc_completed timestamptz; passed_quantity bigint; consumed_quantity bigint;
BEGIN
    SELECT * INTO package FROM hub_packages WHERE id=NEW.package_id FOR UPDATE;
    IF NOT FOUND OR package.state<>'packing' OR package.current_version<>NEW.package_version
       OR package.order_id<>NEW.order_id OR package.hub_id<>NEW.hub_id THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package items require the current packing version';
    END IF;
    IF EXISTS (SELECT 1 FROM hub_package_seals WHERE package_id=NEW.package_id AND retired_at IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package composition cannot change after seal application';
    END IF;
    SELECT packed_at INTO packed_at_value FROM hub_package_versions
     WHERE package_id=NEW.package_id AND version=NEW.package_version;
    SELECT max(s.completed_at) INTO qc_completed FROM hub_qc_sessions s
     WHERE s.cohort_id=NEW.cohort_id AND s.order_id=NEW.order_id
       AND s.vendor_id=NEW.vendor_id AND s.hub_id=NEW.hub_id AND s.state='qc_passed'
       AND NOT EXISTS (SELECT 1 FROM hub_qc_sessions newer WHERE newer.previous_session_id=s.id);
    IF qc_completed IS NULL OR packed_at_value < qc_completed
       OR NEW.created_at < qc_completed OR NEW.created_at < packed_at_value
       OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package item chronology is invalid';
    END IF;
    PERFORM 1 FROM cohort_item_allocations
     WHERE cohort_id=NEW.cohort_id AND order_item_id=NEW.order_item_id
       AND order_id=NEW.order_id AND vendor_id=NEW.vendor_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package item allocation identity is invalid';
    END IF;
    SELECT COALESCE(sum(i.inspected_quantity),0) INTO passed_quantity
      FROM hub_qc_inspections i
      JOIN hub_qc_sessions s ON s.id=i.qc_session_id
     WHERE i.cohort_id=NEW.cohort_id AND i.order_id=NEW.order_id
       AND i.vendor_id=NEW.vendor_id AND i.hub_id=NEW.hub_id
       AND i.order_item_id=NEW.order_item_id AND i.decision='pass'
       AND s.state='qc_passed'
       AND NOT EXISTS (SELECT 1 FROM hub_qc_sessions newer WHERE newer.previous_session_id=s.id);
    SELECT COALESCE(sum(item.quantity),0) INTO consumed_quantity
      FROM hub_package_items item
      JOIN hub_packages aggregate ON aggregate.id=item.package_id
       AND aggregate.current_version=item.package_version
     WHERE item.cohort_id=NEW.cohort_id AND item.order_id=NEW.order_id
       AND item.vendor_id=NEW.vendor_id AND item.hub_id=NEW.hub_id
       AND item.order_item_id=NEW.order_item_id;
    IF consumed_quantity + NEW.quantity > passed_quantity THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package quantity exceeds terminal passed inspection quantity';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_hub_package_items_insert
BEFORE INSERT ON hub_package_items
FOR EACH ROW EXECUTE FUNCTION validate_hub_package_item_insert()
    """,
    """
CREATE TRIGGER tr_hub_package_items_immutable
BEFORE UPDATE OR DELETE ON hub_package_items
FOR EACH ROW EXECUTE FUNCTION reject_package_immutable_mutation()
    """,
    """
CREATE FUNCTION validate_hub_package_seal_insert() RETURNS trigger AS $$
DECLARE package hub_packages%%ROWTYPE; packed_at_value timestamptz; composition_time timestamptz; composition_count integer;
BEGIN
    SELECT * INTO package FROM hub_packages WHERE id=NEW.package_id FOR UPDATE;
    SELECT packed_at INTO packed_at_value FROM hub_package_versions
     WHERE package_id=NEW.package_id AND version=NEW.package_version;
    IF NOT FOUND OR package.state<>'packing' OR package.current_version<>NEW.package_version THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='seal requires the current packing version';
    END IF;
    IF NEW.applied_at < packed_at_value OR NEW.applied_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='seal timestamp violates package chronology';
    END IF;
    SELECT count(*),max(created_at) INTO composition_count,composition_time
      FROM hub_package_items WHERE package_id=NEW.package_id AND package_version=NEW.package_version;
    IF composition_count=0 OR NEW.applied_at < composition_time THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='seal application must follow completed composition';
    END IF;
    IF NEW.retired_at IS NOT NULL OR NEW.retired_by_id IS NOT NULL OR NEW.retirement_reason IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='seals must start active';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_hub_package_seals_insert
BEFORE INSERT ON hub_package_seals
FOR EACH ROW EXECUTE FUNCTION validate_hub_package_seal_insert()
    """,
    """
CREATE FUNCTION validate_hub_package_seal_mutation() RETURNS trigger AS $$
DECLARE intent_boundary timestamptz; custody_boundary timestamptz; package_boundary timestamptz;
BEGIN
    IF TG_OP='DELETE' THEN
        RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='seals are audit records and cannot be deleted';
    END IF;
    SELECT GREATEST(OLD.applied_at,COALESCE(sealed_at,OLD.applied_at),COALESCE(ready_at,OLD.applied_at))
      INTO package_boundary FROM hub_packages WHERE id=OLD.package_id FOR UPDATE;
    IF OLD.retired_at IS NOT NULL OR NEW.id IS DISTINCT FROM OLD.id
       OR NEW.package_id IS DISTINCT FROM OLD.package_id
       OR NEW.package_version IS DISTINCT FROM OLD.package_version
       OR NEW.opaque_value IS DISTINCT FROM OLD.opaque_value
       OR NEW.applied_by_id IS DISTINCT FROM OLD.applied_by_id
       OR NEW.applied_at IS DISTINCT FROM OLD.applied_at
       OR NEW.retired_at IS NULL OR NEW.retired_by_id IS NULL
       OR NEW.retirement_reason IS NULL OR NEW.retired_at < OLD.applied_at
       OR NEW.retired_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='seal permits one-time atomic retirement only';
    END IF;
    IF EXISTS (
        SELECT 1 FROM outbound_shipment_intents i WHERE i.package_id=OLD.package_id
         AND NOT EXISTS (SELECT 1 FROM outbound_shipment_intent_invalidations x WHERE x.intent_id=i.id)
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='active outbound intent must be invalidated before seal retirement';
    END IF;
    IF NEW.retired_at < package_boundary THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='seal retirement must follow package terminal chronology';
    END IF;
    SELECT max(GREATEST(i.created_at, x.invalidated_at)) INTO intent_boundary
      FROM outbound_shipment_intents i
      JOIN outbound_shipment_intent_invalidations x ON x.intent_id=i.id
     WHERE i.package_id=OLD.package_id AND i.package_version=OLD.package_version
       AND i.seal_id=OLD.id;
    IF intent_boundary IS NOT NULL AND NEW.retired_at < intent_boundary THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='seal retirement must follow outbound intent invalidation';
    END IF;
    SELECT max(occurred_at) INTO custody_boundary FROM custody_events WHERE seal_id=OLD.id;
    IF custody_boundary IS NOT NULL AND NEW.retired_at < custody_boundary THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='seal retirement must follow bound custody evidence';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_hub_package_seals_mutation
BEFORE UPDATE OR DELETE ON hub_package_seals
FOR EACH ROW EXECUTE FUNCTION validate_hub_package_seal_mutation()
    """,
    """
CREATE FUNCTION validate_terminal_package_seal_cardinality() RETURNS trigger AS $$
DECLARE package_id_value uuid; package_state varchar; package_version_value integer; active_count integer;
BEGIN
    IF TG_TABLE_NAME='hub_packages' THEN
        package_id_value := NEW.id;
    ELSE
        package_id_value := COALESCE(NEW.package_id, OLD.package_id);
    END IF;
    SELECT state,current_version INTO package_state,package_version_value
      FROM hub_packages WHERE id=package_id_value;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT count(*) INTO active_count FROM hub_package_seals
     WHERE package_id=package_id_value AND package_version=package_version_value
       AND retired_at IS NULL;
    IF package_state IN ('sealed','ready') AND active_count<>1 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='terminal package requires exactly one active current seal';
    ELSIF package_state='packing' AND active_count<>0 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='packing package cannot commit with an active seal';
    END IF;
    RETURN NULL;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE CONSTRAINT TRIGGER tr_hub_packages_seal_cardinality
AFTER INSERT OR UPDATE ON hub_packages
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_terminal_package_seal_cardinality()
    """,
    """
CREATE CONSTRAINT TRIGGER tr_hub_package_seals_cardinality
AFTER INSERT OR UPDATE OR DELETE ON hub_package_seals
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_terminal_package_seal_cardinality()
    """,
    """
CREATE FUNCTION validate_custody_stream_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP='INSERT' THEN
        IF NEW.next_version<>1 OR NEW.created_at>clock_timestamp() THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody stream cannot be future-dated';
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP='DELETE' THEN
        RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='custody streams are audit anchors and cannot be deleted';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.cohort_id IS DISTINCT FROM OLD.cohort_id
       OR NEW.order_id IS DISTINCT FROM OLD.order_id OR NEW.vendor_id IS DISTINCT FROM OLD.vendor_id
       OR NEW.hub_id IS DISTINCT FROM OLD.hub_id
       OR NEW.package_id IS DISTINCT FROM OLD.package_id
       OR NEW.package_version IS DISTINCT FROM OLD.package_version
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.next_version<>OLD.next_version+1 OR pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody stream may advance only through an event insert';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_custody_streams_mutation
BEFORE INSERT OR UPDATE OR DELETE ON custody_streams
FOR EACH ROW EXECUTE FUNCTION validate_custody_stream_mutation()
    """,
    """
CREATE FUNCTION validate_custody_event_insert() RETURNS trigger AS $$
DECLARE stream custody_streams%%ROWTYPE; tip_id uuid; tip_time timestamptz; prior_lifecycle varchar; package_state varchar; current_package_version integer; packed_time timestamptz; seal_applied timestamptz; seal_retired timestamptz;
BEGIN
    SELECT * INTO stream FROM custody_streams WHERE id=NEW.stream_id FOR UPDATE;
    IF NOT FOUND OR stream.cohort_id<>NEW.cohort_id OR stream.order_id<>NEW.order_id
       OR stream.vendor_id<>NEW.vendor_id OR stream.hub_id<>NEW.hub_id
       OR stream.package_id<>NEW.package_id OR stream.package_version<>NEW.package_version THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody event aggregate identity is invalid';
    END IF;
    SELECT id, occurred_at INTO tip_id, tip_time FROM custody_events
     WHERE stream_id=NEW.stream_id ORDER BY version DESC LIMIT 1;
    IF NEW.version<>stream.next_version OR NEW.previous_event_id IS DISTINCT FROM tip_id THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody chain fork';
    END IF;
    SELECT event_type INTO prior_lifecycle FROM custody_events
     WHERE stream_id=NEW.stream_id AND event_type<>'correction'
     ORDER BY version DESC LIMIT 1;
    IF NEW.event_type='correction' THEN
        IF prior_lifecycle IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='illegal custody lifecycle transition';
        END IF;
    ELSIF prior_lifecycle IS NULL THEN
        IF NEW.event_type<>'packed' THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='illegal custody lifecycle transition';
        END IF;
    ELSIF NOT (
        (prior_lifecycle='packed' AND NEW.event_type='sealed') OR
        (prior_lifecycle='sealed' AND NEW.event_type='staged') OR
        (prior_lifecycle='staged' AND NEW.event_type='released') OR
        (prior_lifecycle='released' AND NEW.event_type='tendered') OR
        (prior_lifecycle='tendered' AND NEW.event_type='provider_accepted')
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='illegal custody lifecycle transition';
    END IF;
    IF NEW.recorded_at < stream.created_at OR (tip_time IS NOT NULL AND NEW.occurred_at < tip_time)
       OR NEW.recorded_at < NEW.occurred_at OR NEW.recorded_at > clock_timestamp()
       OR NEW.created_at < NEW.recorded_at OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody event chronology is invalid';
    END IF;
    IF NEW.event_type<>'packed' THEN
        SELECT applied_at,retired_at INTO seal_applied,seal_retired
          FROM hub_package_seals WHERE id=NEW.seal_id
           AND package_id=NEW.package_id AND package_version=NEW.package_version
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody seal interval is invalid';
        END IF;
    END IF;
    SELECT p.state,p.current_version,v.packed_at
      INTO package_state,current_package_version,packed_time
      FROM hub_packages p JOIN hub_package_versions v
        ON v.package_id=p.id AND v.version=NEW.package_version
     WHERE p.id=NEW.package_id AND p.order_id=NEW.order_id AND p.hub_id=NEW.hub_id
     FOR UPDATE OF p;
    IF NOT FOUND OR current_package_version<>NEW.package_version
       OR NEW.occurred_at < packed_time
       OR NOT EXISTS (
            SELECT 1 FROM hub_package_items WHERE package_id=NEW.package_id
             AND package_version=NEW.package_version AND cohort_id=NEW.cohort_id
             AND vendor_id=NEW.vendor_id AND order_id=NEW.order_id AND hub_id=NEW.hub_id
       ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody package binding is invalid';
    END IF;
    IF NEW.event_type<>'packed' THEN
        IF package_state NOT IN ('sealed','ready') THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody event requires sealed package truth';
        END IF;
        IF NEW.occurred_at < seal_applied
           OR (seal_retired IS NOT NULL AND NEW.occurred_at > seal_retired) THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody seal interval is invalid';
        END IF;
    END IF;
    UPDATE custody_streams SET next_version=next_version+1 WHERE id=NEW.stream_id;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_custody_events_insert
BEFORE INSERT ON custody_events
FOR EACH ROW EXECUTE FUNCTION validate_custody_event_insert()
    """,
    """
CREATE TRIGGER tr_custody_events_immutable
BEFORE UPDATE OR DELETE ON custody_events
FOR EACH ROW EXECUTE FUNCTION reject_package_immutable_mutation()
    """,
    """
CREATE FUNCTION validate_outbound_intent_insert() RETURNS trigger AS $$
DECLARE package hub_packages%%ROWTYPE;
BEGIN
    PERFORM 1 FROM hub_package_seals WHERE id=NEW.seal_id
      AND package_id=NEW.package_id AND package_version=NEW.package_version
      AND retired_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent requires exact current ready package and active seal';
    END IF;
    SELECT * INTO package FROM hub_packages WHERE id=NEW.package_id FOR UPDATE;
    IF NOT FOUND OR package.state<>'ready' OR package.current_version<>NEW.package_version
       OR package.order_id<>NEW.order_id OR package.hub_id<>NEW.origin_hub_id
       OR NEW.created_at < package.ready_at OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent requires exact current ready package and active seal';
    END IF;
    IF EXISTS (
        SELECT 1 FROM outbound_shipment_intents i WHERE i.package_id=NEW.package_id
         AND NOT EXISTS (SELECT 1 FROM outbound_shipment_intent_invalidations x WHERE x.intent_id=i.id)
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package already has an active outbound intent';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_outbound_shipment_intents_insert
BEFORE INSERT ON outbound_shipment_intents
FOR EACH ROW EXECUTE FUNCTION validate_outbound_intent_insert()
    """,
    """
CREATE TRIGGER tr_outbound_shipment_intents_immutable
BEFORE UPDATE OR DELETE ON outbound_shipment_intents
FOR EACH ROW EXECUTE FUNCTION reject_package_immutable_mutation()
    """,
    """
CREATE FUNCTION validate_outbound_intent_invalidation_insert() RETURNS trigger AS $$
DECLARE package_id_value uuid; seal_id_value uuid; intent_created_at timestamptz;
BEGIN
    SELECT package_id,seal_id,created_at INTO package_id_value,seal_id_value,intent_created_at
      FROM outbound_shipment_intents WHERE id=NEW.intent_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent does not exist';
    END IF;
    PERFORM 1 FROM hub_package_seals WHERE id=seal_id_value FOR UPDATE;
    PERFORM 1 FROM hub_packages WHERE id=package_id_value FOR UPDATE;
    IF EXISTS (
        SELECT 1 FROM custody_events e JOIN outbound_shipment_intents i
          ON i.package_id=e.package_id AND i.package_version=e.package_version
         WHERE i.id=NEW.intent_id AND e.event_type IN ('released','tendered','provider_accepted')
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent cannot invalidate after custody handoff';
    END IF;
    IF NEW.invalidated_at < intent_created_at OR NEW.invalidated_at > clock_timestamp()
       OR NEW.created_at < NEW.invalidated_at OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent invalidation chronology is invalid';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_outbound_intent_invalidations_insert
BEFORE INSERT ON outbound_shipment_intent_invalidations
FOR EACH ROW EXECUTE FUNCTION validate_outbound_intent_invalidation_insert()
    """,
    """
CREATE TRIGGER tr_outbound_intent_invalidations_immutable
BEFORE UPDATE OR DELETE ON outbound_shipment_intent_invalidations
FOR EACH ROW EXECUTE FUNCTION reject_package_immutable_mutation()
    """,
)

PACKAGE_CUSTODY_DROP_DDLS = (
    "DROP FUNCTION IF EXISTS validate_terminal_package_seal_cardinality() CASCADE",
    "DROP FUNCTION IF EXISTS validate_outbound_intent_invalidation_insert() CASCADE",
    "DROP FUNCTION IF EXISTS validate_outbound_intent_insert() CASCADE",
    "DROP FUNCTION IF EXISTS validate_custody_event_insert() CASCADE",
    "DROP FUNCTION IF EXISTS validate_custody_stream_mutation() CASCADE",
    "DROP FUNCTION IF EXISTS validate_hub_package_seal_mutation() CASCADE",
    "DROP FUNCTION IF EXISTS validate_hub_package_seal_insert() CASCADE",
    "DROP FUNCTION IF EXISTS validate_hub_package_item_insert() CASCADE",
    "DROP FUNCTION IF EXISTS reject_package_immutable_mutation() CASCADE",
    "DROP FUNCTION IF EXISTS validate_hub_package_version_insert() CASCADE",
    "DROP FUNCTION IF EXISTS validate_hub_package_write() CASCADE",
)

for _ddl in PACKAGE_CUSTODY_TRIGGER_DDLS:
    event.listen(
        OutboundShipmentIntentInvalidation.__table__, "after_create", DDL(_ddl)
    )
for _ddl in PACKAGE_CUSTODY_DROP_DDLS:
    event.listen(HubPackage.__table__, "after_drop", DDL(_ddl))
