"""Inert workflow audit, owner projection, and guest capability persistence."""

import uuid

from sqlalchemy import (
    BigInteger,
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.base import Base

_UUID = UUID(as_uuid=True)
_NOW = func.statement_timestamp()


class OrderWorkflowMigrationRun(Base):
    __tablename__ = "order_workflow_migration_runs"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    compatibility_writer_release_id = Column(String(100), nullable=False)
    compatibility_writer_started_at = Column(DateTime(timezone=True), nullable=False)
    migration_revision = Column(String(40), nullable=False)
    deployment_identity = Column(String(200), nullable=False)
    high_watermark_created_at = Column(DateTime(timezone=True))
    high_watermark_order_id = Column(_UUID)
    classification_cutover_at = Column(DateTime(timezone=True))
    validated_constraints = Column(String(4000))
    classified_row_count = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "compatibility_writer_release_id ~ '^[!-~]{1,100}$' AND migration_revision ~ '^[A-Za-z0-9]{1,40}$' AND deployment_identity ~ '^[!-~]{1,200}$'",
            name="ck_order_workflow_migration_runs_identifiers",
        ),
        CheckConstraint(
            "(high_watermark_created_at IS NULL) = (high_watermark_order_id IS NULL) AND (classified_row_count IS NULL OR classified_row_count >= 0)",
            name="ck_order_workflow_migration_runs_progress",
        ),
    )


class OrderWorkflowClassification(Base):
    __tablename__ = "order_workflow_classifications"

    order_id = Column(_UUID, primary_key=True)
    cohort = Column(String(40), nullable=False)
    policy_version = Column(String(40), nullable=False)
    access_mode = Column(String(20), nullable=False)
    evidence_kind = Column(String(60), nullable=False)
    evidence_reference = Column(String(200), nullable=False)
    migration_run_id = Column(
        _UUID,
        ForeignKey("order_workflow_migration_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    classified_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)
    classified_by = Column(String(100), nullable=False)
    notes_hash = Column(CHAR(64), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "cohort", "policy_version", "access_mode"],
            [
                "orders.id",
                "orders.workflow_cohort",
                "orders.workflow_policy_version",
                "orders.checkout_access_mode",
            ],
            name="fk_order_workflow_classifications_order_truth",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "cohort IN ('legacy_pre_bridge','legacy_ambiguous_quarantined','domestic_checkout_v1') AND access_mode IN ('authenticated','guest_capability','legacy_quarantined')",
            name="ck_order_workflow_classifications_values",
        ),
        CheckConstraint(
            "evidence_kind ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,59}$' AND evidence_reference ~ '^[!-~]{1,200}$' AND classified_by ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$' AND notes_hash ~ '^[0-9a-f]{64}$'",
            name="ck_order_workflow_classifications_evidence",
        ),
    )


class OrderCurrentOwner(Base):
    __tablename__ = "order_current_owners"

    order_id = Column(
        _UUID, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    original_customer_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    current_authenticated_user_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT")
    )
    claim_capability_id = Column(_UUID)
    claim_idempotency_key = Column(String(200))
    claimed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)
    row_version = Column(Integer, nullable=False, server_default="1")

    order = relationship("Order", back_populates="current_owner")

    __table_args__ = (
        ForeignKeyConstraint(
            ["claim_capability_id"],
            ["order_guest_capabilities.id"],
            name="fk_order_current_owners_claim_capability",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        UniqueConstraint(
            "order_id", "original_customer_id", name="uq_order_current_owners_original"
        ),
        UniqueConstraint(
            "claim_capability_id", name="uq_order_current_owners_claim_capability"
        ),
        CheckConstraint(
            "row_version > 0 AND ((current_authenticated_user_id IS NULL AND claim_capability_id IS NULL AND claim_idempotency_key IS NULL AND claimed_at IS NULL) OR (current_authenticated_user_id IS NOT NULL AND claim_capability_id IS NOT NULL AND claim_idempotency_key ~ '^[!-~]{1,200}$' AND claimed_at IS NOT NULL))",
            name="ck_order_current_owners_claim_shape",
        ),
    )


class OrderGuestCapability(Base):
    __tablename__ = "order_guest_capabilities"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    order_id = Column(_UUID, nullable=False)
    original_customer_id = Column(_UUID, nullable=False)
    scope = Column(String(40), nullable=False)
    token_digest = Column(BYTEA, nullable=False)
    pepper_key_version = Column(SmallInteger, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    replaced_by_id = Column(
        _UUID, ForeignKey("order_guest_capabilities.id", ondelete="RESTRICT")
    )
    claimed_by_user_id = Column(_UUID, ForeignKey("users.id", ondelete="RESTRICT"))
    claimed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)
    last_used_at = Column(DateTime(timezone=True))
    row_version = Column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "original_customer_id"],
            [
                "order_current_owners.order_id",
                "order_current_owners.original_customer_id",
            ],
            name="fk_order_guest_capabilities_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "scope IN ('checkout_prerequisites','read_order','claim_order') AND octet_length(token_digest)=32 AND pepper_key_version > 0 AND row_version > 0 AND expires_at > created_at AND expires_at <= created_at + interval '30 days'",
            name="ck_order_guest_capabilities_canonical",
        ),
        CheckConstraint(
            "(claimed_by_user_id IS NULL AND claimed_at IS NULL) OR (claimed_by_user_id IS NOT NULL AND claimed_at IS NOT NULL AND revoked_at IS NOT NULL)",
            name="ck_order_guest_capabilities_claim",
        ),
        UniqueConstraint(
            "token_digest",
            "pepper_key_version",
            name="uq_order_guest_capabilities_digest_version",
        ),
        UniqueConstraint(
            "replaced_by_id", name="uq_order_guest_capabilities_replacement"
        ),
        Index(
            "ix_order_guest_capabilities_scope_expiry",
            "order_id",
            "scope",
            "expires_at",
        ),
    )
