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
DO $$ DECLARE run_id uuid; DECLARE candidate record; BEGIN
 IF EXISTS(SELECT 1 FROM orders) THEN
  SELECT id INTO run_id FROM order_workflow_migration_runs ORDER BY compatibility_writer_started_at DESC,id DESC LIMIT 1;
  IF run_id IS NULL THEN RAISE EXCEPTION 'compatibility writer audit row required before classification'; END IF;
  IF EXISTS(SELECT 1 FROM orders WHERE (workflow_cohort IS NULL)::int+(workflow_policy_version IS NULL)::int+(checkout_access_mode IS NULL)::int IN (1,2)) THEN RAISE EXCEPTION 'changed-candidate abort: partial workflow classification'; END IF;
  UPDATE order_workflow_migration_runs SET high_watermark_created_at=watermark.created_at,high_watermark_order_id=watermark.id FROM (SELECT created_at,id FROM orders WHERE workflow_cohort IS NULL ORDER BY created_at DESC,id DESC LIMIT 1) AS watermark WHERE order_workflow_migration_runs.id=run_id AND high_watermark_created_at IS NULL;
  UPDATE orders SET workflow_cohort='legacy_ambiguous_quarantined',workflow_policy_version='legacy_quarantine_v1',checkout_access_mode='legacy_quarantined' WHERE workflow_cohort IS NULL;
  INSERT INTO order_current_owners(order_id,original_customer_id) SELECT id,customer_id FROM orders ON CONFLICT(order_id) DO NOTHING;
  FOR candidate IN SELECT id,workflow_cohort,workflow_policy_version,checkout_access_mode FROM orders LOOP
   IF candidate.workflow_cohort='legacy_ambiguous_quarantined' THEN
    INSERT INTO order_workflow_classifications(order_id,cohort,policy_version,access_mode,evidence_kind,evidence_reference,migration_run_id,classified_by,notes_hash) VALUES(candidate.id,candidate.workflow_cohort,candidate.workflow_policy_version,candidate.checkout_access_mode,'migration_ambiguity_quarantine','historical-evidence-unresolved',run_id,'milestone_2_backfill',encode(sha256(convert_to(candidate.id::text||'|legacy_ambiguous_quarantined|legacy_quarantine_v1|legacy_quarantined|migration_ambiguity_quarantine|historical-evidence-unresolved','UTF8')),'hex')) ON CONFLICT(order_id) DO NOTHING;
   END IF;
   IF NOT EXISTS(SELECT 1 FROM order_workflow_classifications c WHERE c.order_id=candidate.id AND c.cohort=candidate.workflow_cohort AND c.policy_version=candidate.workflow_policy_version AND c.access_mode=candidate.checkout_access_mode) THEN RAISE EXCEPTION 'changed-candidate abort: immutable classification mismatch for order %',candidate.id; END IF;
  END LOOP;
  UPDATE order_workflow_migration_runs SET classification_cutover_at=statement_timestamp(),classified_row_count=(SELECT count(*) FROM order_workflow_classifications),validated_constraints='m2 validation set' WHERE id=run_id;
 END IF;
END $$;
ALTER TABLE orders ADD CONSTRAINT uq_orders_workflow_truth UNIQUE(id,workflow_cohort,workflow_policy_version,checkout_access_mode), ADD CONSTRAINT ck_orders_workflow_cohort CHECK(workflow_cohort IN ('legacy_pre_bridge','legacy_ambiguous_quarantined','domestic_checkout_v1')) NOT VALID, ADD CONSTRAINT ck_orders_workflow_policy_version CHECK(workflow_policy_version ~ '^[!-~]{1,40}$') NOT VALID, ADD CONSTRAINT ck_orders_checkout_access_mode CHECK(checkout_access_mode IN ('authenticated','guest_capability','legacy_quarantined') AND ((workflow_cohort='legacy_ambiguous_quarantined' AND workflow_policy_version='legacy_quarantine_v1' AND checkout_access_mode='legacy_quarantined') OR (workflow_cohort<>'legacy_ambiguous_quarantined' AND checkout_access_mode<>'legacy_quarantined'))) NOT VALID;
ALTER TABLE order_workflow_classifications ADD CONSTRAINT fk_order_workflow_classifications_order_truth FOREIGN KEY(order_id,cohort,policy_version,access_mode) REFERENCES orders(id,workflow_cohort,workflow_policy_version,checkout_access_mode) ON DELETE RESTRICT NOT VALID;
ALTER TABLE orders VALIDATE CONSTRAINT ck_orders_workflow_cohort; ALTER TABLE orders VALIDATE CONSTRAINT ck_orders_workflow_policy_version; ALTER TABLE orders VALIDATE CONSTRAINT ck_orders_checkout_access_mode; ALTER TABLE orders VALIDATE CONSTRAINT fk_orders_checkout_estimate_selection; ALTER TABLE order_items VALIDATE CONSTRAINT ck_order_items_inventory_policy; ALTER TABLE order_items VALIDATE CONSTRAINT ck_order_items_inventory_subject; ALTER TABLE order_items VALIDATE CONSTRAINT ck_order_items_inventory_source; ALTER TABLE stock_reservations VALIDATE CONSTRAINT fk_stock_reservations_order_item; ALTER TABLE stock_reservations VALIDATE CONSTRAINT fk_stock_reservations_checkout_selection; ALTER TABLE stock_reservations VALIDATE CONSTRAINT ck_stock_reservations_workflow_cohort; ALTER TABLE stock_reservations VALIDATE CONSTRAINT ck_stock_reservations_binding_family; ALTER TABLE stock_reservations VALIDATE CONSTRAINT ck_stock_reservations_checkout_money; ALTER TABLE payment_attempts VALIDATE CONSTRAINT fk_payment_attempts_checkout_selection; ALTER TABLE payment_attempts VALIDATE CONSTRAINT ck_payment_attempts_binding_family; ALTER TABLE payment_attempts VALIDATE CONSTRAINT ck_payment_attempts_checkout_money; ALTER TABLE order_workflow_classifications VALIDATE CONSTRAINT fk_order_workflow_classifications_order_truth;
ALTER TABLE orders ALTER COLUMN workflow_cohort SET NOT NULL,ALTER COLUMN workflow_policy_version SET NOT NULL,ALTER COLUMN checkout_access_mode SET NOT NULL;
CREATE INDEX ix_orders_workflow_cohort_created_at ON orders(workflow_cohort,created_at); CREATE INDEX ix_orders_domestic_prerequisite_pending ON orders(id) WHERE workflow_cohort='domestic_checkout_v1' AND checkout_prerequisites_completed_at IS NULL;
ALTER TABLE payment_attempt_reservations ALTER COLUMN order_id SET NOT NULL,ALTER COLUMN order_item_id SET NOT NULL,ALTER COLUMN checkout_estimate_selection_id SET NOT NULL, ADD CONSTRAINT fk_payment_attempt_reservations_attempt FOREIGN KEY(attempt_id,order_id,checkout_estimate_selection_id) REFERENCES payment_attempts(id,order_id,checkout_estimate_selection_id) ON DELETE RESTRICT NOT VALID, ADD CONSTRAINT fk_payment_attempt_reservations_reservation FOREIGN KEY(reservation_id,order_id,order_item_id,checkout_estimate_selection_id) REFERENCES stock_reservations(id,order_id,order_item_id,checkout_estimate_selection_id) ON DELETE RESTRICT NOT VALID; ALTER TABLE payment_attempt_reservations VALIDATE CONSTRAINT fk_payment_attempt_reservations_attempt; ALTER TABLE payment_attempt_reservations VALIDATE CONSTRAINT fk_payment_attempt_reservations_reservation;
"""
    )


def downgrade() -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM order_workflow_classifications) OR EXISTS(SELECT 1 FROM order_workflow_migration_runs) THEN RAISE EXCEPTION 'refusing destructive Milestone 2 downgrade: compatibility writer/new audit data exists'; END IF; END $$"
    )
    op.execute(
        "ALTER TABLE payment_attempt_reservations DROP CONSTRAINT fk_payment_attempt_reservations_reservation,DROP CONSTRAINT fk_payment_attempt_reservations_attempt,ALTER COLUMN checkout_estimate_selection_id DROP NOT NULL,ALTER COLUMN order_item_id DROP NOT NULL,ALTER COLUMN order_id DROP NOT NULL; DROP INDEX ix_orders_domestic_prerequisite_pending; DROP INDEX ix_orders_workflow_cohort_created_at; ALTER TABLE order_workflow_classifications DROP CONSTRAINT fk_order_workflow_classifications_order_truth; ALTER TABLE orders DROP CONSTRAINT ck_orders_checkout_access_mode,DROP CONSTRAINT ck_orders_workflow_policy_version,DROP CONSTRAINT ck_orders_workflow_cohort,DROP CONSTRAINT uq_orders_workflow_truth,ALTER COLUMN checkout_access_mode DROP NOT NULL,ALTER COLUMN workflow_policy_version DROP NOT NULL,ALTER COLUMN workflow_cohort DROP NOT NULL"
    )
