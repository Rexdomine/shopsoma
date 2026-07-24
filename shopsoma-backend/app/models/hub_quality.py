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
    CANCELLED = "cancelled"


_UUID = UUID(as_uuid=True)


def _timestamps():
    return (
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
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
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
    sequence = Column(Integer, nullable=False)
    previous_session_id = Column(_UUID, nullable=True)
    remediation_id = Column(_UUID, nullable=True)
    state = Column(String(30), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
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
            "state IN ('qc_pending', 'qc_in_progress', 'qc_passed', 'qc_failed', "
            "'remediation', 'cancelled')",
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
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
    created_by_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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
            "access_scope = 'hub_quality_private'",
            name="ck_hub_evidence_access_scope",
        ),
        UniqueConstraint("storage_reference", name="uq_hub_evidence_storage_reference"),
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
            "state <> 'completed' OR completed_at IS NOT NULL",
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
    IF OLD.completed_at IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'completed receipt sessions are immutable';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_RECEIPT_IMMUTABILITY_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_receipt_sessions_completed_immutable BEFORE UPDATE ON hub_receipt_sessions
FOR EACH ROW EXECUTE FUNCTION reject_completed_hub_receipt_update()
"""
)
_RECEIPT_QUANTITY_FUNCTION = DDL(
    """
CREATE FUNCTION validate_hub_receipt_item_quantity() RETURNS trigger AS $$
DECLARE allocated integer; already_received integer; receipt_completed timestamptz;
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
BEGIN
    IF NEW.sequence > 1 THEN
        SELECT qc_session_id, receipt_session_id, state
          INTO remediation_session, remediation_receipt, remediation_state
          FROM hub_remediations WHERE id = NEW.remediation_id FOR UPDATE;
        IF remediation_session IS DISTINCT FROM NEW.previous_session_id
           OR remediation_receipt IS DISTINCT FROM NEW.receipt_session_id
           OR remediation_state IS DISTINCT FROM 'completed' THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'reinspection requires completed remediation for the previous QC session';
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
DECLARE qc_completed timestamptz;
BEGIN
    IF TG_TABLE_NAME = 'hub_qc_sessions' THEN
        IF NEW.id IS DISTINCT FROM OLD.id
           OR NEW.receipt_session_id IS DISTINCT FROM OLD.receipt_session_id
           OR NEW.inbound_transfer_id IS DISTINCT FROM OLD.inbound_transfer_id
           OR NEW.cohort_id IS DISTINCT FROM OLD.cohort_id
           OR NEW.order_id IS DISTINCT FROM OLD.order_id
           OR NEW.vendor_id IS DISTINCT FROM OLD.vendor_id
           OR NEW.hub_id IS DISTINCT FROM OLD.hub_id
           OR NEW.sequence IS DISTINCT FROM OLD.sequence
           OR NEW.previous_session_id IS DISTINCT FROM OLD.previous_session_id
           OR NEW.remediation_id IS DISTINCT FROM OLD.remediation_id THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC session aggregate lineage is immutable';
        END IF;
        IF OLD.completed_at IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'completed QC sessions are immutable';
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
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'QC inspection aggregate identity is immutable';
        END IF;
        IF TG_OP = 'UPDATE' AND NEW.decision IS DISTINCT FROM OLD.decision AND EXISTS (
            SELECT 1 FROM hub_remediations WHERE failed_inspection_id = OLD.id
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'remediated inspection decisions are immutable';
        END IF;
        SELECT completed_at INTO qc_completed FROM hub_qc_sessions
        WHERE id = NEW.qc_session_id FOR UPDATE;
        IF qc_completed IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'inspections in completed QC sessions are immutable';
        END IF;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
"""
)
_QC_SESSION_IMMUTABILITY_TRIGGER = DDL(
    """
CREATE TRIGGER tr_hub_qc_sessions_completed_immutable BEFORE UPDATE ON hub_qc_sessions
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
DECLARE inspection_decision hub_qc_decision;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF OLD.completed_at IS NOT NULL OR EXISTS (
            SELECT 1 FROM hub_qc_sessions WHERE remediation_id = OLD.id
        ) THEN
            RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'completed or consumed remediation is immutable';
        END IF;
    END IF;
    SELECT decision INTO inspection_decision
    FROM hub_qc_inspections
    WHERE id = NEW.failed_inspection_id AND qc_session_id = NEW.qc_session_id
    FOR UPDATE;
    IF inspection_decision IS NULL OR inspection_decision NOT IN ('fail', 'rejected') THEN
        RAISE EXCEPTION USING ERRCODE = '23514', MESSAGE = 'remediation requires a failed or rejected inspection';
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
_AUDIT_FUNCTION = DDL(
    """
CREATE FUNCTION reject_hub_quality_audit_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE = '23503', MESSAGE = 'hub quality audit records cannot be deleted';
END; $$ LANGUAGE plpgsql
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
event.listen(HubDiscrepancy.__table__, "after_create", _AUDIT_UPDATE_FUNCTION)
for _table in (HubDiscrepancy.__table__, HubEvidence.__table__):
    event.listen(
        _table,
        "after_create",
        DDL(
            f"CREATE TRIGGER tr_{_table.name}_update_restricted BEFORE UPDATE ON {_table.name} "
            "FOR EACH ROW EXECUTE FUNCTION reject_hub_quality_audit_update()"
        ),
    )
for _table in (
    HubReceiptSession.__table__,
    HubReceiptItem.__table__,
    HubDiscrepancy.__table__,
    HubQCSession.__table__,
    HubQCInspection.__table__,
    HubEvidence.__table__,
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
    DDL("DROP FUNCTION IF EXISTS reject_hub_quality_audit_update() CASCADE"),
)
event.listen(
    HubReceiptSession.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS reject_hub_quality_audit_delete() CASCADE"),
)
