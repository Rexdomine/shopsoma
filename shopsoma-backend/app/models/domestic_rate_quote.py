"""Immutable normalized evidence for sandbox domestic rate quotes.

Only authoritative binding facts and normalized provider results are retained.
Provider payloads, account values, credentials, seal values, and destination PII
must never be represented by this aggregate.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DDL,
    Date,
    DateTime,
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
_ATTEMPT_NOW = func.statement_timestamp()


def _id_column():
    return Column(_UUID, primary_key=True, default=uuid.uuid4)


class OutboundIntentRateGuard(Base):
    """Private mutable serialization row; append-only invalidation remains audit truth."""

    __tablename__ = "outbound_intent_rate_guards"

    intent_id = Column(
        _UUID,
        ForeignKey("outbound_shipment_intents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_invalidated = Column(Boolean, nullable=False, server_default="false")
    active_attempt_id = Column(_UUID)


class DomesticRateAttempt(Base):
    """A provider-call claim bound to one exact authoritative shipment subject."""

    __tablename__ = "domestic_rate_attempts"

    id = _id_column()
    intent_id = Column(
        _UUID,
        ForeignKey("outbound_shipment_intents.id", ondelete="RESTRICT"),
        nullable=False,
    )
    order_id = Column(
        _UUID, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    package_id = Column(_UUID, nullable=False)
    package_version = Column(Integer, nullable=False)
    seal_id = Column(_UUID, nullable=False)
    origin_hub_id = Column(
        _UUID, ForeignKey("fulfillment_hubs.id", ondelete="RESTRICT"), nullable=False
    )
    hub_version = Column(Integer, nullable=False)
    destination_country_code = Column(String(2), nullable=False)
    destination_snapshot_hash = Column(String(64), nullable=False)
    provider = Column(String(20), nullable=False)
    environment = Column(String(20), nullable=False)
    account_alias = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    request_fingerprint = Column(String(64), nullable=False)
    fingerprint_key_version = Column(String(50), nullable=False)
    planned_ship_date = Column(Date, nullable=False)
    adapter_version = Column(String(50), nullable=False)
    schema_version = Column(String(50), nullable=False)
    canonicalization_version = Column(String(50), nullable=False)
    claimed_at = Column(DateTime(timezone=True), nullable=False)
    call_started_at = Column(DateTime(timezone=True))
    result_recorded_at = Column(DateTime(timezone=True))
    classification = Column(String(20), nullable=False)
    failure_code = Column(String(100))
    completion_txid = Column(BigInteger)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=_ATTEMPT_NOW
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["package_id", "package_version"],
            ["hub_package_versions.package_id", "hub_package_versions.version"],
            name="fk_domestic_rate_attempts_package_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["seal_id", "package_id", "package_version"],
            [
                "hub_package_seals.id",
                "hub_package_seals.package_id",
                "hub_package_seals.package_version",
            ],
            name="fk_domestic_rate_attempts_seal_binding",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "provider = 'dhl' AND environment = 'sandbox' "
            "AND destination_country_code = 'NG'",
            name="ck_domestic_rate_attempts_lane",
        ),
        CheckConstraint(
            "package_version > 0 AND hub_version > 0",
            name="ck_domestic_rate_attempts_versions",
        ),
        CheckConstraint(
            "destination_snapshot_hash ~ '^[0-9a-f]{64}$' "
            "AND request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_domestic_rate_attempts_hashes",
        ),
        CheckConstraint(
            "account_alias ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' "
            "AND idempotency_key ~ '^[!-~]+$' "
            "AND fingerprint_key_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' "
            "AND adapter_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' "
            "AND schema_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' "
            "AND canonicalization_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_domestic_rate_attempts_identifiers",
        ),
        CheckConstraint(
            "classification IN ('pending', 'success', 'no_service', 'failure')",
            name="ck_domestic_rate_attempts_classification",
        ),
        CheckConstraint(
            "(call_started_at IS NULL OR call_started_at >= claimed_at) "
            "AND (result_recorded_at IS NULL OR "
            "(call_started_at IS NOT NULL AND result_recorded_at >= call_started_at)) "
            "AND ((classification = 'pending' AND result_recorded_at IS NULL "
            "AND failure_code IS NULL AND completion_txid IS NULL) OR "
            "(classification IN ('success', 'no_service') "
            "AND result_recorded_at IS NOT NULL AND failure_code IS NULL "
            "AND completion_txid IS NOT NULL) OR "
            "(classification = 'failure' AND result_recorded_at IS NOT NULL "
            "AND failure_code IS NOT NULL AND failure_code ~ '^[!-~]+$' "
            "AND completion_txid IS NOT NULL))",
            name="ck_domestic_rate_attempts_lifecycle",
        ),
        UniqueConstraint(
            "provider",
            "environment",
            "account_alias",
            "idempotency_key",
            name="uq_domestic_rate_attempts_idempotency",
        ),
        Index(
            "ix_domestic_rate_attempts_subject",
            "intent_id",
            "package_id",
            "package_version",
        ),
        Index("ix_domestic_rate_attempts_classification", "classification"),
    )


class DomesticRateResponse(Base):
    """One normalized success or no-service result for a completed attempt."""

    __tablename__ = "domestic_rate_responses"

    id = _id_column()
    attempt_id = Column(
        _UUID,
        ForeignKey("domestic_rate_attempts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    result_kind = Column(String(20), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ttl_seconds = Column(Integer, nullable=False)
    completion_txid = Column(BigInteger, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=_ATTEMPT_NOW
    )

    __table_args__ = (
        CheckConstraint(
            "result_kind IN ('success', 'no_service')",
            name="ck_domestic_rate_responses_kind",
        ),
        CheckConstraint(
            "ttl_seconds > 0 AND ttl_seconds <= 86400 "
            "AND expires_at = received_at + ttl_seconds * interval '1 second'",
            name="ck_domestic_rate_responses_ttl",
        ),
        UniqueConstraint("attempt_id", name="uq_domestic_rate_responses_attempt"),
        Index("ix_domestic_rate_responses_expiry", "expires_at"),
    )


class DomesticRateOffer(Base):
    """One exact, normalized provider product/service returned in a response."""

    __tablename__ = "domestic_rate_offers"

    id = _id_column()
    response_id = Column(
        _UUID,
        ForeignKey("domestic_rate_responses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_product_code = Column(String(50), nullable=False)
    provider_service_code = Column(String(100), nullable=False)
    service_label = Column(String(200), nullable=False)
    total_amount = Column(Numeric(18, 4), nullable=False)
    currency = Column(String(3), nullable=False)
    transit_days = Column(Integer)
    delivery_date = Column(Date)
    completion_txid = Column(BigInteger, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=_ATTEMPT_NOW
    )

    __table_args__ = (
        CheckConstraint(
            "provider_product_code ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' "
            "AND provider_service_code ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'",
            name="ck_domestic_rate_offers_codes",
        ),
        CheckConstraint(
            "service_label = btrim(service_label) AND length(service_label) > 0 "
            "AND service_label ~ '^[ -~]+$'",
            name="ck_domestic_rate_offers_label",
        ),
        CheckConstraint(
            "total_amount > 0 AND total_amount <= 99999999999999.9999 "
            "AND currency ~ '^[A-Z]{3}$'",
            name="ck_domestic_rate_offers_money",
        ),
        CheckConstraint(
            "transit_days IS NULL OR (transit_days > 0 AND transit_days <= 365)",
            name="ck_domestic_rate_offers_transit",
        ),
        UniqueConstraint(
            "response_id",
            "provider_product_code",
            "provider_service_code",
            name="uq_domestic_rate_offers_service",
        ),
    )


DOMESTIC_RATE_TRIGGER_DDLS = (
    """
CREATE FUNCTION validate_outbound_intent_rate_guard_write() RETURNS trigger AS $$
BEGIN
    IF pg_trigger_depth() <= 1 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate subject guard is server-maintained';
    END IF;
    IF TG_OP='DELETE' OR (TG_OP='UPDATE' AND (
       NEW.intent_id IS DISTINCT FROM OLD.intent_id
       OR (OLD.is_invalidated AND NOT NEW.is_invalidated))) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate subject guard is append-only';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_outbound_intent_rate_guards_write
BEFORE INSERT OR UPDATE OR DELETE ON outbound_intent_rate_guards
FOR EACH ROW EXECUTE FUNCTION validate_outbound_intent_rate_guard_write()
    """,
    """
CREATE OR REPLACE FUNCTION validate_outbound_intent_invalidation_insert() RETURNS trigger AS $$
DECLARE package_id_value uuid; seal_id_value uuid; intent_created_at timestamptz;
BEGIN
    SELECT package_id,seal_id,created_at INTO package_id_value,seal_id_value,intent_created_at
      FROM outbound_shipment_intents WHERE id=NEW.intent_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent does not exist';
    END IF;
    PERFORM 1 FROM hub_package_seals WHERE id=seal_id_value FOR UPDATE;
    PERFORM 1 FROM hub_packages WHERE id=package_id_value FOR UPDATE;
    INSERT INTO outbound_intent_rate_guards(intent_id,is_invalidated)
      VALUES (NEW.intent_id,false) ON CONFLICT (intent_id) DO NOTHING;
    UPDATE outbound_intent_rate_guards SET is_invalidated=true
      WHERE intent_id=NEW.intent_id AND active_attempt_id IS NULL;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='active rate attempt must complete before intent invalidation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM custody_events e JOIN outbound_shipment_intents i
          ON i.package_id=e.package_id AND i.package_version=e.package_version
         WHERE i.id=NEW.intent_id AND e.event_type IN ('released','tendered','provider_accepted')
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent cannot invalidate after custody handoff';
    END IF;
    IF NEW.invalidated_at < intent_created_at OR NEW.invalidated_at > clock_timestamp()
       OR NEW.created_at < NEW.invalidated_at OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent invalidation chronology is invalid';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE FUNCTION validate_domestic_rate_attempt_insert() RETURNS trigger AS $$
DECLARE intent outbound_shipment_intents%%ROWTYPE; package hub_packages%%ROWTYPE; hub fulfillment_hubs%%ROWTYPE; guard_invalidated boolean;
BEGIN
    IF NEW.classification<>'pending' OR NEW.call_started_at IS NOT NULL
       OR NEW.result_recorded_at IS NOT NULL OR NEW.failure_code IS NOT NULL
       OR NEW.completion_txid IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt must begin pending with no call or result';
    END IF;
    NEW.claimed_at := statement_timestamp();
    NEW.created_at := statement_timestamp();
    PERFORM 1 FROM hub_package_seals WHERE id=NEW.seal_id AND package_id=NEW.package_id
      AND package_version=NEW.package_version AND retired_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt requires the active bound seal';
    END IF;
    SELECT * INTO package FROM hub_packages WHERE id=NEW.package_id FOR UPDATE;
    IF NOT FOUND OR package.state<>'ready' OR package.current_version<>NEW.package_version
       OR package.order_id<>NEW.order_id OR package.hub_id<>NEW.origin_hub_id THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt requires exact current ready package truth';
    END IF;
    INSERT INTO outbound_intent_rate_guards(intent_id,is_invalidated)
      VALUES (NEW.intent_id,false) ON CONFLICT (intent_id) DO NOTHING;
    UPDATE outbound_intent_rate_guards SET active_attempt_id=NEW.id
      WHERE intent_id=NEW.intent_id AND NOT is_invalidated AND active_attempt_id IS NULL
      RETURNING is_invalidated INTO guard_invalidated;
    SELECT * INTO intent FROM outbound_shipment_intents WHERE id=NEW.intent_id FOR KEY SHARE;
    IF NOT FOUND OR guard_invalidated IS DISTINCT FROM false OR intent.order_id<>NEW.order_id
       OR intent.package_id<>NEW.package_id OR intent.package_version<>NEW.package_version
       OR intent.seal_id<>NEW.seal_id OR intent.origin_hub_id<>NEW.origin_hub_id
       OR intent.destination_country_code<>NEW.destination_country_code
       OR EXISTS (SELECT 1 FROM outbound_shipment_intent_invalidations WHERE intent_id=intent.id) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt subject binding is invalid';
    END IF;
    SELECT * INTO hub FROM fulfillment_hubs WHERE id=NEW.origin_hub_id FOR KEY SHARE;
    IF NOT FOUND OR NOT hub.is_active OR hub.version<>NEW.hub_version
       OR hub.country_code<>'NG' THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt requires exact active hub version';
    END IF;
    IF NEW.claimed_at<intent.created_at OR NEW.claimed_at>clock_timestamp()
       OR NEW.created_at<NEW.claimed_at OR NEW.created_at>clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt chronology is invalid';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_domestic_rate_attempts_insert
BEFORE INSERT ON domestic_rate_attempts
FOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_attempt_insert()
    """,
    """
CREATE FUNCTION validate_domestic_rate_attempt_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP='DELETE' THEN
        RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='rate evidence is append-only';
    END IF;
    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.intent_id IS DISTINCT FROM OLD.intent_id
       OR NEW.order_id IS DISTINCT FROM OLD.order_id OR NEW.package_id IS DISTINCT FROM OLD.package_id
       OR NEW.package_version IS DISTINCT FROM OLD.package_version OR NEW.seal_id IS DISTINCT FROM OLD.seal_id
       OR NEW.origin_hub_id IS DISTINCT FROM OLD.origin_hub_id OR NEW.hub_version IS DISTINCT FROM OLD.hub_version
       OR NEW.destination_country_code IS DISTINCT FROM OLD.destination_country_code
       OR NEW.destination_snapshot_hash IS DISTINCT FROM OLD.destination_snapshot_hash
       OR NEW.provider IS DISTINCT FROM OLD.provider OR NEW.environment IS DISTINCT FROM OLD.environment
       OR NEW.account_alias IS DISTINCT FROM OLD.account_alias OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
       OR NEW.fingerprint_key_version IS DISTINCT FROM OLD.fingerprint_key_version
       OR NEW.planned_ship_date IS DISTINCT FROM OLD.planned_ship_date
       OR NEW.adapter_version IS DISTINCT FROM OLD.adapter_version OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
       OR NEW.canonicalization_version IS DISTINCT FROM OLD.canonicalization_version
       OR NEW.claimed_at IS DISTINCT FROM OLD.claimed_at OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt identity is immutable';
    END IF;
    IF OLD.classification<>'pending' THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='completed rate attempt is immutable';
    END IF;
    IF NEW.classification='pending' THEN
        IF NEW.completion_txid IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='pending rate attempt cannot have a completion transaction';
        END IF;
    ELSE
        NEW.completion_txid := txid_current();
        UPDATE outbound_intent_rate_guards SET active_attempt_id=NULL
          WHERE intent_id=OLD.intent_id AND active_attempt_id=OLD.id;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt does not own the active subject claim';
        END IF;
    END IF;
    IF OLD.call_started_at IS NOT NULL AND NEW.call_started_at IS DISTINCT FROM OLD.call_started_at THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt call timestamp is immutable once set';
    ELSIF OLD.call_started_at IS NULL AND NEW.call_started_at IS NOT NULL THEN
        NEW.call_started_at := statement_timestamp();
    END IF;
    IF NEW.classification<>'pending' THEN
        NEW.result_recorded_at := statement_timestamp();
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_domestic_rate_attempts_mutation
BEFORE UPDATE OR DELETE ON domestic_rate_attempts
FOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_attempt_mutation()
    """,
    """
CREATE FUNCTION validate_domestic_rate_attempt_response_shape() RETURNS trigger AS $$
DECLARE attempt_id_value uuid; classification_value varchar; response_count integer;
BEGIN
    IF TG_TABLE_NAME='domestic_rate_attempts' THEN
        attempt_id_value := COALESCE(NEW.id,OLD.id);
    ELSE
        attempt_id_value := COALESCE(NEW.attempt_id,OLD.attempt_id);
    END IF;
    SELECT classification INTO classification_value FROM domestic_rate_attempts
      WHERE id=attempt_id_value;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT count(*) INTO response_count FROM domestic_rate_responses
      WHERE attempt_id=attempt_id_value;
    IF classification_value IN ('success','no_service') AND response_count<>1 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='terminal rate attempt requires exactly one response';
    ELSIF classification_value IN ('pending','failure') AND response_count<>0 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='pending or failed rate attempt cannot have a response';
    END IF;
    RETURN NULL;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE CONSTRAINT TRIGGER tr_domestic_rate_attempts_response_shape
AFTER INSERT OR UPDATE OR DELETE ON domestic_rate_attempts
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_attempt_response_shape()
    """,
    """
CREATE CONSTRAINT TRIGGER tr_domestic_rate_responses_attempt_shape
AFTER INSERT OR UPDATE OR DELETE ON domestic_rate_responses
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_attempt_response_shape()
    """,
    """
CREATE FUNCTION validate_domestic_rate_response_insert() RETURNS trigger AS $$
DECLARE attempt domestic_rate_attempts%%ROWTYPE;
BEGIN
    SELECT * INTO attempt FROM domestic_rate_attempts WHERE id=NEW.attempt_id FOR KEY SHARE;
    NEW.completion_txid := txid_current();
    NEW.received_at := attempt.result_recorded_at;
    NEW.created_at := statement_timestamp();
    NEW.expires_at := NEW.received_at + NEW.ttl_seconds * interval '1 second';
    IF NOT FOUND OR attempt.classification<>NEW.result_kind OR attempt.result_recorded_at IS NULL
       OR attempt.call_started_at IS NULL
       OR attempt.completion_txid IS DISTINCT FROM NEW.completion_txid
       OR NEW.created_at<attempt.result_recorded_at THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate response does not match atomic completed attempt';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_domestic_rate_responses_insert
BEFORE INSERT ON domestic_rate_responses
FOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_response_insert()
    """,
    """
CREATE FUNCTION reject_domestic_rate_evidence_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='rate evidence is append-only';
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_domestic_rate_responses_immutable
BEFORE UPDATE OR DELETE ON domestic_rate_responses
FOR EACH ROW EXECUTE FUNCTION reject_domestic_rate_evidence_mutation()
    """,
    """
CREATE FUNCTION validate_domestic_rate_offer_insert() RETURNS trigger AS $$
DECLARE kind varchar; planned date; response_completion_txid bigint;
BEGIN
    SELECT response.result_kind,attempt.planned_ship_date,response.completion_txid
      INTO kind,planned,response_completion_txid
      FROM domestic_rate_responses response
      JOIN domestic_rate_attempts attempt ON attempt.id=response.attempt_id
     WHERE response.id=NEW.response_id FOR KEY SHARE OF response,attempt;
    NEW.completion_txid := txid_current();
    NEW.created_at := statement_timestamp();
    IF NOT FOUND OR kind<>'success' THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='no-service response cannot contain offers';
    END IF;
    IF NEW.completion_txid IS DISTINCT FROM response_completion_txid THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate response offer set is immutable';
    END IF;
    IF NEW.delivery_date IS NOT NULL AND NEW.delivery_date<=planned
       OR NEW.transit_days IS NOT NULL AND NEW.delivery_date IS NOT NULL
          AND (NEW.delivery_date<planned+NEW.transit_days
               OR NEW.delivery_date>planned+NEW.transit_days+7) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate offer delivery facts are invalid';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE TRIGGER tr_domestic_rate_offers_insert
BEFORE INSERT ON domestic_rate_offers
FOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_offer_insert()
    """,
    """
CREATE TRIGGER tr_domestic_rate_offers_immutable
BEFORE UPDATE OR DELETE ON domestic_rate_offers
FOR EACH ROW EXECUTE FUNCTION reject_domestic_rate_evidence_mutation()
    """,
    """
CREATE FUNCTION validate_domestic_rate_response_offers() RETURNS trigger AS $$
DECLARE response_id_value uuid; kind varchar; offer_count integer;
BEGIN
    IF TG_TABLE_NAME='domestic_rate_responses' THEN
        response_id_value := COALESCE(NEW.id,OLD.id);
    ELSE
        response_id_value := COALESCE(NEW.response_id,OLD.response_id);
    END IF;
    SELECT result_kind INTO kind FROM domestic_rate_responses WHERE id=response_id_value;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT count(*) INTO offer_count FROM domestic_rate_offers WHERE response_id=response_id_value;
    IF kind='success' AND offer_count=0 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='success response requires at least one offer';
    ELSIF kind='no_service' AND offer_count<>0 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='no-service response cannot contain offers';
    END IF;
    RETURN NULL;
END; $$ LANGUAGE plpgsql
    """,
    """
CREATE CONSTRAINT TRIGGER tr_domestic_rate_responses_offer_shape
AFTER INSERT OR UPDATE OR DELETE ON domestic_rate_responses
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_response_offers()
    """,
    """
CREATE CONSTRAINT TRIGGER tr_domestic_rate_offers_response_shape
AFTER INSERT OR UPDATE OR DELETE ON domestic_rate_offers
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_response_offers()
    """,
)

DOMESTIC_RATE_DROP_DDLS = (
    "DROP FUNCTION IF EXISTS validate_domestic_rate_response_offers() CASCADE",
    "DROP FUNCTION IF EXISTS validate_domestic_rate_offer_insert() CASCADE",
    "DROP FUNCTION IF EXISTS reject_domestic_rate_evidence_mutation() CASCADE",
    "DROP FUNCTION IF EXISTS validate_domestic_rate_response_insert() CASCADE",
    "DROP FUNCTION IF EXISTS validate_domestic_rate_attempt_response_shape() CASCADE",
    "DROP FUNCTION IF EXISTS validate_domestic_rate_attempt_mutation() CASCADE",
    "DROP FUNCTION IF EXISTS validate_domestic_rate_attempt_insert() CASCADE",
    "DROP FUNCTION IF EXISTS validate_outbound_intent_rate_guard_write() CASCADE",
)

for _ddl in DOMESTIC_RATE_TRIGGER_DDLS:
    event.listen(DomesticRateOffer.__table__, "after_create", DDL(_ddl))
for _ddl in DOMESTIC_RATE_DROP_DDLS:
    event.listen(DomesticRateAttempt.__table__, "after_drop", DDL(_ddl))
