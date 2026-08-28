"""Repair MTO payment membership and predecessor late-success binding.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""

from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None

_UPGRADE_SQL = r"""CREATE OR REPLACE FUNCTION validate_domestic_checkout_payment_attempt_write() RETURNS trigger LANGUAGE plpgsql AS $$
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
               AND sr.expires_at>now_at))
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
    OR authoritative.estimate_expires_at<=now_at
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
   authoritative.estimate_expires_at,
   COALESCE(earliest_reservation_expiry,authoritative.estimate_expires_at));
 NEW.authorization_deadline_at:=NEW.expires_at+NEW.authorization_grace_seconds*interval '1 second';
 NEW.row_version:=1; NEW.creation_txid:=txid_current();
 RETURN NEW;
END $$;
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
$$ LANGUAGE plpgsql;"""
_DOWNGRADE_SQL = r"""CREATE OR REPLACE FUNCTION validate_domestic_checkout_payment_attempt_write() RETURNS trigger LANGUAGE plpgsql AS $$
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
CREATE OR REPLACE FUNCTION validate_payment_attempt_exact_reservations() RETURNS trigger AS $$
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
                  FROM customer_shipping_quote_selections s
                  JOIN customer_shipping_quotes q ON q.id = s.quote_id
                 WHERE q.order_id = attempt_order
                   AND NOT EXISTS (
                       SELECT 1 FROM customer_shipping_quotes successor
                        WHERE successor.supersedes_quote_id = q.id
                   )
                   AND NOT EXISTS (
                       SELECT 1 FROM outbound_shipment_intent_invalidations invalidation
                        WHERE invalidation.intent_id = s.intent_id
                   )
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
CREATE OR REPLACE FUNCTION protect_reserved_order() RETURNS trigger AS $$
BEGIN
    -- Every order UPDATE already owns the order row, the global serialization
    -- point. Read attempt state without reversing the attempt -> order lock
    -- order; a concurrent attempt transition waits, then revalidates the order.
    IF NEW.payment_status IS DISTINCT FROM OLD.payment_status
       AND EXISTS (
           SELECT 1 FROM payment_attempts pa
            WHERE pa.order_id = OLD.id
              AND pa.state IN ('pending', 'call_started', 'abandoned_unknown')
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
$$ LANGUAGE plpgsql;"""


def upgrade() -> None:
    op.execute(_UPGRADE_SQL)


def downgrade() -> None:
    op.execute(_DOWNGRADE_SQL)
