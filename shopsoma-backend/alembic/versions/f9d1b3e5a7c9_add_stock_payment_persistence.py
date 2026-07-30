"""Add database-enforced stock reservation and payment persistence.

Revision ID: f9d1b3e5a7c9
Revises: e8c0a2d4f6b8
"""

import importlib.util
from pathlib import Path

from alembic import op

revision = "f9d1b3e5a7c9"
down_revision = "e8c0a2d4f6b8"
branch_labels = None
depends_on = None

# Frozen companion SQL installs validate_stock_reservation_write,
# protect_reserved_inventory, protect_reserved_order_item, protect_reserved_order,
# validate_payment_attempt_write, validate_payment_attempt_membership_write,
# validate_payment_attempt_exact_reservations, and
# validate_payment_attempt_evidence_write.
_helper_spec = importlib.util.spec_from_file_location(
    "stock_payment_ddl_f9",
    Path(__file__).parents[1] / "stock_payment_ddl_f9.py",
)
assert _helper_spec is not None and _helper_spec.loader is not None
_helper = importlib.util.module_from_spec(_helper_spec)
_helper_spec.loader.exec_module(_helper)
TRIGGER_DDLS = _helper.TRIGGER_DDLS
DROP_DDLS = _helper.DROP_DDLS


def _statements(blocks):
    for block in blocks:
        remaining = block.strip()
        while remaining:
            if remaining.startswith("CREATE FUNCTION"):
                marker = "$$ LANGUAGE plpgsql;"
                end = remaining.index(marker) + len(marker)
            else:
                end = remaining.index(";") + 1
            yield remaining[:end].strip()
            remaining = remaining[end:].strip()


def upgrade() -> None:
    op.execute(
        r"""
CREATE TABLE stock_reservations (
 id uuid PRIMARY KEY, order_id uuid NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
 order_item_id uuid NOT NULL REFERENCES order_items(id) ON DELETE RESTRICT,
 customer_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 quote_id uuid NOT NULL REFERENCES customer_shipping_quotes(id) ON DELETE RESTRICT,
 quote_selection_id uuid NOT NULL REFERENCES customer_shipping_quote_selections(id) ON DELETE RESTRICT,
 quote_option_id uuid NOT NULL REFERENCES customer_shipping_quote_options(id) ON DELETE RESTRICT,
 intent_id uuid NOT NULL REFERENCES outbound_shipment_intents(id) ON DELETE RESTRICT,
 product_id uuid NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
 variant_id uuid REFERENCES product_variants(id) ON DELETE RESTRICT,
 sku varchar(100) NOT NULL, quantity integer NOT NULL,
 unit_price numeric(18,4) NOT NULL, line_amount numeric(18,4) NOT NULL,
 currency varchar(3) NOT NULL, ttl_seconds integer NOT NULL DEFAULT 1800,
 expires_at timestamptz NOT NULL, state varchar(20) NOT NULL DEFAULT 'active',
 terminal_reason varchar(200), terminal_at timestamptz,
 source_command varchar(100) NOT NULL, idempotency_key varchar(200) NOT NULL,
 row_version integer NOT NULL DEFAULT 1, creation_txid bigint NOT NULL,
 created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 CONSTRAINT ck_stock_reservations_quantity CHECK (quantity > 0),
 CONSTRAINT ck_stock_reservations_money CHECK (unit_price NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND line_amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND unit_price > 0 AND line_amount = unit_price * quantity AND currency ~ '^[A-Z]{3}$'),
 CONSTRAINT ck_stock_reservations_identifiers CHECK (sku ~ '^[!-~]+$' AND source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND idempotency_key ~ '^[!-~]+$'),
 CONSTRAINT ck_stock_reservations_lifecycle CHECK (ttl_seconds BETWEEN 1 AND 1800 AND row_version > 0 AND expires_at > created_at AND expires_at <= created_at + ttl_seconds * interval '1 second'),
 CONSTRAINT ck_stock_reservations_state CHECK (state IN ('active','released','consumed','expired') AND ((state='active' AND terminal_at IS NULL AND terminal_reason IS NULL) OR (state<>'active' AND terminal_at IS NOT NULL AND terminal_reason IS NOT NULL))),
 CONSTRAINT uq_stock_reservations_customer_replay UNIQUE (customer_id,source_command,idempotency_key)
)
"""
    )
    op.execute(
        "CREATE INDEX ix_stock_reservations_inventory_subject ON stock_reservations(product_id,variant_id,state,expires_at)"
    )
    op.execute(
        "CREATE INDEX ix_stock_reservations_selection ON stock_reservations(quote_selection_id,created_at)"
    )
    op.execute(
        r"""
CREATE TABLE payment_attempts (
 id uuid PRIMARY KEY, order_id uuid NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
 customer_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
 quote_id uuid NOT NULL REFERENCES customer_shipping_quotes(id) ON DELETE RESTRICT,
 quote_selection_id uuid NOT NULL REFERENCES customer_shipping_quote_selections(id) ON DELETE RESTRICT,
 quote_option_id uuid NOT NULL REFERENCES customer_shipping_quote_options(id) ON DELETE RESTRICT,
 intent_id uuid NOT NULL REFERENCES outbound_shipment_intents(id) ON DELETE RESTRICT,
 amount numeric(18,4) NOT NULL, currency varchar(3) NOT NULL,
 state varchar(30) NOT NULL DEFAULT 'pending', payment_window_seconds integer NOT NULL DEFAULT 1800,
 authorization_grace_seconds integer NOT NULL DEFAULT 900,
 expires_at timestamptz NOT NULL, authorization_deadline_at timestamptz NOT NULL,
 claim_ttl_seconds integer NOT NULL DEFAULT 300, lease_token uuid,
 call_started_at timestamptz, claim_expires_at timestamptz,
 supersedes_attempt_id uuid REFERENCES payment_attempts(id) ON DELETE RESTRICT,
 terminal_evidence_id uuid, terminal_at timestamptz,
 source_command varchar(100) NOT NULL, idempotency_key varchar(200) NOT NULL,
 row_version integer NOT NULL DEFAULT 1, creation_txid bigint NOT NULL,
 created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 CONSTRAINT ck_payment_attempts_money CHECK (amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) AND amount > 0 AND currency ~ '^[A-Z]{3}$'),
 CONSTRAINT ck_payment_attempts_state CHECK (state IN ('pending','call_started','verified','failed','expired','abandoned_unknown')),
 CONSTRAINT ck_payment_attempts_lifecycle_shape CHECK ((state='pending' AND lease_token IS NULL AND call_started_at IS NULL AND claim_expires_at IS NULL AND terminal_evidence_id IS NULL AND terminal_at IS NULL) OR (state='call_started' AND lease_token IS NOT NULL AND call_started_at IS NOT NULL AND claim_expires_at IS NOT NULL AND terminal_evidence_id IS NULL AND terminal_at IS NULL) OR (state IN ('verified','failed','abandoned_unknown') AND terminal_evidence_id IS NOT NULL AND terminal_at IS NOT NULL) OR (state='expired' AND terminal_evidence_id IS NULL AND terminal_at IS NOT NULL)),
 CONSTRAINT ck_payment_attempts_timing CHECK (payment_window_seconds BETWEEN 1 AND 1800 AND authorization_grace_seconds BETWEEN 0 AND 900 AND claim_ttl_seconds BETWEEN 1 AND 900 AND row_version > 0 AND expires_at > created_at AND authorization_deadline_at = expires_at + authorization_grace_seconds * interval '1 second'),
 CONSTRAINT ck_payment_attempts_identifiers CHECK (source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND idempotency_key ~ '^[!-~]+$'),
 CONSTRAINT uq_payment_attempts_customer_replay UNIQUE (customer_id,source_command,idempotency_key),
 CONSTRAINT uq_payment_attempts_single_successor UNIQUE (supersedes_attempt_id)
)
"""
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_payment_attempts_active_subject ON payment_attempts(quote_selection_id) WHERE state IN ('pending','call_started')"
    )
    op.execute(
        "CREATE INDEX ix_payment_attempts_subject ON payment_attempts(quote_selection_id,created_at)"
    )
    op.execute(
        r"""
CREATE TABLE payment_attempt_reservations (
 attempt_id uuid NOT NULL REFERENCES payment_attempts(id) ON DELETE RESTRICT,
 reservation_id uuid NOT NULL REFERENCES stock_reservations(id) ON DELETE RESTRICT,
 creation_txid bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 PRIMARY KEY(attempt_id,reservation_id)
)
"""
    )
    op.execute(
        r"""
CREATE TABLE payment_attempt_evidence (
 id uuid PRIMARY KEY, attempt_id uuid NOT NULL REFERENCES payment_attempts(id) ON DELETE RESTRICT,
 source varchar(50) NOT NULL, event_id varchar(200) NOT NULL,
 evidence_type varchar(50) NOT NULL, evidence_hash varchar(64) NOT NULL,
 observed_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT statement_timestamp(),
 CONSTRAINT ck_payment_attempt_evidence_identifiers CHECK (source ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND event_id ~ '^[!-~]+$' AND evidence_type ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND evidence_hash ~ '^[0-9a-f]{64}$'),
 CONSTRAINT uq_payment_attempt_evidence_external_event UNIQUE(source,event_id)
)
"""
    )
    op.execute(
        "ALTER TABLE payment_attempts ADD CONSTRAINT fk_payment_attempts_terminal_evidence FOREIGN KEY(terminal_evidence_id) REFERENCES payment_attempt_evidence(id) ON DELETE RESTRICT"
    )
    op.execute(
        "CREATE INDEX ix_payment_attempt_evidence_attempt ON payment_attempt_evidence(attempt_id,created_at)"
    )
    for statement in _statements(TRIGGER_DDLS):
        op.execute(statement)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE payment_attempts DROP CONSTRAINT fk_payment_attempts_terminal_evidence"
    )
    op.execute("DROP INDEX ix_payment_attempt_evidence_attempt")
    op.drop_table("payment_attempt_evidence")
    op.drop_table("payment_attempt_reservations")
    op.execute("DROP INDEX ix_payment_attempts_subject")
    op.execute("DROP INDEX uq_payment_attempts_active_subject")
    op.drop_table("payment_attempts")
    op.execute("DROP INDEX ix_stock_reservations_selection")
    op.execute("DROP INDEX ix_stock_reservations_inventory_subject")
    op.drop_table("stock_reservations")
    for statement in _statements(DROP_DDLS):
        op.execute(statement)
