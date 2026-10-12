"""add order_payment_reminders table for pending payment reminders

Revision ID: a8b9c0d1e2f3
Revises: z9a0b1c2d3e4
Create Date: 2026-10-11 12:00:00.000000

Durable record and idempotency marker for pending payment email reminders.
Ensures single-send guarantees across retries, concurrent workers, and scans.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a8b9c0d1e2f3"
down_revision = "z9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "order_payment_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payment_attempt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reminder_type", sa.String(length=50), nullable=False, server_default="pending_payment_24h"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("claim_owner", sa.String(length=100), nullable=True),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payment_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("statement_timestamp()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("statement_timestamp()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'claimed', 'sent', 'cancelled', 'failed')", name="ck_order_payment_reminders_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_order_payment_reminders_attempt_count"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_order_payment_reminders_idempotency_key"),
    )
    op.create_index(
        "ix_order_payment_reminders_claimable",
        "order_payment_reminders",
        ["status", "scheduled_for"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending', 'claimed')"),
    )
    op.create_index(
        "ix_order_payment_reminders_order_type",
        "order_payment_reminders",
        ["order_id", "reminder_type"],
        unique=False,
    )
    op.create_index(
        "ix_order_payment_reminders_payment_id",
        "order_payment_reminders",
        ["payment_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_order_payment_reminders_payment_id", table_name="order_payment_reminders")
    op.drop_index("ix_order_payment_reminders_order_type", table_name="order_payment_reminders")
    op.drop_index(
        "ix_order_payment_reminders_claimable",
        table_name="order_payment_reminders",
        postgresql_where=sa.text("status IN ('pending', 'claimed')"),
    )
    op.drop_table("order_payment_reminders")
