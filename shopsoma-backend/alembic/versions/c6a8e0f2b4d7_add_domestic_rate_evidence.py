"""Add immutable normalized domestic rate evidence.

Revision ID: c6a8e0f2b4d7
Revises: b5f7d9a2c4e6
"""

from alembic import op

revision = "c6a8e0f2b4d7"
down_revision = "b5f7d9a2c4e6"
branch_labels = None
depends_on = None

_DESTINATION_SNAPSHOT_UPGRADE_DDLS = (
    "ALTER TABLE outbound_shipment_intents "
    "ADD COLUMN destination_snapshot_hash VARCHAR(64)",
    "ALTER TABLE outbound_shipment_intents "
    "DISABLE TRIGGER tr_outbound_shipment_intents_immutable",
    """UPDATE outbound_shipment_intents
SET destination_snapshot_hash = encode(
    sha256(convert_to(jsonb_build_array(
        'destination-snapshot-v1', destination_name, destination_phone,
        destination_address_line1, destination_address_line2,
        destination_city, destination_state, destination_postal_code,
        destination_country_code
    )::text, 'UTF8')),
    'hex'
)""",
    "ALTER TABLE outbound_shipment_intents "
    "ENABLE TRIGGER tr_outbound_shipment_intents_immutable",
    "ALTER TABLE outbound_shipment_intents "
    "ADD CONSTRAINT ck_outbound_intents_destination_snapshot_hash "
    "CHECK (destination_snapshot_hash ~ '^[0-9a-f]{64}$')",
    "ALTER TABLE outbound_shipment_intents "
    "ALTER COLUMN destination_snapshot_hash SET NOT NULL",
    """CREATE OR REPLACE FUNCTION validate_outbound_intent_insert() RETURNS trigger AS $$
DECLARE package hub_packages%ROWTYPE;
BEGIN
    PERFORM 1 FROM hub_package_seals WHERE id=NEW.seal_id
      AND package_id=NEW.package_id AND package_version=NEW.package_version
      AND retired_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent requires exact current ready package and active seal';
    END IF;
    SELECT * INTO package FROM hub_packages WHERE id=NEW.package_id FOR UPDATE;
    IF NOT FOUND OR package.state<>'ready' OR package.current_version<>NEW.package_version
       OR package.order_id<>NEW.order_id OR package.hub_id<>NEW.origin_hub_id
       OR NEW.created_at < package.ready_at OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent requires exact current ready package and active seal';
    END IF;
    IF EXISTS (
        SELECT 1 FROM outbound_shipment_intents i WHERE i.package_id=NEW.package_id
         AND NOT EXISTS (SELECT 1 FROM outbound_shipment_intent_invalidations x WHERE x.intent_id=i.id)
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package already has an active outbound intent';
    END IF;
    NEW.destination_snapshot_hash := encode(
        sha256(convert_to(jsonb_build_array(
            'destination-snapshot-v1', NEW.destination_name, NEW.destination_phone,
            NEW.destination_address_line1, NEW.destination_address_line2,
            NEW.destination_city, NEW.destination_state, NEW.destination_postal_code,
            NEW.destination_country_code
        )::text, 'UTF8')),
        'hex'
    );
    RETURN NEW;
END; $$ LANGUAGE plpgsql""",
)

_RESTORE_OUTBOUND_INTENT_INSERT_DDL = """CREATE OR REPLACE FUNCTION validate_outbound_intent_insert() RETURNS trigger AS $$
DECLARE package hub_packages%ROWTYPE;
BEGIN
    PERFORM 1 FROM hub_package_seals WHERE id=NEW.seal_id
      AND package_id=NEW.package_id AND package_version=NEW.package_version
      AND retired_at IS NULL FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent requires exact current ready package and active seal';
    END IF;
    SELECT * INTO package FROM hub_packages WHERE id=NEW.package_id FOR UPDATE;
    IF NOT FOUND OR package.state<>'ready' OR package.current_version<>NEW.package_version
       OR package.order_id<>NEW.order_id OR package.hub_id<>NEW.origin_hub_id
       OR NEW.created_at < package.ready_at OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent requires exact current ready package and active seal';
    END IF;
    IF EXISTS (
        SELECT 1 FROM outbound_shipment_intents i WHERE i.package_id=NEW.package_id
         AND NOT EXISTS (SELECT 1 FROM outbound_shipment_intent_invalidations x WHERE x.intent_id=i.id)
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='package already has an active outbound intent';
    END IF;
    RETURN NEW;
END; $$ LANGUAGE plpgsql"""

_CREATE_TABLE_SQL = (
    "CREATE TABLE outbound_intent_rate_guards (\n\tintent_id UUID NOT NULL, \n\tis_invalidated BOOLEAN DEFAULT 'false' NOT NULL, \n\tactive_attempt_id UUID, \n\tPRIMARY KEY (intent_id), \n\tFOREIGN KEY(intent_id) REFERENCES outbound_shipment_intents (id) ON DELETE CASCADE\n)",
    "CREATE TABLE domestic_rate_attempts (\n\tid UUID NOT NULL, \n\tintent_id UUID NOT NULL, \n\torder_id UUID NOT NULL, \n\tpackage_id UUID NOT NULL, \n\tpackage_version INTEGER NOT NULL, \n\tseal_id UUID NOT NULL, \n\torigin_hub_id UUID NOT NULL, \n\thub_version INTEGER NOT NULL, \n\tdestination_country_code VARCHAR(2) NOT NULL, \n\tdestination_snapshot_hash VARCHAR(64) NOT NULL, \n\tprovider VARCHAR(20) NOT NULL, \n\tenvironment VARCHAR(20) NOT NULL, \n\taccount_alias VARCHAR(100) NOT NULL, \n\tidempotency_key VARCHAR(200) NOT NULL, \n\trequest_fingerprint VARCHAR(64) NOT NULL, \n\tfingerprint_key_version VARCHAR(50) NOT NULL, \n\tplanned_ship_date DATE NOT NULL, \n\tadapter_version VARCHAR(50) NOT NULL, \n\tschema_version VARCHAR(50) NOT NULL, \n\tcanonicalization_version VARCHAR(50) NOT NULL, \n\tclaimed_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcall_started_at TIMESTAMP WITH TIME ZONE, \n\tresult_recorded_at TIMESTAMP WITH TIME ZONE, \n\tclassification VARCHAR(20) NOT NULL, \n\tfailure_code VARCHAR(100), \n\tcompletion_txid BIGINT, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT statement_timestamp() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT fk_domestic_rate_attempts_package_version FOREIGN KEY(package_id, package_version) REFERENCES hub_package_versions (package_id, version) ON DELETE RESTRICT, \n\tCONSTRAINT fk_domestic_rate_attempts_seal_binding FOREIGN KEY(seal_id, package_id, package_version) REFERENCES hub_package_seals (id, package_id, package_version) ON DELETE RESTRICT, \n\tCONSTRAINT ck_domestic_rate_attempts_lane CHECK (provider = 'dhl' AND environment = 'sandbox' AND destination_country_code = 'NG'), \n\tCONSTRAINT ck_domestic_rate_attempts_versions CHECK (package_version > 0 AND hub_version > 0), \n\tCONSTRAINT ck_domestic_rate_attempts_hashes CHECK (destination_snapshot_hash ~ '^[0-9a-f]{64}$' AND request_fingerprint ~ '^[0-9a-f]{64}$'), \n\tCONSTRAINT ck_domestic_rate_attempts_identifiers CHECK (account_alias ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND idempotency_key ~ '^[!-~]+$' AND fingerprint_key_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND adapter_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND schema_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND canonicalization_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'), \n\tCONSTRAINT ck_domestic_rate_attempts_classification CHECK (classification IN ('pending', 'success', 'no_service', 'failure')), \n\tCONSTRAINT ck_domestic_rate_attempts_lifecycle CHECK ((call_started_at IS NULL OR call_started_at >= claimed_at) AND (result_recorded_at IS NULL OR (call_started_at IS NOT NULL AND result_recorded_at >= call_started_at)) AND ((classification = 'pending' AND result_recorded_at IS NULL AND failure_code IS NULL AND completion_txid IS NULL) OR (classification IN ('success', 'no_service') AND result_recorded_at IS NOT NULL AND failure_code IS NULL AND completion_txid IS NOT NULL) OR (classification = 'failure' AND result_recorded_at IS NOT NULL AND failure_code IS NOT NULL AND failure_code ~ '^[!-~]+$' AND completion_txid IS NOT NULL))), \n\tCONSTRAINT uq_domestic_rate_attempts_idempotency UNIQUE (provider, environment, account_alias, idempotency_key), \n\tFOREIGN KEY(intent_id) REFERENCES outbound_shipment_intents (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(order_id) REFERENCES orders (id) ON DELETE RESTRICT, \n\tFOREIGN KEY(origin_hub_id) REFERENCES fulfillment_hubs (id) ON DELETE RESTRICT\n)",
    "CREATE TABLE domestic_rate_responses (\n\tid UUID NOT NULL, \n\tattempt_id UUID NOT NULL, \n\tresult_kind VARCHAR(20) NOT NULL, \n\treceived_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\texpires_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tttl_seconds INTEGER NOT NULL, \n\tcompletion_txid BIGINT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT statement_timestamp() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_domestic_rate_responses_kind CHECK (result_kind IN ('success', 'no_service')), \n\tCONSTRAINT ck_domestic_rate_responses_ttl CHECK (ttl_seconds > 0 AND ttl_seconds <= 86400 AND expires_at = received_at + ttl_seconds * interval '1 second'), \n\tCONSTRAINT uq_domestic_rate_responses_attempt UNIQUE (attempt_id), \n\tFOREIGN KEY(attempt_id) REFERENCES domestic_rate_attempts (id) ON DELETE RESTRICT\n)",
    "CREATE TABLE domestic_rate_offers (\n\tid UUID NOT NULL, \n\tresponse_id UUID NOT NULL, \n\tprovider_product_code VARCHAR(50) NOT NULL, \n\tprovider_service_code VARCHAR(100) NOT NULL, \n\tservice_label VARCHAR(200) NOT NULL, \n\ttotal_amount NUMERIC(18, 4) NOT NULL, \n\tcurrency VARCHAR(3) NOT NULL, \n\ttransit_days INTEGER, \n\tdelivery_date DATE, \n\tcompletion_txid BIGINT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE DEFAULT statement_timestamp() NOT NULL, \n\tPRIMARY KEY (id), \n\tCONSTRAINT ck_domestic_rate_offers_codes CHECK (provider_product_code ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$' AND provider_service_code ~ '^[A-Za-z0-9][A-Za-z0-9._:-]*$'), \n\tCONSTRAINT ck_domestic_rate_offers_label CHECK (service_label = btrim(service_label) AND length(service_label) > 0 AND service_label ~ '^[ -~]+$'), \n\tCONSTRAINT ck_domestic_rate_offers_money CHECK (total_amount > 0 AND total_amount <= 99999999999999.9999 AND currency ~ '^[A-Z]{3}$'), \n\tCONSTRAINT ck_domestic_rate_offers_transit CHECK (transit_days IS NULL OR (transit_days > 0 AND transit_days <= 365)), \n\tCONSTRAINT uq_domestic_rate_offers_service UNIQUE (response_id, provider_product_code, provider_service_code), \n\tFOREIGN KEY(response_id) REFERENCES domestic_rate_responses (id) ON DELETE RESTRICT\n)",
)
_CREATE_INDEX_SQL = (
    "CREATE INDEX ix_domestic_rate_attempts_classification ON domestic_rate_attempts (classification)",
    "CREATE INDEX ix_domestic_rate_attempts_subject ON domestic_rate_attempts (intent_id, package_id, package_version)",
    "CREATE INDEX ix_domestic_rate_responses_expiry ON domestic_rate_responses (expires_at)",
)
_TRIGGER_DDLS = (
    "CREATE FUNCTION validate_outbound_intent_rate_guard_write() RETURNS trigger AS $$\nBEGIN\n    IF pg_trigger_depth() <= 1 THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate subject guard is server-maintained';\n    END IF;\n    IF TG_OP='DELETE' OR (TG_OP='UPDATE' AND (\n       NEW.intent_id IS DISTINCT FROM OLD.intent_id\n       OR (OLD.is_invalidated AND NOT NEW.is_invalidated))) THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate subject guard is append-only';\n    END IF;\n    RETURN NEW;\nEND; $$ LANGUAGE plpgsql",
    "CREATE TRIGGER tr_outbound_intent_rate_guards_write\nBEFORE INSERT OR UPDATE OR DELETE ON outbound_intent_rate_guards\nFOR EACH ROW EXECUTE FUNCTION validate_outbound_intent_rate_guard_write()",
    "CREATE OR REPLACE FUNCTION validate_outbound_intent_invalidation_insert() RETURNS trigger AS $$\nDECLARE package_id_value uuid; seal_id_value uuid; intent_created_at timestamptz;\nBEGIN\n    SELECT package_id,seal_id,created_at INTO package_id_value,seal_id_value,intent_created_at\n      FROM outbound_shipment_intents WHERE id=NEW.intent_id;\n    IF NOT FOUND THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent does not exist';\n    END IF;\n    PERFORM 1 FROM hub_package_seals WHERE id=seal_id_value FOR UPDATE;\n    PERFORM 1 FROM hub_packages WHERE id=package_id_value FOR UPDATE;\n    INSERT INTO outbound_intent_rate_guards(intent_id,is_invalidated)\n      VALUES (NEW.intent_id,false) ON CONFLICT (intent_id) DO NOTHING;\n    UPDATE outbound_intent_rate_guards SET is_invalidated=true\n      WHERE intent_id=NEW.intent_id AND active_attempt_id IS NULL;\n    IF NOT FOUND THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='active rate attempt must complete before intent invalidation';\n    END IF;\n    IF EXISTS (\n        SELECT 1 FROM custody_events e JOIN outbound_shipment_intents i\n          ON i.package_id=e.package_id AND i.package_version=e.package_version\n         WHERE i.id=NEW.intent_id AND e.event_type IN ('released','tendered','provider_accepted')\n    ) THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent cannot invalidate after custody handoff';\n    END IF;\n    IF NEW.invalidated_at < intent_created_at OR NEW.invalidated_at > clock_timestamp()\n       OR NEW.created_at < NEW.invalidated_at OR NEW.created_at > clock_timestamp() THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent invalidation chronology is invalid';\n    END IF;\n    RETURN NEW;\nEND; $$ LANGUAGE plpgsql",
    "CREATE FUNCTION validate_domestic_rate_attempt_insert() RETURNS trigger AS $$\nDECLARE intent outbound_shipment_intents%ROWTYPE; package hub_packages%ROWTYPE; hub fulfillment_hubs%ROWTYPE; guard_invalidated boolean;\nBEGIN\n    IF NEW.classification<>'pending' OR NEW.call_started_at IS NOT NULL\n       OR NEW.result_recorded_at IS NOT NULL OR NEW.failure_code IS NOT NULL\n       OR NEW.completion_txid IS NOT NULL THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt must begin pending with no call or result';\n    END IF;\n    NEW.claimed_at := statement_timestamp();\n    NEW.created_at := statement_timestamp();\n    PERFORM 1 FROM hub_package_seals WHERE id=NEW.seal_id AND package_id=NEW.package_id\n      AND package_version=NEW.package_version AND retired_at IS NULL FOR UPDATE;\n    IF NOT FOUND THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt requires the active bound seal';\n    END IF;\n    SELECT * INTO package FROM hub_packages WHERE id=NEW.package_id FOR UPDATE;\n    IF NOT FOUND OR package.state<>'ready' OR package.current_version<>NEW.package_version\n       OR package.order_id<>NEW.order_id OR package.hub_id<>NEW.origin_hub_id THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt requires exact current ready package truth';\n    END IF;\n    INSERT INTO outbound_intent_rate_guards(intent_id,is_invalidated)\n      VALUES (NEW.intent_id,false) ON CONFLICT (intent_id) DO NOTHING;\n    UPDATE outbound_intent_rate_guards SET active_attempt_id=NEW.id\n      WHERE intent_id=NEW.intent_id AND NOT is_invalidated AND active_attempt_id IS NULL\n      RETURNING is_invalidated INTO guard_invalidated;\n    SELECT * INTO intent FROM outbound_shipment_intents WHERE id=NEW.intent_id FOR KEY SHARE;\n    IF NOT FOUND OR guard_invalidated IS DISTINCT FROM false OR intent.order_id<>NEW.order_id\n       OR intent.package_id<>NEW.package_id OR intent.package_version<>NEW.package_version\n       OR intent.seal_id<>NEW.seal_id OR intent.origin_hub_id<>NEW.origin_hub_id\n       OR intent.destination_country_code<>NEW.destination_country_code\n       OR intent.destination_snapshot_hash<>NEW.destination_snapshot_hash\n       OR EXISTS (SELECT 1 FROM outbound_shipment_intent_invalidations WHERE intent_id=intent.id) THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt subject binding is invalid';\n    END IF;\n    SELECT * INTO hub FROM fulfillment_hubs WHERE id=NEW.origin_hub_id FOR KEY SHARE;\n    IF NOT FOUND OR NOT hub.is_active OR hub.version<>NEW.hub_version\n       OR hub.country_code<>'NG' THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt requires exact active hub version';\n    END IF;\n    IF NEW.claimed_at<intent.created_at OR NEW.claimed_at>clock_timestamp()\n       OR NEW.created_at<NEW.claimed_at OR NEW.created_at>clock_timestamp() THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt chronology is invalid';\n    END IF;\n    RETURN NEW;\nEND; $$ LANGUAGE plpgsql",
    "CREATE TRIGGER tr_domestic_rate_attempts_insert\nBEFORE INSERT ON domestic_rate_attempts\nFOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_attempt_insert()",
    "CREATE FUNCTION validate_domestic_rate_attempt_mutation() RETURNS trigger AS $$\nBEGIN\n    IF TG_OP='DELETE' THEN\n        RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='rate evidence is append-only';\n    END IF;\n    IF NEW.id IS DISTINCT FROM OLD.id OR NEW.intent_id IS DISTINCT FROM OLD.intent_id\n       OR NEW.order_id IS DISTINCT FROM OLD.order_id OR NEW.package_id IS DISTINCT FROM OLD.package_id\n       OR NEW.package_version IS DISTINCT FROM OLD.package_version OR NEW.seal_id IS DISTINCT FROM OLD.seal_id\n       OR NEW.origin_hub_id IS DISTINCT FROM OLD.origin_hub_id OR NEW.hub_version IS DISTINCT FROM OLD.hub_version\n       OR NEW.destination_country_code IS DISTINCT FROM OLD.destination_country_code\n       OR NEW.destination_snapshot_hash IS DISTINCT FROM OLD.destination_snapshot_hash\n       OR NEW.provider IS DISTINCT FROM OLD.provider OR NEW.environment IS DISTINCT FROM OLD.environment\n       OR NEW.account_alias IS DISTINCT FROM OLD.account_alias OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key\n       OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint\n       OR NEW.fingerprint_key_version IS DISTINCT FROM OLD.fingerprint_key_version\n       OR NEW.planned_ship_date IS DISTINCT FROM OLD.planned_ship_date\n       OR NEW.adapter_version IS DISTINCT FROM OLD.adapter_version OR NEW.schema_version IS DISTINCT FROM OLD.schema_version\n       OR NEW.canonicalization_version IS DISTINCT FROM OLD.canonicalization_version\n       OR NEW.claimed_at IS DISTINCT FROM OLD.claimed_at OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt identity is immutable';\n    END IF;\n    IF OLD.classification<>'pending' THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='completed rate attempt is immutable';\n    END IF;\n    IF NEW.classification='pending' THEN\n        IF NEW.completion_txid IS NOT NULL THEN\n            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='pending rate attempt cannot have a completion transaction';\n        END IF;\n    ELSE\n        NEW.completion_txid := txid_current();\n        UPDATE outbound_intent_rate_guards SET active_attempt_id=NULL\n          WHERE intent_id=OLD.intent_id AND active_attempt_id=OLD.id;\n        IF NOT FOUND THEN\n            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt does not own the active subject claim';\n        END IF;\n    END IF;\n    IF OLD.call_started_at IS NOT NULL AND NEW.call_started_at IS DISTINCT FROM OLD.call_started_at THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt call timestamp is immutable once set';\n    ELSIF OLD.call_started_at IS NULL AND NEW.call_started_at IS NOT NULL THEN\n        NEW.call_started_at := statement_timestamp();\n    END IF;\n    IF NEW.classification<>'pending' THEN\n        NEW.result_recorded_at := statement_timestamp();\n    END IF;\n    RETURN NEW;\nEND; $$ LANGUAGE plpgsql",
    "CREATE TRIGGER tr_domestic_rate_attempts_mutation\nBEFORE UPDATE OR DELETE ON domestic_rate_attempts\nFOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_attempt_mutation()",
    "CREATE FUNCTION validate_domestic_rate_attempt_response_shape() RETURNS trigger AS $$\nDECLARE attempt_id_value uuid; classification_value varchar; response_count integer;\nBEGIN\n    IF TG_TABLE_NAME='domestic_rate_attempts' THEN\n        attempt_id_value := COALESCE(NEW.id,OLD.id);\n    ELSE\n        attempt_id_value := COALESCE(NEW.attempt_id,OLD.attempt_id);\n    END IF;\n    SELECT classification INTO classification_value FROM domestic_rate_attempts\n      WHERE id=attempt_id_value;\n    IF NOT FOUND THEN RETURN NULL; END IF;\n    SELECT count(*) INTO response_count FROM domestic_rate_responses\n      WHERE attempt_id=attempt_id_value;\n    IF classification_value IN ('success','no_service') AND response_count<>1 THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='terminal rate attempt requires exactly one response';\n    ELSIF classification_value IN ('pending','failure') AND response_count<>0 THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='pending or failed rate attempt cannot have a response';\n    END IF;\n    RETURN NULL;\nEND; $$ LANGUAGE plpgsql",
    "CREATE CONSTRAINT TRIGGER tr_domestic_rate_attempts_response_shape\nAFTER INSERT OR UPDATE OR DELETE ON domestic_rate_attempts\nDEFERRABLE INITIALLY DEFERRED\nFOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_attempt_response_shape()",
    "CREATE CONSTRAINT TRIGGER tr_domestic_rate_responses_attempt_shape\nAFTER INSERT OR UPDATE OR DELETE ON domestic_rate_responses\nDEFERRABLE INITIALLY DEFERRED\nFOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_attempt_response_shape()",
    "CREATE FUNCTION validate_domestic_rate_response_insert() RETURNS trigger AS $$\nDECLARE attempt domestic_rate_attempts%ROWTYPE;\nBEGIN\n    SELECT * INTO attempt FROM domestic_rate_attempts WHERE id=NEW.attempt_id FOR KEY SHARE;\n    NEW.completion_txid := txid_current();\n    NEW.received_at := attempt.result_recorded_at;\n    NEW.created_at := statement_timestamp();\n    NEW.expires_at := NEW.received_at + NEW.ttl_seconds * interval '1 second';\n    IF NOT FOUND OR attempt.classification<>NEW.result_kind OR attempt.result_recorded_at IS NULL\n       OR attempt.call_started_at IS NULL\n       OR attempt.completion_txid IS DISTINCT FROM NEW.completion_txid\n       OR NEW.created_at<attempt.result_recorded_at THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate response does not match atomic completed attempt';\n    END IF;\n    RETURN NEW;\nEND; $$ LANGUAGE plpgsql",
    "CREATE TRIGGER tr_domestic_rate_responses_insert\nBEFORE INSERT ON domestic_rate_responses\nFOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_response_insert()",
    "CREATE FUNCTION reject_domestic_rate_evidence_mutation() RETURNS trigger AS $$\nBEGIN\n    RAISE EXCEPTION USING ERRCODE='23503', MESSAGE='rate evidence is append-only';\nEND; $$ LANGUAGE plpgsql",
    "CREATE TRIGGER tr_domestic_rate_responses_immutable\nBEFORE UPDATE OR DELETE ON domestic_rate_responses\nFOR EACH ROW EXECUTE FUNCTION reject_domestic_rate_evidence_mutation()",
    "CREATE FUNCTION validate_domestic_rate_offer_insert() RETURNS trigger AS $$\nDECLARE kind varchar; planned date; response_completion_txid bigint;\nBEGIN\n    SELECT response.result_kind,attempt.planned_ship_date,response.completion_txid\n      INTO kind,planned,response_completion_txid\n      FROM domestic_rate_responses response\n      JOIN domestic_rate_attempts attempt ON attempt.id=response.attempt_id\n     WHERE response.id=NEW.response_id FOR KEY SHARE OF response,attempt;\n    NEW.completion_txid := txid_current();\n    NEW.created_at := statement_timestamp();\n    IF NOT FOUND OR kind<>'success' THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='no-service response cannot contain offers';\n    END IF;\n    IF NEW.completion_txid IS DISTINCT FROM response_completion_txid THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate response offer set is immutable';\n    END IF;\n    IF NEW.delivery_date IS NOT NULL AND NEW.delivery_date<=planned\n       OR NEW.transit_days IS NOT NULL AND NEW.delivery_date IS NOT NULL\n          AND (NEW.delivery_date<planned+NEW.transit_days\n               OR NEW.delivery_date>planned+NEW.transit_days+7) THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate offer delivery facts are invalid';\n    END IF;\n    RETURN NEW;\nEND; $$ LANGUAGE plpgsql",
    "CREATE TRIGGER tr_domestic_rate_offers_insert\nBEFORE INSERT ON domestic_rate_offers\nFOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_offer_insert()",
    "CREATE TRIGGER tr_domestic_rate_offers_immutable\nBEFORE UPDATE OR DELETE ON domestic_rate_offers\nFOR EACH ROW EXECUTE FUNCTION reject_domestic_rate_evidence_mutation()",
    "CREATE FUNCTION validate_domestic_rate_response_offers() RETURNS trigger AS $$\nDECLARE response_id_value uuid; kind varchar; offer_count integer;\nBEGIN\n    IF TG_TABLE_NAME='domestic_rate_responses' THEN\n        response_id_value := COALESCE(NEW.id,OLD.id);\n    ELSE\n        response_id_value := COALESCE(NEW.response_id,OLD.response_id);\n    END IF;\n    SELECT result_kind INTO kind FROM domestic_rate_responses WHERE id=response_id_value;\n    IF NOT FOUND THEN RETURN NULL; END IF;\n    SELECT count(*) INTO offer_count FROM domestic_rate_offers WHERE response_id=response_id_value;\n    IF kind='success' AND offer_count=0 THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='success response requires at least one offer';\n    ELSIF kind='no_service' AND offer_count<>0 THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='no-service response cannot contain offers';\n    END IF;\n    RETURN NULL;\nEND; $$ LANGUAGE plpgsql",
    "CREATE CONSTRAINT TRIGGER tr_domestic_rate_responses_offer_shape\nAFTER INSERT OR UPDATE OR DELETE ON domestic_rate_responses\nDEFERRABLE INITIALLY DEFERRED\nFOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_response_offers()",
    "CREATE CONSTRAINT TRIGGER tr_domestic_rate_offers_response_shape\nAFTER INSERT OR UPDATE OR DELETE ON domestic_rate_offers\nDEFERRABLE INITIALLY DEFERRED\nFOR EACH ROW EXECUTE FUNCTION validate_domestic_rate_response_offers()",
)
_DROP_FUNCTION_DDLS = (
    "DROP FUNCTION IF EXISTS validate_domestic_rate_response_offers() CASCADE",
    "DROP FUNCTION IF EXISTS validate_domestic_rate_offer_insert() CASCADE",
    "DROP FUNCTION IF EXISTS reject_domestic_rate_evidence_mutation() CASCADE",
    "DROP FUNCTION IF EXISTS validate_domestic_rate_response_insert() CASCADE",
    "DROP FUNCTION IF EXISTS validate_domestic_rate_attempt_response_shape() CASCADE",
    "DROP FUNCTION IF EXISTS validate_domestic_rate_attempt_mutation() CASCADE",
    "DROP FUNCTION IF EXISTS validate_domestic_rate_attempt_insert() CASCADE",
    "DROP FUNCTION IF EXISTS validate_outbound_intent_rate_guard_write() CASCADE",
)
_RESTORE_OUTBOUND_INVALIDATION_DDL = "CREATE OR REPLACE FUNCTION validate_outbound_intent_invalidation_insert() RETURNS trigger AS $$\nDECLARE package_id_value uuid; seal_id_value uuid; intent_created_at timestamptz;\nBEGIN\n    SELECT package_id,seal_id,created_at INTO package_id_value,seal_id_value,intent_created_at\n      FROM outbound_shipment_intents WHERE id=NEW.intent_id;\n    IF NOT FOUND THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent does not exist';\n    END IF;\n    PERFORM 1 FROM hub_package_seals WHERE id=seal_id_value FOR UPDATE;\n    PERFORM 1 FROM hub_packages WHERE id=package_id_value FOR UPDATE;\n    IF EXISTS (\n        SELECT 1 FROM custody_events e JOIN outbound_shipment_intents i\n          ON i.package_id=e.package_id AND i.package_version=e.package_version\n         WHERE i.id=NEW.intent_id AND e.event_type IN ('released','tendered','provider_accepted')\n    ) THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent cannot invalidate after custody handoff';\n    END IF;\n    IF NEW.invalidated_at < intent_created_at OR NEW.invalidated_at > clock_timestamp()\n       OR NEW.created_at < NEW.invalidated_at OR NEW.created_at > clock_timestamp() THEN\n        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='outbound intent invalidation chronology is invalid';\n    END IF;\n    RETURN NEW;\nEND; $$ LANGUAGE plpgsql"


def upgrade() -> None:
    for statement in _DESTINATION_SNAPSHOT_UPGRADE_DDLS:
        op.execute(statement)
    for statement in _CREATE_TABLE_SQL:
        op.execute(statement)
    for statement in _CREATE_INDEX_SQL:
        op.execute(statement)
    for statement in _TRIGGER_DDLS:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DROP_FUNCTION_DDLS:
        op.execute(statement)
    op.execute(_RESTORE_OUTBOUND_INVALIDATION_DDL)
    op.drop_table("domestic_rate_offers")
    op.drop_table("domestic_rate_responses")
    op.drop_table("domestic_rate_attempts")
    op.drop_table("outbound_intent_rate_guards")
    op.execute(_RESTORE_OUTBOUND_INTENT_INSERT_DDL)
    op.execute(
        "ALTER TABLE outbound_shipment_intents "
        "DROP CONSTRAINT ck_outbound_intents_destination_snapshot_hash"
    )
    op.execute(
        "ALTER TABLE outbound_shipment_intents " "DROP COLUMN destination_snapshot_hash"
    )
