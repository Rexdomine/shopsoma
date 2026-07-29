"""Customer-owned immutable domestic shipping quotes and normalized options.

This Phase 2A-4A aggregate snapshots customer-facing quote truth.  It is
separate from the Phase 2B provider-call evidence aggregate and may reference
that evidence only through restrictive provenance foreign keys.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    BigInteger,
    Column,
    DDL,
    Date,
    DateTime,
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.base import Base

_UUID = UUID(as_uuid=True)
_NOW = func.statement_timestamp()


def _id_column():
    return Column(_UUID, primary_key=True, default=uuid.uuid4)


class CustomerShippingQuote(Base):
    """Immutable customer quote bound to one exact outbound shipment intent."""

    __tablename__ = "customer_shipping_quotes"

    id = _id_column()
    order_id = Column(
        _UUID, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    intent_id = Column(
        _UUID,
        ForeignKey("outbound_shipment_intents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    package_id = Column(_UUID, nullable=False)
    package_version = Column(Integer, nullable=False)
    seal_id = Column(_UUID, nullable=False)
    origin_hub_id = Column(
        _UUID, ForeignKey("fulfillment_hubs.id", ondelete="RESTRICT"), nullable=False
    )
    destination_snapshot_hash = Column(String(64), nullable=False)
    source_rate_response_id = Column(
        _UUID,
        ForeignKey("domestic_rate_responses.id", ondelete="RESTRICT"),
    )
    supersedes_quote_id = Column(
        _UUID, ForeignKey("customer_shipping_quotes.id", ondelete="RESTRICT")
    )
    currency = Column(String(3), nullable=False)
    ttl_seconds = Column(Integer, nullable=False, server_default="1800")
    expires_at = Column(
        DateTime(timezone=True), nullable=False, server_default=FetchedValue()
    )
    initiating_actor_type = Column(String(30), nullable=False)
    initiating_actor_id = Column(String(200), nullable=False)
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    schema_version = Column(String(50), nullable=False)
    row_version = Column(Integer, nullable=False, server_default="1")
    creation_txid = Column(BigInteger, nullable=False, server_default=FetchedValue())
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        ForeignKeyConstraint(
            ["intent_id", "package_id"],
            ["outbound_shipment_intents.id", "outbound_shipment_intents.package_id"],
            name="fk_customer_shipping_quotes_intent_subject",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["seal_id", "package_id", "package_version"],
            [
                "hub_package_seals.id",
                "hub_package_seals.package_id",
                "hub_package_seals.package_version",
            ],
            name="fk_customer_shipping_quotes_seal_binding",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "package_version > 0 AND row_version = 1 AND creation_txid > 0",
            name="ck_customer_shipping_quotes_versions",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$' "
            "AND destination_snapshot_hash ~ '^[0-9a-f]{64}$' "
            "AND request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_customer_shipping_quotes_canonical",
        ),
        CheckConstraint(
            "ttl_seconds BETWEEN 1 AND 86400",
            name="ck_customer_shipping_quotes_ttl",
        ),
        CheckConstraint(
            "initiating_actor_type ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,29}$' "
            "AND initiating_actor_id ~ '^[!-~]{1,200}$' "
            "AND source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$' "
            "AND idempotency_key ~ '^[!-~]{1,200}$' "
            "AND schema_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,49}$'",
            name="ck_customer_shipping_quotes_identifiers",
        ),
        UniqueConstraint(
            "customer_id",
            "idempotency_key",
            name="uq_customer_shipping_quotes_customer_replay",
        ),
        UniqueConstraint(
            "supersedes_quote_id",
            name="uq_customer_shipping_quotes_single_successor",
        ),
        UniqueConstraint("id", "customer_id", name="uq_customer_shipping_quotes_owner"),
        Index("ix_customer_shipping_quotes_order", "order_id", "created_at"),
        Index("ix_customer_shipping_quotes_expiry", "expires_at"),
    )


class CustomerShippingQuoteOption(Base):
    """Immutable normalized customer-facing service and amount snapshot."""

    __tablename__ = "customer_shipping_quote_options"

    id = _id_column()
    quote_id = Column(
        _UUID,
        ForeignKey("customer_shipping_quotes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_rate_offer_id = Column(
        _UUID, ForeignKey("domestic_rate_offers.id", ondelete="RESTRICT")
    )
    option_key = Column(String(100), nullable=False)
    provider = Column(String(30), nullable=False)
    product_code = Column(String(100), nullable=False)
    service_code = Column(String(100), nullable=False)
    service_label = Column(String(200), nullable=False)
    source_amount = Column(Numeric(18, 4), nullable=False)
    adjustment_amount = Column(Numeric(18, 4), nullable=False, server_default="0")
    total_amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False)
    transit_days = Column(Integer)
    delivery_date = Column(Date)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "option_key ~ '^[!-~]{1,100}$' "
            "AND provider ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,29}$' "
            "AND product_code ~ '^[!-~]{1,100}$' "
            "AND service_code ~ '^[!-~]{1,100}$' "
            "AND service_label = btrim(service_label) "
            "AND length(service_label) BETWEEN 1 AND 200",
            name="ck_customer_shipping_quote_options_identifiers",
        ),
        CheckConstraint(
            "source_amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND adjustment_amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND total_amount NOT IN ('NaN'::numeric, 'Infinity'::numeric, '-Infinity'::numeric) "
            "AND source_amount >= 0 AND total_amount > 0 "
            "AND total_amount = source_amount + adjustment_amount",
            name="ck_customer_shipping_quote_options_amounts",
        ),
        CheckConstraint(
            "currency ~ '^[A-Z]{3}$'",
            name="ck_customer_shipping_quote_options_currency",
        ),
        CheckConstraint(
            "(transit_days IS NULL OR transit_days BETWEEN 0 AND 365) "
            "AND (transit_days IS NOT NULL OR delivery_date IS NOT NULL)",
            name="ck_customer_shipping_quote_options_transit",
        ),
        UniqueConstraint(
            "quote_id", "option_key", name="uq_customer_shipping_quote_options_key"
        ),
        UniqueConstraint(
            "id", "quote_id", name="uq_customer_shipping_quote_options_identity"
        ),
        UniqueConstraint(
            "quote_id",
            "source_rate_offer_id",
            name="uq_customer_shipping_quote_options_source_offer",
        ),
        Index("ix_customer_shipping_quote_options_quote", "quote_id"),
    )


class CustomerShippingQuoteSelection(Base):
    """Optional append-only identity of the customer-selected quote option."""

    __tablename__ = "customer_shipping_quote_selections"

    id = _id_column()
    quote_id = Column(_UUID, nullable=False)
    option_id = Column(_UUID, nullable=False)
    customer_id = Column(_UUID, nullable=False)
    selected_by_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    selected_at = Column(
        DateTime(timezone=True), nullable=False, server_default=FetchedValue()
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        ForeignKeyConstraint(
            ["quote_id", "customer_id"],
            ["customer_shipping_quotes.id", "customer_shipping_quotes.customer_id"],
            name="fk_customer_shipping_quote_selections_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["option_id", "quote_id"],
            [
                "customer_shipping_quote_options.id",
                "customer_shipping_quote_options.quote_id",
            ],
            name="fk_customer_shipping_quote_selections_option",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "selected_by_id = customer_id "
            "AND source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$' "
            "AND idempotency_key ~ '^[!-~]{1,200}$'",
            name="ck_customer_shipping_quote_selections_identifiers",
        ),
        UniqueConstraint(
            "quote_id", name="uq_customer_shipping_quote_selections_quote"
        ),
        UniqueConstraint(
            "customer_id",
            "idempotency_key",
            name="uq_customer_shipping_quote_selections_customer_replay",
        ),
        Index("ix_customer_shipping_quote_selections_option", "option_id"),
    )


CUSTOMER_SHIPPING_QUOTE_TRIGGER_DDLS = (
    """
CREATE FUNCTION validate_customer_shipping_quote_write() RETURNS trigger AS $$
DECLARE
    intent outbound_shipment_intents%%ROWTYPE;
    order_customer uuid;
    package_state text;
    seal_retired_at timestamptz;
    response domestic_rate_responses%%ROWTYPE;
    attempt domestic_rate_attempts%%ROWTYPE;
    predecessor customer_shipping_quotes%%ROWTYPE;
    event_at timestamptz;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='quote records are immutable audit';
    END IF;
    event_at := clock_timestamp();
    NEW.created_at := event_at;
    NEW.expires_at := event_at + NEW.ttl_seconds * interval '1 second';
    NEW.row_version := 1;
    NEW.creation_txid := txid_current();

    SELECT customer_id INTO order_customer FROM orders WHERE id=NEW.order_id FOR UPDATE;
    IF order_customer IS NULL OR order_customer IS DISTINCT FROM NEW.customer_id THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote ownership does not match order';
    END IF;
    IF NEW.initiating_actor_type='customer'
       AND NEW.initiating_actor_id IS DISTINCT FROM NEW.customer_id::text THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='customer actor must match quote owner';
    END IF;
    SELECT retired_at INTO seal_retired_at FROM hub_package_seals
     WHERE id=NEW.seal_id FOR UPDATE;
    SELECT state INTO package_state FROM hub_packages
     WHERE id=NEW.package_id FOR UPDATE;
    SELECT * INTO intent FROM outbound_shipment_intents
     WHERE id=NEW.intent_id FOR UPDATE;
    IF NOT FOUND OR intent.order_id IS DISTINCT FROM NEW.order_id
       OR intent.package_id IS DISTINCT FROM NEW.package_id
       OR intent.package_version IS DISTINCT FROM NEW.package_version
       OR intent.seal_id IS DISTINCT FROM NEW.seal_id
       OR intent.origin_hub_id IS DISTINCT FROM NEW.origin_hub_id
       OR intent.destination_snapshot_hash IS DISTINCT FROM NEW.destination_snapshot_hash THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote subject does not match outbound intent';
    END IF;
    IF EXISTS (SELECT 1 FROM outbound_shipment_intent_invalidations WHERE intent_id=NEW.intent_id) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote cannot use an invalidated outbound intent';
    END IF;
    IF package_state IS DISTINCT FROM 'ready' OR seal_retired_at IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote requires the exact ready sealed package';
    END IF;
    IF EXISTS (
        SELECT 1 FROM custody_events
         WHERE package_id=NEW.package_id AND package_version=NEW.package_version
           AND event_type IN ('released','tendered','provider_accepted')
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote cannot be created after custody handoff';
    END IF;
    IF event_at < intent.created_at THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote chronology precedes outbound intent';
    END IF;

    IF NEW.source_rate_response_id IS NOT NULL THEN
        SELECT * INTO response FROM domestic_rate_responses WHERE id=NEW.source_rate_response_id;
        IF NOT FOUND OR response.result_kind <> 'success'
           OR response.received_at > event_at OR response.expires_at < NEW.expires_at THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='source rate response is not eligible quote evidence';
        END IF;
        SELECT * INTO attempt FROM domestic_rate_attempts WHERE id=response.attempt_id;
        IF NOT FOUND OR attempt.intent_id IS DISTINCT FROM NEW.intent_id
           OR attempt.package_id IS DISTINCT FROM NEW.package_id
           OR attempt.package_version IS DISTINCT FROM NEW.package_version
           OR attempt.seal_id IS DISTINCT FROM NEW.seal_id
           OR attempt.order_id IS DISTINCT FROM NEW.order_id
           OR attempt.destination_snapshot_hash IS DISTINCT FROM NEW.destination_snapshot_hash THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='source rate response does not match quote subject';
        END IF;
    END IF;

    IF NEW.supersedes_quote_id IS NOT NULL THEN
        SELECT * INTO predecessor FROM customer_shipping_quotes
         WHERE id=NEW.supersedes_quote_id FOR UPDATE;
        IF NOT FOUND OR predecessor.customer_id IS DISTINCT FROM NEW.customer_id
           OR predecessor.order_id IS DISTINCT FROM NEW.order_id
           OR predecessor.intent_id IS DISTINCT FROM NEW.intent_id
           OR predecessor.package_id IS DISTINCT FROM NEW.package_id
           OR predecessor.package_version IS DISTINCT FROM NEW.package_version
           OR predecessor.seal_id IS DISTINCT FROM NEW.seal_id
           OR predecessor.origin_hub_id IS DISTINCT FROM NEW.origin_hub_id
           OR predecessor.destination_snapshot_hash IS DISTINCT FROM NEW.destination_snapshot_hash
           OR predecessor.currency IS DISTINCT FROM NEW.currency THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote successor subject must match predecessor';
        END IF;
        IF EXISTS (SELECT 1 FROM customer_shipping_quote_selections WHERE quote_id=predecessor.id) THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='selected quote cannot be superseded';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    """
CREATE TRIGGER customer_shipping_quotes_validate
BEFORE INSERT OR UPDATE OR DELETE ON customer_shipping_quotes
FOR EACH ROW EXECUTE FUNCTION validate_customer_shipping_quote_write();
""",
    """
CREATE FUNCTION validate_customer_shipping_quote_option_write() RETURNS trigger AS $$
DECLARE
    quote customer_shipping_quotes%%ROWTYPE;
    offer domestic_rate_offers%%ROWTYPE;
    offer_response_id uuid;
    source_provider text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='quote option records are immutable audit';
    END IF;
    NEW.created_at := clock_timestamp();
    SELECT * INTO quote FROM customer_shipping_quotes WHERE id=NEW.quote_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='quote option references missing quote';
    END IF;
    IF quote.creation_txid IS DISTINCT FROM txid_current()
       OR quote.expires_at <= clock_timestamp()
       OR EXISTS (SELECT 1 FROM customer_shipping_quotes WHERE supersedes_quote_id=quote.id)
       OR EXISTS (SELECT 1 FROM customer_shipping_quote_selections WHERE quote_id=quote.id) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote no longer accepts options';
    END IF;
    IF NEW.currency IS DISTINCT FROM quote.currency THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote option must match quote currency';
    END IF;
    IF (quote.source_rate_response_id IS NULL) <> (NEW.source_rate_offer_id IS NULL) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote option provenance must match quote provenance';
    END IF;
    IF NEW.source_rate_offer_id IS NOT NULL THEN
        SELECT * INTO offer FROM domestic_rate_offers WHERE id=NEW.source_rate_offer_id;
        SELECT response_id INTO offer_response_id FROM domestic_rate_offers WHERE id=NEW.source_rate_offer_id;
        SELECT a.provider INTO source_provider
        FROM domestic_rate_responses r
        JOIN domestic_rate_attempts a ON a.id=r.attempt_id
        WHERE r.id=quote.source_rate_response_id;
        IF NOT FOUND OR offer_response_id IS DISTINCT FROM quote.source_rate_response_id
           OR source_provider IS DISTINCT FROM NEW.provider
           OR offer.provider_product_code IS DISTINCT FROM NEW.product_code
           OR offer.provider_service_code IS DISTINCT FROM NEW.service_code
           OR offer.service_label IS DISTINCT FROM NEW.service_label
           OR offer.total_amount IS DISTINCT FROM NEW.source_amount
           OR offer.currency IS DISTINCT FROM NEW.currency
           OR offer.transit_days IS DISTINCT FROM NEW.transit_days
           OR offer.delivery_date IS DISTINCT FROM NEW.delivery_date THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='source rate offer does not match quote subject';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    """
CREATE TRIGGER customer_shipping_quote_options_validate
BEFORE INSERT OR UPDATE OR DELETE ON customer_shipping_quote_options
FOR EACH ROW EXECUTE FUNCTION validate_customer_shipping_quote_option_write();
""",
    """
CREATE FUNCTION validate_customer_shipping_quote_selection_write() RETURNS trigger AS $$
DECLARE
    quote customer_shipping_quotes%%ROWTYPE;
    option_quote_id uuid;
    event_at timestamptz;
    package_state text;
    seal_retired_at timestamptz;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='quote selection records are immutable audit';
    END IF;
    SELECT * INTO quote FROM customer_shipping_quotes WHERE id=NEW.quote_id;
    IF NOT FOUND OR quote.customer_id IS DISTINCT FROM NEW.customer_id
       OR NEW.selected_by_id IS DISTINCT FROM NEW.customer_id THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote selection owner does not match quote';
    END IF;
    PERFORM 1 FROM hub_package_seals WHERE id=quote.seal_id FOR UPDATE;
    SELECT state INTO package_state FROM hub_packages
     WHERE id=quote.package_id FOR UPDATE;
    PERFORM 1 FROM outbound_shipment_intents
     WHERE id=quote.intent_id FOR UPDATE;
    SELECT * INTO quote FROM customer_shipping_quotes WHERE id=NEW.quote_id FOR UPDATE;
    event_at := clock_timestamp();
    NEW.selected_at := event_at;
    NEW.created_at := event_at;
    SELECT retired_at INTO seal_retired_at FROM hub_package_seals WHERE id=quote.seal_id;
    IF EXISTS (
        SELECT 1 FROM outbound_shipment_intent_invalidations WHERE intent_id=quote.intent_id
    ) OR package_state IS DISTINCT FROM 'ready' OR seal_retired_at IS NOT NULL
       OR EXISTS (
           SELECT 1 FROM custody_events
            WHERE package_id=quote.package_id AND package_version=quote.package_version
              AND event_type IN ('released','tendered','provider_accepted')
       ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote subject is no longer eligible for selection';
    END IF;
    SELECT quote_id INTO option_quote_id FROM customer_shipping_quote_options
     WHERE id=NEW.option_id FOR KEY SHARE;
    IF option_quote_id IS DISTINCT FROM NEW.quote_id THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote selection must identify an option from the quote';
    END IF;
    IF event_at >= quote.expires_at OR EXISTS (
        SELECT 1 FROM customer_shipping_quotes successor WHERE successor.supersedes_quote_id=quote.id
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='quote is expired or superseded';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    """
CREATE TRIGGER customer_shipping_quote_selections_validate
BEFORE INSERT OR UPDATE OR DELETE ON customer_shipping_quote_selections
FOR EACH ROW EXECUTE FUNCTION validate_customer_shipping_quote_selection_write();
""",
    """
CREATE FUNCTION assert_customer_shipping_quote_has_options() RETURNS trigger AS $$
DECLARE target_quote_id uuid;
BEGIN
    IF TG_TABLE_NAME='customer_shipping_quotes' THEN
        target_quote_id := NEW.id;
    ELSE
        target_quote_id := NEW.quote_id;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM customer_shipping_quote_options WHERE quote_id=target_quote_id) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='customer quote requires at least one option';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
""",
    """
CREATE CONSTRAINT TRIGGER customer_shipping_quotes_require_options
AFTER INSERT ON customer_shipping_quotes DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION assert_customer_shipping_quote_has_options();
""",
    """
CREATE CONSTRAINT TRIGGER customer_shipping_quote_options_require_quote_shape
AFTER INSERT ON customer_shipping_quote_options DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION assert_customer_shipping_quote_has_options();
""",
    """
CREATE FUNCTION protect_customer_shipping_quote_order_owner() RETURNS trigger AS $$
BEGIN
    IF NEW.customer_id IS DISTINCT FROM OLD.customer_id
       AND EXISTS (SELECT 1 FROM customer_shipping_quotes WHERE order_id=OLD.id) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='order ownership is frozen by customer shipping quote';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""",
    """
CREATE TRIGGER orders_protect_customer_shipping_quote_owner
BEFORE UPDATE OF customer_id ON orders
FOR EACH ROW EXECUTE FUNCTION protect_customer_shipping_quote_order_owner();
""",
)

CUSTOMER_SHIPPING_QUOTE_DROP_DDLS = (
    "DROP TRIGGER IF EXISTS orders_protect_customer_shipping_quote_owner ON orders",
    "DROP FUNCTION IF EXISTS protect_customer_shipping_quote_order_owner()",
    "DROP TRIGGER IF EXISTS customer_shipping_quote_options_require_quote_shape ON customer_shipping_quote_options",
    "DROP TRIGGER IF EXISTS customer_shipping_quotes_require_options ON customer_shipping_quotes",
    "DROP FUNCTION IF EXISTS assert_customer_shipping_quote_has_options()",
    "DROP TRIGGER IF EXISTS customer_shipping_quote_selections_validate ON customer_shipping_quote_selections",
    "DROP FUNCTION IF EXISTS validate_customer_shipping_quote_selection_write()",
    "DROP TRIGGER IF EXISTS customer_shipping_quote_options_validate ON customer_shipping_quote_options",
    "DROP FUNCTION IF EXISTS validate_customer_shipping_quote_option_write()",
    "DROP TRIGGER IF EXISTS customer_shipping_quotes_validate ON customer_shipping_quotes",
    "DROP FUNCTION IF EXISTS validate_customer_shipping_quote_write()",
)

for ddl in CUSTOMER_SHIPPING_QUOTE_TRIGGER_DDLS:
    event.listen(Base.metadata, "after_create", DDL(ddl))
for ddl in CUSTOMER_SHIPPING_QUOTE_DROP_DDLS:
    event.listen(Base.metadata, "before_drop", DDL(ddl))


__all__ = [
    "CUSTOMER_SHIPPING_QUOTE_DROP_DDLS",
    "CUSTOMER_SHIPPING_QUOTE_TRIGGER_DDLS",
    "CustomerShippingQuote",
    "CustomerShippingQuoteOption",
    "CustomerShippingQuoteSelection",
]
