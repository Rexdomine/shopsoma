"""Add narrow checkout outbox.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "checkout_outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="pending", nullable=False
        ),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column("claim_owner", sa.String(length=100), nullable=True),
        sa.Column("claim_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("effect_identity", sa.String(length=200), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("statement_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('payment_verified_start_order','payment_failed_release','late_payment_exception')",
            name="ck_checkout_outbox_event_type",
        ),
        sa.CheckConstraint(
            "payload_version=1 AND jsonb_typeof(payload)='object'",
            name="ck_checkout_outbox_payload",
        ),
        sa.CheckConstraint(
            "status IN ('pending','claimed','completed','failed') AND attempt_count>=0",
            name="ck_checkout_outbox_status",
        ),
        sa.CheckConstraint(
            "(status='pending' AND claim_owner IS NULL AND claim_token IS NULL AND claim_expires_at IS NULL AND completed_at IS NULL AND failed_at IS NULL AND failure_code IS NULL) OR "
            "(status='claimed' AND claim_owner IS NOT NULL AND claim_token IS NOT NULL AND claim_expires_at IS NOT NULL AND completed_at IS NULL AND failed_at IS NULL AND failure_code IS NULL) OR "
            "(status='completed' AND claim_owner IS NULL AND claim_token IS NULL AND claim_expires_at IS NULL AND completed_at IS NOT NULL AND failed_at IS NULL AND failure_code IS NULL) OR "
            "(status='failed' AND claim_owner IS NULL AND claim_token IS NULL AND claim_expires_at IS NULL AND completed_at IS NULL AND failed_at IS NOT NULL AND failure_code IS NOT NULL)",
            name="ck_checkout_outbox_lifecycle",
        ),
        sa.CheckConstraint(
            "effect_identity ~ '^checkout-outbox:[0-9a-f-]{36}$' AND "
            "(claim_owner IS NULL OR claim_owner ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$') AND "
            "(failure_code IS NULL OR failure_code ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$')",
            name="ck_checkout_outbox_identifiers",
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_type", "source_id", name="uq_checkout_outbox_logical_event"
        ),
        sa.UniqueConstraint(
            "effect_identity", name="uq_checkout_outbox_effect_identity"
        ),
    )
    op.create_index(
        "ix_checkout_outbox_claimable",
        "checkout_outbox_events",
        ["available_at", "created_at"],
        unique=False,
        postgresql_where=sa.text("status IN ('pending','claimed')"),
    )
    op.create_index(
        "ix_checkout_outbox_order",
        "checkout_outbox_events",
        ["order_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_checkout_outbox_order", table_name="checkout_outbox_events")
    op.drop_index("ix_checkout_outbox_claimable", table_name="checkout_outbox_events")
    op.drop_table("checkout_outbox_events")
