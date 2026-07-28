"""Add expiring leases and truthful recovery to domestic rate attempts.

Revision ID: d7b9f1c3e5a8
Revises: c6a8e0f2b4d7
"""

from alembic import op

revision = "d7b9f1c3e5a8"
down_revision = "c6a8e0f2b4d7"
branch_labels = None
depends_on = None

_NEW_CLASSIFICATION_CHECK = (
    "classification IN ('pending', 'success', 'no_service', 'failure', 'abandoned')"
)
_NEW_LIFECYCLE_CHECK = (
    "claim_ttl_seconds BETWEEN 1 AND 900 "
    "AND claim_expires_at = claimed_at + claim_ttl_seconds * interval '1 second' "
    "AND (call_started_at IS NULL OR call_started_at >= claimed_at) "
    "AND (result_recorded_at IS NULL OR "
    "(call_started_at IS NOT NULL AND result_recorded_at >= call_started_at) OR "
    "(classification = 'abandoned' AND result_recorded_at >= claimed_at)) "
    "AND ((classification = 'pending' AND result_recorded_at IS NULL "
    "AND failure_code IS NULL AND completion_txid IS NULL) OR "
    "(classification IN ('success', 'no_service') "
    "AND result_recorded_at IS NOT NULL AND failure_code IS NULL "
    "AND completion_txid IS NOT NULL) OR "
    "(classification = 'failure' AND result_recorded_at IS NOT NULL "
    "AND failure_code IS NOT NULL AND failure_code ~ '^[!-~]+$' "
    "AND completion_txid IS NOT NULL) OR "
    "(classification = 'abandoned' AND result_recorded_at IS NOT NULL "
    "AND failure_code = 'claim_expired' AND completion_txid IS NOT NULL))"
)
_OLD_CLASSIFICATION_CHECK = (
    "classification IN ('pending', 'success', 'no_service', 'failure')"
)
_OLD_LIFECYCLE_CHECK = (
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
    "AND completion_txid IS NOT NULL))"
)

_NEW_FUNCTION_DDLS = (
    """CREATE OR REPLACE FUNCTION validate_domestic_rate_attempt_insert() RETURNS trigger AS $$
DECLARE intent outbound_shipment_intents%ROWTYPE; package hub_packages%ROWTYPE; hub fulfillment_hubs%ROWTYPE; guard_invalidated boolean; claimed_at_value timestamptz;
BEGIN
    IF NEW.classification<>'pending' OR NEW.call_started_at IS NOT NULL
       OR NEW.result_recorded_at IS NOT NULL OR NEW.failure_code IS NOT NULL
       OR NEW.completion_txid IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt must begin pending with no call or result';
    END IF;
    IF NEW.claim_ttl_seconds IS NULL OR NEW.claim_ttl_seconds NOT BETWEEN 1 AND 900 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt claim duration is invalid';
    END IF;
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
       OR intent.destination_snapshot_hash<>NEW.destination_snapshot_hash
       OR EXISTS (SELECT 1 FROM outbound_shipment_intent_invalidations WHERE intent_id=intent.id) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt subject binding is invalid';
    END IF;
    SELECT * INTO hub FROM fulfillment_hubs WHERE id=NEW.origin_hub_id FOR KEY SHARE;
    IF NOT FOUND OR NOT hub.is_active OR hub.version<>NEW.hub_version
       OR hub.country_code<>'NG' THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt requires exact active hub version';
    END IF;
    claimed_at_value := clock_timestamp();
    NEW.claimed_at := claimed_at_value;
    NEW.claim_expires_at := claimed_at_value + NEW.claim_ttl_seconds * interval '1 second';
    NEW.created_at := claimed_at_value;
    IF NEW.claimed_at<intent.created_at THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt chronology is invalid';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql""",
    """CREATE OR REPLACE FUNCTION validate_domestic_rate_attempt_mutation() RETURNS trigger AS $$
DECLARE event_at timestamptz;
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
       OR NEW.claimed_at IS DISTINCT FROM OLD.claimed_at
       OR NEW.claim_ttl_seconds IS DISTINCT FROM OLD.claim_ttl_seconds
       OR NEW.claim_expires_at IS DISTINCT FROM OLD.claim_expires_at
       OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt identity is immutable';
    END IF;
    IF OLD.classification<>'pending' THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='completed rate attempt is immutable';
    END IF;
    event_at := clock_timestamp();
    IF NEW.classification='pending' THEN
        IF NEW.completion_txid IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='pending rate attempt cannot have a completion transaction';
        END IF;
    ELSE
        IF NEW.classification='abandoned' THEN
            IF event_at<OLD.claim_expires_at THEN
                RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt claim has not expired';
            END IF;
        ELSIF event_at>=OLD.claim_expires_at THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt claim has expired';
        END IF;
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
        IF event_at>=OLD.claim_expires_at THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt claim has expired';
        END IF;
        NEW.call_started_at := event_at;
    END IF;
    IF NEW.classification<>'pending' THEN
        NEW.result_recorded_at := event_at;
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql""",
    """CREATE OR REPLACE FUNCTION validate_domestic_rate_attempt_response_shape() RETURNS trigger AS $$
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
    ELSIF classification_value IN ('pending','failure','abandoned') AND response_count<>0 THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='non-result rate attempt cannot have a response';
    END IF;
    RETURN NULL;
END; $$ LANGUAGE plpgsql""",
)

_OLD_FUNCTION_DDLS = (
    """CREATE OR REPLACE FUNCTION validate_domestic_rate_attempt_insert() RETURNS trigger AS $$
DECLARE intent outbound_shipment_intents%ROWTYPE; package hub_packages%ROWTYPE; hub fulfillment_hubs%ROWTYPE; guard_invalidated boolean;
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
       OR intent.destination_snapshot_hash<>NEW.destination_snapshot_hash
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
END; $$ LANGUAGE plpgsql""",
    """CREATE OR REPLACE FUNCTION validate_domestic_rate_attempt_mutation() RETURNS trigger AS $$
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
END; $$ LANGUAGE plpgsql""",
    """CREATE OR REPLACE FUNCTION validate_domestic_rate_attempt_response_shape() RETURNS trigger AS $$
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
END; $$ LANGUAGE plpgsql""",
)


def _replace_checks(classification: str, lifecycle: str) -> None:
    op.execute(
        "ALTER TABLE domestic_rate_attempts "
        "DROP CONSTRAINT ck_domestic_rate_attempts_classification"
    )
    op.execute(
        "ALTER TABLE domestic_rate_attempts "
        "DROP CONSTRAINT ck_domestic_rate_attempts_lifecycle"
    )
    op.execute(
        "ALTER TABLE domestic_rate_attempts "
        "ADD CONSTRAINT ck_domestic_rate_attempts_classification "
        f"CHECK ({classification})"
    )
    op.execute(
        "ALTER TABLE domestic_rate_attempts "
        "ADD CONSTRAINT ck_domestic_rate_attempts_lifecycle "
        f"CHECK ({lifecycle})"
    )


def upgrade() -> None:
    op.execute(
        "ALTER TABLE domestic_rate_attempts "
        "ADD COLUMN claim_ttl_seconds INTEGER DEFAULT 300 NOT NULL"
    )
    op.execute(
        "ALTER TABLE domestic_rate_attempts "
        "ADD COLUMN claim_expires_at TIMESTAMP WITH TIME ZONE"
    )
    op.execute(
        "UPDATE domestic_rate_attempts SET claim_expires_at = "
        "claimed_at + claim_ttl_seconds * interval '1 second'"
    )
    op.execute(
        "ALTER TABLE domestic_rate_attempts "
        "ALTER COLUMN claim_expires_at SET NOT NULL"
    )
    _replace_checks(_NEW_CLASSIFICATION_CHECK, _NEW_LIFECYCLE_CHECK)
    for statement in _NEW_FUNCTION_DDLS:
        op.execute(statement)


def downgrade() -> None:
    op.execute(
        """DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM domestic_rate_attempts WHERE classification='abandoned'
    ) THEN
        RAISE EXCEPTION USING ERRCODE='55000',
          MESSAGE='cannot downgrade domestic rate leases with abandoned evidence';
    END IF;
END $$"""
    )
    for statement in _OLD_FUNCTION_DDLS:
        op.execute(statement)
    _replace_checks(_OLD_CLASSIFICATION_CHECK, _OLD_LIFECYCLE_CHECK)
    op.execute("ALTER TABLE domestic_rate_attempts DROP COLUMN claim_expires_at")
    op.execute("ALTER TABLE domestic_rate_attempts DROP COLUMN claim_ttl_seconds")
