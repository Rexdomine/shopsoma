"""Narrow transactional outbox for post-payment checkout coordination."""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.core.base import Base


class CheckoutOutboxEvent(Base):
    """One deterministic, provider-free checkout coordination event."""

    __tablename__ = "checkout_outbox_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(50), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)
    order_id = Column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    payload_version = Column(Integer, nullable=False, server_default="1")
    payload = Column(JSONB, nullable=False)
    status = Column(String(20), nullable=False, server_default="pending")
    available_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.statement_timestamp(),
    )
    claim_owner = Column(String(100))
    claim_token = Column(UUID(as_uuid=True))
    claim_expires_at = Column(DateTime(timezone=True))
    attempt_count = Column(Integer, nullable=False, server_default="0")
    effect_identity = Column(String(200), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    failed_at = Column(DateTime(timezone=True))
    failure_code = Column(String(100))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.statement_timestamp(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.statement_timestamp(),
    )

    __table_args__ = (
        UniqueConstraint(
            "event_type", "source_id", name="uq_checkout_outbox_logical_event"
        ),
        UniqueConstraint("effect_identity", name="uq_checkout_outbox_effect_identity"),
        CheckConstraint(
            "event_type IN ('payment_verified_start_order','payment_failed_release','late_payment_exception')",
            name="ck_checkout_outbox_event_type",
        ),
        CheckConstraint(
            "payload_version=1 AND jsonb_typeof(payload)='object'",
            name="ck_checkout_outbox_payload",
        ),
        CheckConstraint(
            "status IN ('pending','claimed','completed','failed') AND attempt_count>=0",
            name="ck_checkout_outbox_status",
        ),
        CheckConstraint(
            "(status='pending' AND claim_owner IS NULL AND claim_token IS NULL AND claim_expires_at IS NULL AND completed_at IS NULL AND failed_at IS NULL AND failure_code IS NULL) OR "
            "(status='claimed' AND claim_owner IS NOT NULL AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL AND completed_at IS NULL AND failed_at IS NULL AND failure_code IS NULL) OR "
            "(status='completed' AND claim_owner IS NULL AND claim_token IS NULL AND claim_expires_at IS NULL AND completed_at IS NOT NULL AND failed_at IS NULL AND failure_code IS NULL) OR "
            "(status='failed' AND claim_owner IS NULL AND claim_token IS NULL AND claim_expires_at IS NULL AND completed_at IS NULL AND failed_at IS NOT NULL AND failure_code IS NOT NULL)",
            name="ck_checkout_outbox_lifecycle",
        ),
        CheckConstraint(
            "effect_identity ~ '^checkout-outbox:[0-9a-f-]{36}$' AND "
            "(claim_owner IS NULL OR claim_owner ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$') AND "
            "(failure_code IS NULL OR failure_code ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$')",
            name="ck_checkout_outbox_identifiers",
        ),
        Index(
            "ix_checkout_outbox_claimable",
            "available_at",
            "created_at",
            postgresql_where=text("status IN ('pending','claimed')"),
        ),
        Index("ix_checkout_outbox_order", "order_id", "created_at"),
    )


__all__ = ["CheckoutOutboxEvent"]
