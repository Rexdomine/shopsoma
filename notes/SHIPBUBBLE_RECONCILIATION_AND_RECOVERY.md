# ShipBubble Fulfillment Incident Postmortem, Reconciliation & Recovery Runbook

## 1. Exact Failure Analysis: Production Order `SHP-20261020-BBB4B3C9`

Evidence below is taken directly from the November 16, 2026 production database snapshot (`shopsoma-production-db.sql`):

| Entity | Identifier / Key | Observed Snapshot Value |
|---|---|---|
| `orders` | `id` / `order_number` | `6a641ea6-39c1-4eb1-affe-6f333043fdc6` / `SHP-20261020-BBB4B3C9` |
| `orders` | `workflow_cohort` | `domestic_checkout_v1` |
| `orders` | `payment_status` / `fulfillment_status` | `PAID` / `delivered` |
| `orders` | `delivery_provider` / `tracking_number` | `shipbubble:GIG Logistics` / `SB-D40825FE22EF` |
| `orders` | `delivered_at` / `updated_at` | `2026-11-13 10:04:54.566054+00` / `2026-11-13 10:04:54.551681+00` |
| `order_items` | `id` (`MMBM SOCKS`) | `f3d2bf16-4e18-430d-ad3a-3cb3e9b3f70b` (`fulfillment_status = order_received`, `inventory_policy = stock_managed`) |
| `vendor_pickups` | `id` | `fbc66a18-4ed0-4ad0-bf98-88e2696c78e4` (`status = IN_TRANSIT`, `actual_pickup_date = 2026-10-27 11:41:31.76199+00`, `completed_at = NULL`, `ready_for_pickup_at = 2026-10-21 16:44:49.010112+00`) |
| `shipbubble_shipments` | `id` / `shipbubble_order_id` | `1b96f4be-51d7-4e42-a890-90866932ee43` / `SB-D40825FE22EF` (`status = confirmed`, `courier_name = GIG Logistics`, `created_at = 2026-10-27 11:41:32.101969+00`, `updated_at = 2026-11-02 13:05:46.594965+00`) |
| `shipbubble_webhook_events` | table count | **0 rows ever recorded** |

### Chronological Failure Sequence (UTC)

1. **`2026-10-20 08:49:51` – `08:51:57`**: Order `SHP-20261020-BBB4B3C9` created on `domestic_checkout_v1`, shipping selection `d54af78e-e9fc-44f0-b7ea-eb069bbdcdc5` saved, Paystack payment `shopsoma-paystack-797f63e95d364f10b12e2d441907bc9c` completed (`2026-10-20T08:51:56.000Z`), and `order_placed` notification `29fd701b-f260-4f88-ab4e-86d8639e29a0` created.
2. **`2026-10-21 16:44:49`**: Vendor marked item ready for pickup (`ready_for_pickup_at`).
3. **`2026-10-23 07:34:03`**: Admin scheduled pickup window `2026-10-23 11:00..13:00 UTC` (`item_pickup_scheduled` notification `2dcf84d1-e587-49aa-8454-c1fb10311adc`).
4. **`2026-10-27 11:41:31` – `11:41:32`**: Pickup collected (`vendor_pickups.actual_pickup_date = 2026-10-27 11:41:31.76199+00`, `vendor_pickups.status = IN_TRANSIT`) and ShipBubble shipment `SB-D40825FE22EF` booked (`shipbubble_shipments.status = confirmed`).
5. **`2026-10-27 11:41:43`**: Admin manually marked the order `delivered` (`order_delivered` notification `8ca3cf99-1da0-4f11-a5c6-f74ed2231d5f`).
6. **`2026-10-30 11:24:22` (Exact failure point)**: A manual/client tracking poll ran while ShipBubble still reported `confirmed` (no ShipBubble webhooks ever arrived). Pre-`a380bff`, `sync_shipbubble_shipment_status` mapped `"confirmed" -> pickup_scheduled` with no forward-only guard and **regressed `orders.fulfillment_status` backwards from `delivered` to `pickup_scheduled`**, emitting vendor notification `48dc6e73-9ac6-4909-bdc6-948f51fde3e6` (`order_pickup_scheduled`).
7. **`2026-11-02 13:05:46`**: Another tracking poll ran (`shipbubble_shipments.updated_at`), with `shipbubble_shipments.status` still at `confirmed`.
8. **`2026-11-13 10:04:54`**: Admin manually marked `SHP-20261020-BBB4B3C9` as `delivered` a second time (`order_delivered` notification `44d3a96d-ff46-4f53-9488-42278d2defa1`), which pre-`a380bff` overwrote `orders.delivered_at` from `2026-10-27` to `2026-11-13 10:04:54.566054+00` while leaving `vendor_pickups.status = IN_TRANSIT` and `order_items.fulfillment_status = order_received`.

### Before / After Reconciliation Record (`SHP-20261020-BBB4B3C9`)

Running Alembic migration `f8a9b0c1d2e3` plus `python scripts/reconcile_shipbubble_orders.py --order-number SHP-20261020-BBB4B3C9 --apply` produces:

| Field | Before | After |
|---|---|---|
| `orders.fulfillment_status` | `delivered` | `delivered` |
| `order_items.fulfillment_status` | `order_received` | `delivered` |
| `vendor_pickups.status` | `IN_TRANSIT` | `COMPLETED` |
| `vendor_pickups.actual_pickup_date` | `2026-10-27 11:41:31.76199+00` | `2026-10-27 11:41:31.76199+00` (preserved) |
| `vendor_pickups.completed_at` | `NULL` | `2026-11-13 10:04:54.566054+00` (or `2026-10-27` if restored below) |

> [!NOTE]
> Because `orders.delivered_at` had already been overwritten to `2026-11-13 10:04:54.566054+00` before `a380bff`, if finance/ops wants the vendor payout hold timer anchored to the original `2026-10-27 11:41:43.871327+00` delivery notification, run this explicit one-off adjustment **before** running `reconcile_shipbubble_orders.py`:
> ```sql
> UPDATE orders
> SET delivered_at = '2026-10-27 11:41:43.871327+00'
> WHERE order_number = 'SHP-20261020-BBB4B3C9'
>   AND delivered_at = '2026-11-13 10:04:54.566054+00';
> ```

---

## 2. Staging Reconciliation Results (`render_backup4.dump` Verification)

Verified locally on a temporary restore of `render_backup4.dump` (`alembic upgrade heads` to `f8a9b0c1d2e3`, followed by `python scripts/reconcile_shipbubble_orders.py --apply`):

| Order Number | ShipBubble ID (`status`) | Before (`order` / `item` / `pickup` / `actual_pickup_date` / `completed_at`) | After (`order` / `item` / `pickup` / `actual_pickup_date` / `completed_at`) |
|---|---|---|---|
| `SHP-20261015-4BFBA016` | `SB-8F97721104F9` (`pending`) | `pickup_scheduled` / `order_received` / `IN_TRANSIT` / `2026-10-15T10:15:41Z` / `NULL` | `picked_up` / `picked_up` / `IN_TRANSIT` / `2026-10-15T10:15:41Z` / `NULL` |
| `SHP-20261015-EB893949` | `SB-E540BE6F91E8` (`completed`) | `delivered` / `order_received` / `IN_TRANSIT` / `2026-10-15T10:21:34Z` / `NULL` | `delivered` / `delivered` / `COMPLETED` / `2026-10-15T10:21:34Z` / `2026-10-15T10:26:28Z` |
| `SHP-20261015-4EB3B889` | `SB-E129BA7380F5` (`pending`) | `pickup_scheduled` / `pickup_scheduled` / `SCHEDULED` / `NULL` / `NULL` | `pickup_scheduled` / `pickup_scheduled` / `SCHEDULED` / `NULL` / `NULL` (unchanged) |
| `SHP-20261015-5F737AA5` | `SB-868E4278EC66` (`pending`) | `pickup_scheduled` / `order_received` / `IN_TRANSIT` / `2026-10-15T11:47:30Z` / `NULL` | `picked_up` / `picked_up` / `IN_TRANSIT` / `2026-10-15T11:47:30Z` / `NULL` |
| `SHP-20261015-02A440DE` | `SB-B9BC4A9C56CE` (`completed`) | `delivered` / `order_received` / `IN_TRANSIT` / `2026-10-15T12:14:53Z` / `NULL` | `delivered` / `delivered` / `COMPLETED` / `2026-10-15T12:14:53Z` / `2026-10-15T12:16:31Z` |
| `SHP-20261015-1EC84042` | `SB-219F419D4C18` (`completed`) | `delivered` / `order_received` / `IN_TRANSIT` / `2026-10-15T12:38:39Z` / `NULL` | `delivered` / `delivered` / `COMPLETED` / `2026-10-15T12:38:39Z` / `2026-10-15T12:41:06Z` |
| `SHP-20261109-179EC334` | `SB-333ADF92DEDB` (`picked_up`) | `picked_up` / `order_received` / `IN_TRANSIT` / `2026-11-09T13:26:34Z` / `NULL` | `picked_up` / `picked_up` / `IN_TRANSIT` / `2026-11-09T13:26:34Z` / `NULL` |
| `SHP-20261120-D14425FD` | `SB-96837C8C7BCF` (`in_transit`) | `delivered` / `order_received` / `COMPLETED` / `NULL` / `2026-11-20T08:55:44Z` | `delivered` / `delivered` / `COMPLETED` / `2026-11-20T08:55:44Z` / `2026-11-20T08:55:44Z` |

Additionally, all unbooked `domestic_checkout_v1` orders whose `order_items.fulfillment_status` had remained `order_received` (including `cancelled` orders) were backfilled in step by migration `f8a9b0c1d2e3`.

---

## 3. Stored `order_items.fulfillment_status` Contract (`domestic_checkout_v1`)

- Previously, `trg_order_items_checkout_completion` fired on `AFTER INSERT OR UPDATE OR DELETE ON order_items` without a column list, re-running `validate_checkout_prerequisite_order(...)` (which enforces `stock_reservations.state = 'active'`) whenever `order_items.fulfillment_status` was updated on a paid order (`state = 'consumed'`).
- Migration `f8a9b0c1d2e3` aligns `trg_order_items_checkout_completion` with `trg_orders_checkout_completion` by scoping `UPDATE OF` to checkout-prerequisite and item-identity/inventory columns (`id,order_id,product_id,variant_id,vendor_id,inventory_policy,inventory_subject_kind,inventory_subject_id,inventory_source_product_id,inventory_source_catalogue_version,inventory_source_evidence_hash,inventory_policy_snapshot_at,quantity,unit_price,subtotal,currency`).
- `sync_vendor_items_and_pickups_for_order_status` now updates `order_items.fulfillment_status` for **all** cohorts including `domestic_checkout_v1`, keeping stored SQL reports and computed UI views in agreement.

---

## 4. Webhook Configuration, Scheduled Polling & Recovery Runbook

### A. ShipBubble Dashboard Webhook Configuration

Configure the webhook URL in both ShipBubble environments (ensure sandbox and live keys each point to their respective API):
- **Staging (Sandbox key `sb_sandbox_...`)**: `https://shopsoma-staging-api.onrender.com/api/v1/shipping/webhooks/shipbubble`
- **Production (Live key `sb_live_...`)**: `https://shopsoma-production-api.onrender.com/api/v1/shipping/webhooks/shipbubble`

Verification & behavior:
- Incoming POSTs must carry `x-ship-signature` (HMAC-SHA512 hex digest of the raw request body keyed with `SHIPBUBBLE_API_KEY`).
- Unmatched payloads (missing `order_id` → HTTP `422`; unknown `shipbubble_order_id` → HTTP `404`) are persisted in `shipbubble_webhook_events` with `status = 'unmatched'` and logged at `WARNING`. If the same payload is later retried after the shipment is saved, deduplication allows re-processing `unmatched` events into `processed`.

### B. Render Celery Worker / Beat Fallback Polling

- Celery task `app.tasks.carrier_tracking_reconciliation.reconcile_carrier_tracking` runs via Celery Beat every `CARRIER_RECONCILIATION_INTERVAL_SECONDS` (default `600` seconds) and polls non-terminal paid ShipBubble orders (`NOT IN ('delivered', 'returned', 'cancelled')`) in batches of `CARRIER_RECONCILIATION_BATCH_SIZE` (default `50`).
- **Render Environment Requirement**: Confirm `SHIPBUBBLE_API_KEY` is synced to the worker service (`shopsoma-staging-checkout-outbox-worker` in `render.yaml` and the corresponding production worker in the Render dashboard). If missing, the task logs a warning and skips polling (`skipped_unconfigured = 1`).

### C. Operational Monitoring Queries

```sql
-- Inspect unmatched or failed webhook deliveries
SELECT id, event_id, event_type, status, error_message, created_at, processed_at
FROM shipbubble_webhook_events
WHERE status <> 'processed'
ORDER BY created_at DESC
LIMIT 50;

-- Detect any residual out-of-step orders across orders, items, and pickups
SELECT o.order_number,
       o.fulfillment_status AS order_status,
       oi.fulfillment_status AS item_status,
       vp.status AS pickup_status,
       vp.actual_pickup_date,
       sb.shipbubble_order_id,
       sb.status AS shipbubble_status
FROM orders o
JOIN order_items oi ON oi.order_id = o.id
LEFT JOIN vendor_pickups vp ON vp.order_item_id = oi.id
LEFT JOIN shipbubble_shipments sb ON sb.order_id = o.id
WHERE (sb.id IS NOT NULL OR o.delivery_provider ILIKE 'shipbubble%')
  AND (
    (oi.fulfillment_status <> 'cancelled' AND oi.fulfillment_status <> o.fulfillment_status)
    OR (o.fulfillment_status = 'delivered' AND (vp.status IS DISTINCT FROM 'COMPLETED' OR vp.actual_pickup_date IS NULL))
    OR (o.fulfillment_status IN ('in_transit', 'out_for_delivery') AND (vp.status NOT IN ('SHIPPED_TO_CUSTOMER', 'COMPLETED') OR vp.actual_pickup_date IS NULL))
    OR (o.fulfillment_status = 'picked_up' AND (vp.status = 'SCHEDULED' OR vp.actual_pickup_date IS NULL))
  )
ORDER BY o.created_at DESC;
```

### D. Running One-Off Reconciliation

1. Ensure migrations are at head (`alembic upgrade heads` / deploy startup).
2. Run a read-only dry run first and capture the JSON output:
   ```bash
   cd shopsoma-backend
   python scripts/reconcile_shipbubble_orders.py --database-url "$DATABASE_URL" --report-path reconcile_dry_run.json
   ```
3. Apply reconciliation (all ShipBubble orders or a specific order):
   ```bash
   python scripts/reconcile_shipbubble_orders.py --database-url "$DATABASE_URL" --apply --report-path reconcile_applied.json
   # Or target a single order:
   python scripts/reconcile_shipbubble_orders.py --database-url "$DATABASE_URL" --order-number SHP-20261020-BBB4B3C9 --apply --report-path prod_reconcile.json
   ```
