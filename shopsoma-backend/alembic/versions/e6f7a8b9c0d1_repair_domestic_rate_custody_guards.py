"""Repair domestic-rate custody/claim trigger parity for upgraded databases.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
"""

from alembic import op

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None

_UPGRADE_DDLS = (
    r"""CREATE OR REPLACE FUNCTION validate_domestic_rate_attempt_insert() RETURNS trigger AS $$
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
    IF EXISTS (
        SELECT 1 FROM custody_events
         WHERE package_id=NEW.package_id AND package_version=NEW.package_version
           AND event_type IN ('released','tendered','provider_accepted')
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='rate attempt cannot claim after custody handoff';
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
    r"""CREATE OR REPLACE FUNCTION validate_custody_event_insert() RETURNS trigger AS $$
DECLARE stream custody_streams%ROWTYPE; tip_id uuid; tip_time timestamptz; prior_lifecycle varchar; package_state varchar; current_package_version integer; packed_time timestamptz; seal_applied timestamptz; seal_retired timestamptz;
BEGIN
    SELECT * INTO stream FROM custody_streams WHERE id=NEW.stream_id FOR UPDATE;
    IF NOT FOUND OR stream.cohort_id<>NEW.cohort_id OR stream.order_id<>NEW.order_id
       OR stream.vendor_id<>NEW.vendor_id OR stream.hub_id<>NEW.hub_id
       OR stream.package_id<>NEW.package_id OR stream.package_version<>NEW.package_version THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody event aggregate identity is invalid';
    END IF;
    SELECT id, occurred_at INTO tip_id, tip_time FROM custody_events
     WHERE stream_id=NEW.stream_id ORDER BY version DESC LIMIT 1;
    IF NEW.version<>stream.next_version OR NEW.previous_event_id IS DISTINCT FROM tip_id THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody chain fork';
    END IF;
    SELECT event_type INTO prior_lifecycle FROM custody_events
     WHERE stream_id=NEW.stream_id AND event_type<>'correction'
     ORDER BY version DESC LIMIT 1;
    IF NEW.event_type='correction' THEN
        IF prior_lifecycle IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='illegal custody lifecycle transition';
        END IF;
    ELSIF prior_lifecycle IS NULL THEN
        IF NEW.event_type<>'packed' THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='illegal custody lifecycle transition';
        END IF;
    ELSIF NOT (
        (prior_lifecycle='packed' AND NEW.event_type='sealed') OR
        (prior_lifecycle='sealed' AND NEW.event_type='staged') OR
        (prior_lifecycle='staged' AND NEW.event_type='released') OR
        (prior_lifecycle='released' AND NEW.event_type='tendered') OR
        (prior_lifecycle='tendered' AND NEW.event_type='provider_accepted')
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='illegal custody lifecycle transition';
    END IF;
    IF NEW.recorded_at < stream.created_at OR (tip_time IS NOT NULL AND NEW.occurred_at < tip_time)
       OR NEW.recorded_at < NEW.occurred_at OR NEW.recorded_at > clock_timestamp()
       OR NEW.created_at < NEW.recorded_at OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody event chronology is invalid';
    END IF;
    IF NEW.event_type<>'packed' THEN
        SELECT applied_at,retired_at INTO seal_applied,seal_retired
          FROM hub_package_seals WHERE id=NEW.seal_id
           AND package_id=NEW.package_id AND package_version=NEW.package_version
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody seal interval is invalid';
        END IF;
    END IF;
    SELECT p.state,p.current_version,v.packed_at
      INTO package_state,current_package_version,packed_time
      FROM hub_packages p JOIN hub_package_versions v
        ON v.package_id=p.id AND v.version=NEW.package_version
     WHERE p.id=NEW.package_id AND p.order_id=NEW.order_id AND p.hub_id=NEW.hub_id
     FOR UPDATE OF p;
    IF NOT FOUND OR current_package_version<>NEW.package_version
       OR NEW.occurred_at < packed_time
       OR NOT EXISTS (
            SELECT 1 FROM hub_package_items WHERE package_id=NEW.package_id
             AND package_version=NEW.package_version AND cohort_id=NEW.cohort_id
             AND vendor_id=NEW.vendor_id AND order_id=NEW.order_id AND hub_id=NEW.hub_id
       ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody package binding is invalid';
    END IF;
    IF NEW.event_type<>'packed' THEN
        IF package_state NOT IN ('sealed','ready') THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody event requires sealed package truth';
        END IF;
        IF NEW.occurred_at < seal_applied
           OR (seal_retired IS NOT NULL AND NEW.occurred_at > seal_retired) THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody seal interval is invalid';
        END IF;
    END IF;
    IF NEW.event_type IN ('released','tendered','provider_accepted') THEN
        UPDATE domestic_rate_attempts attempt
           SET classification='abandoned',
               failure_code='claim_expired'
          FROM outbound_intent_rate_guards guard
          JOIN outbound_shipment_intents intent ON intent.id=guard.intent_id
         WHERE guard.active_attempt_id=attempt.id
           AND intent.package_id=NEW.package_id
           AND intent.package_version=NEW.package_version
           AND NOT guard.is_invalidated
           AND attempt.classification='pending'
           AND attempt.claim_expires_at IS NOT NULL
           AND clock_timestamp() >= attempt.claim_expires_at;
        PERFORM 1
          FROM outbound_intent_rate_guards guard
          JOIN outbound_shipment_intents intent ON intent.id=guard.intent_id
         WHERE intent.package_id=NEW.package_id
           AND intent.package_version=NEW.package_version
           AND NOT guard.is_invalidated
           AND guard.active_attempt_id IS NOT NULL
         FOR UPDATE OF guard;
        IF FOUND THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody handoff blocked by active rate attempt claim';
        END IF;
    END IF;
    UPDATE custody_streams SET next_version=next_version+1 WHERE id=NEW.stream_id;
    RETURN NEW;
END; $$ LANGUAGE plpgsql""",
)

_DOWNGRADE_DDLS = (
    r"""CREATE OR REPLACE FUNCTION validate_domestic_rate_attempt_insert() RETURNS trigger AS $$
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
    r"""CREATE OR REPLACE FUNCTION validate_custody_event_insert() RETURNS trigger AS $$
DECLARE stream custody_streams%ROWTYPE; tip_id uuid; tip_time timestamptz; prior_lifecycle varchar; package_state varchar; current_package_version integer; packed_time timestamptz; seal_applied timestamptz; seal_retired timestamptz;
BEGIN
    SELECT * INTO stream FROM custody_streams WHERE id=NEW.stream_id FOR UPDATE;
    IF NOT FOUND OR stream.cohort_id<>NEW.cohort_id OR stream.order_id<>NEW.order_id
       OR stream.vendor_id<>NEW.vendor_id OR stream.hub_id<>NEW.hub_id
       OR stream.package_id<>NEW.package_id OR stream.package_version<>NEW.package_version THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody event aggregate identity is invalid';
    END IF;
    SELECT id, occurred_at INTO tip_id, tip_time FROM custody_events
     WHERE stream_id=NEW.stream_id ORDER BY version DESC LIMIT 1;
    IF NEW.version<>stream.next_version OR NEW.previous_event_id IS DISTINCT FROM tip_id THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody chain fork';
    END IF;
    SELECT event_type INTO prior_lifecycle FROM custody_events
     WHERE stream_id=NEW.stream_id AND event_type<>'correction'
     ORDER BY version DESC LIMIT 1;
    IF NEW.event_type='correction' THEN
        IF prior_lifecycle IS NULL THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='illegal custody lifecycle transition';
        END IF;
    ELSIF prior_lifecycle IS NULL THEN
        IF NEW.event_type<>'packed' THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='illegal custody lifecycle transition';
        END IF;
    ELSIF NOT (
        (prior_lifecycle='packed' AND NEW.event_type='sealed') OR
        (prior_lifecycle='sealed' AND NEW.event_type='staged') OR
        (prior_lifecycle='staged' AND NEW.event_type='released') OR
        (prior_lifecycle='released' AND NEW.event_type='tendered') OR
        (prior_lifecycle='tendered' AND NEW.event_type='provider_accepted')
    ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='illegal custody lifecycle transition';
    END IF;
    IF NEW.recorded_at < stream.created_at OR (tip_time IS NOT NULL AND NEW.occurred_at < tip_time)
       OR NEW.recorded_at < NEW.occurred_at OR NEW.recorded_at > clock_timestamp()
       OR NEW.created_at < NEW.recorded_at OR NEW.created_at > clock_timestamp() THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody event chronology is invalid';
    END IF;
    IF NEW.event_type<>'packed' THEN
        SELECT applied_at,retired_at INTO seal_applied,seal_retired
          FROM hub_package_seals WHERE id=NEW.seal_id
           AND package_id=NEW.package_id AND package_version=NEW.package_version
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody seal interval is invalid';
        END IF;
    END IF;
    SELECT p.state,p.current_version,v.packed_at
      INTO package_state,current_package_version,packed_time
      FROM hub_packages p JOIN hub_package_versions v
        ON v.package_id=p.id AND v.version=NEW.package_version
     WHERE p.id=NEW.package_id AND p.order_id=NEW.order_id AND p.hub_id=NEW.hub_id
     FOR UPDATE OF p;
    IF NOT FOUND OR current_package_version<>NEW.package_version
       OR NEW.occurred_at < packed_time
       OR NOT EXISTS (
            SELECT 1 FROM hub_package_items WHERE package_id=NEW.package_id
             AND package_version=NEW.package_version AND cohort_id=NEW.cohort_id
             AND vendor_id=NEW.vendor_id AND order_id=NEW.order_id AND hub_id=NEW.hub_id
       ) THEN
        RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody package binding is invalid';
    END IF;
    IF NEW.event_type<>'packed' THEN
        IF package_state NOT IN ('sealed','ready') THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody event requires sealed package truth';
        END IF;
        IF NEW.occurred_at < seal_applied
           OR (seal_retired IS NOT NULL AND NEW.occurred_at > seal_retired) THEN
            RAISE EXCEPTION USING ERRCODE='23514', MESSAGE='custody seal interval is invalid';
        END IF;
    END IF;
    UPDATE custody_streams SET next_version=next_version+1 WHERE id=NEW.stream_id;
    RETURN NEW;
END; $$ LANGUAGE plpgsql""",
)


def upgrade() -> None:
    for statement in _UPGRADE_DDLS:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE_DDLS:
        op.execute(statement)
