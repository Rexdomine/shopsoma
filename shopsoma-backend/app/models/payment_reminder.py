"""Order payment reminder models for abandoned checkout payment recovery."""

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
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.base import Base


class OrderPaymentReminder(Base):
    """Durable record and idempotency marker for pending payment email reminders."""

    __tablename__ = "order_payment_reminders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    payment_attempt_id = Column(UUID(as_uuid=True), nullable=True)
    reminder_type = Column(String(50), nullable=False, default="pending_payment_24h")
    idempotency_key = Column(String(255), unique=True, nullable=False, index=True)
    recipient_email = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, server_default="pending", index=True)

    # Distributed concurrency leasing
    claim_owner = Column(String(100), nullable=True)
    claim_token = Column(UUID(as_uuid=True), nullable=True)
    claim_expires_at = Column(DateTime(timezone=True), nullable=True)
    attempt_count = Column(Integer, nullable=False, server_default="0")

    # Timing
    payment_created_at = Column(DateTime(timezone=True), nullable=False)
    scheduled_for = Column(DateTime(timezone=True), nullable=False, index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)

    # Audit & evidence payload
    evidence_payload = Column(JSONB, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.statement_timestamp(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.statement_timestamp(),
        onupdate=func.statement_timestamp(),
    )

    # Relationships
    order = relationship("Order", back_populates="payment_reminders")
    payment = relationship("Payment")

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'claimed', 'sent', 'cancelled', 'failed')",
            name="ck_order_payment_reminders_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_order_payment_reminders_attempt_count",
        ),
        UniqueConstraint(
            "idempotency_key",
            name="uq_order_payment_reminders_idempotency_key",
        ),
        Index(
            "ix_order_payment_reminders_claimable",
            "status",
            "scheduled_for",
            postgresql_where=text("status IN ('pending', 'claimed')"),
        ),
        Index(
            "ix_order_payment_reminders_order_type",
            "order_id",
            "reminder_type",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<OrderPaymentReminder order_id={self.order_id} "
            f"type={self.reminder_type} status={self.status}>"
        )


__all__ = ["OrderPaymentReminder"]
