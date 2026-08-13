# Checkout Prerequisite Architecture Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Lock the repository-grounded prerequisite contract for a safe, feature-gated `create order -> pre-payment estimate selection -> exact stock reservations -> payment bridge initialization` sequence.

**Architecture:** Preserve legacy behavior for explicitly classified legacy cohorts while introducing an immutable order workflow cohort and a separate pre-payment estimate aggregate. An enforced domestic order must select one server-priced estimate, reserve every stock-managed line, and only then initialize an order-bound payment attempt; final DHL quote truth remains bound to the post-QC, packed, sealed hub package and is never used as checkout estimate truth. All activation is false by default.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL constraints/triggers/row locks, Alembic, React/TypeScript/Vite, pytest, Vitest.

---

## 0. Status, evidence, and frozen scope

This Milestone 1 deliverable is architecture only. It is grounded at parent commit `8d5ef066d2994f62ae5bbef78c43da6f84318b4a` and parent tree `328e3e8438f30cbcf18eae6f7fa817a5d084bee7`.

Repository evidence:

- `AGENTS.md`: backend owns permissions, totals, payment verification, and lifecycle; database owns transactional/audit truth; migrations must be additive and production-safe.
- `/opt/data/projects/shopsoma/PROJECT_CONTEXT.md` lines 32–65: hub-origin domestic DHL, backend-owned quote/payable total, feature gates, immutable evidence, no automatic booking in the payment bridge, and no production activation without commercial/operational confirmation.
- `shopsoma-backend/app/models/order.py`: every order currently requires a `customer_id`; order/item money and status are persisted; no workflow cohort exists.
- `shopsoma-backend/app/api/v1/orders.py`: guest checkout creates/reuses a passwordless user; current create-order path checks stock without row locking, then creates pickups/vendor notifications, decrements product/variant/size stock, commits, and sends emails before payment.
- `shopsoma-backend/app/models/customer_shipping_quote.py` and `app/api/v1/shipping_quotes.py`: existing customer quotes are authenticated-only, immutable, explicitly tied to ready sealed hub packages/outbound intents, and require explicit option selection.
- `shopsoma-backend/app/models/stock_payment_persistence.py`, `app/services/payments/fulfilment_bridge.py`, and migration `f9d1b3e5a7c9_add_stock_payment_persistence.py`: reservations and payment attempts currently require final sealed-package quote/selection/intent identities; lock-coordinator and payment evidence foundations exist; legacy fallback is inferred from missing bridge records.
- `shopsoma-frontend/src/pages/checkout/Checkout.tsx` and `src/services/checkoutService.ts`: client currently reviews, creates an order, and immediately initializes payment; shipping calculation auto-selects a recommended/first rate; the Paystack popup amount is taken from the review state rather than initialization truth.
- `shopsoma-backend/app/core/config.py`: domestic workflow, quote enforcement, and provider-call flags are false by default; quote/payment/auth-grace durations are bounded configuration.

Frozen scope: prerequisites only. No DHL booking, label, pickup, tracking, live carrier call, real payment-provider call, deployment, gate activation, or reinterpretation of historical orders.

## 1. Normative domain boundary

### 1.1 Checkout estimate

A **checkout shipping estimate** is server-created before payment from the order's immutable item, destination, currency, and workflow-policy snapshots. It answers “what shipping amount and service promise may the customer select and pay now?” It may use an approved static domestic rate or later sandbox-derived normalized input, but this architecture does not authorize a carrier call. It is not evidence of final parcel dimensions, seal, custody, DHL acceptance, booking, or final carrier charge.

An estimate is order-bound, expiring, supersedable until selected, and may contain one or more options. When more than one eligible option exists, the customer must explicitly select one; there is no default/first-option server or frontend selection. Selection snapshots the amount added to the payable order total.

### 1.2 Final sealed-package quote

The existing `customer_shipping_quotes`, `customer_shipping_quote_options`, and `customer_shipping_quote_selections` aggregate remains **final post-QC/sealed-package shipping truth**. It requires the exact ready `hub_package`, `hub_package_seal`, `outbound_shipment_intent`, ShopSoma hub, and destination hash. It may later carry normalized DHL evidence. It is not a checkout prerequisite and must not be fabricated before QC/pack/measure/seal.

A final quote may differ from the checkout estimate. The commercial owner must decide before checkout activation who absorbs or collects packed variance and what thresholds block shipment. Safe default: do not mutate the paid order total, do not silently charge/refund, and hold the shipment for staff reconciliation when final cost differs.

### 1.3 Aggregate flow

1. Create a pending order and immutable item/address/price snapshots; perform no external or fulfilment side effect.
2. Create/list checkout estimate options from server truth.
3. Customer explicitly selects one unexpired option.
4. In the same transaction, lock all stock subjects deterministically and create exact reservation rows for every stock-managed order item; made-to-order lines are explicitly recorded as non-stock-managed coverage.
5. Initialize the payment bridge only when selection and complete reservation coverage are valid.
6. On exact server-side verified payment, atomically consume reservations and enqueue post-payment commands.
7. Vendor preparation/inbound-to-hub begins only from those post-payment commands. Final DHL quote occurs only after hub receipt, QC, pack, measure, and seal.

## 2. Persistence contract

All enum-like columns below use PostgreSQL check constraints initially, matching the repository's current string-state persistence and allowing additive enum expansion without PostgreSQL enum surgery.

### 2.1 `orders` additive columns

- `workflow_cohort varchar(40) NULL` during expand/backfill, later `NOT NULL`.
  - Allowed: `legacy_pre_bridge`, `domestic_checkout_v1`.
  - Immutable after insert by trigger.
- `workflow_policy_version varchar(40) NULL` during expand/backfill, later `NOT NULL`; immutable, printable ASCII identifier. Proposed current value for new enforced orders: `domestic_checkout_v1`.
- `checkout_access_mode varchar(20) NULL` during expand/backfill, later `NOT NULL`; allowed `authenticated`, `guest_capability`; immutable.
- `checkout_estimate_selection_id uuid NULL`, FK to `checkout_shipping_estimate_selections(id) ON DELETE RESTRICT`; set once for `domestic_checkout_v1`, then immutable.
- `checkout_prerequisites_completed_at timestamptz NULL`; set only after selection plus coverage are atomically valid.

Checks after validation:

- legacy orders: `workflow_cohort='legacy_pre_bridge'`, no requirement for new selection/completion fields.
- enforced orders: `workflow_cohort='domestic_checkout_v1'`, `workflow_policy_version='domestic_checkout_v1'`; payment initialization requires non-null selection/completion but order insertion does not, because insertion precedes selection.
- `checkout_access_mode` must match whether the order was issued a guest capability at creation; an authenticated order cannot later be downgraded to guest mode.

Indexes:

- `ix_orders_workflow_cohort_created_at(workflow_cohort, created_at)`.
- partial index `ix_orders_domestic_prerequisite_pending(id) WHERE workflow_cohort='domestic_checkout_v1' AND checkout_prerequisites_completed_at IS NULL`.

### 2.2 `checkout_shipping_estimates`

Columns:

- `id uuid PK`.
- `order_id uuid NOT NULL FK orders(id) ON DELETE RESTRICT`.
- `customer_id uuid NOT NULL FK users(id) ON DELETE RESTRICT` (the existing guest-created user remains ownership identity, not bearer authorization).
- `destination_snapshot_hash char(64) NOT NULL` lowercase SHA-256 over canonical server-owned destination snapshot.
- `order_snapshot_hash char(64) NOT NULL` over ordered item IDs, quantities, prices/currencies, destination, discounts/tax policy, and workflow policy version.
- `currency char(3) NOT NULL` uppercase; must equal order currency.
- `ttl_seconds integer NOT NULL`; configured, not hard-coded in business logic; database check `BETWEEN 300 AND 3600`.
- `expires_at timestamptz NOT NULL`, database-derived from creation time.
- `supersedes_estimate_id uuid NULL FK checkout_shipping_estimates(id) ON DELETE RESTRICT`.
- `source_kind varchar(30) NOT NULL`; allowed initially `static_domestic_rate`, `sandbox_normalized` (the second is inert until separately authorized).
- `source_reference varchar(200) NULL`; sanitized internal provenance only, never credentials/raw response.
- `source_command varchar(100) NOT NULL`, `idempotency_key varchar(200) NOT NULL`, `request_fingerprint char(64) NOT NULL`, `schema_version varchar(40) NOT NULL`.
- `created_by_actor_type varchar(20) NOT NULL` allowed `customer`, `guest_capability`, `staff` and `created_by_actor_id varchar(200) NOT NULL` (guest actor ID is capability row ID, never token/hash).
- `created_at timestamptz NOT NULL`, `creation_txid bigint NOT NULL`, `row_version integer NOT NULL DEFAULT 1`.

Constraints/indexes:

- immutable after insert.
- unique `(customer_id, source_command, idempotency_key)`.
- unique `(supersedes_estimate_id)`.
- unique `(id, order_id)` and `(id, customer_id)` for composite ownership FKs.
- only the current unselected leaf may be superseded; selected estimates cannot be superseded.
- checks for positive TTL, hash formats, uppercase currency, nonblank bounded identifiers.
- indexes `(order_id, created_at)`, `(expires_at)`, `(order_snapshot_hash)`.

### 2.3 `checkout_shipping_estimate_options`

Columns:

- `id uuid PK`.
- `estimate_id uuid NOT NULL FK checkout_shipping_estimates(id) ON DELETE RESTRICT`.
- `option_key varchar(100) NOT NULL`.
- `service_code varchar(100) NOT NULL`, `service_label varchar(200) NOT NULL`.
- `amount numeric(18,4) NOT NULL`, `currency char(3) NOT NULL`.
- `min_delivery_days integer NULL`, `max_delivery_days integer NULL`.
- `source_rate_id uuid NULL FK shipping_rates(id) ON DELETE RESTRICT` for current static rate provenance.
- `created_at timestamptz NOT NULL`.

Constraints/indexes:

- immutable after insert; option must be inserted in estimate creation transaction.
- amount finite and `> 0`; currency equals estimate currency.
- delivery range either both null or `0 <= min <= max <= 365`.
- unique `(estimate_id, option_key)`, unique `(id, estimate_id)`, and unique `(estimate_id, source_rate_id)` when source is static.
- index `(estimate_id)`.

### 2.4 `checkout_shipping_estimate_selections`

Columns:

- `id uuid PK`.
- `estimate_id uuid NOT NULL`, `option_id uuid NOT NULL`, `order_id uuid NOT NULL`, `customer_id uuid NOT NULL`.
- `selected_by_actor_type varchar(20) NOT NULL` allowed `customer`, `guest_capability`; `selected_by_actor_id varchar(200) NOT NULL`.
- immutable monetary snapshot: `shipping_amount numeric(18,4) NOT NULL`, `currency char(3) NOT NULL` copied from option.
- `source_command varchar(100) NOT NULL`, `idempotency_key varchar(200) NOT NULL`.
- `selected_at timestamptz NOT NULL`, `created_at timestamptz NOT NULL`.

Composite FKs/checks/indexes:

- `(estimate_id, order_id) -> checkout_shipping_estimates(id, order_id) ON DELETE RESTRICT`.
- `(estimate_id, customer_id) -> checkout_shipping_estimates(id, customer_id) ON DELETE RESTRICT`.
- `(option_id, estimate_id) -> checkout_shipping_estimate_options(id, estimate_id) ON DELETE RESTRICT`.
- amount/currency must equal selected option; estimate must be current, unexpired, snapshot hashes must still match locked order truth.
- unique `(estimate_id)`; unique `(order_id)` (one checkout selection per order); unique `(customer_id, source_command, idempotency_key)`.
- immutable; no update/delete.

Selection atomically writes `orders.checkout_estimate_selection_id`, recalculates `shipping_cost`, `tax_amount`, and `total_amount` from server snapshots, and creates reservation coverage. A changed cart/address/currency requires a new order or an explicit pre-payment order-revision command that invalidates selection and reservations; this plan chooses the smaller safe V1: create a new order and cancel/release the old one.

### 2.5 `order_guest_capabilities`

Columns:

- `id uuid PK` (public token lookup also requires token; UUID alone grants nothing).
- `order_id uuid NOT NULL FK orders(id) ON DELETE RESTRICT`.
- `customer_id uuid NOT NULL FK users(id) ON DELETE RESTRICT`.
- `scope varchar(40) NOT NULL`; allowed initially `checkout_prerequisites`, `read_order`, `claim_order`. Issue separate capabilities per scope; do not overload one broad token.
- `token_digest char(64) NOT NULL` = HMAC-SHA-256(server pepper, random token); plaintext is returned once and never persisted/logged.
- `expires_at timestamptz NOT NULL`, `revoked_at timestamptz NULL`, `replaced_by_id uuid NULL FK same table ON DELETE RESTRICT`.
- `claimed_by_user_id uuid NULL FK users(id) ON DELETE RESTRICT`, `claimed_at timestamptz NULL`.
- `created_at`, `last_used_at`, `row_version integer NOT NULL DEFAULT 1`.

Constraints/indexes:

- unique `(token_digest)`; unique `(replaced_by_id)`; index `(order_id, scope, expires_at)`.
- lifecycle check: active has no revocation/replacement/claim; rotation revokes old and references one new row; claim scope records claimant/time and is revoked in the same transaction.
- maximum TTL is an explicit pre-implementation decision. Safe default: use the existing bounded payment-window plus auth-grace configuration for checkout scope, fail closed if unset/invalid; claim/read TTL needs product/security approval before activation.

### 2.6 Reservation coverage changes

Keep `stock_reservations` and its states, lock coordinator, audit fields, money fields, and exact product/variant/size identities. Replace the pre-payment dependency on final quote truth for new cohorts:

- add `checkout_estimate_selection_id uuid NULL FK checkout_shipping_estimate_selections(id) ON DELETE RESTRICT`.
- retain existing `quote_id`, `quote_selection_id`, `quote_option_id`, `intent_id` as nullable **legacy/final-quote binding columns** during compatibility; do not drop in the expand release.
- add `inventory_subject_kind varchar(20) NOT NULL` allowed `product`, `product_variant`, `size_stock` and `inventory_subject_id uuid NOT NULL`; keep existing identity columns as audit snapshots and require exact consistency.
- add unique `(order_item_id, checkout_estimate_selection_id)` for new checkout reservations.
- binding check: exactly one binding family is populated: all new checkout-selection fields for `domestic_checkout_v1`, or all legacy final-quote fields for existing bridge records. Never infer cohort from which family is null.
- reservation `currency`/unit price must match the order-item snapshot, not estimate shipping amount.

Add `order_inventory_coverage` for made-to-order and completeness proof:

- `order_item_id uuid PK FK order_items(id) ON DELETE RESTRICT`, `order_id uuid NOT NULL`, `coverage_kind varchar(30) NOT NULL` allowed `stock_reservation`, `made_to_order_no_stock`, `coverage_id uuid NULL` (reservation ID for stock-managed; null for MTO), `made_to_order_snapshot boolean NOT NULL`, `created_at`.
- checks enforce stock-managed rows reference exactly one reservation and MTO rows have no reservation plus `made_to_order_snapshot=true`.
- unique `(order_id, order_item_id)` and index `(order_id, coverage_kind)`.

### 2.7 Payment attempt compatibility

For `payment_attempts`:

- add `checkout_estimate_selection_id uuid NULL FK ... ON DELETE RESTRICT` and immutable `workflow_cohort varchar(40) NULL`.
- make final `quote_id`, `quote_selection_id`, `quote_option_id`, `intent_id` nullable only after new checks exist.
- binding check keyed by persisted cohort: `domestic_checkout_v1` requires checkout selection and forbids final-quote fields; `legacy_pre_bridge` retains current binding or true legacy payment behavior.
- `amount` equals the locked order `total_amount`; `currency` equals order currency. Client amount/currency are ignored.
- `payment_attempt_reservations` remains exact immutable membership. Completeness validator requires every `stock_reservation` coverage row and no extra reservation; MTO coverage is proven separately.

No existing final quote table is renamed or repurposed.

## 3. Migration and deployment sequence

### 3.1 Expand (gates off)

1. Add nullable order cohort/policy/access/selection/completion columns and immutable-write guards that permit null historical values.
2. Create checkout estimate, option, selection, guest-capability, and inventory-coverage tables.
3. Add nullable checkout-selection/cohort columns to reservations/attempts; add new subject columns nullable initially.
4. Add `NOT VALID` FKs/checks where table scans/locking could be material; create indexes concurrently in a separate non-transactional Alembic revision if production size warrants it.
5. Deploy code capable of reading both old and new shapes with all gates false. No new cohort is emitted.

Rollback boundary: before any `domestic_checkout_v1` order exists, code may roll back and additive tables/columns may remain inert. Do not downgrade/drop populated audit tables in production.

### 3.2 Historical backfill/classification

Create an auditable classification job/table, not a single inference query:

- `order_workflow_classifications(order_id PK, cohort, policy_version, access_mode, evidence_kind, evidence_reference, classified_at, classified_by, notes_hash)`.
- Deterministic evidence sources: order creation timestamp relative to recorded activation event; an explicit release/deployment marker; existing payment/quote/reservation provenance; authenticated vs guest-created ownership evidence. The exact activation timestamp/release marker must be supplied by operations before running.
- Ambiguous rows go to `classification_required` operational output and remain unenforced. They are not classified from missing quote, reservation, attempt, capability, or shipment rows.
- Backfill `legacy_pre_bridge` only from positive evidence. New cohort assignment occurs only at order insertion after gate/cohort decision.

Stop if the activation marker or ambiguous-row disposition is unavailable. Do not manufacture reservation/deduction provenance for historical rows (consistent with migration `f9...` comments 202–207).

### 3.3 Validate

1. Reconcile counts: every order has one positive classification; no ambiguous row is forced.
2. Backfill new subject-kind/ID only where exact existing reservation columns prove identity.
3. Validate `NOT VALID` constraints in bounded operations.
4. Prove no new-cohort attempt lacks selection or complete coverage; prove no selected estimate is expired/superseded or mismatched.
5. Set order cohort/policy/access columns `NOT NULL` only after reconciliation.

### 3.4 Later contract

Only after all deployed code writes/reads the new model and historical evidence is reconciled:

- remove fallback based on missing records;
- make new reservation subject and attempt cohort fields non-null where applicable;
- optionally move old final-quote reservation/attempt binding to an archived compatibility table;
- drop old columns/constraints only in a separately approved destructive migration.

Safe rollback after new orders exist is **operational**, not schema downgrade: turn gate off for new order assignment while continuing to process existing `domestic_checkout_v1` orders under their immutable policy. Never reinterpret in-flight orders as legacy, delete capabilities/reservations, or re-enable pre-payment side effects.

## 4. Guest security contract

### Issuance

- On guest order creation, generate at least 256 random bits using a CSPRNG.
- Return an opaque value containing capability row ID plus random secret once, over TLS. Store only HMAC-SHA-256 digest with a deployment-managed pepper distinct from JWT/payment secrets.
- Set `orders.checkout_access_mode='guest_capability'`; bind each capability to exact order, guest customer identity, scope, and expiry.
- Never place token in URL/query, analytics, exception text, email logs, or database plaintext. Frontend keeps checkout token in memory or session storage only; claim/read links require a separate one-time scoped token.

### Verification and anti-enumeration

- Require both order ID and bearer capability; constant-time digest comparison after indexed digest lookup.
- Verify scope, order/customer binding, expiry, revocation, replacement, and cohort inside the order row lock.
- Unknown order, wrong owner, wrong token/scope, revoked, and expired return the same generic `404 checkout not available`; rate-limit by network and digest prefix without logging raw credentials.
- UUID/order number/email alone never authorizes quote, selection, reservation, payment initialization, order read, or claim.

### Rotation/revocation

- Rotate by creating a new capability and atomically revoking/linking the old; old token stops immediately.
- Revoke checkout scope on cancellation, successful claim, detected compromise, or terminal payment beyond recovery policy.
- Expiry is database-clock authoritative. Expired checkout capability cannot start a new attempt; authenticated provider evidence may still recover a previously started attempt under payment authorization rules.

### Claim

- Claim requires an authenticated verified-email user plus a valid one-time `claim_order` capability; email equality alone is insufficient.
- Lock capability, order, guest user, and target user in deterministic order. If order is already claimed, replay by same user succeeds; a different user receives generic conflict.
- Set `claimed_by_user_id/claimed_at`, revoke all guest capabilities, transfer order ownership only through the approved service, and preserve immutable original guest customer identity in classification/audit metadata. Existing selections, reservations, attempts, and evidence remain order-bound; ownership FKs must be updated through one audited claim command or ownership must be represented by a separate current-owner projection. Pre-implementation decision: choose the latter (safer, no mutation of immutable aggregate ownership) unless repository-wide order ownership requirements prove otherwise.

## 5. Reservation state machine and locking

The only reservation lifecycle states are `active/released/consumed/expired`; transitions are one-way from `active`, and terminal-state replays are idempotent.

### States and transitions

| From | Command/event | To | Guard and effect |
|---|---|---|---|
| none | `select_checkout_estimate` | active | order/selection valid; all stock subjects locked; available = physical stock minus unexpired active reservations; create exact coverage atomically |
| active | exact verified payment | consumed | attempt contains exact reservation set; decrement each physical stock subject once; set terminal reason/time; enqueue post-payment outbox |
| active | customer/admin cancel before verified payment | released | no verified/unknown-live payment outcome; restore availability by ending claim only (no stock increment because reservation did not decrement) |
| active | database-clock TTL elapsed and no live/unknown attempt | expired | terminalize idempotently; no stock mutation |
| active | payment failure with terminal authenticated evidence | released | terminal failure and no competing started/unknown attempt |
| active | late verified success inside authorization/recovery deadline | consumed | serialize against expiry/release; if released/expired, reacquire exact stock atomically or route to paid-stock-exception without overselling |
| consumed | replay/cancel/failure | consumed | immutable inventory truth; refund/cancellation is a separate compensated restock policy, never state reversal |
| released/expired | duplicate release/expiry | same | idempotent replay |

### Coverage

- Product without detailed variant: reserve `products.total_stock` by `(product, product_id)`.
- `ProductVariant`: reserve `product_variants.stock` by `(product_variant, variant_id)` and include parent product lock.
- `SizeStock`: reserve `size_stocks.stock` by `(size_stock, size_stock_id)` and include variation and parent product locks.
- Made-to-order: no fake stock of `999999`; snapshot `made_to_order_no_stock` coverage. Payment may proceed only if every line has exactly one coverage row.
- Duplicate cart lines for the same subject are aggregated for availability while retaining per-order-item reservation/coverage identity.

### Lock order and concurrency

Canonical transaction order:

1. order coordinator/order row;
2. product IDs ascending;
3. variation IDs ascending;
4. product-variant IDs ascending;
5. size-stock IDs ascending;
6. reservation IDs ascending;
7. payment-attempt ID.

Use the existing `stock_payment_lock_coordinator` namespace and sorted UUIDs. Availability and inserts occur in one transaction under locks. A partial reservation set rolls back fully. Unique idempotency identities replay the same result; same key with different request fingerprint is `409`. Serialization/deadlock failures may retry a bounded number with jitter at service boundary; retry exhaustion returns `409/503` without partial rows. TTL values use bounded settings and database clock; exact production duration remains an explicit operations decision.

### Cancellation and late payment

Cancellation locks order then attempt then reservation subjects. A `call_started` or `abandoned_unknown` attempt blocks destructive cancellation/release until provider outcome reconciliation or authorization deadline. A late success:

- before authorization deadline: attempts atomic reacquisition if reservation expired/released; if unavailable, mark payment verified and create `paid_stock_exception` outbox for human refund/substitution—never decrement below zero and never notify vendor to start;
- after deadline: still record authenticated money truth idempotently, block fulfilment, and route to `late_payment_exception`; do not discard or mislabel received funds.

## 6. Verified-payment side effects and outbox

For `domestic_checkout_v1`, order creation, estimate creation/selection, reservation, and provider initialization must not:

- decrement stock;
- create/schedule `VendorPickup`;
- create/send vendor `order_placed` notification/email;
- instruct production for made-to-order items;
- begin inbound pickup, QC, packing, shipment, payout, or fulfilment status advancement.

Add a narrow `checkout_outbox_events` table in Milestone 4 (not a generalized platform):

- `id uuid PK`, `aggregate_type='order'`, `aggregate_id=order_id`, `event_type` allowed initially `payment_verified_start_order`, `paid_stock_exception`, `late_payment_exception`, `payment_failed_release`, `order_cancelled_release`;
- `idempotency_key varchar(200) NOT NULL UNIQUE`, `payload_schema_version`, sanitized `payload jsonb`, `created_at`, `available_at`, `claimed_at`, `claim_token`, `processed_at`, `attempt_count`, `last_error_code` (no secrets/PII/raw provider payload).

Exact boundary: in the same database transaction that validates immutable payment attempt amount/currency/reference and writes terminal payment evidence:

1. consume the exact reservation membership (or persist exception state);
2. update payment/order truth;
3. insert one outbox row keyed `payment_verified_start_order:{attempt_id}`.

A worker claims with `FOR UPDATE SKIP LOCKED`, creates vendor pickup/notification/production commands idempotently using unique `(source_event_id, effect_kind, subject_id)`, then marks processed. Crash before commit replays; crash after effect commit is deduplicated. Email is sent only from a durable notification record and records provider/message identity. Outbox failure leaves paid order visible as `post_payment_processing_pending`; operators can replay without replaying payment or stock consumption.

Final quote/booking is not emitted by this outbox event; later hub/package readiness drives it independently.

## 7. False-by-default gate and cohort matrix

Introduce `DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED: bool = False` plus a strict server-owned cohort allowlist/percentage policy. Existing DHL gates remain separate; this prerequisite gate must not imply provider calls.

| Case | New order cohort | Behavior |
|---|---|---|
| gate off | `legacy_pre_bridge` | established checkout remains available; no new prerequisites inferred; this is compatibility, not permission to reinterpret an enforced order |
| gate on + eligible authenticated domestic order | `domestic_checkout_v1` | estimate selection + complete coverage required before bridge initialization |
| gate on + eligible guest domestic order | `domestic_checkout_v1` | same, authorized by scoped guest capability |
| gate on + ineligible geography/currency/cohort | `legacy_pre_bridge` or checkout unavailable according to explicit rollout policy | assignment is persisted at creation; no mid-order flip |
| historical order | positively backfilled classification | behavior follows persisted cohort, never current gate and never missing-record inference |
| gate later off | existing enforced order remains enforced | kill switch stops assigning new cohort/provider start as configured but preserves recovery/cancel/release for in-flight orders |
| authenticated claim of guest order | unchanged | cohort/policy immutable; authorization projection changes, prerequisites do not restart |

Safe rollout default: allowlist empty, percentage zero, Nigeria domestic only, no USD unless finance explicitly approves the estimate/payment currency policy. The repository supports NGN/USD, so code/schema must preserve either currency; activation eligibility is a policy decision, not a schema assumption.

## 8. API and frontend sequence

### Backend API

1. `POST /orders` creates the persisted cohort order. For guest mode, response includes the one-time checkout capability only on initial creation. No stock decrement or fulfilment side effects for enforced cohort.
2. `POST /orders/{order_id}/checkout-estimates` with `X-Idempotency-Key` and authenticated identity or `X-ShopSoma-Checkout-Capability`; server revalidates order snapshots and returns options.
3. `GET /orders/{order_id}/checkout-estimates` and `GET .../{estimate_id}` use the same ownership/capability rules and anti-enumeration.
4. `POST /orders/{order_id}/checkout-estimates/{estimate_id}/options/{option_id}/select` with idempotency key; explicit option ID is mandatory even for one option. Transaction creates selection, recalculates totals, and creates complete coverage/reservations.
5. `POST /payments/initialize` accepts order ID, gateway, callback metadata, and capability/auth only. It ignores client amount/currency and initializes from locked order/selection/coverage truth.

Responses expose `workflow_cohort`, prerequisite status, estimate expiry, selected option, and server payable total; they never expose token digest, internal source payload, or capability existence.

### Failure semantics

- `400/422`: malformed request only.
- generic `404`: order/estimate unavailable, ownership/token failure, or revoked/expired capability (anti-enumeration).
- `409`: stale/superseded/expired estimate, cart/address/currency hash changed, selection mismatch, idempotency conflict, insufficient stock, attempt already started, or cancellation blocked by unknown payment.
- `410`: may be used for a known-owned expired estimate after authorization succeeds; never before auth.
- `503`: no eligible estimate options or bounded concurrency retry exhausted; no partial state.
- payment initialization returns server amount/currency/reference. Provider transport failures preserve `call_started/abandoned_unknown` recovery truth and do not release reservations blindly.

### Frontend

- Replace the current `calculate shipping -> auto-select` behavior for enforced cohort with `create order -> fetch estimate options -> customer selects -> confirm selection/reservation -> initialize payment`.
- Display all options with amount, currency, delivery range, and expiry. No recommended/first auto-selection; disable Continue until an explicit radio/button action succeeds.
- On `409 stale/stock`, refresh options or create a replacement order as directed; never silently switch option.
- Use payment initialization response for Paystack/Stripe amount/currency. Remove dependence on `orderReview.summary.total_amount` at the provider boundary.
- Keep guest capability out of URL and attach only to scoped API calls. Clear on claim/cancel/terminal completion.
- Multi-vendor items remain one parent order and one pre-payment estimate selection in this narrow contract. Reservations are line-exact across all vendors; vendor side effects fan out only after payment.

## 9. Edge-case contract

- **Multi-item:** all-or-nothing reservation coverage; one insufficient line returns `409` and creates none.
- **Multi-vendor:** one parent payable total/selection/attempt; post-payment outbox fan-out is per vendor/item and idempotent. Final hub parcels/dispatch cohorts may split later and must not rewrite checkout estimate truth.
- **Made-to-order:** explicit no-stock coverage; no synthetic quantity; production instruction only after verified payment.
- **NGN/USD:** each order, estimate, option, selection, reservation, and attempt uses one uppercase order currency. Conversion rate/policy is snapshotted server-side at order creation. No mixed-currency arithmetic and no frontend-derived provider amount.
- **Guest claim:** cohort and financial/inventory bindings survive; all guest capabilities revoke atomically; same-user replay succeeds.
- **Payment failure:** authenticated terminal failure releases active reservations exactly once if no unknown outcome remains; no vendor/fulfilment effects.
- **Payment late success:** record money truth; consume/reacquire only without oversell; otherwise exception outbox and fulfilment hold.
- **Estimate expiry:** cannot select; create a new superseding estimate. Existing selection remains valid only through reservation/payment windows encoded at selection; expiry semantics after selection must be explicit in service and tests.
- **Reservation expiry:** no new payment initialization; started payment remains in reconciliation/grace state; expiry worker cannot race terminal verification.
- **Cancellation:** before provider start releases; unknown/started blocks until reconciliation; after verified payment uses refund/compensation workflow and never reverses consumed audit state.
- **Final packed variance:** staff hold by safe default; no silent charge, refund, or shipment booking.

## 10. Milestones 2–5

### Milestone 2: Additive schema, classification tooling, and gate

**Goal:** Install inert persistence and explicit cohort truth without changing live checkout behavior.

**Likely paths:**

- Modify `shopsoma-backend/app/models/order.py`
- Create `shopsoma-backend/app/models/checkout_shipping_estimate.py`
- Create `shopsoma-backend/app/models/order_guest_capability.py`
- Modify `shopsoma-backend/app/models/stock_payment_persistence.py`
- Modify `shopsoma-backend/app/models/__init__.py`
- Modify `shopsoma-backend/app/core/config.py`
- Create sequential revisions under `shopsoma-backend/alembic/versions/`
- Create `shopsoma-backend/app/services/orders/workflow_classification.py`
- Create tests listed in Section 12

**Acceptance:** migrations upgrade/downgrade/upgrade on PostgreSQL; gates default false/empty; exact DDL/model parity; explicit positive-evidence classification with ambiguous quarantine; no legacy behavior change; no historical inference from missing rows.

**Verification:**

- `cd shopsoma-backend && pytest -q tests/test_checkout_prerequisite_migration.py tests/test_order_workflow_classification.py tests/test_checkout_prerequisite_models.py`
- `cd shopsoma-backend && alembic upgrade head && alembic downgrade <pre-m2-revision> && alembic upgrade head`
- `cd shopsoma-backend && ruff check app tests && black --check app tests`

**Non-goals:** routes, frontend, reservation execution, payment transport, DHL calls.

**Stop:** any ambiguous historical row would need forced classification; migration is not online-safe; ORM/frozen DDL differs; gate can become true by default.

### Milestone 3: Order-first estimate selection, guest capability, and reservations

**Goal:** Implement the server-only prerequisite sequence through complete reservation coverage, still with payment/provider calls disabled.

**Likely paths:**

- Modify `shopsoma-backend/app/api/v1/orders.py` and `app/schemas/order.py`
- Create `shopsoma-backend/app/api/v1/checkout_estimates.py`
- Create `shopsoma-backend/app/schemas/checkout_shipping_estimate.py`
- Create `shopsoma-backend/app/services/checkout/estimates.py`
- Create `shopsoma-backend/app/services/checkout/reservations.py`
- Create `shopsoma-backend/app/services/checkout/guest_capabilities.py`
- Modify `shopsoma-backend/app/main.py`
- Add future tests in Section 12

**Acceptance:** enforced create-order has no decrement/pickup/notification; explicit selection creates all-or-none exact coverage; MTO represented explicitly; guest endpoints require scoped hashed capability; deterministic concurrency prevents oversell; cancellation/expiry are idempotent; gate-off and historical paths remain unchanged.

**Verification:**

- `cd shopsoma-backend && pytest -q tests/test_checkout_estimate_api.py tests/test_guest_checkout_capability.py tests/test_checkout_reservation_lifecycle.py tests/test_checkout_reservation_concurrency.py tests/test_order_creation_side_effect_gate.py`
- `cd shopsoma-backend && ruff check app tests && black --check app tests`

**Non-goals:** provider initialization/calls, final DHL quote, vendor work, frontend.

**Stop:** any enforced order can reach payment-ready without exact coverage; UUID/email authorizes guest access; stock can go negative; pre-payment side effect remains.

### Milestone 4: Payment bridge and exactly-once post-payment boundary

**Goal:** Bind initialization and verified-payment finalization to persisted cohort/selection/coverage and release post-payment work through a narrow durable outbox.

**Likely paths:**

- Modify `shopsoma-backend/app/services/payments/fulfilment_bridge.py`
- Modify `shopsoma-backend/app/api/v1/payments.py`
- Modify `shopsoma-backend/app/models/stock_payment_persistence.py`
- Create `shopsoma-backend/app/models/checkout_outbox.py`
- Create `shopsoma-backend/app/services/checkout/outbox.py`
- Modify vendor pickup/notification entry points currently invoked by `app/api/v1/orders.py`
- Add Alembic revision and future tests in Section 12

**Acceptance:** initialization uses only locked server total/currency; exact reservation membership required; verified payment consumes/decrements once and inserts one outbox event atomically; retries cannot duplicate stock/pickup/vendor/production effects; failure/late success/unknown outcome follow Section 5; existing enforced cohorts remain recoverable when gate turns off.

**Verification:**

- `cd shopsoma-backend && pytest -q tests/test_checkout_payment_bridge_prerequisites.py tests/test_verified_payment_inventory.py tests/test_checkout_outbox_exactly_once.py tests/test_checkout_late_payment.py tests/test_payment_fulfilment_bridge_contract.py`
- `cd shopsoma-backend && ruff check app tests && black --check app tests`

**Non-goals:** real Stripe/Paystack calls in tests, DHL call/booking, broad generic outbox platform.

**Stop:** provider can initialize from client money; payment and stock/outbox are not atomic; unknown outcomes release stock; any pre-verification vendor effect survives.

### Milestone 5: Frontend sequence and inert end-to-end acceptance

**Goal:** Make checkout explicitly select a server estimate and use payment initialization truth while all external calls remain mocked/disabled.

**Likely paths:**

- Modify `shopsoma-frontend/src/pages/checkout/Checkout.tsx`
- Modify `shopsoma-frontend/src/services/checkoutService.ts`
- Modify `shopsoma-frontend/src/services/paymentService.ts`
- Create/modify checkout tests under `shopsoma-frontend/src/pages/checkout/` or repository-established test location
- Add backend end-to-end contract tests under `shopsoma-backend/tests/`

**Acceptance:** no auto-selection; multiple options require a customer action; guest capability never enters URL/log output; stale/expiry/stock failures are recoverable and truthful; provider widget receives initialization response amount/currency; authenticated and guest mocked journeys pass for NGN and schema-compatible USD; no external network.

**Verification:**

- `cd shopsoma-frontend && npm test -- --run`
- `cd shopsoma-frontend && npm run lint && npm run build`
- `cd shopsoma-backend && pytest -q tests/test_checkout_prerequisite_end_to_end.py`
- final candidate only: repository canonical backend/frontend gates and independent NightWing exact-tree review.

**Non-goals:** live payment, DHL, deployment, activation, booking/labels/pickup/tracking.

**Stop:** UI can initialize without explicit option selection; client review money reaches provider boundary; guest access survives claim/revocation; any test calls an external system.

## 11. Security, concurrency, and failure matrix

| Threat/failure | Enforcement | Expected result/recovery |
|---|---|---|
| UUID/order-number enumeration | auth or scoped capability plus generic 404 | no existence/owner disclosure |
| plaintext guest-token leak | CSPRNG token returned once; HMAC digest only; redaction | rotate/revoke without database token recovery |
| token replay after claim/rotation | row lock + revoked/replaced/claimed checks | generic 404; same claim replay only for claimant |
| token used on another order/scope | order/customer/scope binding | generic 404 |
| stale cart/address/currency | order/destination snapshot hashes under order lock | 409; create replacement order/estimate |
| option substitution/client amount tamper | composite FKs; server option snapshot; initialization ignores client money | 409 or ignored client fields; no provider call |
| multiple options auto-selected | API requires option ID; frontend explicit action | no selection/payment readiness until action |
| concurrent final selection | order lock + unique order selection | one commit; identical idempotent replay or 409 |
| two carts reserve last unit | deterministic coordinator/stock row locks; active-reservation subtraction | one succeeds; one 409; no negative stock |
| partial multi-line reservation | one DB transaction + completeness check | full rollback |
| deadlock/serialization failure | canonical lock order, bounded service retry | clean retry then 409/503; no partial state |
| expiry races payment verification | order -> attempt -> reservation lock order; DB clock | one terminal path; success reconciled/exceptioned without oversell |
| cancellation races provider call | started/unknown attempt blocks release | reconcile before cancellation completion |
| duplicate webhook/verification | unique external evidence and outbox idempotency | replay result; one stock consumption/event |
| crash after payment truth before vendor work | payment + stock + outbox atomic transaction | worker resumes durable event |
| crash during vendor fan-out | per-effect unique source identity | replay missing effects only |
| final quote differs from estimate | separate aggregates; paid total immutable | staff variance hold; explicit later policy |
| gate disabled mid-order | immutable cohort/policy | no new assignment; in-flight recovery remains |
| legacy row lacks bridge records | positive classification only | never automatically reclassified |
| payment arrives after stock unavailable | authenticated money truth + paid-stock exception | no negative stock/vendor start; human refund/substitution |
| provider timeout/unknown | leased attempt + immutable evidence | reconciliation; no blind retry/release |
| sensitive payload in logs/outbox | hashes/sanitized metadata only | reject/redact raw provider/token/PII payload |

## 12. Executable RED contract inventory (future tests; do not add in Milestone 1)

Each named test must initially fail because the stated behavior is absent.

### `shopsoma-backend/tests/test_checkout_prerequisite_models.py`

- `test_order_workflow_cohort_is_immutable_and_required_after_validation`: absent cohort/policy columns and immutability.
- `test_checkout_estimate_is_distinct_from_sealed_customer_quote`: absent pre-payment aggregate.
- `test_estimate_option_money_and_currency_are_constrained`: absent estimate option table/checks.
- `test_selection_composite_fks_prevent_cross_order_option_substitution`: absent composite binding.
- `test_reservation_requires_exactly_one_binding_family`: current reservation only supports final quote binding.
- `test_made_to_order_line_requires_explicit_non_stock_coverage`: absent coverage table.

### `shopsoma-backend/tests/test_checkout_prerequisite_migration.py`

- `test_expand_upgrade_downgrade_upgrade_preserves_legacy_rows`: absent revisions.
- `test_constraints_install_not_valid_then_validate`: absent staged constraints.
- `test_populated_new_audit_tables_block_destructive_rollback`: absent safe rollback guard/runbook assertion.

### `shopsoma-backend/tests/test_order_workflow_classification.py`

- `test_missing_bridge_records_never_classifies_legacy_order`: current bridge falls back from missing attempt/selection.
- `test_positive_release_evidence_classifies_legacy_order`: absent classifier.
- `test_ambiguous_history_is_quarantined_not_guessed`: absent quarantine.
- `test_gate_change_does_not_change_existing_order_cohort`: absent immutable cohort.

### `shopsoma-backend/tests/test_guest_checkout_capability.py`

- `test_guest_token_plaintext_is_returned_once_and_never_persisted`: absent capability.
- `test_uuid_or_email_without_capability_cannot_access_order`: current guest ownership is a passwordless user identity without this capability boundary.
- `test_capability_is_order_scope_and_ttl_bound`: absent binding.
- `test_wrong_expired_revoked_and_unknown_tokens_are_indistinguishable`: absent anti-enumeration.
- `test_rotation_revokes_old_token_atomically`: absent rotation.
- `test_claim_requires_authenticated_user_and_one_time_claim_scope`: absent claim capability.
- `test_claim_revokes_all_guest_capabilities_without_restarting_checkout`: absent claim lifecycle.

### `shopsoma-backend/tests/test_checkout_estimate_api.py`

- `test_create_order_then_create_estimate_from_server_snapshots`: current review precedes order and uses static shipping rate.
- `test_multiple_options_require_explicit_selection`: current frontend/server defaults to first/default rate.
- `test_stale_or_superseded_estimate_returns_conflict`: absent pre-payment estimate.
- `test_selection_recalculates_order_total_from_server_option`: absent selection total update.
- `test_idempotency_key_replay_rejects_changed_fingerprint`: absent estimate idempotency.

### `shopsoma-backend/tests/test_checkout_reservation_lifecycle.py`

- `test_selection_creates_all_stock_and_mto_coverage_atomically`: current order decrements stock directly.
- `test_product_variant_and_size_stock_subjects_are_exact`: current reservation creation is not in checkout sequence.
- `test_active_release_consume_expire_are_one_way_and_idempotent`: lifecycle exists in schema but prerequisite behavior is absent.
- `test_cancel_before_provider_start_releases_without_incrementing_stock`: current stock was already decremented.
- `test_started_or_unknown_payment_blocks_release`: prerequisite cancellation integration absent.
- `test_expiry_uses_database_clock_and_preserves_started_recovery`: absent sequence.

### `shopsoma-backend/tests/test_checkout_reservation_concurrency.py`

- `test_concurrent_selection_of_last_product_unit_has_one_winner`: current stock check is unlocked.
- `test_concurrent_product_variant_reservation_cannot_oversell`: absent order-first reservation flow.
- `test_concurrent_size_stock_reservation_uses_product_variation_size_lock_order`: absent flow.
- `test_multi_line_failure_rolls_back_every_reservation`: absent atomic selection/reservation.
- `test_deadlock_retry_exhaustion_leaves_no_partial_coverage`: absent bounded orchestration.

### `shopsoma-backend/tests/test_order_creation_side_effect_gate.py`

- `test_enforced_order_creation_does_not_decrement_any_stock`: current create route decrements.
- `test_enforced_order_creation_does_not_create_vendor_pickup_or_notification`: current create route creates both.
- `test_enforced_order_creation_does_not_send_vendor_email_or_start_mto`: current route sends vendor email.
- `test_gate_off_legacy_order_preserves_explicit_compatibility_behavior`: cohort-aware branch absent.

### `shopsoma-backend/tests/test_checkout_payment_bridge_prerequisites.py`

- `test_initialization_requires_persisted_cohort_selection_and_complete_coverage`: current bridge depends on final sealed quote records and missing-record fallback.
- `test_initialization_uses_locked_order_amount_and_currency_only`: service has server truth but checkout still supplies/uses client review money.
- `test_new_cohort_cannot_fall_back_when_prerequisite_record_is_missing`: current `_ensure_bridge_attempt` can return legacy fallback.
- `test_exact_attempt_membership_excludes_mto_coverage_and_includes_all_stock_reservations`: absent new coverage contract.
- `test_gate_off_does_not_reinterpret_existing_enforced_order`: absent cohort binding.

### `shopsoma-backend/tests/test_verified_payment_inventory.py`

- `test_verified_payment_consumes_and_decrements_each_subject_once`: current enforced prerequisite path absent.
- `test_duplicate_verification_does_not_double_decrement`: absent consumption integration.
- `test_failed_payment_releases_without_vendor_side_effect`: absent release integration.
- `test_amount_currency_reference_mismatch_changes_nothing`: bridge validation exists; atomic reservation/outbox assertion absent.

### `shopsoma-backend/tests/test_checkout_outbox_exactly_once.py`

- `test_payment_stock_and_outbox_commit_atomically`: outbox absent.
- `test_duplicate_payment_evidence_inserts_one_start_order_event`: outbox absent.
- `test_worker_crash_replay_deduplicates_pickup_notification_and_mto_command`: absent durable effects.
- `test_outbox_payload_contains_no_token_provider_payload_or_pii`: outbox absent.

### `shopsoma-backend/tests/test_checkout_late_payment.py`

- `test_late_success_reacquires_available_stock_atomically`: absent behavior.
- `test_late_success_without_stock_creates_paid_stock_exception_and_no_fulfilment`: absent behavior.
- `test_success_after_authorization_deadline_records_money_and_holds_order`: absent policy enforcement.
- `test_unknown_outcome_prevents_expiry_release_until_reconciled`: partial attempt state exists; reservation interaction absent.

### `shopsoma-backend/tests/test_checkout_prerequisite_end_to_end.py`

- `test_authenticated_ngn_order_estimate_selection_reservation_mock_payment`: absent sequence.
- `test_guest_ngn_order_capability_sequence_and_claim`: absent sequence.
- `test_usd_contract_preserves_single_currency_without_implicit_activation`: absent sequence.
- `test_multi_vendor_mto_and_stock_items_start_only_after_verified_payment`: absent sequence.
- `test_final_sealed_quote_is_not_required_for_checkout_payment`: current persistence requires it.

### `shopsoma-frontend/src/pages/checkout/Checkout.test.tsx` (or repository-standard colocated path)

- `requires_customer_click_when_multiple_estimate_options_exist`: current auto-selection.
- `does_not_initialize_payment_before_selection_and_reservation_success`: current immediate create-order -> initialize.
- `uses_payment_initialization_amount_and_currency_for_paystack`: current review total is used.
- `recovers_from_stale_estimate_and_stock_conflict_without_silent_switch`: absent flow.
- `keeps_guest_capability_out_of_url_and_clears_after_claim_or_completion`: absent capability flow.

## 13. Explicit pre-implementation decisions and safe defaults

These do not block this architecture; they block activation if unresolved:

1. **Cohort eligibility:** exact domestic geography, account/cohort allowlist, order cap, and whether USD participates. Safe default: empty allowlist/0%, Nigeria only, NGN only.
2. **TTL values:** checkout estimate, guest read/claim, reservation, payment, and authorization grace. Safe enforcement: bounded settings using database clock; no unbounded token/reservation.
3. **Packed variance:** party bearing estimate-vs-final difference and thresholds. Safe default: fulfilment hold and staff reconciliation; no silent charge/refund.
4. **Guest ownership claim representation:** safe default is immutable original customer plus current-owner projection, pending repository-wide ownership audit.
5. **Late paid/no-stock customer remedy:** refund vs substitution SLA. Safe default: hold, alert staff, no vendor start, no negative stock.
6. **Tax treatment of shipping estimate and FX source/version:** must be finance-approved and snapshotted. Preserve current server tax/FX behavior until explicitly changed; never recompute historical orders.
7. **Gate-off policy for otherwise eligible new customers:** compatibility legacy path versus checkout unavailable. Safe launch default is checkout unavailable for pilot-targeted eligibility if prerequisites cannot complete; do not silently downgrade an order after creation.

## 14. Explicit non-goals

- No DHL booking, shipment creation, labels, pickup scheduling, tracking, live rates, sandbox/production carrier calls, credentials, or provider activation.
- No real Stripe, Paystack, or other payment-provider call.
- No deployment, migration execution, feature activation, PR merge/update, or production data change.
- No final packed-variance automation, refunds, returns, payouts, broad notification platform, generic multi-provider framework, or international customs workflow.
- No schema/code/test/frontend implementation in Milestone 1.

## 15. Milestone 1 acceptance audit

- Domain boundary: Sections 1 and 8.
- Exact persistence/constraints/indexes: Section 2.
- Expand/backfill/validate/contract and rollback: Section 3.
- Guest issuance/hash/binding/TTL/revocation/claim/anti-enumeration: Section 4.
- Reservation states, stock surfaces, locking, TTL, concurrency, cancellation/late payment: Section 5.
- Verified-payment-only side effects/outbox/recovery: Section 6.
- False-default gate and cohort cases: Section 7.
- API/frontend order and failures/explicit option selection: Section 8.
- Multi-item/vendor/MTO/currencies/claim/payment/expiry/cancel: Section 9.
- Milestones 2–5 with paths, acceptance, commands, non-goals, stops: Section 10.
- Security/concurrency/failure matrix: Section 11.
- RED inventory: Section 12.
- Decisions/safe defaults and explicit non-goals: Sections 13–14.
