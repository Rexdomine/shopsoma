"""Hub receipt, discrepancy, private evidence, and quality-control persistence."""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    DDL,
    Enum as SQLEnum,
    event,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.base import Base
from app.models.fulfillment_cohort import _enum_values


class DiscrepancyType(str, enum.Enum):
    SHORTAGE = "shortage"
    EXCESS = "excess"
    WRONG_ITEM = "wrong_item"
    DAMAGE = "damage"


class QCDecision(str, enum.Enum):
    PENDING = "pending"
    PASS = "pass"
    FAIL = "fail"
    REJECTED = "rejected"


class QuarantineDisposition(str, enum.Enum):
    NOT_APPLICABLE = "not_applicable"
    QUARANTINED = "quarantined"
    RETURN_TO_VENDOR = "return_to_vendor"
    REWORK = "rework"
    REFUND = "refund"
    DISPOSAL = "disposal"
    INVESTIGATION = "investigation"


class EvidencePurpose(str, enum.Enum):
    HUB_RECEIPT = "hub_receipt"
    DISCREPANCY = "discrepancy"
    QC_INSPECTION = "qc_inspection"
    REMEDIATION = "remediation"


class RemediationAction(str, enum.Enum):
    REWORK = "rework"
    RETURN_TO_VENDOR = "return_to_vendor"
    REFUND = "refund"
    DISPOSAL = "disposal"
    INVESTIGATE = "investigate"


class RemediationState(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


_UUID = UUID(as_uuid=True)


def _timestamps():
    return (
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.statement_timestamp(),
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.statement_timestamp(),
            onupdate=func.statement_timestamp(),
        ),
    )


class HubReceiptSession(Base):
    """One idempotent operator-attested receipt of an inbound transfer."""

    __tablename__ = "hub_receipt_sessions"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    inbound_transfer_id = Column(_UUID, nullable=False)
    cohort_id = Column(_UUID, nullable=False)
    order_id = Column(_UUID, nullable=False)
    vendor_id = Column(_UUID, nullable=False)
    hub_id = Column(_UUID, nullable=False)
    operator_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    idempotency_key = Column(String(200), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at, updated_at = _timestamps()

    __table_args__ = (
        ForeignKeyConstraint(
            ["inbound_transfer_id", "cohort_id", "order_id", "vendor_id", "hub_id"],
            [
                "inbound_transfers.id",
                "inbound_transfers.cohort_id",
                "inbound_transfers.order_id",
                "inbound_transfers.vendor_id",
                "inbound_transfers.target_hub_id",
            ],
            name="fk_hub_receipt_sessions_transfer_hub_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_hub_receipt_sessions_time_order",
        ),
        CheckConstraint(
            "version >= 1", name="ck_hub_receipt_sessions_version_positive"
        ),
        CheckConstraint(
            "idempotency_key = btrim(idempotency_key) AND length(idempotency_key) > 0",
            name="ck_hub_receipt_sessions_idempotency_canonical",
        ),
        UniqueConstraint(
            "hub_id", "idempotency_key", name="uq_hub_receipt_sessions_idempotency"
        ),
        UniqueConstraint(
            "id",
            "order_id",
            "vendor_id",
            "hub_id",
            name="uq_hub_receipt_sessions_evidence_identity",
        ),
        UniqueConstraint(
            "id",
            "inbound_transfer_id",
            "cohort_id",
            "order_id",
            "vendor_id",
            "hub_id",
            name="uq_hub_receipt_sessions_identity",
        ),
    )
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}


class HubReceiptItem(Base):
    """Quantity reconciliation for one allocated item in a receipt session."""

    __tablename__ = "hub_receipt_items"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    receipt_session_id = Column(_UUID, nullable=False)
    inbound_transfer_id = Column(_UUID, nullable=False)
    cohort_id = Column(_UUID, nullable=False)
    order_id = Column(_UUID, nullable=False)
    vendor_id = Column(_UUID, nullable=False)
    hub_id = Column(_UUID, nullable=False)
    order_item_id = Column(_UUID, nullable=False)
    expected_quantity = Column(Integer, nullable=False)
    received_quantity = Column(Integer, nullable=False)
    scan_identity = Column(String(200), nullable=False)
    created_at, updated_at = _timestamps()

    __table_args__ = (
        ForeignKeyConstraint(
            [
                "receipt_session_id",
                "inbound_transfer_id",
                "cohort_id",
                "order_id",
                "vendor_id",
                "hub_id",
            ],
            [
                "hub_receipt_sessions.id",
                "hub_receipt_sessions.inbound_transfer_id",
                "hub_receipt_sessions.cohort_id",
                "hub_receipt_sessions.order_id",
                "hub_receipt_sessions.vendor_id",
                "hub_receipt_sessions.hub_id",
            ],
            name="fk_hub_receipt_items_session_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "inbound_transfer_id",
                "order_item_id",
                "cohort_id",
                "order_id",
                "vendor_id",
            ],
            [
                "inbound_transfer_item_allocations.transfer_id",
                "inbound_transfer_item_allocations.order_item_id",
                "inbound_transfer_item_allocations.cohort_id",
                "inbound_transfer_item_allocations.order_id",
                "inbound_transfer_item_allocations.vendor_id",
            ],
            name="fk_hub_receipt_items_transfer_allocation",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "expected_quantity > 0", name="ck_hub_receipt_items_expected_positive"
        ),
        CheckConstraint(
            "received_quantity >= 0", name="ck_hub_receipt_items_received_nonnegative"
        ),
        CheckConstraint(
            "scan_identity = btrim(scan_identity) AND length(scan_identity) > 0",
            name="ck_hub_receipt_items_scan_canonical",
        ),
        UniqueConstraint(
            "receipt_session_id", "order_item_id", name="uq_hub_receipt_items_item"
        ),
        UniqueConstraint(
            "inbound_transfer_id", "scan_identity", name="uq_hub_receipt_items_scan"
        ),
        UniqueConstraint(
            "id",
            "receipt_session_id",
            "inbound_transfer_id",
            "cohort_id",
            "order_id",
            "vendor_id",
            "hub_id",
            "order_item_id",
            name="uq_hub_receipt_items_identity",
        ),
    )


class HubDiscrepancy(Base):
    """An auditable quantity discrepancy and its quarantine disposition."""

    __tablename__ = "hub_discrepancies"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    receipt_session_id = Column(_UUID, nullable=False)
    receipt_item_id = Column(_UUID, nullable=False)
    inbound_transfer_id = Column(_UUID, nullable=False)
    cohort_id = Column(_UUID, nullable=False)
    order_id = Column(_UUID, nullable=False)
    vendor_id = Column(_UUID, nullable=False)
    hub_id = Column(_UUID, nullable=False)
    order_item_id = Column(_UUID, nullable=False)
    type = Column(
        SQLEnum(
            DiscrepancyType, values_callable=_enum_values, name="hub_discrepancy_type"
        ),
        nullable=False,
    )
    quantity = Column(Integer, nullable=False)
    observed_item_identity = Column(String(200), nullable=True)
    reason_code = Column(String(100), nullable=True)
    private_notes = Column(Text, nullable=True)
    quarantine_disposition = Column(
        SQLEnum(
            QuarantineDisposition,
            values_callable=_enum_values,
            name="hub_quarantine_disposition",
        ),
        nullable=False,
        default=QuarantineDisposition.NOT_APPLICABLE,
        server_default=QuarantineDisposition.NOT_APPLICABLE.value,
    )
    recorded_by_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    recorded_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.statement_timestamp(),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            [
                "receipt_item_id",
                "receipt_session_id",
                "inbound_transfer_id",
                "cohort_id",
                "order_id",
                "vendor_id",
                "hub_id",
                "order_item_id",
            ],
            [
                "hub_receipt_items.id",
                "hub_receipt_items.receipt_session_id",
                "hub_receipt_items.inbound_transfer_id",
                "hub_receipt_items.cohort_id",
                "hub_receipt_items.order_id",
                "hub_receipt_items.vendor_id",
                "hub_receipt_items.hub_id",
                "hub_receipt_items.order_item_id",
            ],
            name="fk_hub_discrepancies_receipt_item_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint("quantity > 0", name="ck_hub_discrepancies_quantity_positive"),
        CheckConstraint(
            "(type = 'shortage' AND quarantine_disposition = 'not_applicable') OR "
            "(type <> 'shortage' AND quarantine_disposition <> 'not_applicable')",
            name="ck_hub_discrepancies_quarantine_semantics",
        ),
        CheckConstraint(
            "(type = 'wrong_item' AND observed_item_identity IS NOT NULL AND "
            "observed_item_identity = btrim(observed_item_identity) AND "
            "length(observed_item_identity) > 0) OR "
            "(type <> 'wrong_item' AND observed_item_identity IS NULL)",
            name="ck_hub_discrepancies_observed_identity_semantics",
        ),
        UniqueConstraint(
            "id",
            "receipt_session_id",
            "order_id",
            "vendor_id",
            "hub_id",
            name="uq_hub_discrepancies_identity",
        ),
    )


class HubQCSession(Base):
    """A versioned QC pass; reinspections link to the immutable prior pass."""

    __tablename__ = "hub_qc_sessions"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    receipt_session_id = Column(_UUID, nullable=False)
    inbound_transfer_id = Column(_UUID, nullable=False)
    cohort_id = Column(_UUID, nullable=False)
    order_id = Column(_UUID, nullable=False)
    vendor_id = Column(_UUID, nullable=False)
    hub_id = Column(_UUID, nullable=False)
    operator_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    sequence = Column(Integer, nullable=False)
    previous_session_id = Column(_UUID, nullable=True)
    remediation_id = Column(_UUID, nullable=True)
    state = Column(String(30), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at, updated_at = _timestamps()

    __table_args__ = (
        ForeignKeyConstraint(
            [
                "receipt_session_id",
                "inbound_transfer_id",
                "cohort_id",
                "order_id",
                "vendor_id",
                "hub_id",
            ],
            [
                "hub_receipt_sessions.id",
                "hub_receipt_sessions.inbound_transfer_id",
                "hub_receipt_sessions.cohort_id",
                "hub_receipt_sessions.order_id",
                "hub_receipt_sessions.vendor_id",
                "hub_receipt_sessions.hub_id",
            ],
            name="fk_hub_qc_sessions_receipt_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["previous_session_id", "receipt_session_id"],
            ["hub_qc_sessions.id", "hub_qc_sessions.receipt_session_id"],
            name="fk_hub_qc_sessions_previous_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["remediation_id", "receipt_session_id", "order_id", "vendor_id", "hub_id"],
            [
                "hub_remediations.id",
                "hub_remediations.receipt_session_id",
                "hub_remediations.order_id",
                "hub_remediations.vendor_id",
                "hub_remediations.hub_id",
            ],
            name="fk_hub_qc_sessions_remediation_identity",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint("sequence >= 1", name="ck_hub_qc_sessions_sequence_positive"),
        CheckConstraint(
            "source_command = btrim(source_command) AND length(source_command) > 0 AND "
            "idempotency_key = btrim(idempotency_key) AND length(idempotency_key) > 0",
            name="ck_hub_qc_sessions_command_identity_canonical",
        ),
        CheckConstraint(
            "state IN ('qc_pending', 'qc_in_progress', 'qc_passed', 'qc_failed')",
            name="ck_hub_qc_sessions_state",
        ),
        CheckConstraint(
            "(sequence = 1 AND previous_session_id IS NULL AND remediation_id IS NULL) OR "
            "(sequence > 1 AND previous_session_id IS NOT NULL AND remediation_id IS NOT NULL)",
            name="ck_hub_qc_sessions_reinspection_lineage",
        ),
        CheckConstraint(
            "completed_at IS NULL OR started_at IS NOT NULL",
            name="ck_hub_qc_sessions_completion_started",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_hub_qc_sessions_time_order",
        ),
        CheckConstraint("version >= 1", name="ck_hub_qc_sessions_version_positive"),
        UniqueConstraint(
            "hub_id", "idempotency_key", name="uq_hub_qc_sessions_idempotency"
        ),
        UniqueConstraint(
            "receipt_session_id", "sequence", name="uq_hub_qc_sessions_sequence"
        ),
        UniqueConstraint(
            "id", "receipt_session_id", name="uq_hub_qc_sessions_previous_identity"
        ),
        UniqueConstraint("previous_session_id", name="uq_hub_qc_sessions_previous"),
        UniqueConstraint("remediation_id", name="uq_hub_qc_sessions_remediation"),
        UniqueConstraint(
            "id",
            "receipt_session_id",
            "order_id",
            "vendor_id",
            "hub_id",
            name="uq_hub_qc_sessions_identity",
        ),
    )
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}


class HubQCInspection(Base):
    """Item-level decision within one QC session."""

    __tablename__ = "hub_qc_inspections"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    qc_session_id = Column(_UUID, nullable=False)
    receipt_session_id = Column(_UUID, nullable=False)
    inbound_transfer_id = Column(_UUID, nullable=False)
    cohort_id = Column(_UUID, nullable=False)
    order_id = Column(_UUID, nullable=False)
    vendor_id = Column(_UUID, nullable=False)
    hub_id = Column(_UUID, nullable=False)
    receipt_item_id = Column(_UUID, nullable=False)
    order_item_id = Column(_UUID, nullable=False)
    decision = Column(
        SQLEnum(QCDecision, values_callable=_enum_values, name="hub_qc_decision"),
        nullable=False,
    )
    inspected_quantity = Column(Integer, nullable=False)
    reason_code = Column(String(100), nullable=True)
    private_notes = Column(Text, nullable=True)
    quarantine_disposition = Column(
        SQLEnum(
            QuarantineDisposition,
            values_callable=_enum_values,
            name="hub_quarantine_disposition",
            create_type=False,
        ),
        nullable=False,
        default=QuarantineDisposition.NOT_APPLICABLE,
        server_default=QuarantineDisposition.NOT_APPLICABLE.value,
    )
    inspected_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.statement_timestamp(),
    )
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at, updated_at = _timestamps()

    __table_args__ = (
        ForeignKeyConstraint(
            ["qc_session_id", "receipt_session_id", "order_id", "vendor_id", "hub_id"],
            [
                "hub_qc_sessions.id",
                "hub_qc_sessions.receipt_session_id",
                "hub_qc_sessions.order_id",
                "hub_qc_sessions.vendor_id",
                "hub_qc_sessions.hub_id",
            ],
            name="fk_hub_qc_inspections_session_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "receipt_item_id",
                "receipt_session_id",
                "inbound_transfer_id",
                "cohort_id",
                "order_id",
                "vendor_id",
                "hub_id",
                "order_item_id",
            ],
            [
                "hub_receipt_items.id",
                "hub_receipt_items.receipt_session_id",
                "hub_receipt_items.inbound_transfer_id",
                "hub_receipt_items.cohort_id",
                "hub_receipt_items.order_id",
                "hub_receipt_items.vendor_id",
                "hub_receipt_items.hub_id",
                "hub_receipt_items.order_item_id",
            ],
            name="fk_hub_qc_inspections_receipt_item_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "inspected_quantity > 0", name="ck_hub_qc_inspections_quantity_positive"
        ),
        CheckConstraint(
            "(decision IN ('fail', 'rejected') AND reason_code IS NOT NULL AND "
            "length(btrim(reason_code)) > 0 AND quarantine_disposition <> 'not_applicable') OR "
            "(decision NOT IN ('fail', 'rejected') AND quarantine_disposition = 'not_applicable')",
            name="ck_hub_qc_inspections_decision_semantics",
        ),
        CheckConstraint("version >= 1", name="ck_hub_qc_inspections_version_positive"),
        UniqueConstraint(
            "qc_session_id", "receipt_item_id", name="uq_hub_qc_inspections_item"
        ),
        UniqueConstraint(
            "id",
            "receipt_session_id",
            "order_id",
            "vendor_id",
            "hub_id",
            name="uq_hub_qc_inspections_evidence_identity",
        ),
        UniqueConstraint(
            "id",
            "qc_session_id",
            "receipt_session_id",
            "order_id",
            "vendor_id",
            "hub_id",
            name="uq_hub_qc_inspections_identity",
        ),
    )
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}


class HubEvidence(Base):
    """Private object-store metadata; never a public, signed, or upload URL."""

    __tablename__ = "hub_evidence"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    receipt_session_id = Column(_UUID, nullable=False)
    inspection_id = Column(_UUID, nullable=True)
    discrepancy_id = Column(_UUID, nullable=True)
    remediation_id = Column(_UUID, nullable=True)
    order_id = Column(_UUID, nullable=False)
    vendor_id = Column(_UUID, nullable=False)
    hub_id = Column(_UUID, nullable=False)
    purpose = Column(
        SQLEnum(
            EvidencePurpose, values_callable=_enum_values, name="hub_evidence_purpose"
        ),
        nullable=False,
    )
    access_scope = Column(String(100), nullable=False)
    storage_reference = Column(String(500), nullable=False)
    integrity_hash = Column(String(64), nullable=False)
    content_type = Column(String(100), nullable=False)
    byte_size = Column(Integer, nullable=False)
    retention_until = Column(DateTime(timezone=True), nullable=False)
    legal_hold = Column(Boolean, nullable=False, default=False, server_default="false")
    retention_policy_updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.statement_timestamp(),
    )
    created_by_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.statement_timestamp(),
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["receipt_session_id", "order_id", "vendor_id", "hub_id"],
            [
                "hub_receipt_sessions.id",
                "hub_receipt_sessions.order_id",
                "hub_receipt_sessions.vendor_id",
                "hub_receipt_sessions.hub_id",
            ],
            name="fk_hub_evidence_receipt_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["inspection_id", "receipt_session_id", "order_id", "vendor_id", "hub_id"],
            [
                "hub_qc_inspections.id",
                "hub_qc_inspections.receipt_session_id",
                "hub_qc_inspections.order_id",
                "hub_qc_inspections.vendor_id",
                "hub_qc_inspections.hub_id",
            ],
            name="fk_hub_evidence_inspection_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["discrepancy_id", "receipt_session_id", "order_id", "vendor_id", "hub_id"],
            [
                "hub_discrepancies.id",
                "hub_discrepancies.receipt_session_id",
                "hub_discrepancies.order_id",
                "hub_discrepancies.vendor_id",
                "hub_discrepancies.hub_id",
            ],
            name="fk_hub_evidence_discrepancy_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["remediation_id", "receipt_session_id", "order_id", "vendor_id", "hub_id"],
            [
                "hub_remediations.id",
                "hub_remediations.receipt_session_id",
                "hub_remediations.order_id",
                "hub_remediations.vendor_id",
                "hub_remediations.hub_id",
            ],
            name="fk_hub_evidence_remediation_identity",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        CheckConstraint(
            "(purpose = 'hub_receipt' AND inspection_id IS NULL AND discrepancy_id IS NULL "
            "AND remediation_id IS NULL) OR "
            "(purpose = 'discrepancy' AND discrepancy_id IS NOT NULL AND inspection_id IS NULL "
            "AND remediation_id IS NULL) OR "
            "(purpose = 'qc_inspection' AND inspection_id IS NOT NULL AND discrepancy_id IS NULL "
            "AND remediation_id IS NULL) OR "
            "(purpose = 'remediation' AND remediation_id IS NOT NULL AND inspection_id IS NULL "
            "AND discrepancy_id IS NULL)",
            name="ck_hub_evidence_purpose_subject",
        ),
        CheckConstraint(
            "integrity_hash ~ '^[0-9a-f]{64}$'", name="ck_hub_evidence_integrity_hash"
        ),
        CheckConstraint(
            "storage_reference = btrim(storage_reference) "
            "AND storage_reference ~ '^private/[^/?#]+(/[^/?#]+)*$' "
            "AND strpos(storage_reference, chr(92)) = 0 "
            "AND storage_reference !~ '(^|/)[.]{1,2}(/|$)'",
            name="ck_hub_evidence_private_reference",
        ),
        CheckConstraint("byte_size > 0", name="ck_hub_evidence_byte_size_positive"),
        CheckConstraint(
            "retention_until > created_at", name="ck_hub_evidence_retention_future"
        ),
        CheckConstraint(
            "retention_policy_updated_at >= created_at",
            name="ck_hub_evidence_policy_timestamp_order",
        ),
        CheckConstraint(
            "access_scope = 'hub_quality_private'",
            name="ck_hub_evidence_access_scope",
        ),
        UniqueConstraint("storage_reference", name="uq_hub_evidence_storage_reference"),
    )


class HubEvidenceRetentionEvent(Base):
    """Append-only audit event that changes an evidence retention snapshot."""

    __tablename__ = "hub_evidence_retention_events"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    evidence_id = Column(
        _UUID, ForeignKey("hub_evidence.id", ondelete="RESTRICT"), nullable=False
    )
    actor_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    reason = Column(String(500), nullable=False)
    previous_legal_hold = Column(Boolean, nullable=False)
    resulting_legal_hold = Column(Boolean, nullable=False)
    previous_retention_until = Column(DateTime(timezone=True), nullable=False)
    resulting_retention_until = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "reason = btrim(reason) AND length(reason) > 0",
            name="ck_hub_evidence_retention_events_reason_canonical",
        ),
        CheckConstraint(
            "previous_legal_hold IS DISTINCT FROM resulting_legal_hold OR "
            "previous_retention_until IS DISTINCT FROM resulting_retention_until",
            name="ck_hub_evidence_retention_events_changes_policy",
        ),
    )


class HubRemediation(Base):
    """Authorized disposition and remediation for one failed inspection."""

    __tablename__ = "hub_remediations"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    failed_inspection_id = Column(_UUID, nullable=False)
    qc_session_id = Column(_UUID, nullable=False)
    receipt_session_id = Column(_UUID, nullable=False)
    order_id = Column(_UUID, nullable=False)
    vendor_id = Column(_UUID, nullable=False)
    hub_id = Column(_UUID, nullable=False)
    owner_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    action = Column(
        SQLEnum(
            RemediationAction,
            values_callable=_enum_values,
            name="hub_remediation_action",
        ),
        nullable=False,
    )
    state = Column(
        SQLEnum(
            RemediationState, values_callable=_enum_values, name="hub_remediation_state"
        ),
        nullable=False,
    )
    disposition = Column(
        SQLEnum(
            QuarantineDisposition,
            values_callable=_enum_values,
            name="hub_quarantine_disposition",
            create_type=False,
        ),
        nullable=False,
    )
    private_notes = Column(Text, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, nullable=False, default=1, server_default="1")
    created_at, updated_at = _timestamps()

    __table_args__ = (
        ForeignKeyConstraint(
            [
                "failed_inspection_id",
                "qc_session_id",
                "receipt_session_id",
                "order_id",
                "vendor_id",
                "hub_id",
            ],
            [
                "hub_qc_inspections.id",
                "hub_qc_inspections.qc_session_id",
                "hub_qc_inspections.receipt_session_id",
                "hub_qc_inspections.order_id",
                "hub_qc_inspections.vendor_id",
                "hub_qc_inspections.hub_id",
            ],
            name="fk_hub_remediations_failed_inspection_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "disposition <> 'not_applicable'",
            name="ck_hub_remediations_disposition_required",
        ),
        CheckConstraint(
            "(state = 'pending_approval' AND approved_at IS NULL AND approved_by_id IS NULL) OR "
            "(state <> 'pending_approval' AND approved_at IS NOT NULL AND approved_by_id IS NOT NULL)",
            name="ck_hub_remediations_approval_audit",
        ),
        CheckConstraint(
            "completed_at IS NULL OR approved_at IS NOT NULL",
            name="ck_hub_remediations_completion_approved",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= approved_at",
            name="ck_hub_remediations_time_order",
        ),
        CheckConstraint(
            "(state = 'completed' AND completed_at IS NOT NULL) OR "
            "(state <> 'completed' AND completed_at IS NULL)",
            name="ck_hub_remediations_completed_timestamp",
        ),
        CheckConstraint("version >= 1", name="ck_hub_remediations_version_positive"),
        UniqueConstraint(
            "failed_inspection_id", name="uq_hub_remediations_failed_inspection"
        ),
        UniqueConstraint(
            "id",
            "receipt_session_id",
            "order_id",
            "vendor_id",
            "hub_id",
            name="uq_hub_remediations_identity",
        ),
    )
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}


for _model in (HubReceiptSession, HubQCSession, HubQCInspection, HubRemediation):
    event.listen(
        _model,
        "before_update",
        lambda _mapper, _connection, target: setattr(
            target, "version", target.version + 1
        ),
    )

_RECEIPT_IMMUTABILITY_FUNCTION = DDL(
    """
CREATE FUNCTION reject_completed_hub_receipt_update() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.started_at > clock_timestamp() THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'receipt start timestamp cannot be future-dated';
        END IF;
        IF NEW.completed_at IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'receipt sessions must start incomplete';
        END IF;
        RETURN NEW;
    END IF;
    IF NEW.completed_at IS NOT NULL AND NEW.completed_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'receipt completion timestamp cannot be future-dated';
    END IF;
    IF OLD.completed_at IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'completed receipt sessions are immutable';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.inbound_transfer_id IS DISTINCT FROM OLD.inbound_transfer_id
       OR NEW.cohort_id IS DISTINCT FROM OLD.cohort_id
       OR NEW.order_id IS DISTINCT FROM OLD.order_id
       OR NEW.vendor_id IS DISTINCT FROM OLD.vendor_id
       OR NEW.hub_id IS DISTINCT FROM OLD.hub_id
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.operator_id IS DISTINCT FROM OLD.operator_id
       OR NEW.started_at IS DISTINCT FROM OLD.started_at
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'receipt session identity is immutable';
    END IF;
    IF OLD.completed_at IS NULL AND NEW.completed_at IS NOT NULL THEN
        PERFORM 1 FROM inbound_transfers
        WHERE id = NEW.inbound_transfer_id FOR UPDATE;
        IF NOT EXISTS (
            SELECT 1 FROM hub_receipt_items WHERE receipt_session_id = NEW.id
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'receipt completion requires receipt items';
        END IF;
        IF EXISTS (
            SELECT 1 FROM inbound_transfer_item_allocations allocation
            WHERE allocation.transfer_id = NEW.inbound_transfer_id
              AND NOT EXISTS (
                  SELECT 1 FROM hub_receipt_items item
                  WHERE item.receipt_session_id = NEW.id
                    AND item.order_item_id = allocation.order_item_id
              )
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'receipt completion requires every transfer allocation to be reconciled';
        END IF;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_RECEIPT_IMMUTABILITY_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_receipt_sessions_completed_immutable BEFORE INSERT OR UPDATE ON hub_receipt_sessions
FOR EACH ROW EXECUTE FUNCTION reject_completed_hub_receipt_update()
"""
)
_RECEIPT_QUANTITY_FUNCTION = DDL(
    """
CREATE FUNCTION validate_hub_receipt_item_quantity() RETURNS trigger AS $$
DECLARE allocated integer; already_received integer; receipt_completed timestamptz;
        max_inspected integer;
BEGIN
    IF TG_OP = 'UPDATE' AND (
        NEW.id IS DISTINCT FROM OLD.id
        OR NEW.receipt_session_id IS DISTINCT FROM OLD.receipt_session_id
        OR NEW.inbound_transfer_id IS DISTINCT FROM OLD.inbound_transfer_id
        OR NEW.cohort_id IS DISTINCT FROM OLD.cohort_id
        OR NEW.order_id IS DISTINCT FROM OLD.order_id
        OR NEW.vendor_id IS DISTINCT FROM OLD.vendor_id
        OR NEW.hub_id IS DISTINCT FROM OLD.hub_id
        OR NEW.order_item_id IS DISTINCT FROM OLD.order_item_id
        OR NEW.scan_identity IS DISTINCT FROM OLD.scan_identity
        OR NEW.created_at IS DISTINCT FROM OLD.created_at
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'receipt item aggregate identity is immutable';
    END IF;
    SELECT completed_at INTO receipt_completed FROM hub_receipt_sessions
    WHERE id = NEW.receipt_session_id FOR UPDATE;
    IF receipt_completed IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'completed receipt sessions are immutable';
    END IF;
    SELECT allocated_quantity INTO allocated FROM inbound_transfer_item_allocations
    WHERE transfer_id = NEW.inbound_transfer_id AND order_item_id = NEW.order_item_id FOR UPDATE;
    IF allocated IS NULL OR NEW.expected_quantity <> allocated THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'receipt expected quantity must equal transfer allocation';
    END IF;
    SELECT COALESCE(SUM(received_quantity), 0) INTO already_received
    FROM hub_receipt_items
    WHERE inbound_transfer_id = NEW.inbound_transfer_id
      AND order_item_id = NEW.order_item_id
      AND id <> NEW.id;
    IF already_received + NEW.received_quantity > allocated THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'cumulative received quantity exceeds transfer allocation';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF (NEW.expected_quantity IS DISTINCT FROM OLD.expected_quantity
            OR NEW.received_quantity IS DISTINCT FROM OLD.received_quantity)
           AND EXISTS (
               SELECT 1 FROM hub_discrepancies WHERE receipt_item_id = OLD.id
           ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'receipt quantity is frozen after discrepancy';
        END IF;
        SELECT COALESCE(MAX(inspected_quantity), 0) INTO max_inspected
        FROM hub_qc_inspections WHERE receipt_item_id = NEW.id;
        IF NEW.received_quantity < max_inspected THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'received quantity cannot drop below inspected quantity';
        END IF;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_RECEIPT_QUANTITY_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_receipt_items_quantity_safe BEFORE INSERT OR UPDATE ON hub_receipt_items
FOR EACH ROW EXECUTE FUNCTION validate_hub_receipt_item_quantity()
"""
)
_INSPECTION_QUANTITY_FUNCTION = DDL(
    """
CREATE FUNCTION validate_hub_qc_inspection_quantity() RETURNS trigger AS $$
DECLARE received integer;
BEGIN
    SELECT received_quantity INTO received FROM hub_receipt_items WHERE id = NEW.receipt_item_id FOR UPDATE;
    IF received IS NULL OR NEW.inspected_quantity > received THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'inspection quantity exceeds received quantity';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_INSPECTION_QUANTITY_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_qc_inspections_quantity_safe BEFORE INSERT OR UPDATE ON hub_qc_inspections
FOR EACH ROW EXECUTE FUNCTION validate_hub_qc_inspection_quantity()
"""
)
_QC_LINEAGE_FUNCTION = DDL(
    """
CREATE FUNCTION validate_hub_qc_reinspection_lineage() RETURNS trigger AS $$
DECLARE previous_sequence integer; previous_state varchar; previous_completed timestamptz;
        remediation_session uuid; remediation_receipt uuid; remediation_state hub_remediation_state;
        remediation_completed timestamptz;
BEGIN
    IF NEW.sequence > 1 THEN
        PERFORM 1 FROM hub_remediations
         WHERE qc_session_id = NEW.previous_session_id
         ORDER BY id
         FOR UPDATE;
        SELECT qc_session_id, receipt_session_id, state, completed_at
          INTO remediation_session, remediation_receipt, remediation_state, remediation_completed
          FROM hub_remediations WHERE id = NEW.remediation_id;
        IF remediation_session IS DISTINCT FROM NEW.previous_session_id
           OR remediation_receipt IS DISTINCT FROM NEW.receipt_session_id
           OR remediation_state IS DISTINCT FROM 'completed' THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'reinspection requires completed remediation for the previous QC session';
        END IF;
        IF remediation_completed IS NULL OR NEW.started_at < remediation_completed THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'reinspection must start after remediation completion';
        END IF;
        SELECT sequence, state, completed_at
          INTO previous_sequence, previous_state, previous_completed
          FROM hub_qc_sessions
         WHERE id = NEW.previous_session_id AND receipt_session_id = NEW.receipt_session_id
         FOR UPDATE;
        IF previous_sequence IS NULL OR previous_sequence <> NEW.sequence - 1 THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'reinspection must follow the immediately previous QC sequence';
        END IF;
        IF previous_state <> 'qc_failed' OR previous_completed IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'reinspection requires a completed failed previous QC session';
        END IF;
        IF EXISTS (
            SELECT 1
              FROM hub_qc_inspections AS inspection
              LEFT JOIN hub_remediations AS remediation
                ON remediation.failed_inspection_id = inspection.id
               AND remediation.qc_session_id = inspection.qc_session_id
             WHERE inspection.qc_session_id = NEW.previous_session_id
               AND inspection.decision IN ('fail', 'rejected')
               AND (
                   remediation.id IS NULL
                   OR remediation.state <> 'completed'
                   OR remediation.completed_at IS NULL
                   OR remediation.completed_at > NEW.started_at
               )
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'every failed inspection requires completed remediation before reinspection';
        END IF;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_QC_LINEAGE_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_qc_sessions_reinspection_lineage
BEFORE INSERT ON hub_qc_sessions
FOR EACH ROW EXECUTE FUNCTION validate_hub_qc_reinspection_lineage()
"""
)
_QC_IMMUTABILITY_FUNCTION = DDL(
    """
CREATE FUNCTION reject_completed_hub_qc_update() RETURNS trigger AS $$
DECLARE qc_completed timestamptz; qc_started timestamptz; qc_state varchar;
        receipt_completed timestamptz;
BEGIN
    IF TG_TABLE_NAME = 'hub_qc_sessions' THEN
        IF TG_OP = 'INSERT' THEN
            IF NEW.started_at > clock_timestamp() THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC start timestamp cannot be future-dated';
            END IF;
            IF NEW.completed_at IS NOT NULL THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC sessions must start incomplete';
            END IF;
            IF NEW.state IN ('qc_passed', 'qc_failed') THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'terminal QC state requires completion';
            END IF;
            IF NEW.state NOT IN ('qc_pending', 'qc_in_progress') THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC sessions must start pending or in progress';
            END IF;
            SELECT completed_at INTO receipt_completed FROM hub_receipt_sessions
            WHERE id = NEW.receipt_session_id FOR UPDATE;
            IF receipt_completed IS NULL THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC sessions require a completed receipt session';
            END IF;
            IF NEW.started_at < receipt_completed THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC start must follow receipt completion';
            END IF;
            RETURN NEW;
        END IF;
        IF OLD.completed_at IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'completed QC sessions are immutable';
        END IF;
        IF NEW.completed_at IS NOT NULL AND NEW.completed_at > clock_timestamp() THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC completion timestamp cannot be future-dated';
        END IF;
        IF NEW.id IS DISTINCT FROM OLD.id
           OR NEW.receipt_session_id IS DISTINCT FROM OLD.receipt_session_id
           OR NEW.inbound_transfer_id IS DISTINCT FROM OLD.inbound_transfer_id
           OR NEW.cohort_id IS DISTINCT FROM OLD.cohort_id
           OR NEW.order_id IS DISTINCT FROM OLD.order_id
           OR NEW.vendor_id IS DISTINCT FROM OLD.vendor_id
           OR NEW.hub_id IS DISTINCT FROM OLD.hub_id
           OR NEW.operator_id IS DISTINCT FROM OLD.operator_id
           OR NEW.source_command IS DISTINCT FROM OLD.source_command
           OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
           OR NEW.sequence IS DISTINCT FROM OLD.sequence
           OR NEW.previous_session_id IS DISTINCT FROM OLD.previous_session_id
           OR NEW.remediation_id IS DISTINCT FROM OLD.remediation_id
           OR NEW.started_at IS DISTINCT FROM OLD.started_at
           OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC session aggregate lineage is immutable';
        END IF;
        IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
            (OLD.state = 'qc_pending' AND NEW.state = 'qc_in_progress') OR
            (OLD.state = 'qc_in_progress' AND NEW.state IN ('qc_passed', 'qc_failed'))
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'illegal QC state transition';
        END IF;
        IF NEW.state IN ('qc_passed', 'qc_failed') AND NEW.completed_at IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'terminal QC state requires completion';
        END IF;
        IF NEW.state NOT IN ('qc_passed', 'qc_failed') AND NEW.completed_at IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC completion requires a terminal state';
        END IF;
        IF OLD.completed_at IS NULL AND NEW.completed_at IS NOT NULL THEN
            IF NEW.state NOT IN ('qc_passed', 'qc_failed') THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC completion requires a terminal state';
            END IF;
            SELECT completed_at INTO receipt_completed FROM hub_receipt_sessions
            WHERE id = NEW.receipt_session_id FOR UPDATE;
            IF receipt_completed IS NULL THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC completion requires a completed receipt session';
            END IF;
            IF NEW.completed_at < receipt_completed THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC completion must follow receipt completion';
            END IF;
            IF EXISTS (
                SELECT 1 FROM hub_qc_inspections
                WHERE qc_session_id = NEW.id
                  AND (inspected_at < NEW.started_at OR inspected_at > NEW.completed_at)
            ) THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC completion requires inspection timestamps within the session';
            END IF;
            IF EXISTS (
                SELECT 1 FROM hub_qc_inspections inspection
                WHERE inspection.qc_session_id = NEW.id
                  AND NOT EXISTS (
                      SELECT 1 FROM hub_evidence evidence
                      WHERE evidence.purpose = 'qc_inspection'
                        AND evidence.inspection_id = inspection.id
                        AND evidence.created_at >= inspection.inspected_at
                        AND evidence.created_at <= NEW.completed_at
                  )
            ) THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC completion requires evidence for every inspection';
            END IF;
            IF NEW.state = 'qc_passed' AND (
                NOT EXISTS (
                    SELECT 1 FROM hub_receipt_items
                    WHERE receipt_session_id = NEW.receipt_session_id
                ) OR EXISTS (
                    SELECT 1 FROM hub_receipt_items item
                    WHERE item.receipt_session_id = NEW.receipt_session_id
                      AND item.received_quantity > 0
                      AND NOT EXISTS (
                          SELECT 1 FROM hub_qc_inspections inspection
                          WHERE inspection.qc_session_id = NEW.id
                            AND inspection.receipt_item_id = item.id
                            AND inspection.decision = 'pass'
                      )
                )
            ) THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'passed QC completion requires all receipt items to pass';
            END IF;
            IF NEW.state = 'qc_failed' AND NOT EXISTS (
                SELECT 1 FROM hub_qc_inspections
                WHERE qc_session_id = NEW.id AND decision IN ('fail', 'rejected')
            ) THEN
                RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'failed QC completion requires a failed or rejected inspection';
            END IF;
        END IF;
    ELSE
        IF TG_OP = 'UPDATE' AND (
            NEW.id IS DISTINCT FROM OLD.id
            OR NEW.qc_session_id IS DISTINCT FROM OLD.qc_session_id
            OR NEW.receipt_session_id IS DISTINCT FROM OLD.receipt_session_id
            OR NEW.inbound_transfer_id IS DISTINCT FROM OLD.inbound_transfer_id
            OR NEW.cohort_id IS DISTINCT FROM OLD.cohort_id
            OR NEW.order_id IS DISTINCT FROM OLD.order_id
            OR NEW.vendor_id IS DISTINCT FROM OLD.vendor_id
            OR NEW.hub_id IS DISTINCT FROM OLD.hub_id
            OR NEW.receipt_item_id IS DISTINCT FROM OLD.receipt_item_id
            OR NEW.order_item_id IS DISTINCT FROM OLD.order_item_id
            OR NEW.created_at IS DISTINCT FROM OLD.created_at
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC inspection aggregate identity is immutable';
        END IF;
        SELECT state, started_at, completed_at INTO qc_state, qc_started, qc_completed FROM hub_qc_sessions
        WHERE id = NEW.qc_session_id FOR UPDATE;
        IF qc_completed IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'inspections in completed QC sessions are immutable';
        END IF;
        IF qc_state IS DISTINCT FROM 'qc_in_progress' THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'inspections require QC in progress';
        END IF;
        IF NEW.inspected_at < qc_started OR NEW.inspected_at > clock_timestamp() THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'inspection timestamp must fall within the active QC session';
        END IF;
        IF TG_OP = 'UPDATE' AND EXISTS (
            SELECT 1 FROM hub_remediations WHERE failed_inspection_id = OLD.id
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'remediated inspections are immutable';
        END IF;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_QC_SESSION_IMMUTABILITY_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_qc_sessions_completed_immutable BEFORE INSERT OR UPDATE ON hub_qc_sessions
FOR EACH ROW EXECUTE FUNCTION reject_completed_hub_qc_update()
"""
)
_QC_INSPECTION_IMMUTABILITY_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_qc_inspections_completed_immutable BEFORE INSERT OR UPDATE ON hub_qc_inspections
FOR EACH ROW EXECUTE FUNCTION reject_completed_hub_qc_update()
"""
)
_REMEDIATION_INVARIANT_FUNCTION = DDL(
    """
CREATE FUNCTION validate_hub_remediation_invariants() RETURNS trigger AS $$
DECLARE inspection_decision hub_qc_decision; inspection_time timestamptz;
        parent_qc_state varchar;
        parent_qc_completed timestamptz;
BEGIN
    IF TG_OP = 'INSERT' AND NEW.state IS DISTINCT FROM 'pending_approval' THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'remediations must start pending';
    END IF;
    IF NEW.approved_at IS NOT NULL AND (
        NEW.approved_at < NEW.created_at OR NEW.approved_at > clock_timestamp()
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'approval timestamp must follow creation and not be future-dated';
    END IF;
    IF NEW.completed_at IS NOT NULL AND (
        NEW.approved_at IS NULL OR NEW.completed_at < NEW.approved_at
        OR NEW.completed_at > clock_timestamp()
    ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'completion timestamp must follow approval and not be future-dated';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF OLD.state = 'completed' OR EXISTS (
            SELECT 1 FROM hub_qc_sessions WHERE remediation_id = OLD.id
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'terminal or consumed remediation is immutable';
        END IF;
        IF NEW.id IS DISTINCT FROM OLD.id
           OR NEW.failed_inspection_id IS DISTINCT FROM OLD.failed_inspection_id
           OR NEW.qc_session_id IS DISTINCT FROM OLD.qc_session_id
           OR NEW.receipt_session_id IS DISTINCT FROM OLD.receipt_session_id
           OR NEW.order_id IS DISTINCT FROM OLD.order_id
           OR NEW.vendor_id IS DISTINCT FROM OLD.vendor_id
           OR NEW.hub_id IS DISTINCT FROM OLD.hub_id
           OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'remediation identity is immutable';
        END IF;
        IF NEW.state IS DISTINCT FROM OLD.state AND NOT (
            (OLD.state = 'pending_approval' AND NEW.state = 'approved'
             AND NEW.approved_by_id IS NOT NULL AND NEW.approved_at IS NOT NULL)
            OR (OLD.state = 'approved' AND NEW.state = 'in_progress')
            OR (OLD.state = 'in_progress' AND NEW.state = 'completed'
                AND NEW.completed_at IS NOT NULL)
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'illegal remediation state transition';
        END IF;
        IF OLD.state IN ('approved', 'in_progress') AND (
            NEW.owner_id IS DISTINCT FROM OLD.owner_id
            OR NEW.action IS DISTINCT FROM OLD.action
            OR NEW.disposition IS DISTINCT FROM OLD.disposition
            OR NEW.approved_by_id IS DISTINCT FROM OLD.approved_by_id
            OR NEW.approved_at IS DISTINCT FROM OLD.approved_at
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'approved remediation terms and audit are immutable';
        END IF;
        IF NEW.completed_at IS DISTINCT FROM OLD.completed_at
           AND NOT (OLD.state = 'in_progress' AND NEW.state = 'completed'
                    AND NEW.completed_at IS NOT NULL) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'completion timestamp requires completion transition';
        END IF;
    END IF;
    SELECT state, completed_at INTO parent_qc_state, parent_qc_completed
    FROM hub_qc_sessions WHERE id = NEW.qc_session_id FOR UPDATE;
    IF TG_OP = 'UPDATE'
       AND OLD.state = 'in_progress' AND NEW.state = 'completed'
       AND NOT EXISTS (
           SELECT 1 FROM hub_evidence
           WHERE purpose = 'remediation' AND remediation_id = NEW.id
             AND created_at >= NEW.created_at AND created_at <= NEW.completed_at
       ) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'remediation completion requires evidence';
    END IF;
    IF NEW.state IN ('approved', 'in_progress', 'completed') THEN
        IF parent_qc_state IS DISTINCT FROM 'qc_failed' OR parent_qc_completed IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'remediation approval requires a completed failed QC session';
        END IF;
        IF NEW.approved_at < parent_qc_completed THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'remediation approval must follow QC completion';
        END IF;
    END IF;
    SELECT decision, inspected_at INTO inspection_decision, inspection_time
    FROM hub_qc_inspections
    WHERE id = NEW.failed_inspection_id AND qc_session_id = NEW.qc_session_id;
    IF inspection_decision IS NULL OR inspection_decision NOT IN ('fail', 'rejected') THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'remediation requires a failed or rejected inspection';
    END IF;
    IF NEW.created_at < inspection_time OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'remediation creation must follow inspection and not be future-dated';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_REMEDIATION_INVARIANT_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_remediations_invariants BEFORE INSERT OR UPDATE ON hub_remediations
FOR EACH ROW EXECUTE FUNCTION validate_hub_remediation_invariants()
"""
)
_EVIDENCE_INSERT_FUNCTION = DDL(
    """
CREATE OR REPLACE FUNCTION validate_hub_evidence_insert() RETURNS trigger AS $$
DECLARE subject_at timestamptz;
BEGIN
    IF NEW.created_at > clock_timestamp()
       OR NEW.retention_policy_updated_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'evidence timestamps cannot be future-dated';
    END IF;
    IF NEW.purpose = 'hub_receipt' THEN
        SELECT started_at INTO subject_at FROM hub_receipt_sessions
        WHERE id = NEW.receipt_session_id FOR KEY SHARE;
    ELSIF NEW.purpose = 'discrepancy' THEN
        SELECT recorded_at INTO subject_at FROM hub_discrepancies
        WHERE id = NEW.discrepancy_id FOR KEY SHARE;
    ELSIF NEW.purpose = 'qc_inspection' THEN
        SELECT inspected_at INTO subject_at FROM hub_qc_inspections
        WHERE id = NEW.inspection_id FOR KEY SHARE;
    ELSIF NEW.purpose = 'remediation' THEN
        SELECT created_at INTO subject_at FROM hub_remediations
        WHERE id = NEW.remediation_id FOR KEY SHARE;
    END IF;
    IF subject_at IS NOT NULL AND NEW.created_at < subject_at THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'evidence cannot predate its subject';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_EVIDENCE_INSERT_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_evidence_insert_valid BEFORE INSERT ON hub_evidence
FOR EACH ROW EXECUTE FUNCTION validate_hub_evidence_insert()
"""
)
_EVIDENCE_UPDATE_FUNCTION = DDL(
    """
CREATE OR REPLACE FUNCTION validate_hub_evidence_update() RETURNS trigger AS $$
BEGIN
    IF NEW.id IS DISTINCT FROM OLD.id
       OR NEW.receipt_session_id IS DISTINCT FROM OLD.receipt_session_id
       OR NEW.inspection_id IS DISTINCT FROM OLD.inspection_id
       OR NEW.discrepancy_id IS DISTINCT FROM OLD.discrepancy_id
       OR NEW.remediation_id IS DISTINCT FROM OLD.remediation_id
       OR NEW.order_id IS DISTINCT FROM OLD.order_id
       OR NEW.vendor_id IS DISTINCT FROM OLD.vendor_id
       OR NEW.hub_id IS DISTINCT FROM OLD.hub_id
       OR NEW.purpose IS DISTINCT FROM OLD.purpose
       OR NEW.access_scope IS DISTINCT FROM OLD.access_scope
       OR NEW.storage_reference IS DISTINCT FROM OLD.storage_reference
       OR NEW.integrity_hash IS DISTINCT FROM OLD.integrity_hash
       OR NEW.content_type IS DISTINCT FROM OLD.content_type
       OR NEW.byte_size IS DISTINCT FROM OLD.byte_size
       OR NEW.created_by_id IS DISTINCT FROM OLD.created_by_id
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR (NEW.legal_hold IS NOT DISTINCT FROM OLD.legal_hold
           AND NEW.retention_until IS NOT DISTINCT FROM OLD.retention_until
           AND NEW.retention_policy_updated_at IS NOT DISTINCT FROM OLD.retention_policy_updated_at) THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'hub quality audit records are immutable';
    END IF;
    IF pg_trigger_depth() <> 2 THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'evidence policy changes require a retention event';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_EVIDENCE_UPDATE_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_evidence_update_restricted BEFORE UPDATE ON hub_evidence
FOR EACH ROW EXECUTE FUNCTION validate_hub_evidence_update()
"""
)
_EVIDENCE_RETENTION_FUNCTION = DDL(
    """
CREATE OR REPLACE FUNCTION validate_hub_evidence_retention_event() RETURNS trigger AS $$
DECLARE current_hold boolean; current_retention timestamptz; evidence_created timestamptz;
        current_policy_updated_at timestamptz;
BEGIN
    SELECT legal_hold, retention_until, created_at, retention_policy_updated_at
      INTO current_hold, current_retention, evidence_created, current_policy_updated_at
      FROM hub_evidence WHERE id = NEW.evidence_id FOR UPDATE;
    IF evidence_created IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = '23503', MESSAGE = 'retention event evidence does not exist';
    END IF;
    IF NEW.occurred_at < evidence_created OR NEW.occurred_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'event timestamp must follow evidence creation and not be future-dated';
    END IF;
    IF NEW.occurred_at <= current_policy_updated_at THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'retention event timestamps must strictly increase';
    END IF;
    IF NEW.previous_legal_hold IS DISTINCT FROM current_hold
       OR NEW.previous_retention_until IS DISTINCT FROM current_retention THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'retention event previous state is stale';
    END IF;
    IF NEW.resulting_legal_hold IS NOT DISTINCT FROM current_hold
       AND NEW.resulting_retention_until IS NOT DISTINCT FROM current_retention THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'retention event must change policy';
    END IF;
    IF NEW.resulting_retention_until <= evidence_created THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'resulting retention must be after evidence creation';
    END IF;
    UPDATE hub_evidence
       SET legal_hold = NEW.resulting_legal_hold,
           retention_until = NEW.resulting_retention_until,
           retention_policy_updated_at = NEW.occurred_at
     WHERE id = NEW.evidence_id;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_EVIDENCE_RETENTION_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_evidence_retention_events_apply
BEFORE INSERT ON hub_evidence_retention_events
FOR EACH ROW EXECUTE FUNCTION validate_hub_evidence_retention_event()
"""
)
_AUDIT_FUNCTION = DDL(
    """
CREATE FUNCTION reject_hub_quality_audit_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '23503', MESSAGE = 'hub quality audit records cannot be deleted';
END; $$ LANGUAGE plpgsql
"""
)
_DISCREPANCY_INSERT_FUNCTION = DDL(
    """
CREATE FUNCTION validate_hub_discrepancy_insert() RETURNS trigger AS $$
DECLARE receipt_completed timestamptz; receipt_started timestamptz;
BEGIN
    PERFORM 1 FROM hub_receipt_items
    WHERE id = NEW.receipt_item_id AND receipt_session_id = NEW.receipt_session_id
    FOR UPDATE;
    SELECT started_at, completed_at INTO receipt_started, receipt_completed FROM hub_receipt_sessions
    WHERE id = NEW.receipt_session_id FOR UPDATE;
    IF receipt_completed IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'completed receipt sessions are immutable';
    END IF;
    IF NEW.recorded_at < receipt_started OR NEW.recorded_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'discrepancy timestamp must fall within the open receipt session';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_DISCREPANCY_INSERT_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_discrepancies_receipt_open BEFORE INSERT ON hub_discrepancies
FOR EACH ROW EXECUTE FUNCTION validate_hub_discrepancy_insert()
"""
)
_AUDIT_UPDATE_FUNCTION = DDL(
    """
CREATE FUNCTION reject_hub_quality_audit_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'hub quality audit records are immutable';
END; $$ LANGUAGE plpgsql
"""
)


event.listen(
    HubReceiptSession.__table__, "after_create", _RECEIPT_IMMUTABILITY_FUNCTION
)
event.listen(HubReceiptSession.__table__, "after_create", _RECEIPT_IMMUTABILITY_TRIGGER)
event.listen(HubReceiptItem.__table__, "after_create", _RECEIPT_QUANTITY_FUNCTION)
event.listen(HubReceiptItem.__table__, "after_create", _RECEIPT_QUANTITY_TRIGGER)
event.listen(HubQCInspection.__table__, "after_create", _INSPECTION_QUANTITY_FUNCTION)
event.listen(HubQCInspection.__table__, "after_create", _INSPECTION_QUANTITY_TRIGGER)
event.listen(HubQCSession.__table__, "after_create", _QC_IMMUTABILITY_FUNCTION)
event.listen(HubQCSession.__table__, "after_create", _QC_SESSION_IMMUTABILITY_TRIGGER)
event.listen(
    HubQCInspection.__table__, "after_create", _QC_INSPECTION_IMMUTABILITY_TRIGGER
)
event.listen(HubRemediation.__table__, "after_create", _REMEDIATION_INVARIANT_FUNCTION)
event.listen(HubRemediation.__table__, "after_create", _REMEDIATION_INVARIANT_TRIGGER)
event.listen(HubRemediation.__table__, "after_create", _QC_LINEAGE_FUNCTION)
event.listen(HubRemediation.__table__, "after_create", _QC_LINEAGE_TRIGGER)
event.listen(HubReceiptSession.__table__, "after_create", _AUDIT_FUNCTION)
event.listen(HubDiscrepancy.__table__, "after_create", _DISCREPANCY_INSERT_FUNCTION)
event.listen(HubDiscrepancy.__table__, "after_create", _DISCREPANCY_INSERT_TRIGGER)
event.listen(HubDiscrepancy.__table__, "after_create", _AUDIT_UPDATE_FUNCTION)
event.listen(HubEvidence.__table__, "after_create", _EVIDENCE_INSERT_FUNCTION)
event.listen(HubEvidence.__table__, "after_create", _EVIDENCE_INSERT_TRIGGER)
event.listen(HubEvidence.__table__, "after_create", _EVIDENCE_UPDATE_FUNCTION)
event.listen(HubEvidence.__table__, "after_create", _EVIDENCE_UPDATE_TRIGGER)
event.listen(
    HubEvidenceRetentionEvent.__table__, "after_create", _EVIDENCE_RETENTION_FUNCTION
)
event.listen(
    HubEvidenceRetentionEvent.__table__, "after_create", _EVIDENCE_RETENTION_TRIGGER
)
event.listen(
    HubDiscrepancy.__table__,
    "after_create",
    DDL(
        "CREATE TRIGGER tr_hub_discrepancies_update_restricted BEFORE UPDATE ON hub_discrepancies "
        "FOR EACH ROW EXECUTE FUNCTION reject_hub_quality_audit_update()"
    ),
)
event.listen(
    HubEvidenceRetentionEvent.__table__,
    "after_create",
    DDL(
        "CREATE TRIGGER tr_hub_evidence_retention_events_update_restricted "
        "BEFORE UPDATE ON hub_evidence_retention_events FOR EACH ROW "
        "EXECUTE FUNCTION reject_hub_quality_audit_update()"
    ),
)
for _table in (
    HubReceiptSession.__table__,
    HubReceiptItem.__table__,
    HubDiscrepancy.__table__,
    HubQCSession.__table__,
    HubQCInspection.__table__,
    HubEvidence.__table__,
    HubEvidenceRetentionEvent.__table__,
    HubRemediation.__table__,
):
    event.listen(
        _table,
        "after_create",
        DDL(
            f"CREATE TRIGGER tr_{_table.name}_delete_restricted BEFORE DELETE ON {_table.name} "
            "FOR EACH ROW EXECUTE FUNCTION reject_hub_quality_audit_delete()"
        ),
    )

event.listen(
    HubEvidenceRetentionEvent.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_hub_evidence_retention_event() CASCADE"),
)
event.listen(
    HubEvidence.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_hub_evidence_update() CASCADE"),
)
event.listen(
    HubEvidence.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_hub_evidence_insert() CASCADE"),
)
event.listen(
    HubReceiptItem.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_hub_receipt_item_quantity() CASCADE"),
)
event.listen(
    HubQCInspection.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_hub_qc_inspection_quantity() CASCADE"),
)
event.listen(
    HubRemediation.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_hub_qc_reinspection_lineage() CASCADE"),
)
event.listen(
    HubRemediation.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_hub_remediation_invariants() CASCADE"),
)
event.listen(
    HubQCSession.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS reject_completed_hub_qc_update() CASCADE"),
)
event.listen(
    HubReceiptSession.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS reject_completed_hub_receipt_update() CASCADE"),
)
event.listen(
    HubDiscrepancy.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_hub_discrepancy_insert() CASCADE"),
)
event.listen(
    HubDiscrepancy.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS reject_hub_quality_audit_update() CASCADE"),
)
event.listen(
    HubReceiptSession.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS reject_hub_quality_audit_delete() CASCADE"),
)
