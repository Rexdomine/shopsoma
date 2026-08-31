"""Milestone 2 validate and classification cutover.

Revision ID: a2b3c4d5e6f7
Revises: a1b2c3d4e5f6
"""

from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
DO $$ DECLARE run_row record; BEGIN
 IF EXISTS(SELECT 1 FROM orders) THEN
  SELECT * INTO run_row FROM order_workflow_migration_runs
   ORDER BY compatibility_writer_started_at DESC,id DESC LIMIT 1;
  IF run_row.id IS NULL THEN
   RAISE EXCEPTION 'compatibility writer audit row required before classification';
  END IF;
  IF EXISTS(SELECT 1 FROM orders WHERE
      (workflow_cohort IS NULL)::int+(workflow_policy_version IS NULL)::int+
      (checkout_access_mode IS NULL)::int IN (1,2)) THEN
   RAISE EXCEPTION 'changed-candidate abort: partial workflow classification';
  END IF;
  IF run_row.high_watermark_created_at IS NULL
     OR run_row.high_watermark_order_id IS NULL
     OR run_row.classification_cutover_at IS NULL
     OR run_row.classified_row_count IS NULL THEN
   RAISE EXCEPTION 'classification reconciliation incomplete: executable classifier has not finalized';
  END IF;
  IF EXISTS(
      SELECT 1 FROM orders o
      LEFT JOIN order_workflow_classifications c ON c.order_id=o.id
      LEFT JOIN order_current_owners owner ON owner.order_id=o.id
      WHERE c.order_id IS NULL OR owner.order_id IS NULL
         OR owner.original_customer_id IS DISTINCT FROM o.customer_id
         OR o.workflow_cohort IS DISTINCT FROM c.cohort
         OR o.workflow_policy_version IS DISTINCT FROM c.policy_version
         OR o.checkout_access_mode IS DISTINCT FROM c.access_mode
    )
    OR EXISTS(
      SELECT 1 FROM order_workflow_classifications c
      LEFT JOIN orders o ON o.id=c.order_id WHERE o.id IS NULL
    )
    OR EXISTS(
      SELECT 1 FROM orders o
      LEFT JOIN order_workflow_classifications c ON c.order_id=o.id
      WHERE (o.created_at,o.id)<=(run_row.high_watermark_created_at,
                                 run_row.high_watermark_order_id)
        AND c.order_id IS NULL
    ) THEN
RAISE EXCEPTION 'classification reconciliation incomplete: exact totals or truth mismatch';
  END IF;
 END IF;
END $$;
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
ALTER TABLE orders ADD CONSTRAINT uq_orders_workflow_truth UNIQUE(id,workflow_cohort,workflow_policy_version,checkout_access_mode), ADD CONSTRAINT ck_orders_workflow_cohort CHECK(workflow_cohort IN ('legacy_pre_bridge','legacy_ambiguous_quarantined','domestic_checkout_v1')) NOT VALID, ADD CONSTRAINT ck_orders_workflow_policy_version CHECK(workflow_policy_version ~ '^[!-~]{1,40}$') NOT VALID, ADD CONSTRAINT ck_orders_checkout_access_mode CHECK(checkout_access_mode IN ('authenticated','guest_capability','legacy_quarantined') AND ((workflow_cohort='legacy_ambiguous_quarantined' AND workflow_policy_version='legacy_quarantine_v1' AND checkout_access_mode='legacy_quarantined') OR (workflow_cohort<>'legacy_ambiguous_quarantined' AND checkout_access_mode<>'legacy_quarantined'))) NOT VALID;
ALTER TABLE order_workflow_classifications ADD CONSTRAINT fk_order_workflow_classifications_order_truth FOREIGN KEY(order_id,cohort,policy_version,access_mode) REFERENCES orders(id,workflow_cohort,workflow_policy_version,checkout_access_mode) ON DELETE RESTRICT NOT VALID;
ALTER TABLE orders VALIDATE CONSTRAINT ck_orders_workflow_cohort; ALTER TABLE orders VALIDATE CONSTRAINT ck_orders_workflow_policy_version; ALTER TABLE orders VALIDATE CONSTRAINT ck_orders_checkout_access_mode; ALTER TABLE orders VALIDATE CONSTRAINT fk_orders_checkout_estimate_selection; ALTER TABLE order_items VALIDATE CONSTRAINT ck_order_items_inventory_policy; ALTER TABLE order_items VALIDATE CONSTRAINT ck_order_items_inventory_subject; ALTER TABLE order_items VALIDATE CONSTRAINT ck_order_items_inventory_source; ALTER TABLE stock_reservations VALIDATE CONSTRAINT fk_stock_reservations_order_item; ALTER TABLE stock_reservations VALIDATE CONSTRAINT fk_stock_reservations_checkout_selection; ALTER TABLE stock_reservations VALIDATE CONSTRAINT ck_stock_reservations_workflow_cohort; ALTER TABLE stock_reservations VALIDATE CONSTRAINT ck_stock_reservations_binding_family; ALTER TABLE stock_reservations VALIDATE CONSTRAINT ck_stock_reservations_checkout_money; ALTER TABLE payment_attempts VALIDATE CONSTRAINT fk_payment_attempts_checkout_selection; ALTER TABLE payment_attempts VALIDATE CONSTRAINT ck_payment_attempts_binding_family; ALTER TABLE payment_attempts VALIDATE CONSTRAINT ck_payment_attempts_checkout_money; ALTER TABLE order_workflow_classifications VALIDATE CONSTRAINT fk_order_workflow_classifications_order_truth;
ALTER TABLE orders ALTER COLUMN workflow_cohort SET NOT NULL,ALTER COLUMN workflow_policy_version SET NOT NULL,ALTER COLUMN checkout_access_mode SET NOT NULL;
CREATE INDEX ix_orders_workflow_cohort_created_at ON orders(workflow_cohort,created_at); CREATE INDEX ix_orders_domestic_prerequisite_pending ON orders(id) WHERE workflow_cohort='domestic_checkout_v1' AND checkout_prerequisites_completed_at IS NULL;
ALTER TABLE payment_attempt_reservations ADD CONSTRAINT ck_payment_attempt_reservations_family_truth CHECK((membership_family='legacy_f9' AND order_id IS NULL AND order_item_id IS NULL AND checkout_estimate_selection_id IS NULL) OR (membership_family='domestic_checkout_v1' AND order_id IS NOT NULL AND order_item_id IS NOT NULL AND checkout_estimate_selection_id IS NOT NULL)) NOT VALID, ADD CONSTRAINT fk_payment_attempt_reservations_attempt FOREIGN KEY(attempt_id,order_id,checkout_estimate_selection_id) REFERENCES payment_attempts(id,order_id,checkout_estimate_selection_id) ON DELETE RESTRICT NOT VALID, ADD CONSTRAINT fk_payment_attempt_reservations_reservation FOREIGN KEY(reservation_id,order_id,order_item_id,checkout_estimate_selection_id) REFERENCES stock_reservations(id,order_id,order_item_id,checkout_estimate_selection_id) ON DELETE RESTRICT NOT VALID; ALTER TABLE payment_attempt_reservations VALIDATE CONSTRAINT ck_payment_attempt_reservations_family_truth; ALTER TABLE payment_attempt_reservations VALIDATE CONSTRAINT fk_payment_attempt_reservations_attempt; ALTER TABLE payment_attempt_reservations VALIDATE CONSTRAINT fk_payment_attempt_reservations_reservation;
ALTER TABLE order_guest_capabilities ADD CONSTRAINT uq_order_guest_capabilities_id_order UNIQUE(id,order_id);
ALTER TABLE order_current_owners DROP CONSTRAINT fk_order_current_owners_claim_capability;
ALTER TABLE order_current_owners ADD CONSTRAINT fk_order_current_owners_claim_capability_order FOREIGN KEY(claim_capability_id,order_id) REFERENCES order_guest_capabilities(id,order_id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED NOT VALID;
ALTER TABLE order_current_owners VALIDATE CONSTRAINT fk_order_current_owners_claim_capability_order;
"""
    )
    op.execute(
        r"""
CREATE FUNCTION validate_checkout_estimate_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE authoritative_order record; predecessor record;
BEGIN
 IF TG_OP <> 'INSERT' THEN
  RAISE EXCEPTION 'checkout estimate is immutable audit';
 END IF;
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
     OR EXISTS(SELECT 1 FROM checkout_shipping_estimates
               WHERE supersedes_estimate_id=predecessor.id)
     OR EXISTS(SELECT 1 FROM checkout_shipping_estimate_selections
               WHERE estimate_id=predecessor.id) THEN
   RAISE EXCEPTION 'checkout estimate predecessor is not the current unselected leaf';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_checkout_estimates_truth
BEFORE INSERT OR UPDATE OR DELETE ON checkout_shipping_estimates
FOR EACH ROW EXECUTE FUNCTION validate_checkout_estimate_write();

CREATE FUNCTION validate_checkout_estimate_option_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE estimate record;
BEGIN
 IF TG_OP <> 'INSERT' THEN
  RAISE EXCEPTION 'checkout estimate option is immutable audit';
 END IF;
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
CREATE TRIGGER trg_checkout_estimate_options_truth
BEFORE INSERT OR UPDATE OR DELETE ON checkout_shipping_estimate_options
FOR EACH ROW EXECUTE FUNCTION validate_checkout_estimate_option_write();

CREATE FUNCTION validate_checkout_estimate_selection_write() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE authoritative_order record; estimate record; selected_option record;
DECLARE database_now timestamptz;
BEGIN
 IF TG_OP <> 'INSERT' THEN
  RAISE EXCEPTION 'checkout estimate selection is immutable audit';
 END IF;
 SELECT customer_id,currency,workflow_cohort,checkout_estimate_selection_id
 INTO authoritative_order FROM orders WHERE id=NEW.order_id FOR UPDATE;
 SELECT * INTO estimate FROM checkout_shipping_estimates
 WHERE id=NEW.estimate_id FOR UPDATE;
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
    OR EXISTS(SELECT 1 FROM checkout_shipping_estimates
              WHERE supersedes_estimate_id=estimate.id)
    OR EXISTS(SELECT 1 FROM checkout_shipping_estimate_selections
              WHERE estimate_id=estimate.id) THEN
  RAISE EXCEPTION 'checkout estimate selection truth is invalid';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER trg_checkout_estimate_selections_truth
BEFORE INSERT OR UPDATE OR DELETE ON checkout_shipping_estimate_selections
FOR EACH ROW EXECUTE FUNCTION validate_checkout_estimate_selection_write();

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
              AND OLD.inventory_subject_id IS NULL
              AND OLD.inventory_source_product_id IS NULL
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
  IF NEW.inventory_subject_kind='product' THEN
   source_product:=NEW.inventory_subject_id;
  ELSIF NEW.inventory_subject_kind='product_variant' THEN
   SELECT product_id INTO source_product FROM product_variants
    WHERE id=NEW.inventory_subject_id;
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
CREATE TRIGGER trg_order_items_inventory_snapshot
BEFORE INSERT OR UPDATE ON order_items
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
 SELECT count(*) INTO coverage_count FROM order_inventory_coverage
  WHERE order_id=target_order_id;
 SELECT count(*) INTO invalid_count FROM order_items oi
 LEFT JOIN order_inventory_coverage c ON c.order_item_id=oi.id AND c.order_id=oi.order_id
 WHERE oi.order_id=target_order_id
   AND (c.order_item_id IS NULL
        OR c.checkout_estimate_selection_id IS DISTINCT FROM selected.id
        OR c.inventory_policy IS DISTINCT FROM oi.inventory_policy
        OR (oi.inventory_policy='stock_managed' AND NOT EXISTS(
            SELECT 1 FROM payment_attempt_reservations ar
            JOIN stock_reservations r ON r.id=ar.reservation_id
            WHERE ar.order_id=oi.order_id
              AND ar.order_item_id=oi.id
              AND ar.checkout_estimate_selection_id=selected.id
              AND ar.membership_family='domestic_checkout_v1'
              AND r.order_id=oi.order_id
              AND r.order_item_id=oi.id
              AND r.checkout_estimate_selection_id=selected.id
              AND r.state='active'
              AND r.expires_at>statement_timestamp()))
        OR (oi.inventory_policy='made_to_order' AND c.reservation_id IS NOT NULL));
 IF item_count=0 OR coverage_count<>item_count OR invalid_count<>0 THEN
  RAISE EXCEPTION 'checkout prerequisite completion requires exact inventory coverage';
 END IF;
END $$;
CREATE FUNCTION validate_checkout_prerequisite_completion() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_order_id uuid;
BEGIN
 IF TG_TABLE_NAME='orders' THEN
  target_order_id:=COALESCE(NEW.id,OLD.id);
 ELSE
  target_order_id:=COALESCE(NEW.order_id,OLD.order_id);
 END IF;
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
"""
    )
    op.execute(
        r"""
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
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM order_workflow_classifications) OR EXISTS(SELECT 1 FROM order_workflow_migration_runs) THEN RAISE EXCEPTION 'refusing destructive Milestone 2 downgrade: compatibility writer/new audit data exists'; END IF; END $$"
    )
    op.execute(
        "DROP TRIGGER trg_order_items_checkout_completion ON order_items; "
        "DROP TRIGGER trg_checkout_selection_completion ON checkout_shipping_estimate_selections; "
        "DROP TRIGGER trg_checkout_coverage_completion ON order_inventory_coverage; "
        "DROP TRIGGER trg_orders_checkout_completion ON orders; "
        "DROP FUNCTION validate_checkout_prerequisite_completion(); "
        "DROP FUNCTION validate_checkout_prerequisite_order(uuid); "
        "DROP TRIGGER trg_order_items_inventory_snapshot_completion ON order_items; "
        "DROP FUNCTION validate_order_item_inventory_snapshot_completion(); "
        "DROP TRIGGER trg_order_items_inventory_snapshot ON order_items; "
        "DROP FUNCTION validate_order_item_inventory_snapshot(); "
        "DROP TRIGGER trg_checkout_estimate_selections_truth ON checkout_shipping_estimate_selections; "
        "DROP FUNCTION validate_checkout_estimate_selection_write(); "
        "DROP TRIGGER trg_checkout_estimate_options_truth ON checkout_shipping_estimate_options; "
        "DROP FUNCTION validate_checkout_estimate_option_write(); "
        "DROP TRIGGER trg_checkout_estimates_truth ON checkout_shipping_estimates; "
        "DROP FUNCTION validate_checkout_estimate_write(); "
        "DROP TRIGGER trg_order_workflow_migration_runs_truth ON order_workflow_migration_runs; "
        "DROP FUNCTION protect_order_workflow_migration_run()"
    )
    op.execute(
        "DROP TRIGGER trg_order_current_owners_claim ON order_current_owners; "
        "DROP FUNCTION validate_order_current_owner_claim(); "
        "DROP TRIGGER trg_order_guest_capabilities_truth ON order_guest_capabilities; "
        "DROP FUNCTION validate_order_guest_capability_write(); "
        "ALTER TABLE order_current_owners DROP CONSTRAINT fk_order_current_owners_claim_capability_order; "
        "ALTER TABLE order_current_owners ADD CONSTRAINT fk_order_current_owners_claim_capability FOREIGN KEY(claim_capability_id) REFERENCES order_guest_capabilities(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED NOT VALID; "
        "ALTER TABLE order_guest_capabilities DROP CONSTRAINT uq_order_guest_capabilities_id_order; "
        "CREATE OR REPLACE FUNCTION protect_order_current_owner() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE order_customer uuid; BEGIN IF TG_OP='DELETE' THEN IF pg_trigger_depth()>1 THEN RETURN OLD; END IF; RAISE EXCEPTION 'order current owner projection cannot be deleted'; END IF; IF TG_OP='INSERT' THEN SELECT customer_id INTO order_customer FROM orders WHERE id=NEW.order_id; IF order_customer IS NULL OR NEW.original_customer_id IS DISTINCT FROM order_customer THEN RAISE EXCEPTION 'original owner must equal order customer'; END IF; RETURN NEW; END IF; IF OLD.order_id IS DISTINCT FROM NEW.order_id OR OLD.original_customer_id IS DISTINCT FROM NEW.original_customer_id THEN RAISE EXCEPTION 'immutable original owner identity'; END IF; IF OLD.current_authenticated_user_id IS NULL AND OLD.claim_capability_id IS NULL AND OLD.claim_idempotency_key IS NULL AND OLD.claimed_at IS NULL THEN RETURN NEW; END IF; IF OLD.current_authenticated_user_id IS DISTINCT FROM NEW.current_authenticated_user_id OR OLD.claim_capability_id IS DISTINCT FROM NEW.claim_capability_id OR OLD.claim_idempotency_key IS DISTINCT FROM NEW.claim_idempotency_key OR OLD.claimed_at IS DISTINCT FROM NEW.claimed_at THEN RAISE EXCEPTION 'owner claim transition is immutable after claim'; END IF; RETURN NEW; END $$; "
        "CREATE TRIGGER order_current_owners_identity_immutable BEFORE INSERT OR UPDATE OR DELETE ON order_current_owners FOR EACH ROW EXECUTE FUNCTION protect_order_current_owner(); "
        "CREATE TRIGGER order_guest_capabilities_no_delete BEFORE DELETE ON order_guest_capabilities FOR EACH ROW EXECUTE FUNCTION protect_append_only_checkout_prerequisite()"
    )
    op.execute(
        "ALTER TABLE payment_attempt_reservations DROP CONSTRAINT fk_payment_attempt_reservations_reservation,DROP CONSTRAINT fk_payment_attempt_reservations_attempt,DROP CONSTRAINT ck_payment_attempt_reservations_family_truth; DROP INDEX ix_orders_domestic_prerequisite_pending; DROP INDEX ix_orders_workflow_cohort_created_at; ALTER TABLE order_workflow_classifications DROP CONSTRAINT fk_order_workflow_classifications_order_truth; ALTER TABLE orders DROP CONSTRAINT ck_orders_checkout_access_mode,DROP CONSTRAINT ck_orders_workflow_policy_version,DROP CONSTRAINT ck_orders_workflow_cohort,DROP CONSTRAINT uq_orders_workflow_truth,ALTER COLUMN checkout_access_mode DROP NOT NULL,ALTER COLUMN workflow_policy_version DROP NOT NULL,ALTER COLUMN workflow_cohort DROP NOT NULL"
    )
