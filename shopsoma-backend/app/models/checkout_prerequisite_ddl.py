"""ORM-owned PostgreSQL programs for Milestone 2 checkout prerequisite truth."""

M2_CHECKOUT_TRIGGER_DDL = r"""
CREATE FUNCTION protect_order_workflow_migration_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN
  RAISE EXCEPTION 'workflow migration run mission truth is immutable';
 END IF;
 IF (OLD.id,OLD.compatibility_writer_release_id,OLD.compatibility_writer_started_at,
     OLD.migration_revision,OLD.deployment_identity,OLD.high_watermark_created_at,
     OLD.high_watermark_order_id,OLD.created_at)
    IS DISTINCT FROM
    (NEW.id,NEW.compatibility_writer_release_id,NEW.compatibility_writer_started_at,
     NEW.migration_revision,NEW.deployment_identity,NEW.high_watermark_created_at,
     NEW.high_watermark_order_id,NEW.created_at) THEN
  RAISE EXCEPTION 'workflow migration run mission truth is immutable';
 END IF;
 IF OLD.classification_cutover_at IS NULL
    AND OLD.validated_constraints IS NULL
    AND OLD.classified_row_count IS NULL
    AND NEW.classification_cutover_at IS NOT NULL
    AND NEW.validated_constraints IS NOT NULL
    AND NEW.classified_row_count IS NOT NULL THEN
  RETURN NEW;
 END IF;
 RAISE EXCEPTION 'workflow migration run finalization is set once';
END $$;
CREATE TRIGGER trg_order_workflow_migration_runs_truth
BEFORE UPDATE OR DELETE ON order_workflow_migration_runs
FOR EACH ROW EXECUTE FUNCTION protect_order_workflow_migration_run();

CREATE FUNCTION validate_checkout_estimate_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE authoritative_order record; predecessor record;
BEGIN
 IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'checkout estimate is immutable audit'; END IF;
 SELECT customer_id,currency,workflow_cohort INTO authoritative_order
 FROM orders WHERE id=NEW.order_id FOR UPDATE;
 IF NOT FOUND OR authoritative_order.customer_id IS DISTINCT FROM NEW.customer_id
    OR authoritative_order.currency IS DISTINCT FROM NEW.currency
    OR authoritative_order.workflow_cohort IS DISTINCT FROM 'domestic_checkout_v1' THEN
  RAISE EXCEPTION 'checkout estimate order truth is invalid';
 END IF;
 IF NEW.supersedes_estimate_id IS NOT NULL THEN
  SELECT * INTO predecessor FROM checkout_shipping_estimates
   WHERE id=NEW.supersedes_estimate_id FOR UPDATE;
  IF NOT FOUND OR predecessor.order_id IS DISTINCT FROM NEW.order_id
     OR predecessor.customer_id IS DISTINCT FROM NEW.customer_id
     OR predecessor.currency IS DISTINCT FROM NEW.currency
     OR EXISTS(SELECT 1 FROM checkout_shipping_estimates WHERE supersedes_estimate_id=predecessor.id)
     OR EXISTS(SELECT 1 FROM checkout_shipping_estimate_selections WHERE estimate_id=predecessor.id) THEN
   RAISE EXCEPTION 'checkout estimate predecessor is not the current unselected leaf';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_checkout_estimates_truth BEFORE INSERT OR UPDATE OR DELETE
ON checkout_shipping_estimates FOR EACH ROW EXECUTE FUNCTION validate_checkout_estimate_write();

CREATE FUNCTION validate_checkout_estimate_option_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE estimate record;
BEGIN
 IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'checkout estimate option is immutable audit'; END IF;
 SELECT currency,source_kind,creation_txid INTO estimate
 FROM checkout_shipping_estimates WHERE id=NEW.estimate_id FOR UPDATE;
 IF NOT FOUND OR estimate.currency IS DISTINCT FROM NEW.currency
    OR estimate.creation_txid IS DISTINCT FROM txid_current()
    OR (estimate.source_kind='static_domestic_rate' AND NEW.source_rate_id IS NULL)
    OR (estimate.source_kind='sandbox_normalized' AND NEW.source_rate_id IS NOT NULL) THEN
  RAISE EXCEPTION 'checkout estimate option truth is invalid';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_checkout_estimate_options_truth BEFORE INSERT OR UPDATE OR DELETE
ON checkout_shipping_estimate_options FOR EACH ROW EXECUTE FUNCTION validate_checkout_estimate_option_write();

CREATE FUNCTION validate_checkout_estimate_selection_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE authoritative_order record; estimate record; selected_option record;
DECLARE database_now timestamptz;
BEGIN
 IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'checkout estimate selection is immutable audit'; END IF;
 SELECT customer_id,currency,workflow_cohort,checkout_estimate_selection_id INTO authoritative_order
 FROM orders WHERE id=NEW.order_id FOR UPDATE;
 SELECT * INTO estimate FROM checkout_shipping_estimates WHERE id=NEW.estimate_id FOR UPDATE;
 database_now:=clock_timestamp();
 SELECT amount,currency INTO selected_option FROM checkout_shipping_estimate_options
 WHERE id=NEW.option_id AND estimate_id=NEW.estimate_id;
 IF authoritative_order.customer_id IS DISTINCT FROM NEW.customer_id
    OR authoritative_order.currency IS DISTINCT FROM NEW.currency
    OR authoritative_order.workflow_cohort IS DISTINCT FROM 'domestic_checkout_v1'
    OR authoritative_order.checkout_estimate_selection_id IS NOT NULL
    OR NOT FOUND OR estimate.order_id IS DISTINCT FROM NEW.order_id
    OR estimate.customer_id IS DISTINCT FROM NEW.customer_id
    OR estimate.currency IS DISTINCT FROM NEW.currency
    OR estimate.expires_at <= database_now
    OR NEW.selected_at < estimate.created_at OR NEW.selected_at > database_now
    OR selected_option.amount IS DISTINCT FROM NEW.shipping_amount
    OR selected_option.currency IS DISTINCT FROM NEW.currency
    OR EXISTS(SELECT 1 FROM checkout_shipping_estimates WHERE supersedes_estimate_id=estimate.id)
    OR EXISTS(SELECT 1 FROM checkout_shipping_estimate_selections WHERE estimate_id=estimate.id) THEN
  RAISE EXCEPTION 'checkout estimate selection truth is invalid';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_checkout_estimate_selections_truth BEFORE INSERT OR UPDATE OR DELETE
ON checkout_shipping_estimate_selections FOR EACH ROW EXECUTE FUNCTION validate_checkout_estimate_selection_write();

CREATE FUNCTION validate_order_item_inventory_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source_product uuid; domestic boolean;
BEGIN
 IF TG_OP='UPDATE' THEN
  IF (OLD.inventory_policy,OLD.inventory_subject_kind,OLD.inventory_subject_id,
      OLD.inventory_source_product_id,OLD.inventory_source_catalogue_version,
      OLD.inventory_source_evidence_hash,OLD.inventory_policy_snapshot_at)
     IS DISTINCT FROM
     (NEW.inventory_policy,NEW.inventory_subject_kind,NEW.inventory_subject_id,
      NEW.inventory_source_product_id,NEW.inventory_source_catalogue_version,
      NEW.inventory_source_evidence_hash,NEW.inventory_policy_snapshot_at)
     AND NOT (OLD.inventory_policy IS NULL AND OLD.inventory_subject_kind IS NULL
              AND OLD.inventory_subject_id IS NULL AND OLD.inventory_source_product_id IS NULL
              AND OLD.inventory_source_catalogue_version IS NULL
              AND OLD.inventory_source_evidence_hash IS NULL
              AND OLD.inventory_policy_snapshot_at IS NULL) THEN
   RAISE EXCEPTION 'order item inventory snapshot is immutable';
  END IF;
 END IF;
 SELECT workflow_cohort='domestic_checkout_v1' INTO domestic
 FROM orders WHERE id=NEW.order_id FOR UPDATE;
 IF domestic AND (NEW.inventory_policy IS NULL OR NEW.inventory_source_product_id IS NULL
    OR NEW.inventory_source_product_id IS DISTINCT FROM NEW.product_id) THEN
  IF TG_OP<>'INSERT' OR NEW.inventory_policy IS NOT NULL
     OR NEW.inventory_subject_kind IS NOT NULL OR NEW.inventory_subject_id IS NOT NULL
     OR NEW.inventory_source_product_id IS NOT NULL
     OR NEW.inventory_source_catalogue_version IS NOT NULL
     OR NEW.inventory_source_evidence_hash IS NOT NULL
     OR NEW.inventory_policy_snapshot_at IS NOT NULL THEN
   RAISE EXCEPTION 'order item inventory snapshot is incomplete';
  END IF;
 END IF;
 IF NEW.inventory_policy='stock_managed' THEN
  IF NEW.inventory_subject_kind='product' THEN source_product:=NEW.inventory_subject_id;
  ELSIF NEW.inventory_subject_kind='product_variant' THEN
   SELECT product_id INTO source_product FROM product_variants WHERE id=NEW.inventory_subject_id;
  ELSIF NEW.inventory_subject_kind='size_stock' THEN
   SELECT v.product_id INTO source_product FROM size_stocks ss
   JOIN variations v ON v.id=ss.variation_id WHERE ss.id=NEW.inventory_subject_id;
  END IF;
  IF source_product IS NULL OR source_product IS DISTINCT FROM NEW.product_id
     OR (NEW.inventory_subject_kind='product_variant'
         AND NEW.variant_id IS DISTINCT FROM NEW.inventory_subject_id) THEN
   RAISE EXCEPTION 'order item inventory subject ancestry is invalid';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_order_items_inventory_snapshot BEFORE INSERT OR UPDATE ON order_items
FOR EACH ROW EXECUTE FUNCTION validate_order_item_inventory_snapshot();

CREATE FUNCTION validate_order_item_inventory_snapshot_completion() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE current_item record;
BEGIN
 SELECT oi.inventory_policy,oi.inventory_source_product_id,oi.product_id,
        o.workflow_cohort INTO current_item
 FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE oi.id=NEW.id;
 IF FOUND AND current_item.workflow_cohort='domestic_checkout_v1'
    AND (current_item.inventory_policy IS NULL
         OR current_item.inventory_source_product_id IS NULL
         OR current_item.inventory_source_product_id IS DISTINCT FROM current_item.product_id) THEN
  RAISE EXCEPTION 'order item inventory snapshot is incomplete';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER trg_order_items_inventory_snapshot_completion
AFTER INSERT OR UPDATE ON order_items DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION validate_order_item_inventory_snapshot_completion();

CREATE FUNCTION validate_checkout_prerequisite_order(target_order_id uuid) RETURNS void LANGUAGE plpgsql AS $$
DECLARE authoritative_order record; selected record;
DECLARE item_count bigint; coverage_count bigint; invalid_count bigint;
BEGIN
 SELECT * INTO authoritative_order FROM orders WHERE id=target_order_id FOR UPDATE;
 IF NOT FOUND OR authoritative_order.workflow_cohort<>'domestic_checkout_v1'
    OR authoritative_order.checkout_prerequisites_completed_at IS NULL THEN
  RETURN;
 END IF;
 SELECT s.id,s.order_id,s.customer_id,s.selected_at INTO selected
 FROM checkout_shipping_estimate_selections s
 WHERE s.id=authoritative_order.checkout_estimate_selection_id;
 IF NOT FOUND OR selected.order_id IS DISTINCT FROM authoritative_order.id
    OR selected.customer_id IS DISTINCT FROM authoritative_order.customer_id
    OR authoritative_order.checkout_prerequisites_completed_at < selected.selected_at THEN
  RAISE EXCEPTION 'checkout prerequisite completion requires a valid current selection';
 END IF;
 SELECT count(*) INTO item_count FROM order_items WHERE order_id=target_order_id;
 SELECT count(*) INTO coverage_count FROM order_inventory_coverage WHERE order_id=target_order_id;
 SELECT count(*) INTO invalid_count
 FROM order_items oi
 LEFT JOIN order_inventory_coverage c ON c.order_item_id=oi.id
  AND c.order_id=oi.order_id
 LEFT JOIN stock_reservations r ON r.id=c.reservation_id
 WHERE oi.order_id=target_order_id
   AND (c.order_item_id IS NULL
        OR c.checkout_estimate_selection_id IS DISTINCT FROM selected.id
        OR c.inventory_policy IS DISTINCT FROM oi.inventory_policy
        OR (oi.inventory_policy='stock_managed'
            AND (r.id IS NULL OR r.order_id IS DISTINCT FROM oi.order_id
                 OR r.order_item_id IS DISTINCT FROM oi.id
                 OR r.checkout_estimate_selection_id IS DISTINCT FROM selected.id
                 OR r.state IS DISTINCT FROM 'active'))
        OR (oi.inventory_policy='made_to_order' AND c.reservation_id IS NOT NULL));
 IF item_count=0 OR coverage_count<>item_count OR invalid_count<>0 THEN
  RAISE EXCEPTION 'checkout prerequisite completion requires exact inventory coverage';
 END IF;
END $$;
CREATE FUNCTION validate_checkout_prerequisite_completion() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_order_id uuid;
BEGIN
 IF TG_TABLE_NAME='orders' THEN target_order_id:=COALESCE(NEW.id,OLD.id);
 ELSE target_order_id:=COALESCE(NEW.order_id,OLD.order_id); END IF;
 IF TG_TABLE_NAME='order_items' THEN
  IF TG_OP='UPDATE' AND OLD.order_id IS DISTINCT FROM NEW.order_id THEN
   PERFORM validate_checkout_prerequisite_order(OLD.order_id);
  END IF;
 END IF;
 PERFORM validate_checkout_prerequisite_order(target_order_id);
 RETURN COALESCE(NEW,OLD);
END $$;
CREATE CONSTRAINT TRIGGER trg_orders_checkout_completion
AFTER INSERT OR UPDATE OF checkout_estimate_selection_id,checkout_prerequisites_completed_at
ON orders DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION validate_checkout_prerequisite_completion();
CREATE CONSTRAINT TRIGGER trg_checkout_coverage_completion
AFTER INSERT OR UPDATE OR DELETE ON order_inventory_coverage
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION validate_checkout_prerequisite_completion();
CREATE CONSTRAINT TRIGGER trg_checkout_selection_completion
AFTER INSERT OR UPDATE OR DELETE ON checkout_shipping_estimate_selections
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION validate_checkout_prerequisite_completion();
CREATE CONSTRAINT TRIGGER trg_order_items_checkout_completion
AFTER INSERT OR UPDATE OR DELETE ON order_items
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
EXECUTE FUNCTION validate_checkout_prerequisite_completion();

DROP TRIGGER IF EXISTS order_guest_capabilities_no_delete ON order_guest_capabilities;
DROP TRIGGER IF EXISTS order_current_owners_identity_immutable ON order_current_owners;
DROP FUNCTION IF EXISTS protect_order_current_owner();

CREATE FUNCTION validate_order_guest_capability_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE database_now timestamptz := statement_timestamp(); expiry_now timestamptz; replacement record;
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'guest capability cannot be deleted'; END IF;
 IF TG_OP='INSERT' THEN
  PERFORM 1 FROM order_current_owners
   WHERE order_id=NEW.order_id AND original_customer_id=NEW.original_customer_id FOR UPDATE;
  IF NOT FOUND OR NEW.created_at>database_now THEN
   RAISE EXCEPTION 'guest capability owner or creation chronology is invalid';
  END IF;
  RETURN NEW;
 END IF;
 PERFORM 1 FROM order_current_owners WHERE order_id=OLD.order_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'guest capability owner projection is missing'; END IF;
 IF (OLD.id,OLD.order_id,OLD.original_customer_id,OLD.scope,OLD.token_digest,
     OLD.pepper_key_version,OLD.expires_at,OLD.created_at)
    IS DISTINCT FROM
    (NEW.id,NEW.order_id,NEW.original_customer_id,NEW.scope,NEW.token_digest,
     NEW.pepper_key_version,NEW.expires_at,NEW.created_at) THEN
  RAISE EXCEPTION 'guest capability identity and credential facts are immutable';
 END IF;
 IF OLD.last_used_at IS DISTINCT FROM NEW.last_used_at
    AND OLD.revoked_at IS NOT DISTINCT FROM NEW.revoked_at
    AND OLD.replaced_by_id IS NOT DISTINCT FROM NEW.replaced_by_id
    AND OLD.claimed_by_user_id IS NOT DISTINCT FROM NEW.claimed_by_user_id
    AND OLD.claimed_at IS NOT DISTINCT FROM NEW.claimed_at
    AND NEW.row_version=OLD.row_version+1
    AND NEW.last_used_at=database_now
    AND (OLD.last_used_at IS NULL OR NEW.last_used_at>=OLD.last_used_at)
    AND NEW.last_used_at>=NEW.created_at
    AND NEW.revoked_at IS NULL AND NEW.replaced_by_id IS NULL
    AND NEW.claimed_by_user_id IS NULL THEN
  expiry_now:=clock_timestamp();
  IF NEW.expires_at<=expiry_now THEN
   RAISE EXCEPTION 'guest capability is expired';
  END IF;
  RETURN NEW;
 END IF;
 IF OLD.revoked_at IS NULL AND NEW.revoked_at=database_now
    AND OLD.replaced_by_id IS NOT DISTINCT FROM NEW.replaced_by_id
    AND OLD.claimed_by_user_id IS NOT DISTINCT FROM NEW.claimed_by_user_id
    AND OLD.claimed_at IS NOT DISTINCT FROM NEW.claimed_at
    AND OLD.last_used_at IS NOT DISTINCT FROM NEW.last_used_at
    AND NEW.row_version=OLD.row_version+1 THEN
  RETURN NEW;
 END IF;
 IF OLD.revoked_at IS NULL AND OLD.replaced_by_id IS NULL
    AND OLD.claimed_by_user_id IS NULL AND NEW.replaced_by_id IS NOT NULL
    AND NEW.revoked_at=database_now
    AND OLD.claimed_by_user_id IS NOT DISTINCT FROM NEW.claimed_by_user_id
    AND OLD.claimed_at IS NOT DISTINCT FROM NEW.claimed_at
    AND OLD.last_used_at IS NOT DISTINCT FROM NEW.last_used_at
    AND NEW.row_version=OLD.row_version+1 THEN
  SELECT order_id,original_customer_id,scope,created_at,expires_at,revoked_at,
         replaced_by_id,claimed_by_user_id INTO replacement
  FROM order_guest_capabilities WHERE id=NEW.replaced_by_id FOR UPDATE;
  expiry_now:=clock_timestamp();
  IF NOT FOUND OR NEW.replaced_by_id=NEW.id
     OR replacement.order_id IS DISTINCT FROM NEW.order_id
     OR replacement.original_customer_id IS DISTINCT FROM NEW.original_customer_id
     OR replacement.scope IS DISTINCT FROM NEW.scope
     OR replacement.created_at<NEW.created_at OR replacement.created_at>database_now
     OR replacement.expires_at<=expiry_now OR replacement.revoked_at IS NOT NULL
     OR replacement.replaced_by_id IS NOT NULL OR replacement.claimed_by_user_id IS NOT NULL THEN
   RAISE EXCEPTION 'guest capability replacement is invalid';
  END IF;
  RETURN NEW;
 END IF;
 IF pg_trigger_depth()>1 AND OLD.revoked_at IS NULL AND OLD.replaced_by_id IS NULL
    AND OLD.claimed_by_user_id IS NULL AND OLD.claimed_at IS NULL
    AND NEW.revoked_at=database_now AND NEW.replaced_by_id IS NULL
    AND NEW.claimed_by_user_id IS NOT NULL AND NEW.claimed_at=database_now
    AND OLD.last_used_at IS NOT DISTINCT FROM NEW.last_used_at
    AND NEW.row_version=OLD.row_version+1 THEN
  RETURN NEW;
 END IF;
 IF OLD IS NOT DISTINCT FROM NEW THEN RETURN NEW; END IF;
 RAISE EXCEPTION 'illegal guest capability lifecycle transition';
END $$;
CREATE TRIGGER trg_order_guest_capabilities_truth
BEFORE INSERT OR UPDATE OR DELETE ON order_guest_capabilities
FOR EACH ROW EXECUTE FUNCTION validate_order_guest_capability_write();

CREATE FUNCTION validate_order_current_owner_claim() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE order_customer uuid; capability record; database_now timestamptz := statement_timestamp();
DECLARE expiry_now timestamptz;
BEGIN
 IF TG_OP='DELETE' THEN
  IF pg_trigger_depth()>1 THEN RETURN OLD; END IF;
  RAISE EXCEPTION 'order current owner projection cannot be deleted';
 END IF;
 IF TG_OP='INSERT' THEN
  SELECT customer_id INTO order_customer FROM orders WHERE id=NEW.order_id FOR UPDATE;
  IF NOT FOUND OR NEW.original_customer_id IS DISTINCT FROM order_customer
     OR NEW.current_authenticated_user_id IS NOT NULL OR NEW.claim_capability_id IS NOT NULL
     OR NEW.claim_idempotency_key IS NOT NULL OR NEW.claimed_at IS NOT NULL THEN
   RAISE EXCEPTION 'initial order owner projection is invalid';
  END IF;
  RETURN NEW;
 END IF;
 IF OLD.order_id IS DISTINCT FROM NEW.order_id
    OR OLD.original_customer_id IS DISTINCT FROM NEW.original_customer_id
    OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
  RAISE EXCEPTION 'original owner identity is immutable';
 END IF;
 IF OLD.current_authenticated_user_id IS NOT NULL THEN
  IF OLD.current_authenticated_user_id IS NOT DISTINCT FROM NEW.current_authenticated_user_id
     AND OLD.claim_capability_id IS NOT DISTINCT FROM NEW.claim_capability_id
     AND OLD.claim_idempotency_key IS NOT DISTINCT FROM NEW.claim_idempotency_key
     AND OLD.claimed_at IS NOT DISTINCT FROM NEW.claimed_at
     AND OLD.row_version=NEW.row_version THEN RETURN NEW;
  END IF;
  RAISE EXCEPTION 'order claim conflicts with the current owner';
 END IF;
 IF NEW.current_authenticated_user_id IS NULL OR NEW.claim_capability_id IS NULL
    OR NEW.claim_idempotency_key IS NULL OR NEW.claimed_at<>database_now
    OR NEW.row_version<>OLD.row_version+1 THEN
  RAISE EXCEPTION 'order claim transition is invalid';
 END IF;
 PERFORM 1 FROM order_guest_capabilities WHERE order_id=NEW.order_id ORDER BY id FOR UPDATE;
 expiry_now:=clock_timestamp();
 SELECT * INTO capability FROM order_guest_capabilities
  WHERE id=NEW.claim_capability_id AND order_id=NEW.order_id;
 IF NOT FOUND OR capability.original_customer_id IS DISTINCT FROM NEW.original_customer_id
    OR capability.scope<>'claim_order' OR capability.created_at>database_now
    OR capability.expires_at<=expiry_now OR capability.revoked_at IS NOT NULL
    OR capability.replaced_by_id IS NOT NULL OR capability.claimed_by_user_id IS NOT NULL
    OR capability.claimed_at IS NOT NULL THEN
  RAISE EXCEPTION 'claim capability is not active for this order';
 END IF;
 UPDATE order_guest_capabilities
 SET revoked_at=COALESCE(revoked_at,database_now),
     claimed_by_user_id=CASE WHEN id=NEW.claim_capability_id
                             THEN NEW.current_authenticated_user_id
                             ELSE claimed_by_user_id END,
     claimed_at=CASE WHEN id=NEW.claim_capability_id THEN database_now ELSE claimed_at END,
     row_version=row_version+1
 WHERE order_id=NEW.order_id
   AND (revoked_at IS NULL OR id=NEW.claim_capability_id);
 RETURN NEW;
END $$;
CREATE TRIGGER trg_order_current_owners_claim
BEFORE INSERT OR UPDATE OR DELETE ON order_current_owners
FOR EACH ROW EXECUTE FUNCTION validate_order_current_owner_claim();
"""


M2_FINDING5_TRIGGER_DDL = r"""
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
DECLARE requires_stock_reservations boolean;
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
   requires_stock_reservations:=EXISTS(
       SELECT 1 FROM order_inventory_coverage coverage
              WHERE coverage.order_id=OLD.order_id
                AND coverage.checkout_estimate_selection_id=OLD.checkout_estimate_selection_id
                AND coverage.inventory_policy='stock_managed');
   IF now_at>=OLD.expires_at OR (
       requires_stock_reservations
       AND NOT EXISTS(
       SELECT 1 FROM payment_attempt_reservations ar WHERE ar.attempt_id=OLD.id))
      OR EXISTS(
       SELECT 1 FROM payment_attempt_reservations ar
       JOIN stock_reservations sr ON sr.id=ar.reservation_id
       WHERE ar.attempt_id=OLD.id AND (
        ar.membership_family<>'domestic_checkout_v1'
        OR ar.order_id IS DISTINCT FROM OLD.order_id
        OR ar.checkout_estimate_selection_id IS DISTINCT FROM OLD.checkout_estimate_selection_id
        OR sr.order_id IS DISTINCT FROM OLD.order_id
        OR sr.checkout_estimate_selection_id IS DISTINCT FROM OLD.checkout_estimate_selection_id
        OR sr.state<>'active' OR sr.expires_at<=now_at
        OR NOT EXISTS(SELECT 1 FROM order_inventory_coverage coverage
          WHERE coverage.order_id=OLD.order_id
            AND coverage.checkout_estimate_selection_id=OLD.checkout_estimate_selection_id
            AND coverage.inventory_policy='stock_managed'
            AND coverage.order_item_id=ar.order_item_id))
      OR EXISTS(
       SELECT 1 FROM order_inventory_coverage coverage
       WHERE coverage.order_id=OLD.order_id
         AND coverage.checkout_estimate_selection_id=OLD.checkout_estimate_selection_id
         AND coverage.inventory_policy='stock_managed'
         AND NOT EXISTS(
             SELECT 1 FROM payment_attempt_reservations ar
             JOIN stock_reservations sr ON sr.id=ar.reservation_id
             WHERE ar.attempt_id=OLD.id
               AND ar.membership_family='domestic_checkout_v1'
               AND ar.order_id=OLD.order_id
               AND ar.order_item_id=coverage.order_item_id
               AND ar.checkout_estimate_selection_id=OLD.checkout_estimate_selection_id
               AND sr.order_id=OLD.order_id
               AND sr.order_item_id=coverage.order_item_id
               AND sr.checkout_estimate_selection_id=OLD.checkout_estimate_selection_id
               AND sr.state='active'
               AND sr.expires_at>now_at)))
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
  IF OLD.state='call_started' AND NEW.state='expired' THEN
   now_at:=clock_timestamp();
   IF now_at<OLD.authorization_deadline_at THEN RAISE EXCEPTION 'payment authorization deadline has not elapsed'; END IF;
   IF NEW.terminal_evidence_id IS NOT NULL THEN
   RAISE EXCEPTION 'payment attempt transition is illegal'; END IF;
   NEW.lease_token:=NULL; NEW.call_started_at:=NULL; NEW.claim_expires_at:=NULL;
   NEW.terminal_evidence_id:=NULL; NEW.terminal_at:=now_at; NEW.updated_at:=now_at; RETURN NEW;
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
      AND ((now_at>=OLD.claim_expires_at AND NOT (
           NEW.state='failed'
           AND OLD.supersedes_attempt_id IS NOT NULL
           AND EXISTS(
            SELECT 1 FROM payment_attempt_evidence pe
             WHERE pe.id=NEW.terminal_evidence_id
               AND pe.attempt_id=OLD.id
               AND pe.evidence_type='payment_failed'
               AND pe.source='payment.success_reconciliation')
      )) OR evidence.created_at<OLD.call_started_at
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
    requires_stock_reservations:=EXISTS(
       SELECT 1 FROM order_inventory_coverage coverage
        WHERE coverage.order_id=OLD.order_id
          AND coverage.checkout_estimate_selection_id=OLD.checkout_estimate_selection_id
          AND coverage.inventory_policy='stock_managed');
    IF (requires_stock_reservations AND NOT EXISTS(
          SELECT 1 FROM payment_attempt_reservations WHERE attempt_id=OLD.id))
       OR EXISTS(SELECT 1 FROM payment_attempt_reservations ar
          JOIN stock_reservations sr ON sr.id=ar.reservation_id
          WHERE ar.attempt_id=OLD.id AND (sr.state<>'active'
           OR (sr.expires_at<=now_at AND OLD.call_started_at>=sr.expires_at)))
       OR EXISTS(SELECT 1 FROM stock_reservations sr
          WHERE sr.order_id=OLD.order_id
            AND sr.checkout_estimate_selection_id=OLD.checkout_estimate_selection_id
            AND sr.workflow_cohort='domestic_checkout_v1'
            AND sr.state='active' AND sr.expires_at>now_at
            AND NOT EXISTS(SELECT 1 FROM payment_attempt_reservations ar
               WHERE ar.attempt_id=OLD.id AND ar.reservation_id=sr.id))
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
        s.order_id AS selection_order_id,s.customer_id AS selection_customer_id,
        e.expires_at AS estimate_expires_at
   INTO authoritative
   FROM orders o
   JOIN checkout_shipping_estimate_selections s ON s.id=NEW.checkout_estimate_selection_id
   JOIN checkout_shipping_estimates e ON e.id=s.estimate_id
  WHERE o.id=NEW.order_id FOR UPDATE OF o;
 IF NOT FOUND OR authoritative.customer_id<>NEW.customer_id
    OR authoritative.selection_order_id<>NEW.order_id
    OR authoritative.selection_customer_id<>NEW.customer_id
    OR authoritative.total_amount<>NEW.amount OR authoritative.currency<>NEW.currency
    OR authoritative.payment_status='PAID' OR authoritative.fulfillment_status='cancelled'
 THEN RAISE EXCEPTION 'domestic payment attempt binding is invalid'; END IF;
 requires_stock_reservations:=EXISTS(
   SELECT 1 FROM order_inventory_coverage coverage
    WHERE coverage.order_id=NEW.order_id
      AND coverage.checkout_estimate_selection_id=NEW.checkout_estimate_selection_id
      AND coverage.inventory_policy='stock_managed');
 SELECT min(expires_at) INTO earliest_reservation_expiry FROM stock_reservations
  WHERE order_id=NEW.order_id AND checkout_estimate_selection_id=NEW.checkout_estimate_selection_id
    AND workflow_cohort='domestic_checkout_v1' AND state='active' AND expires_at>now_at;
 IF requires_stock_reservations AND earliest_reservation_expiry IS NULL
 THEN RAISE EXCEPTION 'payment attempt requires active reservations'; END IF;
 IF EXISTS(SELECT 1 FROM payment_attempts WHERE order_id=NEW.order_id AND state IN ('pending','call_started'))
 THEN RAISE EXCEPTION 'payment attempt already active for order'; END IF;
 NEW.created_at:=now_at; NEW.updated_at:=now_at;
 NEW.expires_at:=LEAST(
   now_at+NEW.payment_window_seconds*interval '1 second',
   COALESCE(earliest_reservation_expiry,authoritative.estimate_expires_at));
 NEW.authorization_deadline_at:=NEW.expires_at+NEW.authorization_grace_seconds*interval '1 second';
 NEW.row_version:=1; NEW.creation_txid:=txid_current();
 RETURN NEW;
END $$;
CREATE TRIGGER trg_payment_attempts_validate_domestic_insert BEFORE INSERT ON payment_attempts FOR EACH ROW WHEN (NEW.workflow_cohort='domestic_checkout_v1') EXECUTE FUNCTION validate_domestic_checkout_payment_attempt_write();
CREATE TRIGGER trg_payment_attempts_validate_domestic_update BEFORE UPDATE ON payment_attempts FOR EACH ROW WHEN (OLD.workflow_cohort='domestic_checkout_v1' OR NEW.workflow_cohort='domestic_checkout_v1') EXECUTE FUNCTION validate_domestic_checkout_payment_attempt_write();
CREATE OR REPLACE FUNCTION validate_payment_attempt_exact_reservations() RETURNS trigger AS $$
DECLARE
    target_attempt uuid; attempt_order uuid; attempt_workflow text;
    attempt_selection uuid; item_count bigint; coverage_count bigint;
    invalid_count bigint; missing_count bigint; extra_count bigint;
    composition_mismatch_count bigint;
BEGIN
    IF TG_TABLE_NAME = 'payment_attempts' THEN target_attempt := NEW.id;
    ELSE target_attempt := NEW.attempt_id; END IF;
    SELECT pa.order_id,pa.workflow_cohort,pa.checkout_estimate_selection_id
      INTO attempt_order,attempt_workflow,attempt_selection
      FROM payment_attempts pa WHERE pa.id = target_attempt;
    IF attempt_workflow='domestic_checkout_v1' THEN
        SELECT count(*) INTO item_count FROM order_items WHERE order_id=attempt_order;
        SELECT count(*) INTO coverage_count FROM order_inventory_coverage
         WHERE order_id=attempt_order;
        SELECT count(*) INTO invalid_count FROM order_items oi
        LEFT JOIN order_inventory_coverage coverage
          ON coverage.order_id=oi.order_id AND coverage.order_item_id=oi.id
        WHERE oi.order_id=attempt_order AND (
          coverage.order_item_id IS NULL
          OR coverage.checkout_estimate_selection_id IS DISTINCT FROM attempt_selection
          OR coverage.inventory_policy IS DISTINCT FROM oi.inventory_policy
          OR (oi.inventory_policy='made_to_order' AND coverage.reservation_id IS NOT NULL)
          OR (oi.inventory_policy='stock_managed' AND NOT EXISTS(
              SELECT 1 FROM payment_attempt_reservations ar
              JOIN stock_reservations sr ON sr.id=ar.reservation_id
              WHERE ar.attempt_id=target_attempt
                AND ar.membership_family='domestic_checkout_v1'
                AND ar.order_id=attempt_order
                AND ar.order_item_id=oi.id
                AND ar.checkout_estimate_selection_id=attempt_selection
                AND sr.order_id=attempt_order
                AND sr.order_item_id=oi.id
                AND sr.checkout_estimate_selection_id=attempt_selection
                AND sr.state='active'
                AND sr.expires_at>statement_timestamp())));
        SELECT count(*) INTO missing_count FROM order_inventory_coverage coverage
         WHERE coverage.order_id=attempt_order
           AND coverage.checkout_estimate_selection_id=attempt_selection
           AND coverage.inventory_policy='stock_managed'
           AND NOT EXISTS(SELECT 1 FROM payment_attempt_reservations ar
             JOIN stock_reservations sr ON sr.id=ar.reservation_id
             WHERE ar.attempt_id=target_attempt
               AND ar.membership_family='domestic_checkout_v1'
               AND ar.order_id=attempt_order
               AND ar.order_item_id=coverage.order_item_id
               AND ar.checkout_estimate_selection_id=attempt_selection
               AND sr.order_id=attempt_order
               AND sr.order_item_id=coverage.order_item_id
               AND sr.checkout_estimate_selection_id=attempt_selection
               AND sr.state='active'
               AND sr.expires_at>statement_timestamp());
        SELECT count(*) INTO extra_count FROM payment_attempt_reservations ar
         WHERE ar.attempt_id=target_attempt AND NOT EXISTS(
           SELECT 1 FROM order_inventory_coverage coverage
           JOIN stock_reservations sr ON sr.id=ar.reservation_id
           WHERE coverage.order_id=attempt_order
             AND coverage.checkout_estimate_selection_id=attempt_selection
             AND coverage.inventory_policy='stock_managed'
             AND coverage.order_item_id=ar.order_item_id
             AND ar.membership_family='domestic_checkout_v1'
             AND ar.order_id=attempt_order
             AND ar.checkout_estimate_selection_id=attempt_selection
             AND sr.order_id=attempt_order
             AND sr.order_item_id=ar.order_item_id
             AND sr.checkout_estimate_selection_id=attempt_selection
             AND sr.state='active'
             AND sr.expires_at>statement_timestamp());
        IF item_count=0 OR coverage_count<>item_count OR invalid_count<>0
           OR missing_count<>0 OR extra_count<>0 THEN
            RAISE EXCEPTION 'payment attempt must cover exact stock-managed coverage';
        END IF;
        RETURN NULL;
    END IF;
    SELECT count(*) INTO missing_count FROM stock_reservations sr
     WHERE sr.order_id=attempt_order AND sr.state='active'
       AND sr.expires_at>statement_timestamp() AND NOT EXISTS(
         SELECT 1 FROM payment_attempt_reservations ar
          WHERE ar.attempt_id=target_attempt AND ar.reservation_id=sr.id);
    SELECT count(*) INTO extra_count FROM payment_attempt_reservations ar
      JOIN stock_reservations sr ON sr.id=ar.reservation_id
     WHERE ar.attempt_id=target_attempt AND (sr.order_id<>attempt_order
       OR sr.state<>'active' OR sr.expires_at<=statement_timestamp());
    IF missing_count<>0 OR extra_count<>0 OR NOT EXISTS(
       SELECT 1 FROM payment_attempt_reservations WHERE attempt_id=target_attempt) THEN
        RAISE EXCEPTION 'payment attempt must cover the exact active reservation set';
    END IF;
    SELECT count(*) INTO composition_mismatch_count FROM (
      SELECT q.package_id,q.package_version,sr.order_item_id,sum(sr.quantity) reserved_quantity
        FROM payment_attempt_reservations ar JOIN stock_reservations sr ON sr.id=ar.reservation_id
        JOIN customer_shipping_quotes q ON q.id=sr.quote_id
       WHERE ar.attempt_id=target_attempt GROUP BY q.package_id,q.package_version,sr.order_item_id
    ) reserved FULL OUTER JOIN (
      SELECT hpi.package_id,hpi.package_version,hpi.order_item_id,sum(hpi.quantity) package_quantity
        FROM hub_package_items hpi JOIN (
          SELECT DISTINCT q.package_id,q.package_version FROM customer_shipping_quote_selections s
          JOIN customer_shipping_quotes q ON q.id=s.quote_id WHERE q.order_id=attempt_order
          AND NOT EXISTS(SELECT 1 FROM customer_shipping_quotes successor
                          WHERE successor.supersedes_quote_id=q.id)
          AND NOT EXISTS(SELECT 1 FROM outbound_shipment_intent_invalidations invalidation
                          WHERE invalidation.intent_id=s.intent_id)
        ) selected_packages ON selected_packages.package_id=hpi.package_id
          AND selected_packages.package_version=hpi.package_version
       GROUP BY hpi.package_id,hpi.package_version,hpi.order_item_id
    ) composed USING(package_id,package_version,order_item_id)
    WHERE reserved.reserved_quantity IS DISTINCT FROM composed.package_quantity;
    IF composition_mismatch_count<>0 THEN
      RAISE EXCEPTION 'payment attempt must cover exact quoted package composition'; END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE OR REPLACE FUNCTION protect_reserved_order() RETURNS trigger AS $$
DECLARE presented_late_attempt text;
BEGIN
    presented_late_attempt:=current_setting('shopsoma.late_payment_attempt_id',true);
    IF NEW.payment_status IS DISTINCT FROM OLD.payment_status
       AND EXISTS (
           SELECT 1 FROM payment_attempts pa
            WHERE pa.order_id = OLD.id
              AND pa.state IN ('pending', 'call_started', 'abandoned_unknown')
       ) AND NOT (
           NEW.payment_status='PAID'
           AND presented_late_attempt IS NOT NULL
           AND EXISTS (
               SELECT 1 FROM payment_attempts late
                WHERE late.id::text=presented_late_attempt
                  AND late.order_id=OLD.id AND late.state='failed'
           )
       ) THEN
        RAISE EXCEPTION 'payment attempt prevents legacy payment status write';
    END IF;
    IF NEW.fulfillment_status = 'cancelled'
       AND OLD.fulfillment_status IS DISTINCT FROM 'cancelled'
       AND EXISTS (
           SELECT 1 FROM payment_attempts pa
            WHERE pa.order_id = OLD.id
              AND pa.state IN ('call_started', 'abandoned_unknown', 'verified')
       ) THEN
        RAISE EXCEPTION 'unresolved or verified payment prevents order cancellation';
    END IF;
    IF EXISTS (SELECT 1 FROM stock_reservations WHERE order_id = OLD.id)
       AND (NEW.customer_id IS DISTINCT FROM OLD.customer_id
            OR NEW.currency IS DISTINCT FROM OLD.currency
            OR NEW.total_amount IS DISTINCT FROM OLD.total_amount) THEN
        RAISE EXCEPTION 'reserved order payment truth is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

M2_FINDING5_DROP_DDL = r"""
DROP TRIGGER IF EXISTS trg_payment_attempt_reservations_validate_domestic ON payment_attempt_reservations;
DROP TRIGGER IF EXISTS trg_payment_attempts_validate_domestic_update ON payment_attempts;
DROP TRIGGER IF EXISTS trg_payment_attempts_validate_domestic_insert ON payment_attempts;
DROP TRIGGER IF EXISTS trg_payment_attempts_validate_delete ON payment_attempts;
DROP TRIGGER IF EXISTS trg_payment_attempts_validate_legacy_update ON payment_attempts;
DROP TRIGGER IF EXISTS trg_payment_attempts_validate_legacy_insert ON payment_attempts;
DROP FUNCTION IF EXISTS validate_domestic_checkout_payment_attempt_write();
DROP TRIGGER IF EXISTS trg_stock_reservations_validate_domestic_update ON stock_reservations;
DROP TRIGGER IF EXISTS trg_stock_reservations_validate_domestic_insert ON stock_reservations;
DROP TRIGGER IF EXISTS trg_stock_reservations_validate_delete ON stock_reservations;
DROP TRIGGER IF EXISTS trg_stock_reservations_validate_legacy_update ON stock_reservations;
DROP TRIGGER IF EXISTS trg_stock_reservations_validate_legacy_insert ON stock_reservations;
DROP FUNCTION IF EXISTS validate_domestic_checkout_reservation_write();
DROP FUNCTION IF EXISTS validate_domestic_checkout_membership_write();
"""

M2_CHECKOUT_TRIGGER_DDL += M2_FINDING5_TRIGGER_DDL

M2_CHECKOUT_DROP_DDL = (
    M2_FINDING5_DROP_DDL
    + r"""
DROP TRIGGER IF EXISTS trg_order_current_owners_claim ON order_current_owners;
DROP FUNCTION IF EXISTS validate_order_current_owner_claim();
DROP TRIGGER IF EXISTS trg_order_guest_capabilities_truth ON order_guest_capabilities;
DROP FUNCTION IF EXISTS validate_order_guest_capability_write();
DROP TRIGGER IF EXISTS trg_order_items_checkout_completion ON order_items;
DROP TRIGGER IF EXISTS trg_checkout_selection_completion ON checkout_shipping_estimate_selections;
DROP TRIGGER IF EXISTS trg_checkout_coverage_completion ON order_inventory_coverage;
DROP TRIGGER IF EXISTS trg_orders_checkout_completion ON orders;
DROP FUNCTION IF EXISTS validate_checkout_prerequisite_completion();
DROP FUNCTION IF EXISTS validate_checkout_prerequisite_order(uuid);
DROP TRIGGER IF EXISTS trg_order_items_inventory_snapshot_completion ON order_items;
DROP FUNCTION IF EXISTS validate_order_item_inventory_snapshot_completion();
DROP TRIGGER IF EXISTS trg_order_items_inventory_snapshot ON order_items;
DROP FUNCTION IF EXISTS validate_order_item_inventory_snapshot();
DROP TRIGGER IF EXISTS trg_checkout_estimate_selections_truth ON checkout_shipping_estimate_selections;
DROP FUNCTION IF EXISTS validate_checkout_estimate_selection_write();
DROP TRIGGER IF EXISTS trg_checkout_estimate_options_truth ON checkout_shipping_estimate_options;
DROP FUNCTION IF EXISTS validate_checkout_estimate_option_write();
DROP TRIGGER IF EXISTS trg_checkout_estimates_truth ON checkout_shipping_estimates;
DROP FUNCTION IF EXISTS validate_checkout_estimate_write();
DROP TRIGGER IF EXISTS trg_order_workflow_migration_runs_truth ON order_workflow_migration_runs;
DROP FUNCTION IF EXISTS protect_order_workflow_migration_run();
"""
)
