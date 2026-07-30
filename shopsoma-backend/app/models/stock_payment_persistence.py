"""Database-enforced stock reservation and checkout payment persistence.

This lane contains no provider transport, credentials, raw payloads, or feature
activation. It records exact authoritative checkout subjects and audit evidence.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DDL,
    DateTime,
    FetchedValue,
    ForeignKey,
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


class StockReservation(Base):
    """A bounded stock claim for one exact selected checkout line."""

    __tablename__ = "stock_reservations"

    id = _id_column()
    order_id = Column(
        _UUID, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    order_item_id = Column(
        _UUID, ForeignKey("order_items.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    quote_id = Column(
        _UUID,
        ForeignKey("customer_shipping_quotes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quote_selection_id = Column(
        _UUID,
        ForeignKey("customer_shipping_quote_selections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quote_option_id = Column(
        _UUID,
        ForeignKey("customer_shipping_quote_options.id", ondelete="RESTRICT"),
        nullable=False,
    )
    intent_id = Column(
        _UUID,
        ForeignKey("outbound_shipment_intents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    product_id = Column(
        _UUID, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    variant_id = Column(_UUID, ForeignKey("product_variants.id", ondelete="RESTRICT"))
    size_stock_id = Column(_UUID, ForeignKey("size_stocks.id", ondelete="RESTRICT"))
    # Catalog SKUs are optional snapshots. The UUID subject columns above are
    # the collision-free server-owned inventory identity.
    sku = Column(String(100))
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Numeric(18, 4), nullable=False)
    line_amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False)
    ttl_seconds = Column(Integer, nullable=False, server_default="1800")
    expires_at = Column(
        DateTime(timezone=True), nullable=False, server_default=FetchedValue()
    )
    state = Column(String(20), nullable=False, server_default="active")
    terminal_reason = Column(String(200))
    terminal_at = Column(DateTime(timezone=True))
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    row_version = Column(Integer, nullable=False, server_default="1")
    creation_txid = Column(BigInteger, nullable=False, server_default=FetchedValue())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_reservations_quantity"),
        CheckConstraint(
            "unit_price NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND line_amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND unit_price > 0 AND line_amount = unit_price * quantity "
            "AND currency ~ '^[A-Z]{3}$'",
            name="ck_stock_reservations_money",
        ),
        CheckConstraint(
            "(sku IS NULL OR sku ~ '^[!-~]+$') "
            "AND source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' "
            "AND idempotency_key ~ '^[!-~]+$'",
            name="ck_stock_reservations_identifiers",
        ),
        CheckConstraint(
            "variant_id IS NULL OR size_stock_id IS NULL",
            name="ck_stock_reservations_one_detailed_subject",
        ),
        CheckConstraint(
            "ttl_seconds BETWEEN 1 AND 1800 AND row_version > 0 "
            "AND expires_at > created_at "
            "AND expires_at <= created_at + ttl_seconds * interval '1 second'",
            name="ck_stock_reservations_lifecycle",
        ),
        CheckConstraint(
            "state IN ('active','released','consumed','expired') AND "
            "((state='active' AND terminal_at IS NULL AND terminal_reason IS NULL) OR "
            "(state<>'active' AND terminal_at IS NOT NULL AND terminal_reason IS NOT NULL))",
            name="ck_stock_reservations_state",
        ),
        UniqueConstraint(
            "customer_id",
            "source_command",
            "idempotency_key",
            name="uq_stock_reservations_customer_replay",
        ),
        Index(
            "ix_stock_reservations_inventory_subject",
            "product_id",
            "variant_id",
            "size_stock_id",
            "state",
            "expires_at",
        ),
        Index("ix_stock_reservations_selection", "quote_selection_id", "created_at"),
    )


class PaymentAttempt(Base):
    """One leased checkout payment attempt bound to an immutable reservation set."""

    __tablename__ = "payment_attempts"

    id = _id_column()
    order_id = Column(
        _UUID, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    quote_id = Column(
        _UUID,
        ForeignKey("customer_shipping_quotes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quote_selection_id = Column(
        _UUID,
        ForeignKey("customer_shipping_quote_selections.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quote_option_id = Column(
        _UUID,
        ForeignKey("customer_shipping_quote_options.id", ondelete="RESTRICT"),
        nullable=False,
    )
    intent_id = Column(
        _UUID,
        ForeignKey("outbound_shipment_intents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False)
    state = Column(String(30), nullable=False, server_default="pending")
    payment_window_seconds = Column(Integer, nullable=False, server_default="1800")
    authorization_grace_seconds = Column(Integer, nullable=False, server_default="900")
    expires_at = Column(
        DateTime(timezone=True), nullable=False, server_default=FetchedValue()
    )
    authorization_deadline_at = Column(
        DateTime(timezone=True), nullable=False, server_default=FetchedValue()
    )
    claim_ttl_seconds = Column(Integer, nullable=False, server_default="300")
    lease_token = Column(_UUID)
    call_started_at = Column(DateTime(timezone=True))
    claim_expires_at = Column(DateTime(timezone=True))
    supersedes_attempt_id = Column(
        _UUID, ForeignKey("payment_attempts.id", ondelete="RESTRICT")
    )
    terminal_evidence_id = Column(
        _UUID,
        ForeignKey(
            "payment_attempt_evidence.id",
            name="fk_payment_attempts_terminal_evidence",
            ondelete="RESTRICT",
            use_alter=True,
        ),
    )
    terminal_at = Column(DateTime(timezone=True))
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    row_version = Column(Integer, nullable=False, server_default="1")
    creation_txid = Column(BigInteger, nullable=False, server_default=FetchedValue())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND amount > 0 AND currency ~ '^[A-Z]{3}$'",
            name="ck_payment_attempts_money",
        ),
        CheckConstraint(
            "state IN ('pending','call_started','verified','failed','expired','abandoned_unknown')",
            name="ck_payment_attempts_state",
        ),
        CheckConstraint(
            "(state='pending' AND lease_token IS NULL AND call_started_at IS NULL "
            "AND claim_expires_at IS NULL AND terminal_evidence_id IS NULL AND terminal_at IS NULL) OR "
            "(state='call_started' AND lease_token IS NOT NULL AND call_started_at IS NOT NULL "
            "AND claim_expires_at IS NOT NULL AND terminal_evidence_id IS NULL AND terminal_at IS NULL) OR "
            "(state IN ('verified','failed','abandoned_unknown') AND terminal_evidence_id IS NOT NULL "
            "AND terminal_at IS NOT NULL) OR "
            "(state='expired' AND terminal_evidence_id IS NULL AND terminal_at IS NOT NULL)",
            name="ck_payment_attempts_lifecycle_shape",
        ),
        CheckConstraint(
            "payment_window_seconds BETWEEN 1 AND 1800 "
            "AND authorization_grace_seconds BETWEEN 0 AND 900 "
            "AND claim_ttl_seconds BETWEEN 1 AND 900 AND row_version > 0 "
            "AND expires_at > created_at "
            "AND authorization_deadline_at = expires_at "
            "+ authorization_grace_seconds * interval '1 second'",
            name="ck_payment_attempts_timing",
        ),
        CheckConstraint(
            "source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' "
            "AND idempotency_key ~ '^[!-~]+$'",
            name="ck_payment_attempts_identifiers",
        ),
        UniqueConstraint(
            "customer_id",
            "source_command",
            "idempotency_key",
            name="uq_payment_attempts_customer_replay",
        ),
        UniqueConstraint(
            "supersedes_attempt_id", name="uq_payment_attempts_single_successor"
        ),
        Index("ix_payment_attempts_subject", "quote_selection_id", "created_at"),
        Index(
            "uq_payment_attempts_active_subject",
            "order_id",
            unique=True,
            postgresql_where=text("state IN ('pending','call_started')"),
        ),
    )


class PaymentAttemptReservation(Base):
    """Immutable exact membership of reservations in an attempt."""

    __tablename__ = "payment_attempt_reservations"

    attempt_id = Column(
        _UUID,
        ForeignKey("payment_attempts.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    reservation_id = Column(
        _UUID,
        ForeignKey("stock_reservations.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    creation_txid = Column(BigInteger, nullable=False, server_default=FetchedValue())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)


class PaymentAttemptEvidence(Base):
    """Provider-neutral append-only evidence metadata; never a raw payload."""

    __tablename__ = "payment_attempt_evidence"

    id = _id_column()
    attempt_id = Column(
        _UUID, ForeignKey("payment_attempts.id", ondelete="RESTRICT"), nullable=False
    )
    source = Column(String(50), nullable=False)
    event_id = Column(String(200), nullable=False)
    evidence_type = Column(String(50), nullable=False)
    evidence_hash = Column(String(64), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "source ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND event_id ~ '^[!-~]+$' "
            "AND evidence_type ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' "
            "AND evidence_hash ~ '^[0-9a-f]{64}$'",
            name="ck_payment_attempt_evidence_identifiers",
        ),
        UniqueConstraint(
            "source", "event_id", name="uq_payment_attempt_evidence_external_event"
        ),
        Index("ix_payment_attempt_evidence_attempt", "attempt_id", "created_at"),
    )


STOCK_PAYMENT_TRIGGER_DDLS: tuple[str, ...] = (
    r"""
CREATE FUNCTION validate_stock_reservation_write() RETURNS trigger AS $$
DECLARE
    now_at timestamptz := statement_timestamp();
    item_order uuid;
    item_product uuid;
    item_variant uuid;
    item_size_stock uuid;
    item_variation uuid;
    item_size text;
    item_quantity integer;
    item_unit_price numeric;
    item_currency text;
    order_customer uuid;
    product_stock integer;
    product_sku text;
    product_made_to_order boolean;
    variant_stock integer;
    variant_sku text;
    variant_product uuid;
    size_stock_stock integer;
    size_stock_product uuid;
    size_stock_variation uuid;
    size_stock_size text;
    selection_quote uuid;
    selection_option uuid;
    selection_intent uuid;
    selection_customer uuid;
    quote_order uuid;
    quote_package uuid;
    quote_package_version integer;
    quote_expires timestamptz;
    package_item_quantity integer;
    active_quantity bigint;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'stock reservation is immutable audit';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'active' OR NEW.terminal_at IS NOT NULL OR NEW.terminal_reason IS NOT NULL THEN
            RAISE EXCEPTION 'stock reservation must start active';
        END IF;
        NEW.row_version := 1;
        NEW.creation_txid := txid_current();

        -- Serialize order -> item before snapshotting either row. Inventory and
        -- quote locks come later in the shared cross-aggregate lock order.
        PERFORM 1 FROM orders WHERE id = NEW.order_id FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'stock reservation subject binding is invalid';
        END IF;
        SELECT oi.order_id, oi.product_id, oi.variant_id,
               NULLIF(oi.variant_details->>'size_stock_id', '')::uuid,
               NULLIF(oi.variant_details->>'variation_id', '')::uuid,
               oi.variant_details->>'size', oi.quantity,
               oi.unit_price, oi.currency, o.customer_id
          INTO item_order, item_product, item_variant, item_size_stock,
               item_variation, item_size, item_quantity,
               item_unit_price, item_currency, order_customer
          FROM order_items oi JOIN orders o ON o.id = oi.order_id
         WHERE oi.id = NEW.order_item_id AND o.id = NEW.order_id
         FOR UPDATE OF oi;
        IF NOT FOUND OR item_order <> NEW.order_id OR order_customer <> NEW.customer_id
           OR item_product <> NEW.product_id OR item_variant IS DISTINCT FROM NEW.variant_id
           OR item_size_stock IS DISTINCT FROM NEW.size_stock_id
           OR item_unit_price <> NEW.unit_price OR item_currency <> NEW.currency
           OR NEW.line_amount <> NEW.unit_price * NEW.quantity THEN
            RAISE EXCEPTION 'stock reservation subject binding is invalid';
        END IF;

        SELECT total_stock, sku, made_to_order
          INTO product_stock, product_sku, product_made_to_order
          FROM products WHERE id = NEW.product_id FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'stock reservation subject binding is invalid';
        END IF;
        IF NEW.size_stock_id IS NOT NULL THEN
            -- Lock the parent before the child. Otherwise a concurrent
            -- variation move can commit after this reservation and retarget
            -- the same SizeStock to another product.
            PERFORM 1 FROM variations WHERE id = item_variation FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'stock reservation subject binding is invalid';
            END IF;
            SELECT ss.stock, v.product_id, ss.variation_id, ss.size::text
              INTO size_stock_stock, size_stock_product, size_stock_variation, size_stock_size
              FROM size_stocks ss
              JOIN variations v ON v.id = ss.variation_id
             WHERE ss.id = NEW.size_stock_id FOR UPDATE OF ss;
            IF NOT FOUND OR size_stock_product <> NEW.product_id
               OR size_stock_variation IS DISTINCT FROM item_variation
               OR size_stock_size IS DISTINCT FROM item_size OR NEW.sku IS NOT NULL THEN
                RAISE EXCEPTION 'stock reservation subject binding is invalid';
            END IF;
        ELSIF NEW.variant_id IS NOT NULL THEN
            SELECT stock, sku, product_id INTO variant_stock, variant_sku, variant_product
              FROM product_variants WHERE id = NEW.variant_id FOR UPDATE;
            IF NOT FOUND OR variant_product <> NEW.product_id OR variant_sku IS DISTINCT FROM NEW.sku THEN
                RAISE EXCEPTION 'stock reservation subject binding is invalid';
            END IF;
        ELSIF product_sku IS DISTINCT FROM NEW.sku THEN
            RAISE EXCEPTION 'stock reservation subject binding is invalid';
        END IF;

        SELECT s.quote_id, s.option_id, s.intent_id, s.customer_id,
               q.order_id, q.package_id, q.package_version, q.expires_at
          INTO selection_quote, selection_option, selection_intent, selection_customer,
               quote_order, quote_package, quote_package_version, quote_expires
          FROM customer_shipping_quote_selections s
          JOIN customer_shipping_quotes q ON q.id = s.quote_id
         WHERE s.id = NEW.quote_selection_id
         FOR UPDATE OF q;
        -- Product, variant, and quote locks can wait. Re-sample only after the
        -- complete authoritative subject is locked so an expired quote cannot
        -- create an immediately expired active reservation.
        now_at := clock_timestamp();
        NEW.created_at := now_at;
        NEW.updated_at := now_at;
        IF NOT FOUND OR selection_quote <> NEW.quote_id OR selection_option <> NEW.quote_option_id
           OR selection_intent <> NEW.intent_id OR selection_customer <> NEW.customer_id
           OR quote_order <> NEW.order_id OR quote_expires <= now_at
           OR EXISTS (SELECT 1 FROM customer_shipping_quotes successor
                       WHERE successor.supersedes_quote_id = NEW.quote_id) THEN
            RAISE EXCEPTION 'stock reservation subject binding is invalid';
        END IF;
        SELECT COALESCE(sum(quantity), 0) INTO package_item_quantity
          FROM hub_package_items
         WHERE package_id = quote_package
           AND package_version = quote_package_version
           AND order_item_id = NEW.order_item_id;
        IF package_item_quantity = 0 THEN
            RAISE EXCEPTION 'stock reservation is not in quoted package composition';
        END IF;
        NEW.expires_at := LEAST(
            now_at + NEW.ttl_seconds * interval '1 second',
            quote_expires
        );
        IF EXISTS (
            SELECT 1 FROM payment_attempts
             WHERE order_id = NEW.order_id
               AND state IN ('pending', 'call_started')
        ) THEN
            RAISE EXCEPTION 'reservation set is locked by active payment attempt';
        END IF;

        SELECT COALESCE(sum(quantity), 0) INTO active_quantity
          FROM stock_reservations sr
         WHERE sr.product_id = NEW.product_id
           AND sr.variant_id IS NOT DISTINCT FROM NEW.variant_id
           AND sr.size_stock_id IS NOT DISTINCT FROM NEW.size_stock_id
           AND sr.state = 'active'
           AND (sr.expires_at > now_at OR EXISTS (
               SELECT 1 FROM payment_attempt_reservations ar
               JOIN payment_attempts pa ON pa.id = ar.attempt_id
                WHERE ar.reservation_id = sr.id
                 AND (pa.state = 'verified' OR (
                     pa.state = 'call_started'
                     AND pa.call_started_at < sr.expires_at
                     AND pa.claim_expires_at > now_at
                     AND pa.authorization_deadline_at >= now_at
                 ))
           ));
        IF NOT product_made_to_order
           AND active_quantity + NEW.quantity > COALESCE(size_stock_stock, variant_stock, product_stock) THEN
            RAISE EXCEPTION 'stock reservation exceeds available inventory';
        END IF;
        SELECT COALESCE(sum(quantity), 0) INTO active_quantity
          FROM stock_reservations sr
         WHERE sr.order_item_id = NEW.order_item_id
           AND sr.state = 'active'
           AND (sr.expires_at > now_at OR EXISTS (
               SELECT 1 FROM payment_attempt_reservations ar
               JOIN payment_attempts pa ON pa.id = ar.attempt_id
                WHERE ar.reservation_id = sr.id
                 AND (pa.state = 'verified' OR (
                     pa.state = 'call_started'
                     AND pa.call_started_at < sr.expires_at
                     AND pa.claim_expires_at > now_at
                     AND pa.authorization_deadline_at >= now_at
                 ))
           ));
        IF active_quantity + NEW.quantity > item_quantity THEN
            RAISE EXCEPTION 'stock reservation exceeds order item quantity';
        END IF;
        SELECT COALESCE(sum(quantity), 0) INTO active_quantity
          FROM stock_reservations sr
         WHERE sr.quote_selection_id = NEW.quote_selection_id
           AND sr.order_item_id = NEW.order_item_id
           AND sr.state = 'active'
           AND (sr.expires_at > now_at OR EXISTS (
               SELECT 1 FROM payment_attempt_reservations ar
               JOIN payment_attempts pa ON pa.id = ar.attempt_id
                WHERE ar.reservation_id = sr.id
                  AND (pa.state = 'verified' OR (
                      pa.state = 'call_started'
                      AND pa.call_started_at < sr.expires_at
                      AND pa.claim_expires_at > now_at
                      AND pa.authorization_deadline_at >= now_at
                  ))
           ));
        IF active_quantity + NEW.quantity > package_item_quantity THEN
            RAISE EXCEPTION 'stock reservation exceeds quoted package item quantity';
        END IF;
        RETURN NEW;
    END IF;

    IF OLD.state <> 'active' THEN
        RAISE EXCEPTION 'stock reservation is terminal';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.order_id IS DISTINCT FROM OLD.order_id
       OR NEW.order_item_id IS DISTINCT FROM OLD.order_item_id
       OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
       OR NEW.quote_id IS DISTINCT FROM OLD.quote_id
       OR NEW.quote_selection_id IS DISTINCT FROM OLD.quote_selection_id
       OR NEW.quote_option_id IS DISTINCT FROM OLD.quote_option_id
       OR NEW.intent_id IS DISTINCT FROM OLD.intent_id
       OR NEW.product_id IS DISTINCT FROM OLD.product_id
       OR NEW.variant_id IS DISTINCT FROM OLD.variant_id
       OR NEW.size_stock_id IS DISTINCT FROM OLD.size_stock_id
       OR NEW.sku IS DISTINCT FROM OLD.sku OR NEW.quantity IS DISTINCT FROM OLD.quantity
       OR NEW.unit_price IS DISTINCT FROM OLD.unit_price
       OR NEW.line_amount IS DISTINCT FROM OLD.line_amount
       OR NEW.currency IS DISTINCT FROM OLD.currency
       OR NEW.ttl_seconds IS DISTINCT FROM OLD.ttl_seconds
       OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
       OR NEW.source_command IS DISTINCT FROM OLD.source_command
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.creation_txid IS DISTINCT FROM OLD.creation_txid
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'stock reservation identity is immutable';
    END IF;
    IF NEW.state NOT IN ('released', 'consumed', 'expired') OR NEW.row_version <> OLD.row_version + 1 THEN
        RAISE EXCEPTION 'stock reservation transition is illegal';
    END IF;
    -- Lock order: reservation transitions already own the reservation row and
    -- only read payment state; payment verification owns its attempt row before
    -- locking linked reservations. Never lock an attempt from this path.
    IF NEW.state IN ('released', 'expired') AND EXISTS (
        SELECT 1 FROM payment_attempt_reservations ar
        JOIN payment_attempts pa ON pa.id = ar.attempt_id
        WHERE ar.reservation_id = OLD.id
          AND pa.state IN ('pending', 'call_started')
    ) THEN
        RAISE EXCEPTION 'reservation set is locked by active payment attempt';
    END IF;
    IF NEW.state IN ('released', 'expired') AND EXISTS (
        SELECT 1 FROM payment_attempt_reservations ar
        JOIN payment_attempts pa ON pa.id = ar.attempt_id
        WHERE ar.reservation_id = OLD.id AND pa.state = 'verified'
    ) THEN
        RAISE EXCEPTION 'stock reservation cannot be released after verified payment';
    END IF;
    IF NEW.terminal_reason IS NULL OR btrim(NEW.terminal_reason) = '' THEN
        RAISE EXCEPTION 'stock reservation terminal reason required';
    END IF;
    IF NEW.state = 'expired' AND now_at < OLD.expires_at THEN
        RAISE EXCEPTION 'stock reservation expiry has not elapsed';
    END IF;
    IF NEW.state = 'consumed' AND NOT EXISTS (
        SELECT 1 FROM payment_attempt_reservations ar
        JOIN payment_attempts pa ON pa.id = ar.attempt_id
        WHERE ar.reservation_id = OLD.id AND pa.state = 'verified'
    ) THEN
        RAISE EXCEPTION 'stock reservation consumption requires verified payment';
    END IF;
    NEW.terminal_at := now_at;
    NEW.updated_at := now_at;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_stock_reservations_validate
BEFORE INSERT OR UPDATE OR DELETE ON stock_reservations
FOR EACH ROW EXECUTE FUNCTION validate_stock_reservation_write();
""",
    r"""
CREATE FUNCTION protect_reserved_inventory() RETURNS trigger AS $$
DECLARE
    active_quantity bigint;
    new_stock integer;
    old_stock integer;
    new_sku text;
    old_sku text;
    new_product_id uuid;
    old_product_id uuid;
    new_variation_id uuid;
    old_variation_id uuid;
    new_size text;
    old_size text;
    new_made_to_order boolean;
    old_made_to_order boolean;
    now_at timestamptz := clock_timestamp();
BEGIN
    IF TG_TABLE_NAME = 'products' THEN
        new_stock := (to_jsonb(NEW)->>'total_stock')::integer;
        old_stock := (to_jsonb(OLD)->>'total_stock')::integer;
        new_sku := to_jsonb(NEW)->>'sku';
        old_sku := to_jsonb(OLD)->>'sku';
        new_made_to_order := (to_jsonb(NEW)->>'made_to_order')::boolean;
        old_made_to_order := (to_jsonb(OLD)->>'made_to_order')::boolean;
        IF (new_sku IS DISTINCT FROM old_sku AND EXISTS (
            SELECT 1 FROM stock_reservations
             WHERE product_id = OLD.id AND variant_id IS NULL AND size_stock_id IS NULL
        )) OR (new_made_to_order IS DISTINCT FROM old_made_to_order AND EXISTS (
            SELECT 1 FROM stock_reservations WHERE product_id = OLD.id
        )) THEN
            RAISE EXCEPTION 'reserved product identity is immutable';
        END IF;
        IF new_stock IS NOT DISTINCT FROM old_stock OR new_made_to_order THEN
            RETURN NEW;
        END IF;
        PERFORM 1 FROM products WHERE id = OLD.id FOR UPDATE;
        SELECT COALESCE(sum(quantity), 0) INTO active_quantity
          FROM stock_reservations sr
         WHERE sr.product_id = OLD.id AND sr.variant_id IS NULL AND sr.size_stock_id IS NULL
           AND sr.state = 'active'
           AND (sr.expires_at > now_at OR EXISTS (
               SELECT 1 FROM payment_attempt_reservations ar
               JOIN payment_attempts pa ON pa.id = ar.attempt_id
                WHERE ar.reservation_id = sr.id
                 AND (pa.state = 'verified' OR (
                     pa.state = 'call_started'
                     AND pa.call_started_at < sr.expires_at
                     AND pa.claim_expires_at > now_at
                     AND pa.authorization_deadline_at >= now_at
                 ))
           ));
        IF new_stock < active_quantity THEN
            RAISE EXCEPTION 'inventory cannot be reduced below active reservations';
        END IF;
    ELSIF TG_TABLE_NAME = 'product_variants' THEN
        new_stock := (to_jsonb(NEW)->>'stock')::integer;
        old_stock := (to_jsonb(OLD)->>'stock')::integer;
        new_sku := to_jsonb(NEW)->>'sku';
        old_sku := to_jsonb(OLD)->>'sku';
        new_product_id := (to_jsonb(NEW)->>'product_id')::uuid;
        old_product_id := (to_jsonb(OLD)->>'product_id')::uuid;
        IF (new_sku IS DISTINCT FROM old_sku OR new_product_id IS DISTINCT FROM old_product_id)
           AND EXISTS (SELECT 1 FROM stock_reservations WHERE variant_id = OLD.id) THEN
            RAISE EXCEPTION 'reserved product identity is immutable';
        END IF;
        IF new_stock IS NOT DISTINCT FROM old_stock THEN
            RETURN NEW;
        END IF;
        PERFORM 1 FROM product_variants WHERE id = OLD.id FOR UPDATE;
        SELECT COALESCE(sum(quantity), 0) INTO active_quantity
          FROM stock_reservations sr
         WHERE sr.product_id = OLD.product_id AND sr.variant_id = OLD.id
           AND sr.state = 'active'
           AND (sr.expires_at > now_at OR EXISTS (
               SELECT 1 FROM payment_attempt_reservations ar
               JOIN payment_attempts pa ON pa.id = ar.attempt_id
                WHERE ar.reservation_id = sr.id
                 AND (pa.state = 'verified' OR (
                     pa.state = 'call_started'
                     AND pa.call_started_at < sr.expires_at
                     AND pa.claim_expires_at > now_at
                     AND pa.authorization_deadline_at >= now_at
                 ))
           ));
        IF new_stock < active_quantity THEN
            RAISE EXCEPTION 'inventory cannot be reduced below active reservations';
        END IF;
    ELSIF TG_TABLE_NAME = 'size_stocks' THEN
        new_stock := (to_jsonb(NEW)->>'stock')::integer;
        old_stock := (to_jsonb(OLD)->>'stock')::integer;
        new_variation_id := (to_jsonb(NEW)->>'variation_id')::uuid;
        old_variation_id := (to_jsonb(OLD)->>'variation_id')::uuid;
        new_size := to_jsonb(NEW)->>'size';
        old_size := to_jsonb(OLD)->>'size';
        IF (new_variation_id IS DISTINCT FROM old_variation_id
            OR new_size IS DISTINCT FROM old_size)
           AND EXISTS (SELECT 1 FROM stock_reservations WHERE size_stock_id = OLD.id) THEN
            RAISE EXCEPTION 'reserved product identity is immutable';
        END IF;
        IF new_stock IS NOT DISTINCT FROM old_stock THEN
            RETURN NEW;
        END IF;
        PERFORM 1 FROM size_stocks WHERE id = OLD.id FOR UPDATE;
        SELECT COALESCE(sum(quantity), 0) INTO active_quantity
          FROM stock_reservations sr
         WHERE sr.size_stock_id = OLD.id AND sr.state = 'active'
           AND (sr.expires_at > now_at OR EXISTS (
               SELECT 1 FROM payment_attempt_reservations ar
               JOIN payment_attempts pa ON pa.id = ar.attempt_id
                WHERE ar.reservation_id = sr.id
                 AND (pa.state = 'verified' OR (
                     pa.state = 'call_started'
                     AND pa.call_started_at < sr.expires_at
                     AND pa.claim_expires_at > now_at
                     AND pa.authorization_deadline_at >= now_at
                 ))
           ));
        IF new_stock < active_quantity THEN
            RAISE EXCEPTION 'inventory cannot be reduced below active reservations';
        END IF;
    ELSIF TG_TABLE_NAME = 'variations' THEN
        new_product_id := (to_jsonb(NEW)->>'product_id')::uuid;
        old_product_id := (to_jsonb(OLD)->>'product_id')::uuid;
        IF new_product_id IS DISTINCT FROM old_product_id AND EXISTS (
            SELECT 1 FROM size_stocks ss
            JOIN stock_reservations sr ON sr.size_stock_id = ss.id
            WHERE ss.variation_id = OLD.id
        ) THEN
            RAISE EXCEPTION 'reserved product identity is immutable';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_products_reserved_inventory
BEFORE UPDATE ON products FOR EACH ROW EXECUTE FUNCTION protect_reserved_inventory();
CREATE TRIGGER trg_product_variants_reserved_inventory
BEFORE UPDATE ON product_variants FOR EACH ROW EXECUTE FUNCTION protect_reserved_inventory();
CREATE TRIGGER trg_size_stocks_reserved_inventory
BEFORE UPDATE ON size_stocks FOR EACH ROW EXECUTE FUNCTION protect_reserved_inventory();
CREATE TRIGGER trg_variations_reserved_inventory
BEFORE UPDATE ON variations FOR EACH ROW EXECUTE FUNCTION protect_reserved_inventory();

CREATE FUNCTION protect_reserved_order_item() RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM stock_reservations WHERE order_item_id = OLD.id)
       AND (NEW.order_id IS DISTINCT FROM OLD.order_id
            OR NEW.product_id IS DISTINCT FROM OLD.product_id
            OR NEW.variant_id IS DISTINCT FROM OLD.variant_id
            OR NEW.variant_details IS DISTINCT FROM OLD.variant_details
            OR NEW.quantity IS DISTINCT FROM OLD.quantity
            OR NEW.unit_price IS DISTINCT FROM OLD.unit_price
            OR NEW.currency IS DISTINCT FROM OLD.currency) THEN
        RAISE EXCEPTION 'reserved order item truth is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_order_items_reserved_truth
BEFORE UPDATE ON order_items FOR EACH ROW EXECUTE FUNCTION protect_reserved_order_item();

CREATE FUNCTION protect_reserved_order() RETURNS trigger AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM stock_reservations WHERE order_id = OLD.id)
       AND (NEW.customer_id IS DISTINCT FROM OLD.customer_id
            OR NEW.currency IS DISTINCT FROM OLD.currency
            OR NEW.total_amount IS DISTINCT FROM OLD.total_amount) THEN
        RAISE EXCEPTION 'reserved order payment truth is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_orders_reserved_payment_truth
BEFORE UPDATE ON orders FOR EACH ROW EXECUTE FUNCTION protect_reserved_order();
""",
    r"""
CREATE FUNCTION validate_payment_attempt_write() RETURNS trigger AS $$
DECLARE
    now_at timestamptz := statement_timestamp();
    selection_quote uuid;
    selection_option uuid;
    selection_intent uuid;
    selection_customer uuid;
    quote_order uuid;
    quote_expires timestamptz;
    order_amount numeric;
    order_currency text;
    earliest_reservation_expiry timestamptz;
    predecessor payment_attempts%%ROWTYPE;
    evidence_attempt uuid;
    presented_lease_token text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'payment attempt is immutable audit';
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'pending' OR NEW.lease_token IS NOT NULL OR NEW.call_started_at IS NOT NULL
           OR NEW.claim_expires_at IS NOT NULL OR NEW.terminal_evidence_id IS NOT NULL
           OR NEW.terminal_at IS NOT NULL THEN
            RAISE EXCEPTION 'payment attempt must start pending';
        END IF;
        -- Cross-aggregate lock order is always order then quote. Quote creation
        -- already locks its order before a predecessor quote.
        SELECT total_amount, currency INTO order_amount, order_currency
          FROM orders WHERE id = NEW.order_id FOR UPDATE;
        IF NOT FOUND OR NEW.amount <> order_amount OR NEW.currency <> order_currency THEN
            RAISE EXCEPTION 'payment amount is server-owned';
        END IF;
        SELECT s.quote_id, s.option_id, s.intent_id, s.customer_id,
               q.order_id, q.expires_at
          INTO selection_quote, selection_option, selection_intent, selection_customer,
               quote_order, quote_expires
          FROM customer_shipping_quote_selections s
          JOIN customer_shipping_quotes q ON q.id = s.quote_id
         WHERE s.id = NEW.quote_selection_id FOR UPDATE OF q;
        IF NOT FOUND OR selection_quote <> NEW.quote_id OR selection_option <> NEW.quote_option_id
           OR selection_intent <> NEW.intent_id OR selection_customer <> NEW.customer_id
           OR quote_order <> NEW.order_id OR quote_expires <= now_at
           OR EXISTS (SELECT 1 FROM customer_shipping_quotes successor
                       WHERE successor.supersedes_quote_id = NEW.quote_id) THEN
            RAISE EXCEPTION 'payment attempt subject binding is invalid';
        END IF;
        SELECT min(expires_at) INTO earliest_reservation_expiry
          FROM stock_reservations
         WHERE order_id = NEW.order_id
           AND state = 'active' AND expires_at > now_at;
        IF earliest_reservation_expiry IS NULL THEN
            RAISE EXCEPTION 'payment attempt requires active reservations';
        END IF;
        IF EXISTS (
            SELECT 1 FROM payment_attempts active_attempt
             WHERE active_attempt.order_id = NEW.order_id
               AND active_attempt.state IN ('pending', 'call_started')
        ) THEN
            RAISE EXCEPTION 'payment attempt already active for order';
        END IF;
        SELECT * INTO predecessor FROM payment_attempts prior
         WHERE prior.order_id = NEW.order_id
         ORDER BY prior.created_at DESC, prior.id DESC
         LIMIT 1 FOR UPDATE;
        IF FOUND THEN
            IF NEW.supersedes_attempt_id IS NULL
               OR NEW.supersedes_attempt_id IS DISTINCT FROM predecessor.id
               OR predecessor.order_id <> NEW.order_id
               OR predecessor.customer_id <> NEW.customer_id
               OR predecessor.state NOT IN ('failed','expired','abandoned_unknown') THEN
                RAISE EXCEPTION 'payment retry must supersede current terminal leaf';
            END IF;
        ELSIF NEW.supersedes_attempt_id IS NOT NULL THEN
            RAISE EXCEPTION 'payment attempt predecessor is invalid';
        END IF;
        NEW.created_at := now_at;
        NEW.updated_at := now_at;
        NEW.expires_at := LEAST(
            now_at + NEW.payment_window_seconds * interval '1 second',
            quote_expires,
            earliest_reservation_expiry
        );
        NEW.authorization_deadline_at := NEW.expires_at
            + NEW.authorization_grace_seconds * interval '1 second';
        NEW.row_version := 1;
        NEW.creation_txid := txid_current();
        RETURN NEW;
    END IF;

    IF EXISTS (SELECT 1 FROM payment_attempts successor
               WHERE successor.supersedes_attempt_id = OLD.id) THEN
        RAISE EXCEPTION 'superseded payment attempt cannot complete';
    END IF;
    IF OLD.state NOT IN ('pending', 'call_started') THEN
        RAISE EXCEPTION 'payment attempt is terminal';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.order_id IS DISTINCT FROM OLD.order_id
       OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
       OR NEW.quote_id IS DISTINCT FROM OLD.quote_id
       OR NEW.quote_selection_id IS DISTINCT FROM OLD.quote_selection_id
       OR NEW.quote_option_id IS DISTINCT FROM OLD.quote_option_id
       OR NEW.intent_id IS DISTINCT FROM OLD.intent_id OR NEW.amount IS DISTINCT FROM OLD.amount
       OR NEW.currency IS DISTINCT FROM OLD.currency
       OR NEW.payment_window_seconds IS DISTINCT FROM OLD.payment_window_seconds
       OR NEW.authorization_grace_seconds IS DISTINCT FROM OLD.authorization_grace_seconds
       OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
       OR NEW.authorization_deadline_at IS DISTINCT FROM OLD.authorization_deadline_at
       OR NEW.claim_ttl_seconds IS DISTINCT FROM OLD.claim_ttl_seconds
       OR NEW.supersedes_attempt_id IS DISTINCT FROM OLD.supersedes_attempt_id
       OR NEW.source_command IS DISTINCT FROM OLD.source_command
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.creation_txid IS DISTINCT FROM OLD.creation_txid
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'payment attempt identity is immutable';
    END IF;
    IF NEW.row_version <> OLD.row_version + 1 THEN
        RAISE EXCEPTION 'payment attempt transition is illegal';
    END IF;
    IF (OLD.state = 'pending' AND NEW.call_started_at IS NOT NULL)
       OR (OLD.state = 'call_started'
           AND NEW.call_started_at IS DISTINCT FROM OLD.call_started_at) THEN
        RAISE EXCEPTION 'payment attempt call start audit is immutable';
    END IF;

    IF OLD.state = 'pending' AND NEW.state = 'call_started' THEN
        IF NEW.lease_token IS NULL THEN
            RAISE EXCEPTION 'payment attempt lease token required';
        END IF;
        -- PostgreSQL owns the target row lock before this BEFORE UPDATE trigger
        -- runs. Re-sample wall-clock time after any wait on that row.
        now_at := clock_timestamp();
        IF now_at >= OLD.expires_at THEN
            RAISE EXCEPTION 'payment attempt window elapsed';
        END IF;
        NEW.call_started_at := now_at;
        NEW.claim_expires_at := now_at + NEW.claim_ttl_seconds * interval '1 second';
        NEW.updated_at := now_at;
        RETURN NEW;
    END IF;

    IF OLD.state = 'pending' AND NEW.state = 'expired' THEN
        IF now_at < OLD.expires_at THEN
            RAISE EXCEPTION 'payment attempt expiry has not elapsed';
        END IF;
        NEW.lease_token := NULL;
        NEW.call_started_at := NULL;
        NEW.claim_expires_at := NULL;
        NEW.terminal_evidence_id := NULL;
        NEW.terminal_at := now_at;
        NEW.updated_at := now_at;
        RETURN NEW;
    END IF;

    IF NEW.state IN ('failed', 'verified', 'abandoned_unknown') THEN
        IF NEW.terminal_evidence_id IS NULL THEN
            RAISE EXCEPTION 'payment attempt terminal evidence required';
        END IF;
        IF OLD.state = 'call_started' THEN
            presented_lease_token := current_setting('shopsoma.payment_lease_token', true);
            IF presented_lease_token IS NULL
               OR presented_lease_token IS DISTINCT FROM OLD.lease_token::text THEN
                RAISE EXCEPTION 'payment lease token does not own claim';
            END IF;
            now_at := clock_timestamp();
            IF NEW.state IN ('failed', 'verified')
               AND (OLD.claim_expires_at IS NULL OR now_at >= OLD.claim_expires_at) THEN
                RAISE EXCEPTION 'payment claim lease expired';
            END IF;
        END IF;
        SELECT attempt_id INTO evidence_attempt FROM payment_attempt_evidence
         WHERE id = NEW.terminal_evidence_id;
        IF NOT FOUND OR evidence_attempt <> OLD.id THEN
            RAISE EXCEPTION 'payment attempt terminal evidence is invalid';
        END IF;
        IF NEW.state = 'abandoned_unknown' THEN
            IF OLD.state <> 'call_started' OR now_at < OLD.claim_expires_at THEN
                RAISE EXCEPTION 'payment attempt lease has not expired';
            END IF;
        ELSIF NEW.state = 'verified' THEN
            IF OLD.state <> 'call_started' THEN
                RAISE EXCEPTION 'payment attempt transition is illegal';
            END IF;
            IF now_at > OLD.authorization_deadline_at THEN
                RAISE EXCEPTION 'payment attempt authorization deadline elapsed';
            END IF;
            -- Reservation insertion serializes on the authoritative inventory
            -- rows. Acquire the same product -> variation -> detailed-stock
            -- order before the reservation rows so verification cannot become
            -- visible after an expired unit was concurrently reserved again.
            PERFORM p.id FROM products p
            JOIN (
                SELECT DISTINCT sr.product_id
                FROM stock_reservations sr
                JOIN payment_attempt_reservations ar ON ar.reservation_id = sr.id
                WHERE ar.attempt_id = OLD.id
            ) subjects ON subjects.product_id = p.id
            ORDER BY p.id FOR UPDATE OF p;
            PERFORM v.id FROM variations v
            JOIN (
                SELECT DISTINCT ss.variation_id
                FROM stock_reservations sr
                JOIN payment_attempt_reservations ar ON ar.reservation_id = sr.id
                JOIN size_stocks ss ON ss.id = sr.size_stock_id
                WHERE ar.attempt_id = OLD.id
            ) subjects ON subjects.variation_id = v.id
            ORDER BY v.id FOR UPDATE OF v;
            PERFORM pv.id FROM product_variants pv
            JOIN (
                SELECT DISTINCT sr.variant_id
                FROM stock_reservations sr
                JOIN payment_attempt_reservations ar ON ar.reservation_id = sr.id
                WHERE ar.attempt_id = OLD.id AND sr.variant_id IS NOT NULL
            ) subjects ON subjects.variant_id = pv.id
            ORDER BY pv.id FOR UPDATE OF pv;
            PERFORM ss.id FROM size_stocks ss
            JOIN (
                SELECT DISTINCT sr.size_stock_id
                FROM stock_reservations sr
                JOIN payment_attempt_reservations ar ON ar.reservation_id = sr.id
                WHERE ar.attempt_id = OLD.id AND sr.size_stock_id IS NOT NULL
            ) subjects ON subjects.size_stock_id = ss.id
            ORDER BY ss.id FOR UPDATE OF ss;
            -- Shared serialization point with reservation release/expiry. Lock
            -- the exact linked set in stable order before reading its state.
            PERFORM 1 FROM stock_reservations sr
            JOIN payment_attempt_reservations ar ON ar.reservation_id = sr.id
            WHERE ar.attempt_id = OLD.id
            ORDER BY sr.id
            FOR UPDATE OF sr;
            -- A lock wait can cross reservation, claim, or authorization boundaries;
            -- re-sample wall-clock truth only after the exact set is locked.
            now_at := clock_timestamp();
            IF OLD.claim_expires_at IS NULL OR now_at >= OLD.claim_expires_at THEN
                RAISE EXCEPTION 'payment claim lease expired';
            END IF;
            IF now_at > OLD.authorization_deadline_at THEN
                RAISE EXCEPTION 'payment attempt authorization deadline elapsed';
            END IF;
            IF EXISTS (
                SELECT 1 FROM payment_attempt_reservations ar
                JOIN stock_reservations sr ON sr.id = ar.reservation_id
                WHERE ar.attempt_id = OLD.id
                  AND (sr.state <> 'active'
                       OR (sr.expires_at <= now_at AND OLD.call_started_at >= sr.expires_at))
            ) OR NOT EXISTS (
                SELECT 1 FROM payment_attempt_reservations WHERE attempt_id = OLD.id
            ) OR EXISTS (
                SELECT 1 FROM stock_reservations sr
                WHERE sr.order_id = OLD.order_id
                  AND sr.state = 'active' AND sr.expires_at > now_at
                  AND NOT EXISTS (
                      SELECT 1 FROM payment_attempt_reservations ar
                      WHERE ar.attempt_id = OLD.id AND ar.reservation_id = sr.id
                  )
            ) THEN
                RAISE EXCEPTION 'payment verification requires live reservations';
            END IF;
        ELSIF OLD.state NOT IN ('pending', 'call_started') THEN
            RAISE EXCEPTION 'payment attempt transition is illegal';
        END IF;
        NEW.lease_token := NULL;
        NEW.claim_expires_at := NULL;
        NEW.terminal_at := now_at;
        NEW.updated_at := now_at;
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'payment attempt transition is illegal';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_payment_attempts_validate
BEFORE INSERT OR UPDATE OR DELETE ON payment_attempts
FOR EACH ROW EXECUTE FUNCTION validate_payment_attempt_write();
""",
    r"""
CREATE FUNCTION validate_payment_attempt_membership_write() RETURNS trigger AS $$
DECLARE
    attempt_state text;
    attempt_txid bigint;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'payment attempt reservation membership is append-only';
    END IF;
    SELECT state, creation_txid INTO attempt_state, attempt_txid
      FROM payment_attempts WHERE id = NEW.attempt_id FOR UPDATE;
    IF NOT FOUND OR attempt_state <> 'pending' OR attempt_txid <> txid_current() THEN
        RAISE EXCEPTION 'payment attempt reservation membership creation is closed';
    END IF;
    PERFORM 1 FROM stock_reservations
     WHERE id = NEW.reservation_id AND state = 'active'
       AND expires_at > statement_timestamp() FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'payment attempt reservation is not live';
    END IF;
    NEW.creation_txid := txid_current();
    NEW.created_at := statement_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_payment_attempt_reservations_validate
BEFORE INSERT OR UPDATE OR DELETE ON payment_attempt_reservations
FOR EACH ROW EXECUTE FUNCTION validate_payment_attempt_membership_write();

CREATE FUNCTION validate_payment_attempt_exact_reservations() RETURNS trigger AS $$
DECLARE
    target_attempt uuid;
    attempt_order uuid;
    missing_count bigint;
    extra_count bigint;
    composition_mismatch_count bigint;
BEGIN
    IF TG_TABLE_NAME = 'payment_attempts' THEN
        target_attempt := NEW.id;
    ELSE
        target_attempt := NEW.attempt_id;
    END IF;
    SELECT pa.order_id INTO attempt_order
      FROM payment_attempts pa
     WHERE pa.id = target_attempt;
    SELECT count(*) INTO missing_count
      FROM stock_reservations sr
     WHERE sr.order_id = attempt_order
       AND sr.state = 'active' AND sr.expires_at > statement_timestamp()
       AND NOT EXISTS (
           SELECT 1 FROM payment_attempt_reservations ar
            WHERE ar.attempt_id = target_attempt AND ar.reservation_id = sr.id
       );
    SELECT count(*) INTO extra_count
      FROM payment_attempt_reservations ar
      JOIN stock_reservations sr ON sr.id = ar.reservation_id
     WHERE ar.attempt_id = target_attempt
       AND (sr.order_id <> attempt_order OR sr.state <> 'active'
            OR sr.expires_at <= statement_timestamp());
    IF missing_count <> 0 OR extra_count <> 0 OR NOT EXISTS (
        SELECT 1 FROM payment_attempt_reservations WHERE attempt_id = target_attempt
    ) THEN
        RAISE EXCEPTION 'payment attempt must cover the exact active reservation set';
    END IF;
    SELECT count(*) INTO composition_mismatch_count
      FROM (
          SELECT q.package_id, q.package_version, sr.order_item_id,
                 sum(sr.quantity) AS reserved_quantity
            FROM payment_attempt_reservations ar
            JOIN stock_reservations sr ON sr.id = ar.reservation_id
            JOIN customer_shipping_quotes q ON q.id = sr.quote_id
           WHERE ar.attempt_id = target_attempt
           GROUP BY q.package_id, q.package_version, sr.order_item_id
      ) reserved
      FULL OUTER JOIN (
          SELECT hpi.package_id, hpi.package_version, hpi.order_item_id,
                 sum(hpi.quantity) AS package_quantity
            FROM hub_package_items hpi
            JOIN (
                SELECT DISTINCT q.package_id, q.package_version
                  FROM payment_attempt_reservations ar
                  JOIN stock_reservations sr ON sr.id = ar.reservation_id
                  JOIN customer_shipping_quotes q ON q.id = sr.quote_id
                 WHERE ar.attempt_id = target_attempt
            ) selected_packages
              ON selected_packages.package_id = hpi.package_id
             AND selected_packages.package_version = hpi.package_version
           GROUP BY hpi.package_id, hpi.package_version, hpi.order_item_id
      ) composed
        USING (package_id, package_version, order_item_id)
     WHERE reserved.reserved_quantity IS DISTINCT FROM composed.package_quantity;
    IF composition_mismatch_count <> 0 THEN
        RAISE EXCEPTION 'payment attempt must cover exact quoted package composition';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER trg_payment_attempts_exact_reservations
AFTER INSERT ON payment_attempts DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_payment_attempt_exact_reservations();
CREATE CONSTRAINT TRIGGER trg_payment_attempt_reservations_exact_set
AFTER INSERT ON payment_attempt_reservations DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_payment_attempt_exact_reservations();
""",
    r"""
CREATE FUNCTION validate_payment_attempt_evidence_write() RETURNS trigger AS $$
DECLARE
    attempt_state text;
    attempt_created_at timestamptz;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION 'payment attempt evidence is append-only';
    END IF;
    SELECT state, created_at INTO attempt_state, attempt_created_at
      FROM payment_attempts WHERE id = NEW.attempt_id FOR UPDATE;
    IF NOT FOUND OR attempt_state NOT IN ('pending', 'call_started') THEN
        RAISE EXCEPTION 'payment attempt evidence creation is closed';
    END IF;
    IF NEW.observed_at > clock_timestamp() THEN
        RAISE EXCEPTION 'payment attempt evidence chronology is invalid';
    END IF;
    IF NEW.observed_at < attempt_created_at THEN
        RAISE EXCEPTION 'payment evidence predates attempt';
    END IF;
    NEW.created_at := statement_timestamp();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_payment_attempt_evidence_validate
BEFORE INSERT OR UPDATE OR DELETE ON payment_attempt_evidence
FOR EACH ROW EXECUTE FUNCTION validate_payment_attempt_evidence_write();
""",
)

STOCK_PAYMENT_DROP_DDLS: tuple[str, ...] = (
    r"""
DROP TRIGGER IF EXISTS trg_orders_reserved_payment_truth ON orders;
DROP TRIGGER IF EXISTS trg_order_items_reserved_truth ON order_items;
DROP TRIGGER IF EXISTS trg_variations_reserved_inventory ON variations;
DROP TRIGGER IF EXISTS trg_size_stocks_reserved_inventory ON size_stocks;
DROP TRIGGER IF EXISTS trg_product_variants_reserved_inventory ON product_variants;
DROP TRIGGER IF EXISTS trg_products_reserved_inventory ON products;
DROP FUNCTION IF EXISTS protect_reserved_order();
DROP FUNCTION IF EXISTS protect_reserved_order_item();
DROP FUNCTION IF EXISTS protect_reserved_inventory();
DROP FUNCTION IF EXISTS validate_payment_attempt_evidence_write();
DROP FUNCTION IF EXISTS validate_payment_attempt_exact_reservations();
DROP FUNCTION IF EXISTS validate_payment_attempt_membership_write();
DROP FUNCTION IF EXISTS validate_payment_attempt_write();
DROP FUNCTION IF EXISTS validate_stock_reservation_write();
""",
)


def _iter_stock_payment_ddl_statements(blocks: tuple[str, ...]):
    """Yield one command at a time for asyncpg's prepared-statement contract."""

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


for _ddl in _iter_stock_payment_ddl_statements(STOCK_PAYMENT_TRIGGER_DDLS):
    event.listen(PaymentAttemptEvidence.__table__, "after_create", DDL(_ddl))
for _ddl in _iter_stock_payment_ddl_statements(STOCK_PAYMENT_DROP_DDLS):
    event.listen(StockReservation.__table__, "after_drop", DDL(_ddl))


__all__ = [
    "PaymentAttempt",
    "PaymentAttemptEvidence",
    "PaymentAttemptReservation",
    "STOCK_PAYMENT_DROP_DDLS",
    "STOCK_PAYMENT_TRIGGER_DDLS",
    "StockReservation",
]
