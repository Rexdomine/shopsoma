"""Milestone 2 expand persistence.

Revision ID: a0b1c2d3e4f5
Revises: f9d1b3e5a7c9
"""

from alembic import op

revision = "a0b1c2d3e4f5"
down_revision = "f9d1b3e5a7c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
ALTER TABLE orders ADD COLUMN workflow_cohort varchar(40), ADD COLUMN workflow_policy_version varchar(40), ADD COLUMN checkout_access_mode varchar(20), ADD COLUMN checkout_estimate_selection_id uuid, ADD COLUMN checkout_prerequisites_completed_at timestamptz;
ALTER TABLE order_items ADD COLUMN inventory_policy varchar(30), ADD COLUMN inventory_subject_kind varchar(20), ADD COLUMN inventory_subject_id uuid, ADD COLUMN inventory_source_product_id uuid REFERENCES products(id) ON DELETE RESTRICT, ADD COLUMN inventory_source_catalogue_version varchar(100), ADD COLUMN inventory_source_evidence_hash char(64), ADD COLUMN inventory_policy_snapshot_at timestamptz;
ALTER TABLE order_items ADD CONSTRAINT uq_order_items_id_order UNIQUE(id,order_id), ADD CONSTRAINT uq_order_items_id_order_inventory_policy UNIQUE(id,order_id,inventory_policy), ADD CONSTRAINT ck_order_items_inventory_policy CHECK(inventory_policy IS NULL OR inventory_policy IN ('stock_managed','made_to_order')) NOT VALID, ADD CONSTRAINT ck_order_items_inventory_subject CHECK((inventory_policy IS NULL AND inventory_subject_kind IS NULL AND inventory_subject_id IS NULL) OR (inventory_policy='made_to_order' AND inventory_subject_kind IS NULL AND inventory_subject_id IS NULL) OR (inventory_policy='stock_managed' AND inventory_subject_kind IN ('product','product_variant','size_stock') AND inventory_subject_id IS NOT NULL)) NOT VALID, ADD CONSTRAINT ck_order_items_inventory_source CHECK((inventory_source_product_id IS NULL AND inventory_source_catalogue_version IS NULL AND inventory_source_evidence_hash IS NULL AND inventory_policy_snapshot_at IS NULL) OR (inventory_source_product_id IS NOT NULL AND inventory_source_catalogue_version ~ '^[!-~]{1,100}$' AND inventory_source_evidence_hash ~ '^[0-9a-f]{64}$' AND inventory_policy_snapshot_at IS NOT NULL)) NOT VALID;
CREATE TABLE order_workflow_migration_runs(id uuid PRIMARY KEY, compatibility_writer_release_id varchar(100) NOT NULL, compatibility_writer_started_at timestamptz NOT NULL, migration_revision varchar(40) NOT NULL, deployment_identity varchar(200) NOT NULL, high_watermark_created_at timestamptz, high_watermark_order_id uuid, classification_cutover_at timestamptz, validated_constraints varchar(4000), classified_row_count bigint, created_at timestamptz NOT NULL DEFAULT statement_timestamp(), CONSTRAINT ck_order_workflow_migration_runs_identifiers CHECK(compatibility_writer_release_id ~ '^[!-~]{1,100}$' AND migration_revision ~ '^[A-Za-z0-9]{1,40}$' AND deployment_identity ~ '^[!-~]{1,200}$'), CONSTRAINT ck_order_workflow_migration_runs_progress CHECK((high_watermark_created_at IS NULL)=(high_watermark_order_id IS NULL) AND (classified_row_count IS NULL OR classified_row_count>=0)));
CREATE TABLE order_current_owners(order_id uuid PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE, original_customer_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT, current_authenticated_user_id uuid REFERENCES users(id) ON DELETE RESTRICT, claim_capability_id uuid, claim_idempotency_key varchar(200), claimed_at timestamptz, created_at timestamptz NOT NULL DEFAULT statement_timestamp(), row_version integer NOT NULL DEFAULT 1, CONSTRAINT uq_order_current_owners_original UNIQUE(order_id,original_customer_id), CONSTRAINT uq_order_current_owners_claim_capability UNIQUE(claim_capability_id), CONSTRAINT ck_order_current_owners_claim_shape CHECK(row_version>0 AND ((current_authenticated_user_id IS NULL AND claim_capability_id IS NULL AND claim_idempotency_key IS NULL AND claimed_at IS NULL) OR (current_authenticated_user_id IS NOT NULL AND claim_capability_id IS NOT NULL AND claim_idempotency_key ~ '^[!-~]{1,200}$' AND claimed_at IS NOT NULL))));
CREATE TABLE checkout_shipping_estimates(id uuid PRIMARY KEY, order_id uuid NOT NULL REFERENCES orders(id) ON DELETE RESTRICT, customer_id uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT, destination_snapshot_hash char(64) NOT NULL, order_snapshot_hash char(64) NOT NULL, currency char(3) NOT NULL, ttl_seconds integer NOT NULL, expires_at timestamptz NOT NULL, supersedes_estimate_id uuid REFERENCES checkout_shipping_estimates(id) ON DELETE RESTRICT, source_kind varchar(30) NOT NULL, source_reference varchar(200), source_command varchar(100) NOT NULL, idempotency_key varchar(200) NOT NULL, request_fingerprint char(64) NOT NULL, schema_version varchar(40) NOT NULL, created_by_actor_type varchar(20) NOT NULL, created_by_actor_id varchar(200) NOT NULL, created_at timestamptz NOT NULL DEFAULT statement_timestamp(), creation_txid bigint NOT NULL DEFAULT txid_current(), row_version integer NOT NULL DEFAULT 1, CONSTRAINT ck_checkout_shipping_estimates_canonical CHECK(destination_snapshot_hash ~ '^[0-9a-f]{64}$' AND order_snapshot_hash ~ '^[0-9a-f]{64}$' AND request_fingerprint ~ '^[0-9a-f]{64}$' AND currency ~ '^[A-Z]{3}$'), CONSTRAINT ck_checkout_shipping_estimates_lifecycle CHECK(ttl_seconds BETWEEN 300 AND 3600 AND expires_at>created_at AND row_version=1), CONSTRAINT ck_checkout_shipping_estimates_kinds CHECK(source_kind IN ('static_domestic_rate','sandbox_normalized') AND created_by_actor_type IN ('customer','guest_capability','staff')), CONSTRAINT ck_checkout_shipping_estimates_identifiers CHECK(source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$' AND idempotency_key ~ '^[!-~]{1,200}$' AND schema_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,39}$' AND created_by_actor_id ~ '^[!-~]{1,200}$'), CONSTRAINT uq_checkout_shipping_estimates_replay UNIQUE(customer_id,source_command,idempotency_key), CONSTRAINT uq_checkout_shipping_estimates_successor UNIQUE(supersedes_estimate_id), CONSTRAINT uq_checkout_shipping_estimates_order UNIQUE(id,order_id), CONSTRAINT uq_checkout_shipping_estimates_customer UNIQUE(id,customer_id));
CREATE INDEX ix_checkout_shipping_estimates_order_created ON checkout_shipping_estimates(order_id,created_at); CREATE INDEX ix_checkout_shipping_estimates_expires ON checkout_shipping_estimates(expires_at); CREATE INDEX ix_checkout_shipping_estimates_snapshot ON checkout_shipping_estimates(order_snapshot_hash);
CREATE TABLE checkout_shipping_estimate_options(id uuid PRIMARY KEY, estimate_id uuid NOT NULL REFERENCES checkout_shipping_estimates(id) ON DELETE RESTRICT, option_key varchar(100) NOT NULL, service_code varchar(100) NOT NULL, service_label varchar(200) NOT NULL, amount numeric(10,2) NOT NULL, currency char(3) NOT NULL, min_delivery_days integer, max_delivery_days integer, source_rate_id uuid REFERENCES shipping_rates(id) ON DELETE RESTRICT, created_at timestamptz NOT NULL DEFAULT statement_timestamp(), CONSTRAINT ck_checkout_estimate_options_money CHECK(amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric) AND amount>0 AND amount<=99999999.99 AND currency ~ '^[A-Z]{3}$'), CONSTRAINT ck_checkout_estimate_options_identifiers CHECK(option_key ~ '^[!-~]{1,100}$' AND service_code ~ '^[!-~]{1,100}$' AND service_label=btrim(service_label) AND length(service_label) BETWEEN 1 AND 200), CONSTRAINT ck_checkout_estimate_options_delivery CHECK((min_delivery_days IS NULL AND max_delivery_days IS NULL) OR (min_delivery_days>=0 AND min_delivery_days<=max_delivery_days AND max_delivery_days<=365)), CONSTRAINT uq_checkout_estimate_options_key UNIQUE(estimate_id,option_key), CONSTRAINT uq_checkout_estimate_options_estimate UNIQUE(id,estimate_id), CONSTRAINT uq_checkout_estimate_options_rate UNIQUE(estimate_id,source_rate_id)); CREATE INDEX ix_checkout_estimate_options_estimate ON checkout_shipping_estimate_options(estimate_id);
CREATE TABLE checkout_shipping_estimate_selections(id uuid PRIMARY KEY, estimate_id uuid NOT NULL, option_id uuid NOT NULL, order_id uuid NOT NULL, customer_id uuid NOT NULL, selected_by_actor_type varchar(20) NOT NULL, selected_by_actor_id varchar(200) NOT NULL, shipping_amount numeric(10,2) NOT NULL, currency char(3) NOT NULL, source_command varchar(100) NOT NULL, idempotency_key varchar(200) NOT NULL, selected_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT statement_timestamp(), CONSTRAINT fk_checkout_estimate_selections_order FOREIGN KEY(estimate_id,order_id) REFERENCES checkout_shipping_estimates(id,order_id) ON DELETE RESTRICT, CONSTRAINT fk_checkout_estimate_selections_customer FOREIGN KEY(estimate_id,customer_id) REFERENCES checkout_shipping_estimates(id,customer_id) ON DELETE RESTRICT, CONSTRAINT fk_checkout_estimate_selections_option FOREIGN KEY(option_id,estimate_id) REFERENCES checkout_shipping_estimate_options(id,estimate_id) ON DELETE RESTRICT, CONSTRAINT ck_checkout_estimate_selections_money CHECK(shipping_amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric) AND shipping_amount>0 AND shipping_amount<=99999999.99 AND currency ~ '^[A-Z]{3}$'), CONSTRAINT ck_checkout_estimate_selections_identifiers CHECK(selected_by_actor_type IN ('customer','guest_capability') AND selected_by_actor_id ~ '^[!-~]{1,200}$' AND source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$' AND idempotency_key ~ '^[!-~]{1,200}$'), CONSTRAINT uq_checkout_estimate_selections_estimate UNIQUE(estimate_id), CONSTRAINT uq_checkout_estimate_selections_order UNIQUE(order_id), CONSTRAINT uq_checkout_estimate_selections_replay UNIQUE(customer_id,source_command,idempotency_key), CONSTRAINT uq_checkout_estimate_selections_id_order UNIQUE(id,order_id));
ALTER TABLE orders ADD CONSTRAINT fk_orders_checkout_estimate_selection FOREIGN KEY(checkout_estimate_selection_id,id) REFERENCES checkout_shipping_estimate_selections(id,order_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED NOT VALID;
CREATE TABLE order_guest_capabilities(id uuid PRIMARY KEY, order_id uuid NOT NULL, original_customer_id uuid NOT NULL, scope varchar(40) NOT NULL, token_digest bytea NOT NULL, pepper_key_version smallint NOT NULL, expires_at timestamptz NOT NULL, revoked_at timestamptz, replaced_by_id uuid REFERENCES order_guest_capabilities(id) ON DELETE RESTRICT, claimed_by_user_id uuid REFERENCES users(id) ON DELETE RESTRICT, claimed_at timestamptz, created_at timestamptz NOT NULL DEFAULT statement_timestamp(), last_used_at timestamptz, row_version integer NOT NULL DEFAULT 1, CONSTRAINT fk_order_guest_capabilities_owner FOREIGN KEY(order_id,original_customer_id) REFERENCES order_current_owners(order_id,original_customer_id) ON DELETE RESTRICT, CONSTRAINT ck_order_guest_capabilities_canonical CHECK(scope IN ('checkout_prerequisites','read_order','claim_order') AND octet_length(token_digest)=32 AND pepper_key_version>0 AND row_version>0 AND expires_at>created_at AND expires_at<=created_at+interval '30 days'), CONSTRAINT ck_order_guest_capabilities_claim CHECK((claimed_by_user_id IS NULL AND claimed_at IS NULL) OR (claimed_by_user_id IS NOT NULL AND claimed_at IS NOT NULL AND revoked_at IS NOT NULL)), CONSTRAINT uq_order_guest_capabilities_digest_version UNIQUE(token_digest,pepper_key_version), CONSTRAINT uq_order_guest_capabilities_replacement UNIQUE(replaced_by_id)); CREATE INDEX ix_order_guest_capabilities_scope_expiry ON order_guest_capabilities(order_id,scope,expires_at);
ALTER TABLE order_current_owners ADD CONSTRAINT fk_order_current_owners_claim_capability FOREIGN KEY(claim_capability_id) REFERENCES order_guest_capabilities(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED NOT VALID;
ALTER TABLE stock_reservations ADD COLUMN workflow_cohort varchar(40), ADD COLUMN checkout_estimate_selection_id uuid, ADD COLUMN inventory_subject_kind varchar(20), ADD COLUMN inventory_subject_id uuid; ALTER TABLE stock_reservations ALTER COLUMN quote_id DROP NOT NULL, ALTER COLUMN quote_selection_id DROP NOT NULL, ALTER COLUMN quote_option_id DROP NOT NULL, ALTER COLUMN intent_id DROP NOT NULL; ALTER TABLE stock_reservations ADD CONSTRAINT fk_stock_reservations_order_item FOREIGN KEY(order_item_id,order_id) REFERENCES order_items(id,order_id) ON DELETE RESTRICT NOT VALID, ADD CONSTRAINT fk_stock_reservations_checkout_selection FOREIGN KEY(checkout_estimate_selection_id,order_id) REFERENCES checkout_shipping_estimate_selections(id,order_id) ON DELETE RESTRICT NOT VALID, ADD CONSTRAINT uq_stock_reservations_checkout_membership_target UNIQUE(id,order_id,order_item_id,checkout_estimate_selection_id), ADD CONSTRAINT ck_stock_reservations_workflow_cohort CHECK(workflow_cohort IS NULL OR workflow_cohort IN ('legacy_pre_bridge','legacy_ambiguous_quarantined','domestic_checkout_v1')) NOT VALID, ADD CONSTRAINT ck_stock_reservations_binding_family CHECK(workflow_cohort IS NULL OR (workflow_cohort='legacy_pre_bridge' AND checkout_estimate_selection_id IS NULL AND quote_id IS NOT NULL AND quote_selection_id IS NOT NULL AND quote_option_id IS NOT NULL AND intent_id IS NOT NULL) OR (workflow_cohort='domestic_checkout_v1' AND checkout_estimate_selection_id IS NOT NULL AND quote_id IS NULL AND quote_selection_id IS NULL AND quote_option_id IS NULL AND intent_id IS NULL AND inventory_subject_kind IN ('product','product_variant','size_stock') AND inventory_subject_id IS NOT NULL)) NOT VALID, ADD CONSTRAINT ck_stock_reservations_checkout_money CHECK(workflow_cohort IS NULL OR workflow_cohort<>'domestic_checkout_v1' OR (unit_price=round(unit_price,2) AND line_amount=round(line_amount,2) AND unit_price<=99999999.99 AND line_amount<=99999999.99)) NOT VALID;
ALTER TABLE payment_attempts ADD COLUMN workflow_cohort varchar(40), ADD COLUMN checkout_estimate_selection_id uuid; ALTER TABLE payment_attempts ALTER COLUMN quote_id DROP NOT NULL, ALTER COLUMN quote_selection_id DROP NOT NULL, ALTER COLUMN quote_option_id DROP NOT NULL, ALTER COLUMN intent_id DROP NOT NULL; ALTER TABLE payment_attempts ADD CONSTRAINT fk_payment_attempts_checkout_selection FOREIGN KEY(checkout_estimate_selection_id,order_id) REFERENCES checkout_shipping_estimate_selections(id,order_id) ON DELETE RESTRICT NOT VALID, ADD CONSTRAINT uq_payment_attempts_checkout_membership_target UNIQUE(id,order_id,checkout_estimate_selection_id), ADD CONSTRAINT ck_payment_attempts_binding_family CHECK((workflow_cohort='legacy_pre_bridge' AND checkout_estimate_selection_id IS NULL AND quote_id IS NOT NULL AND quote_selection_id IS NOT NULL AND quote_option_id IS NOT NULL AND intent_id IS NOT NULL) OR (workflow_cohort='domestic_checkout_v1' AND checkout_estimate_selection_id IS NOT NULL AND quote_id IS NULL AND quote_selection_id IS NULL AND quote_option_id IS NULL AND intent_id IS NULL)) NOT VALID, ADD CONSTRAINT ck_payment_attempts_checkout_money CHECK(workflow_cohort<>'domestic_checkout_v1' OR (amount=round(amount,2) AND amount<=99999999.99)) NOT VALID;
ALTER TABLE payment_attempt_reservations ADD COLUMN membership_family varchar(30) NOT NULL DEFAULT 'legacy_f9', ADD COLUMN order_id uuid, ADD COLUMN order_item_id uuid, ADD COLUMN checkout_estimate_selection_id uuid;
CREATE TABLE order_inventory_coverage(order_item_id uuid PRIMARY KEY, order_id uuid NOT NULL, checkout_estimate_selection_id uuid NOT NULL, inventory_policy varchar(30) NOT NULL, reservation_id uuid, created_at timestamptz NOT NULL DEFAULT statement_timestamp(), CONSTRAINT fk_order_inventory_coverage_item FOREIGN KEY(order_item_id,order_id,inventory_policy) REFERENCES order_items(id,order_id,inventory_policy) ON DELETE RESTRICT, CONSTRAINT fk_order_inventory_coverage_selection FOREIGN KEY(checkout_estimate_selection_id,order_id) REFERENCES checkout_shipping_estimate_selections(id,order_id) ON DELETE RESTRICT, CONSTRAINT fk_order_inventory_coverage_reservation FOREIGN KEY(reservation_id,order_id,order_item_id,checkout_estimate_selection_id) REFERENCES stock_reservations(id,order_id,order_item_id,checkout_estimate_selection_id) ON DELETE RESTRICT, CONSTRAINT ck_order_inventory_coverage_binding CHECK(inventory_policy IN ('stock_managed','made_to_order') AND ((inventory_policy='stock_managed' AND reservation_id IS NOT NULL) OR (inventory_policy='made_to_order' AND reservation_id IS NULL))), CONSTRAINT uq_order_inventory_coverage_order_item UNIQUE(order_id,order_item_id)); CREATE INDEX ix_order_inventory_coverage_policy ON order_inventory_coverage(order_id,inventory_policy);
"""
    )
    op.execute(
        r"""
CREATE FUNCTION validate_domestic_checkout_membership_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE attempt_binding record; reservation_binding record;
BEGIN
 SELECT order_id,checkout_estimate_selection_id INTO attempt_binding FROM payment_attempts WHERE id=NEW.attempt_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'domestic checkout membership attempt is missing'; END IF;
 SELECT order_id,order_item_id,checkout_estimate_selection_id INTO reservation_binding FROM stock_reservations WHERE id=NEW.reservation_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'domestic checkout membership reservation is missing'; END IF;
 IF NEW.order_id IS NULL OR NEW.order_item_id IS NULL OR NEW.checkout_estimate_selection_id IS NULL
    OR attempt_binding.order_id IS DISTINCT FROM NEW.order_id
    OR attempt_binding.checkout_estimate_selection_id IS DISTINCT FROM NEW.checkout_estimate_selection_id
    OR reservation_binding.order_id IS DISTINCT FROM NEW.order_id
    OR reservation_binding.order_item_id IS DISTINCT FROM NEW.order_item_id
    OR reservation_binding.checkout_estimate_selection_id IS DISTINCT FROM NEW.checkout_estimate_selection_id
 THEN RAISE EXCEPTION 'domestic checkout membership binding is invalid'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_payment_attempt_reservations_validate_domestic BEFORE INSERT ON payment_attempt_reservations FOR EACH ROW WHEN (NEW.membership_family='domestic_checkout_v1') EXECUTE FUNCTION validate_domestic_checkout_membership_write();
DROP TRIGGER trg_stock_reservations_validate ON stock_reservations;
CREATE TRIGGER trg_stock_reservations_validate_legacy_insert BEFORE INSERT ON stock_reservations FOR EACH ROW WHEN (NEW.workflow_cohort IS DISTINCT FROM 'domestic_checkout_v1') EXECUTE FUNCTION validate_stock_reservation_write();
CREATE TRIGGER trg_stock_reservations_validate_legacy_update BEFORE UPDATE ON stock_reservations FOR EACH ROW WHEN (OLD.workflow_cohort IS DISTINCT FROM 'domestic_checkout_v1' AND NEW.workflow_cohort IS DISTINCT FROM 'domestic_checkout_v1') EXECUTE FUNCTION validate_stock_reservation_write();
CREATE TRIGGER trg_stock_reservations_validate_delete BEFORE DELETE ON stock_reservations FOR EACH ROW EXECUTE FUNCTION validate_stock_reservation_write();
CREATE FUNCTION validate_domestic_checkout_reservation_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item record; now_at timestamptz := statement_timestamp();
BEGIN
 IF TG_OP='UPDATE' THEN
  IF OLD.state<>'active' THEN RAISE EXCEPTION 'stock reservation is terminal'; END IF;
  IF NEW.id IS DISTINCT FROM OLD.id OR NEW.order_id IS DISTINCT FROM OLD.order_id
     OR NEW.order_item_id IS DISTINCT FROM OLD.order_item_id
     OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
     OR NEW.workflow_cohort IS DISTINCT FROM OLD.workflow_cohort
     OR NEW.checkout_estimate_selection_id IS DISTINCT FROM OLD.checkout_estimate_selection_id
     OR NEW.quote_id IS DISTINCT FROM OLD.quote_id
     OR NEW.quote_selection_id IS DISTINCT FROM OLD.quote_selection_id
     OR NEW.quote_option_id IS DISTINCT FROM OLD.quote_option_id
     OR NEW.intent_id IS DISTINCT FROM OLD.intent_id
     OR NEW.inventory_subject_kind IS DISTINCT FROM OLD.inventory_subject_kind
     OR NEW.inventory_subject_id IS DISTINCT FROM OLD.inventory_subject_id
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
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
  THEN RAISE EXCEPTION 'stock reservation identity is immutable'; END IF;
  IF NEW.state NOT IN ('released','consumed','expired')
     OR NEW.row_version<>OLD.row_version+1
     OR NEW.terminal_at IS NOT NULL
  THEN RAISE EXCEPTION 'stock reservation transition is illegal'; END IF;
  IF NEW.terminal_reason IS NULL OR btrim(NEW.terminal_reason)=''
  THEN RAISE EXCEPTION 'stock reservation terminal reason required'; END IF;
  IF NEW.state IN ('released','expired') AND EXISTS(
      SELECT 1 FROM payment_attempt_reservations ar
      JOIN payment_attempts pa ON pa.id=ar.attempt_id
      WHERE ar.reservation_id=OLD.id
        AND pa.state IN ('pending','call_started','abandoned_unknown'))
  THEN RAISE EXCEPTION 'reservation set is locked by active payment attempt'; END IF;
  IF NEW.state IN ('released','expired') AND EXISTS(
      SELECT 1 FROM payment_attempt_reservations ar
      JOIN payment_attempts pa ON pa.id=ar.attempt_id
      WHERE ar.reservation_id=OLD.id AND pa.state='verified')
  THEN RAISE EXCEPTION 'stock reservation cannot be released after verified payment'; END IF;
  now_at:=clock_timestamp();
  IF NEW.state='expired' AND now_at<OLD.expires_at
  THEN RAISE EXCEPTION 'stock reservation expiry has not elapsed'; END IF;
  IF NEW.state='consumed' AND NOT EXISTS(
      SELECT 1 FROM payment_attempt_reservations ar
      JOIN payment_attempts pa ON pa.id=ar.attempt_id
      WHERE ar.reservation_id=OLD.id AND pa.state='verified')
  THEN RAISE EXCEPTION 'stock reservation consumption requires verified payment'; END IF;
  NEW.terminal_at:=now_at; NEW.updated_at:=now_at; RETURN NEW;
 END IF;
 IF NEW.state<>'active' OR NEW.terminal_at IS NOT NULL OR NEW.terminal_reason IS NOT NULL
    OR NEW.workflow_cohort<>'domestic_checkout_v1'
 THEN RAISE EXCEPTION 'stock reservation must start active'; END IF;
 SELECT oi.order_id,oi.product_id,oi.variant_id,oi.quantity,oi.unit_price,oi.currency,
        oi.inventory_policy,oi.inventory_subject_kind,oi.inventory_subject_id,
        o.customer_id,o.workflow_cohort
   INTO item
   FROM order_items oi JOIN orders o ON o.id=oi.order_id
  WHERE oi.id=NEW.order_item_id AND oi.order_id=NEW.order_id
  FOR UPDATE OF oi;
 IF NOT FOUND OR item.workflow_cohort<>'domestic_checkout_v1'
    OR item.customer_id<>NEW.customer_id OR item.inventory_policy<>'stock_managed'
    OR item.inventory_subject_kind<>NEW.inventory_subject_kind
    OR item.inventory_subject_id<>NEW.inventory_subject_id
    OR item.product_id<>NEW.product_id OR item.variant_id IS DISTINCT FROM NEW.variant_id
    OR item.quantity<>NEW.quantity OR item.unit_price<>NEW.unit_price
    OR item.currency<>NEW.currency OR NEW.line_amount<>NEW.unit_price*NEW.quantity
    OR (NEW.inventory_subject_kind='product' AND (NEW.inventory_subject_id<>NEW.product_id OR NEW.variant_id IS NOT NULL OR NEW.size_stock_id IS NOT NULL))
    OR (NEW.inventory_subject_kind='product_variant' AND (NEW.inventory_subject_id IS DISTINCT FROM NEW.variant_id OR NEW.variant_id IS NULL OR NEW.size_stock_id IS NOT NULL))
    OR (NEW.inventory_subject_kind='size_stock' AND (NEW.inventory_subject_id IS DISTINCT FROM NEW.size_stock_id OR NEW.size_stock_id IS NULL))
 THEN RAISE EXCEPTION 'domestic checkout reservation subject binding is invalid'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_stock_reservations_validate_domestic_insert BEFORE INSERT ON stock_reservations FOR EACH ROW WHEN (NEW.workflow_cohort='domestic_checkout_v1') EXECUTE FUNCTION validate_domestic_checkout_reservation_write();
CREATE TRIGGER trg_stock_reservations_validate_domestic_update BEFORE UPDATE ON stock_reservations FOR EACH ROW WHEN (OLD.workflow_cohort='domestic_checkout_v1' OR NEW.workflow_cohort='domestic_checkout_v1') EXECUTE FUNCTION validate_domestic_checkout_reservation_write();
DROP TRIGGER trg_payment_attempts_validate ON payment_attempts;
CREATE TRIGGER trg_payment_attempts_validate_legacy_insert BEFORE INSERT ON payment_attempts FOR EACH ROW WHEN (NEW.workflow_cohort IS DISTINCT FROM 'domestic_checkout_v1') EXECUTE FUNCTION validate_payment_attempt_write();
CREATE TRIGGER trg_payment_attempts_validate_legacy_update BEFORE UPDATE ON payment_attempts FOR EACH ROW WHEN (OLD.workflow_cohort IS DISTINCT FROM 'domestic_checkout_v1' AND NEW.workflow_cohort IS DISTINCT FROM 'domestic_checkout_v1') EXECUTE FUNCTION validate_payment_attempt_write();
CREATE TRIGGER trg_payment_attempts_validate_delete BEFORE DELETE ON payment_attempts FOR EACH ROW EXECUTE FUNCTION validate_payment_attempt_write();
CREATE FUNCTION validate_domestic_checkout_payment_attempt_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE authoritative record; earliest_reservation_expiry timestamptz; now_at timestamptz := clock_timestamp();
DECLARE evidence record; previous_evidence record; presented_lease_token text;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF OLD.state NOT IN ('pending','call_started','abandoned_unknown')
  THEN RAISE EXCEPTION 'payment attempt is terminal'; END IF;
  IF OLD.state='abandoned_unknown' AND NEW.state NOT IN ('failed','verified')
  THEN RAISE EXCEPTION 'unknown payment attempt requires definitive reconciliation'; END IF;
  IF NEW.id IS DISTINCT FROM OLD.id OR NEW.order_id IS DISTINCT FROM OLD.order_id
     OR NEW.customer_id IS DISTINCT FROM OLD.customer_id
     OR NEW.workflow_cohort IS DISTINCT FROM OLD.workflow_cohort
     OR NEW.checkout_estimate_selection_id IS DISTINCT FROM OLD.checkout_estimate_selection_id
     OR NEW.quote_id IS DISTINCT FROM OLD.quote_id
     OR NEW.quote_selection_id IS DISTINCT FROM OLD.quote_selection_id
     OR NEW.quote_option_id IS DISTINCT FROM OLD.quote_option_id
     OR NEW.intent_id IS DISTINCT FROM OLD.intent_id
     OR NEW.amount IS DISTINCT FROM OLD.amount OR NEW.currency IS DISTINCT FROM OLD.currency
     OR NEW.provider IS DISTINCT FROM OLD.provider
     OR NEW.provider_reference IS DISTINCT FROM OLD.provider_reference
     OR NEW.payment_window_seconds IS DISTINCT FROM OLD.payment_window_seconds
     OR NEW.authorization_grace_seconds IS DISTINCT FROM OLD.authorization_grace_seconds
     OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
     OR NEW.authorization_deadline_at IS DISTINCT FROM OLD.authorization_deadline_at
     OR NEW.claim_ttl_seconds IS DISTINCT FROM OLD.claim_ttl_seconds
     OR NEW.supersedes_attempt_id IS DISTINCT FROM OLD.supersedes_attempt_id
     OR NEW.source_command IS DISTINCT FROM OLD.source_command
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
     OR NEW.creation_txid IS DISTINCT FROM OLD.creation_txid
     OR NEW.created_at IS DISTINCT FROM OLD.created_at
  THEN RAISE EXCEPTION 'payment attempt identity is immutable'; END IF;
  IF NEW.row_version<>OLD.row_version+1
  THEN RAISE EXCEPTION 'payment attempt transition is illegal'; END IF;
  IF NEW.call_started_at IS DISTINCT FROM OLD.call_started_at
     AND NOT (OLD.state='pending' AND NEW.state='call_started')
  THEN RAISE EXCEPTION 'payment attempt call start audit is immutable'; END IF;
  IF OLD.state='pending' AND NEW.state='call_started' THEN
   IF NEW.lease_token IS NULL OR NEW.terminal_evidence_id IS NOT NULL
      OR NEW.terminal_at IS NOT NULL
   THEN RAISE EXCEPTION 'payment attempt lease token required'; END IF;
   SELECT o.fulfillment_status,o.payment_status INTO authoritative
     FROM orders o
     JOIN checkout_shipping_estimate_selections s
       ON s.id=OLD.checkout_estimate_selection_id AND s.order_id=o.id
    WHERE o.id=OLD.order_id AND s.customer_id=OLD.customer_id FOR UPDATE OF o;
   IF NOT FOUND OR authoritative.fulfillment_status='cancelled'
   THEN RAISE EXCEPTION 'cancelled order cannot start payment call'; END IF;
   IF authoritative.payment_status='PAID'
   THEN RAISE EXCEPTION 'paid order cannot start payment call'; END IF;
   PERFORM 1 FROM stock_reservations sr
     JOIN payment_attempt_reservations ar ON ar.reservation_id=sr.id
    WHERE ar.attempt_id=OLD.id ORDER BY sr.id FOR UPDATE OF sr;
   now_at:=clock_timestamp();
   IF now_at>=OLD.expires_at OR NOT EXISTS(
       SELECT 1 FROM payment_attempt_reservations ar WHERE ar.attempt_id=OLD.id)
      OR EXISTS(
       SELECT 1 FROM payment_attempt_reservations ar
       JOIN stock_reservations sr ON sr.id=ar.reservation_id
       WHERE ar.attempt_id=OLD.id AND (
        ar.membership_family<>'domestic_checkout_v1'
        OR ar.order_id IS DISTINCT FROM OLD.order_id
        OR ar.checkout_estimate_selection_id IS DISTINCT FROM OLD.checkout_estimate_selection_id
        OR sr.order_id IS DISTINCT FROM OLD.order_id
        OR sr.checkout_estimate_selection_id IS DISTINCT FROM OLD.checkout_estimate_selection_id
        OR sr.state<>'active' OR sr.expires_at<=now_at))
      OR EXISTS(
       SELECT 1 FROM stock_reservations sr
       WHERE sr.order_id=OLD.order_id
         AND sr.checkout_estimate_selection_id=OLD.checkout_estimate_selection_id
         AND sr.workflow_cohort='domestic_checkout_v1'
         AND sr.state='active' AND sr.expires_at>now_at
         AND NOT EXISTS(SELECT 1 FROM payment_attempt_reservations ar
                        WHERE ar.attempt_id=OLD.id AND ar.reservation_id=sr.id))
   THEN RAISE EXCEPTION 'payment call requires live authoritative reservations'; END IF;
   NEW.call_started_at:=now_at;
   NEW.claim_expires_at:=now_at+NEW.claim_ttl_seconds*interval '1 second';
   NEW.updated_at:=now_at; RETURN NEW;
  END IF;
  IF OLD.state='pending' AND NEW.state='expired' THEN
   now_at:=clock_timestamp();
   IF now_at<OLD.expires_at THEN RAISE EXCEPTION 'payment attempt expiry has not elapsed'; END IF;
   IF NEW.terminal_evidence_id IS NOT NULL OR NEW.terminal_at IS NOT NULL
   THEN RAISE EXCEPTION 'payment attempt transition is illegal'; END IF;
   NEW.lease_token:=NULL; NEW.call_started_at:=NULL; NEW.claim_expires_at:=NULL;
   NEW.terminal_at:=now_at; NEW.updated_at:=now_at; RETURN NEW;
  END IF;
  IF NEW.state IN ('failed','verified','abandoned_unknown') THEN
   IF NEW.terminal_evidence_id IS NULL
      OR NEW.terminal_at IS DISTINCT FROM OLD.terminal_at
   THEN RAISE EXCEPTION 'payment attempt terminal evidence required'; END IF;
   IF OLD.state='call_started' THEN
    presented_lease_token:=current_setting('shopsoma.payment_lease_token',true);
    IF presented_lease_token IS NULL OR presented_lease_token IS DISTINCT FROM OLD.lease_token::text
    THEN RAISE EXCEPTION 'payment lease token does not own claim'; END IF;
   END IF;
   SELECT * INTO evidence FROM payment_attempt_evidence WHERE id=NEW.terminal_evidence_id;
   IF NOT FOUND OR evidence.attempt_id IS DISTINCT FROM OLD.id
      OR evidence.provider IS DISTINCT FROM OLD.provider
      OR evidence.provider_reference IS DISTINCT FROM OLD.provider_reference
   THEN RAISE EXCEPTION 'payment attempt terminal evidence is invalid'; END IF;
   IF evidence.evidence_type IS DISTINCT FROM (CASE NEW.state
       WHEN 'verified' THEN 'payment_verified'
       WHEN 'failed' THEN 'payment_failed' ELSE 'outcome_unknown' END)
   THEN RAISE EXCEPTION 'payment evidence does not match target state'; END IF;
   now_at:=clock_timestamp();
   IF NEW.state='abandoned_unknown' AND (OLD.state<>'call_started'
      OR now_at<OLD.claim_expires_at OR evidence.created_at<OLD.claim_expires_at
      OR evidence.observed_at<OLD.claim_expires_at)
   THEN RAISE EXCEPTION 'payment attempt lease has not expired'; END IF;
   IF NEW.state IN ('failed','verified') AND OLD.state='call_started'
      AND (now_at>=OLD.claim_expires_at OR evidence.created_at<OLD.call_started_at
           OR evidence.observed_at<OLD.call_started_at)
   THEN RAISE EXCEPTION 'payment evidence chronology is invalid'; END IF;
   IF OLD.state='abandoned_unknown' THEN
    SELECT * INTO previous_evidence FROM payment_attempt_evidence
     WHERE id=OLD.terminal_evidence_id;
    IF NEW.terminal_evidence_id=OLD.terminal_evidence_id
       OR evidence.created_at<=OLD.terminal_at OR evidence.observed_at<=OLD.terminal_at
       OR evidence.created_at<=previous_evidence.created_at
       OR evidence.observed_at<=previous_evidence.observed_at
    THEN RAISE EXCEPTION 'definitive reconciliation evidence required'; END IF;
   END IF;
   IF NEW.state='verified' THEN
    IF OLD.state NOT IN ('call_started','abandoned_unknown')
    THEN RAISE EXCEPTION 'payment attempt transition is illegal'; END IF;
    SELECT fulfillment_status,payment_status INTO authoritative FROM orders
     WHERE id=OLD.order_id FOR UPDATE;
    IF NOT FOUND OR authoritative.fulfillment_status='cancelled'
       OR authoritative.payment_status='PAID'
    THEN RAISE EXCEPTION 'order cannot verify payment'; END IF;
    PERFORM 1 FROM stock_reservations sr
     JOIN payment_attempt_reservations ar ON ar.reservation_id=sr.id
     WHERE ar.attempt_id=OLD.id ORDER BY sr.id FOR UPDATE OF sr;
    now_at:=clock_timestamp();
    IF OLD.state='call_started' AND now_at>OLD.authorization_deadline_at
    THEN RAISE EXCEPTION 'payment attempt authorization deadline elapsed'; END IF;
    IF NOT EXISTS(SELECT 1 FROM payment_attempt_reservations WHERE attempt_id=OLD.id)
       OR EXISTS(SELECT 1 FROM payment_attempt_reservations ar
          JOIN stock_reservations sr ON sr.id=ar.reservation_id
          WHERE ar.attempt_id=OLD.id AND (sr.state<>'active'
           OR (sr.expires_at<=now_at AND OLD.call_started_at>=sr.expires_at)))
    THEN RAISE EXCEPTION 'payment verification requires live reservations'; END IF;
   ELSIF NEW.state='abandoned_unknown' AND OLD.state<>'call_started' THEN
    RAISE EXCEPTION 'payment attempt transition is illegal';
   END IF;
   NEW.lease_token:=NULL; NEW.claim_expires_at:=NULL;
   NEW.terminal_at:=now_at; NEW.updated_at:=now_at; RETURN NEW;
  END IF;
  RAISE EXCEPTION 'payment attempt transition is illegal';
 END IF;
 IF NEW.state<>'pending' OR NEW.lease_token IS NOT NULL OR NEW.call_started_at IS NOT NULL
    OR NEW.claim_expires_at IS NOT NULL OR NEW.terminal_evidence_id IS NOT NULL
    OR NEW.terminal_at IS NOT NULL OR NEW.provider IS NULL OR NEW.provider_reference IS NULL
    OR NEW.workflow_cohort<>'domestic_checkout_v1'
 THEN RAISE EXCEPTION 'payment attempt must start pending'; END IF;
 SELECT o.customer_id,o.total_amount,o.currency,o.payment_status,o.fulfillment_status,
        s.order_id AS selection_order_id,s.customer_id AS selection_customer_id
   INTO authoritative
   FROM orders o
   JOIN checkout_shipping_estimate_selections s ON s.id=NEW.checkout_estimate_selection_id
  WHERE o.id=NEW.order_id FOR UPDATE OF o;
 IF NOT FOUND OR authoritative.customer_id<>NEW.customer_id
    OR authoritative.selection_order_id<>NEW.order_id
    OR authoritative.selection_customer_id<>NEW.customer_id
    OR authoritative.total_amount<>NEW.amount OR authoritative.currency<>NEW.currency
    OR authoritative.payment_status='PAID' OR authoritative.fulfillment_status='cancelled'
 THEN RAISE EXCEPTION 'domestic payment attempt binding is invalid'; END IF;
 SELECT min(expires_at) INTO earliest_reservation_expiry FROM stock_reservations
  WHERE order_id=NEW.order_id AND checkout_estimate_selection_id=NEW.checkout_estimate_selection_id
    AND workflow_cohort='domestic_checkout_v1' AND state='active' AND expires_at>now_at;
 IF earliest_reservation_expiry IS NULL THEN RAISE EXCEPTION 'payment attempt requires active reservations'; END IF;
 IF EXISTS(SELECT 1 FROM payment_attempts WHERE order_id=NEW.order_id AND state IN ('pending','call_started'))
 THEN RAISE EXCEPTION 'payment attempt already active for order'; END IF;
 NEW.created_at:=now_at; NEW.updated_at:=now_at;
 NEW.expires_at:=LEAST(now_at+NEW.payment_window_seconds*interval '1 second',earliest_reservation_expiry);
 NEW.authorization_deadline_at:=NEW.expires_at+NEW.authorization_grace_seconds*interval '1 second';
 NEW.row_version:=1; NEW.creation_txid:=txid_current();
 RETURN NEW;
END $$;
CREATE TRIGGER trg_payment_attempts_validate_domestic_insert BEFORE INSERT ON payment_attempts FOR EACH ROW WHEN (NEW.workflow_cohort='domestic_checkout_v1') EXECUTE FUNCTION validate_domestic_checkout_payment_attempt_write();
CREATE TRIGGER trg_payment_attempts_validate_domestic_update BEFORE UPDATE ON payment_attempts FOR EACH ROW WHEN (OLD.workflow_cohort='domestic_checkout_v1' OR NEW.workflow_cohort='domestic_checkout_v1') EXECUTE FUNCTION validate_domestic_checkout_payment_attempt_write();
"""
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM order_workflow_migration_runs) OR EXISTS(SELECT 1 FROM order_guest_capabilities) OR EXISTS(SELECT 1 FROM checkout_shipping_estimates) THEN RAISE EXCEPTION 'refusing destructive Milestone 2 downgrade: compatibility writer or audit data exists'; END IF; END $$"
    )
    op.execute(
        "DROP TRIGGER trg_payment_attempt_reservations_validate_domestic ON payment_attempt_reservations; DROP FUNCTION validate_domestic_checkout_membership_write(); DROP TRIGGER trg_payment_attempts_validate_domestic_update ON payment_attempts; DROP TRIGGER trg_payment_attempts_validate_domestic_insert ON payment_attempts; DROP FUNCTION validate_domestic_checkout_payment_attempt_write(); DROP TRIGGER trg_payment_attempts_validate_delete ON payment_attempts; DROP TRIGGER trg_payment_attempts_validate_legacy_update ON payment_attempts; DROP TRIGGER trg_payment_attempts_validate_legacy_insert ON payment_attempts; CREATE TRIGGER trg_payment_attempts_validate BEFORE INSERT OR UPDATE OR DELETE ON payment_attempts FOR EACH ROW EXECUTE FUNCTION validate_payment_attempt_write(); DROP TRIGGER trg_stock_reservations_validate_domestic_update ON stock_reservations; DROP TRIGGER trg_stock_reservations_validate_domestic_insert ON stock_reservations; DROP FUNCTION validate_domestic_checkout_reservation_write(); DROP TRIGGER trg_stock_reservations_validate_delete ON stock_reservations; DROP TRIGGER trg_stock_reservations_validate_legacy_update ON stock_reservations; DROP TRIGGER trg_stock_reservations_validate_legacy_insert ON stock_reservations; CREATE TRIGGER trg_stock_reservations_validate BEFORE INSERT OR UPDATE OR DELETE ON stock_reservations FOR EACH ROW EXECUTE FUNCTION validate_stock_reservation_write()"
    )
    op.execute(
        r"""
DROP TABLE order_inventory_coverage; ALTER TABLE payment_attempt_reservations DROP COLUMN checkout_estimate_selection_id,DROP COLUMN order_item_id,DROP COLUMN order_id,DROP COLUMN membership_family; ALTER TABLE payment_attempts DROP CONSTRAINT ck_payment_attempts_checkout_money,DROP CONSTRAINT ck_payment_attempts_binding_family,DROP CONSTRAINT uq_payment_attempts_checkout_membership_target,DROP CONSTRAINT fk_payment_attempts_checkout_selection,DROP COLUMN checkout_estimate_selection_id,DROP COLUMN workflow_cohort; ALTER TABLE payment_attempts ALTER COLUMN quote_id SET NOT NULL,ALTER COLUMN quote_selection_id SET NOT NULL,ALTER COLUMN quote_option_id SET NOT NULL,ALTER COLUMN intent_id SET NOT NULL; ALTER TABLE stock_reservations DROP CONSTRAINT ck_stock_reservations_checkout_money,DROP CONSTRAINT ck_stock_reservations_binding_family,DROP CONSTRAINT ck_stock_reservations_workflow_cohort,DROP CONSTRAINT uq_stock_reservations_checkout_membership_target,DROP CONSTRAINT fk_stock_reservations_checkout_selection,DROP CONSTRAINT fk_stock_reservations_order_item,DROP COLUMN inventory_subject_id,DROP COLUMN inventory_subject_kind,DROP COLUMN checkout_estimate_selection_id,DROP COLUMN workflow_cohort; ALTER TABLE stock_reservations ALTER COLUMN quote_id SET NOT NULL,ALTER COLUMN quote_selection_id SET NOT NULL,ALTER COLUMN quote_option_id SET NOT NULL,ALTER COLUMN intent_id SET NOT NULL; ALTER TABLE order_current_owners DROP CONSTRAINT fk_order_current_owners_claim_capability; DROP TABLE order_guest_capabilities; ALTER TABLE orders DROP CONSTRAINT fk_orders_checkout_estimate_selection; DROP TABLE checkout_shipping_estimate_selections; DROP TABLE checkout_shipping_estimate_options; DROP TABLE checkout_shipping_estimates; DROP TABLE order_current_owners; DROP TABLE order_workflow_migration_runs; ALTER TABLE order_items DROP CONSTRAINT ck_order_items_inventory_source,DROP CONSTRAINT ck_order_items_inventory_subject,DROP CONSTRAINT ck_order_items_inventory_policy,DROP CONSTRAINT uq_order_items_id_order_inventory_policy,DROP CONSTRAINT uq_order_items_id_order,DROP COLUMN inventory_policy_snapshot_at,DROP COLUMN inventory_source_evidence_hash,DROP COLUMN inventory_source_catalogue_version,DROP COLUMN inventory_source_product_id,DROP COLUMN inventory_subject_id,DROP COLUMN inventory_subject_kind,DROP COLUMN inventory_policy; ALTER TABLE orders DROP COLUMN checkout_prerequisites_completed_at,DROP COLUMN checkout_estimate_selection_id,DROP COLUMN checkout_access_mode,DROP COLUMN workflow_policy_version,DROP COLUMN workflow_cohort;
"""
    )
