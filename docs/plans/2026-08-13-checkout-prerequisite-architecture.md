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

- `workflow_cohort varchar(40) NULL` during expand/backfill, then `NOT NULL` after the Section 3 compatibility-writer/backfill cutover.
  - Allowed: `legacy_pre_bridge`, `legacy_ambiguous_quarantined`, `domestic_checkout_v1`.
  - Immutable after insert by trigger.
- `workflow_policy_version varchar(40) NULL` during expand/backfill, later `NOT NULL`; immutable, printable ASCII identifier. Proposed current value for new enforced orders: `domestic_checkout_v1`.
- `checkout_access_mode varchar(20) NULL` during expand/backfill, later `NOT NULL`; allowed `authenticated`, `guest_capability`, `legacy_quarantined`; immutable.
- `checkout_estimate_selection_id uuid NULL`; after both tables exist, composite FK `(checkout_estimate_selection_id, id) -> checkout_shipping_estimate_selections(id, order_id) ON DELETE RESTRICT`, `DEFERRABLE INITIALLY DEFERRED`; set once for `domestic_checkout_v1`, then immutable.
- `checkout_prerequisites_completed_at timestamptz NULL`; set only after selection plus coverage are atomically valid.

Checks after validation:

- positively evidenced legacy orders: `workflow_cohort='legacy_pre_bridge'`, no requirement for new selection/completion fields.
- ambiguous historical orders: `workflow_cohort='legacy_ambiguous_quarantined'`, `workflow_policy_version='legacy_quarantine_v1'`, `checkout_access_mode='legacy_quarantined'`; no customer/capability authorization, new estimate, selection, reservation, payment initialization, fulfilment transition, ownership claim, or automatic side effect is permitted. Read/cancel/refund/reconciliation are staff-only through existing audited legacy operations. The positive classification row is the mandatory quarantine evidence; absence of another record is never evidence.
- enforced orders: `workflow_cohort='domestic_checkout_v1'`, `workflow_policy_version='domestic_checkout_v1'`; payment initialization requires non-null selection/completion but order insertion does not, because insertion precedes selection.
- For non-quarantine cohorts, `checkout_access_mode` must match whether the order was issued a guest capability at creation; an authenticated order cannot later be downgraded to guest mode. Quarantine requires `legacy_quarantined` and forbids capabilities.

Indexes:

- `ix_orders_workflow_cohort_created_at(workflow_cohort, created_at)`.
- partial index `ix_orders_domestic_prerequisite_pending(id) WHERE workflow_cohort='domestic_checkout_v1' AND checkout_prerequisites_completed_at IS NULL`.

### 2.2 `checkout_shipping_estimates`

Columns:

- `id uuid PK`.
- `order_id uuid NOT NULL FK orders(id) ON DELETE RESTRICT`.
- `customer_id uuid NOT NULL FK users(id) ON DELETE RESTRICT` (immutable original order customer, including the guest-created user; current authorization comes only from Section 2.6's owner projection/capability rule).
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
- insert trigger requires `customer_id = orders.customer_id`, currency equality, and an allowed non-quarantine cohort; these fields are immutable.
- only the current unselected leaf may be superseded; selected estimates cannot be superseded.
- checks for positive TTL, hash formats, uppercase currency, nonblank bounded identifiers.
- indexes `(order_id, created_at)`, `(expires_at)`, `(order_snapshot_hash)`.

### 2.3 `checkout_shipping_estimate_options`

Columns:

- `id uuid PK`.
- `estimate_id uuid NOT NULL FK checkout_shipping_estimates(id) ON DELETE RESTRICT`.
- `option_key varchar(100) NOT NULL`.
- `service_code varchar(100) NOT NULL`, `service_label varchar(200) NOT NULL`.
- `amount numeric(10,2) NOT NULL`, `currency char(3) NOT NULL`.
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
- immutable monetary snapshot: `shipping_amount numeric(10,2) NOT NULL`, `currency char(3) NOT NULL` copied from option.
- `source_command varchar(100) NOT NULL`, `idempotency_key varchar(200) NOT NULL`.
- `selected_at timestamptz NOT NULL`, `created_at timestamptz NOT NULL`.

Composite FKs/checks/indexes:

- `(estimate_id, order_id) -> checkout_shipping_estimates(id, order_id) ON DELETE RESTRICT`.
- `(estimate_id, customer_id) -> checkout_shipping_estimates(id, customer_id) ON DELETE RESTRICT`.
- `(option_id, estimate_id) -> checkout_shipping_estimate_options(id, estimate_id) ON DELETE RESTRICT`.
- amount/currency must equal selected option; estimate must be current, unexpired, snapshot hashes must still match locked order truth.
- unique `(estimate_id)`; unique `(order_id)` (one checkout selection per order); unique `(customer_id, source_command, idempotency_key)`.
- unique `(id, order_id)` for the composite order pointer and downstream ownership FKs.
- immutable; no update/delete.

Selection atomically writes `orders.checkout_estimate_selection_id`, recalculates `shipping_cost`, `tax_amount`, and `total_amount` from server snapshots, and creates reservation coverage. A changed cart/address/currency requires a new order or an explicit pre-payment order-revision command that invalidates selection and reservations; this plan chooses the smaller safe V1: create a new order and cancel/release the old one.

### 2.5 `order_guest_capabilities`

Columns:

- `id uuid PK`; this is the bounded public row ID in the opaque credential `<base64url(id)>.<base64url(32-byte secret)>`. The parser accepts exactly this versioned shape and rejects oversized input before database access.
- `order_id uuid NOT NULL`, `original_customer_id uuid NOT NULL`, with composite FK `(order_id, original_customer_id) -> order_current_owners(order_id, original_customer_id) ON DELETE RESTRICT`; for guest orders this is the immutable original guest-created user.
- `scope varchar(40) NOT NULL`; allowed initially `checkout_prerequisites`, `read_order`, `claim_order`. Issue separate capabilities per scope.
- `token_digest bytea NOT NULL`, exactly 32 bytes, computed as HMAC-SHA-256 using the key identified by `pepper_key_version smallint NOT NULL`; plaintext is returned once and never persisted.
- `expires_at timestamptz NOT NULL`, `revoked_at timestamptz NULL`, `replaced_by_id uuid NULL FK same table ON DELETE RESTRICT`.
- `claimed_by_user_id uuid NULL FK users(id) ON DELETE RESTRICT`, `claimed_at timestamptz NULL`.
- `created_at`, `last_used_at`, `row_version integer NOT NULL DEFAULT 1`.

Constraints/indexes:

- unique `(token_digest, pepper_key_version)`; unique `(replaced_by_id)`; index `(order_id, scope, expires_at)`.
- lifecycle check: active has no revocation/replacement/claim; rotation revokes old and references one new row; claim records claimant and database-clock timestamp and revokes the row in the same transaction.
- maximum TTL is configurable but schema-bounded; checkout defaults to the existing payment-window plus auth grace and fails closed when invalid. Read/claim TTL values are activation-only decisions.

### 2.6 `order_current_owners`

This one-row-per-order projection is the single post-claim authorization source; order and aggregate `customer_id` values remain immutable original ownership evidence.

- `order_id uuid PK FK orders(id) ON DELETE RESTRICT`.
- `original_customer_id uuid NOT NULL FK users(id) ON DELETE RESTRICT`; equals immutable `orders.customer_id` and, for guest orders, permanently preserves the original guest-created owner.
- `current_authenticated_user_id uuid NULL FK users(id) ON DELETE RESTRICT`; null until claim.
- `claim_capability_id uuid NULL UNIQUE`, added as `DEFERRABLE INITIALLY DEFERRED` FK to `order_guest_capabilities(id) ON DELETE RESTRICT` after both tables exist.
- `claim_idempotency_key varchar(200) NULL`, `claimed_at timestamptz NULL`, `created_at timestamptz NOT NULL`, `row_version integer NOT NULL DEFAULT 1`.
- unique `(order_id, original_customer_id)` supports capability ownership. A shape check requires all claim fields null or all non-null. A trigger requires original identity to equal the order, forbids its mutation, permits only the one null-to-user claim transition, and rejects delete.

Claim locks through the global coordinator, validates the one-time claim capability, and atomically sets `current_authenticated_user_id`, capability identity/idempotency identity, and database-clock `claimed_at`, while revoking **all** order guest capabilities. Same capability/idempotency key and same user replay returns success; any different user or changed identity is a generic conflict. Every estimate create/read/select, payment initialize/read, order read/cancel, and claim endpoint applies exactly one rule: an authenticated actor must equal `COALESCE(order_current_owners.current_authenticated_user_id, orders.customer_id)`; while no authenticated owner is projected, a valid exact-order/scope capability may authorize only its scope. After claim, capabilities never authorize.

### 2.7 Immutable order-item inventory snapshot

Add to `order_items`:

- `inventory_policy varchar(30) NULL` during expand/backfill, then non-null for `domestic_checkout_v1`; allowed `stock_managed`, `made_to_order`.
- `inventory_subject_kind varchar(20) NULL`, `inventory_subject_id uuid NULL`; stock-managed requires exactly one `product`, `product_variant`, or `size_stock` identity; MTO requires both null.
- `inventory_source_product_id uuid NULL`, `inventory_source_catalogue_version varchar(100) NULL`, `inventory_source_evidence_hash char(64) NULL`, and `inventory_policy_snapshot_at timestamptz NULL` during expand/backfill, required together for every `domestic_checkout_v1` item, capturing the server catalogue row/version and normalized evidence used at order creation. Historical legacy/quarantine nulls are permitted only where positive evidence cannot support a snapshot.
- unique `(id, order_id)` (in addition to existing `(id, order_id, vendor_id)`) and unique `(id, order_id, inventory_policy)` for composite ownership.

A database trigger makes all snapshot fields immutable after insert and verifies subject ancestry against the source product when inserted. Reservation/coverage checks use only this frozen snapshot, never mutable current product flags. Flipping a product between stock-managed and MTO after order creation therefore cannot change existing coverage, availability, payment readiness, or fulfilment behavior.

### 2.8 Reservation coverage changes and relational topology

Keep `stock_reservations` states, coordinator/audit fields, and exact product/variant/size evidence. For new checkout reservations:

- add immutable `workflow_cohort`, `checkout_estimate_selection_id`, and canonical `inventory_subject_kind`/`inventory_subject_id` columns.
- add unique `(id, order_id, order_item_id, checkout_estimate_selection_id)` and FK `(order_item_id, order_id) -> order_items(id, order_id) ON DELETE RESTRICT`.
- FK `(checkout_estimate_selection_id, order_id) -> checkout_shipping_estimate_selections(id, order_id) ON DELETE RESTRICT` and trigger requiring the reservation subject/policy to equal the frozen order-item snapshot.
- retain final `quote_id`, `quote_selection_id`, `quote_option_id`, `intent_id` only as the legacy/final-quote family. The binding check requires exactly the cohort-specific family; no all-null or mixed family is valid.
- existing reservation `unit_price numeric(18,4)` and `line_amount numeric(18,4)` columns remain for legacy compatibility, but `domestic_checkout_v1` rows must be two-decimal quantized, within the order's `numeric(10,2)` maximum, and equal the order-item snapshot exactly; currency also equals the order item.

`order_inventory_coverage` is the completeness proof:

- `order_item_id uuid PK`, `order_id uuid NOT NULL`, `checkout_estimate_selection_id uuid NOT NULL`, `inventory_policy varchar(30) NOT NULL`, `reservation_id uuid NULL`, `created_at timestamptz NOT NULL`.
- FK `(order_item_id, order_id, inventory_policy) -> order_items(id, order_id, inventory_policy) ON DELETE RESTRICT`.
- FK `(checkout_estimate_selection_id, order_id) -> checkout_shipping_estimate_selections(id, order_id) ON DELETE RESTRICT`.
- stock-managed rows require `reservation_id` and composite FK `(reservation_id, order_id, order_item_id, checkout_estimate_selection_id) -> stock_reservations(id, order_id, order_item_id, checkout_estimate_selection_id) ON DELETE RESTRICT`; MTO rows require null reservation and are bound to the immutable selected prerequisite aggregate/version through selection/order plus the item's frozen `inventory_policy='made_to_order'`.
- unique `(order_id, order_item_id)` and index `(order_id, inventory_policy)`.

A deferred constraint trigger on order prerequisite completion proves exactly one coverage row for every order item, no extras, and exact selection/order ownership. Direct SQL cannot cross-link customers because estimates and selections retain immutable original customer equal to the order, enforced by ownership triggers; authorization uses the current-owner projection, not mutable aggregate FKs.

The intentional FK cycle is inserted in this order within one transaction: order and items -> owner projection -> estimate/options -> selection -> reservations -> coverage -> set order selection/completion. Only the order-pointer FK and capability/owner claim FK are deferred; all ownership FKs are immediate. Deletes are `RESTRICT`; pre-payment cancellation terminalizes/releases rows rather than deleting them. Migration creation order omits cyclic FKs until target tables exist, then adds them `NOT VALID`, validates them, and installs immutability triggers last.

### 2.9 Payment attempt compatibility and money contract

Canonical order transaction storage remains `numeric(10,2)` for orders, order items, estimates, and selections; this milestone does not expand it. Existing bridge reservation/attempt columns remain `numeric(18,4)` for legacy compatibility and are not narrowed, but new `domestic_checkout_v1` values must equal their two-decimal order snapshots (`value = round(value, 2)`) and be `<= 99,999,999.99`. Inputs are parsed as decimal, converted/discounted/taxed only at the existing server-defined stages, and each persisted component is quantized once to `0.01` using `ROUND_HALF_UP` before totals are summed. No binary float participates. DB checks reject non-finite, negative where forbidden, excess scale for enforced rows, or order-total overflow; arithmetic uses widened expressions and rejects overflow before assignment. Provider minor units derive from the final persisted attempt amount. NGN and USD retain their existing one-currency-per-order semantics; no implicit FX or mixed-currency arithmetic is introduced.

For `payment_attempts`, add immutable `workflow_cohort` and `checkout_estimate_selection_id`; add unique `(id, order_id, checkout_estimate_selection_id)`, FK `(checkout_estimate_selection_id, order_id) -> checkout_shipping_estimate_selections(id, order_id) ON DELETE RESTRICT`, and a trigger requiring attempt `customer_id = orders.customer_id`, cohort equality, and currency equality. Make final quote fields nullable only after this matrix check exists:

| Attempt cohort/form | Checkout selection | Final quote fields | Permitted |
|---|---:|---:|---|
| `domestic_checkout_v1` | non-null and composite-owned by attempt order | all null | yes |
| `legacy_pre_bridge` bridge attempt | null | all four non-null and mutually owned | yes |
| `legacy_pre_bridge` no attempt | no row | n/a | yes; absence is not a binding form |
| `legacy_ambiguous_quarantined` | n/a | n/a | no new attempt permitted |
| any cohort, all-null attempt binding | null | all null | no |
| any cohort, mixed binding | any | partial/mixed | no |

No separate all-null attempt form is required. Existing bridge attempts are positively backfilled `legacy_pre_bridge`; orders with no attempt remain orders with no attempt. Attempt amount/currency must equal the locked quantized order total/currency. `payment_attempt_reservations` remains exact immutable membership and gains denormalized immutable `order_id`/`checkout_estimate_selection_id` plus composite FKs to `(attempt_id, order_id, checkout_estimate_selection_id)` and `(reservation_id, order_id, order_item_id, checkout_estimate_selection_id)`; every stock coverage reservation is included once, no extra reservation is included, and MTO coverage is excluded.

No existing final quote table is renamed or repurposed.

## 3. Migration and deployment sequence

### 3.1 Expand and compatibility-writer start (gates off)

1. Add nullable order cohort/policy/access/selection/completion columns and additive order-item snapshot columns; create classification/quarantine, owner, estimate, option, selection, capability, and coverage tables.
2. Add nullable checkout/cohort/subject columns to reservations/attempts and install the cohort binding checks before making legacy final-quote fields nullable. Add cyclic composite FKs only after both targets exist.
3. Add `NOT VALID` FKs/checks where validation scans could be material; create indexes concurrently in a separate non-transactional revision when required.
4. Deploy the **compatibility writer** at recorded release ID and database-clock `compatibility_writer_started_at`. From that instant every insert, including gate-off/ineligible orders, writes a non-null immutable cohort/policy/access mode, owner projection, and applicable item inventory snapshots. Gates remain false, so no `domestic_checkout_v1` is emitted; ordinary new rows are positively `legacy_pre_bridge`.
5. Record the writer release, timestamp, migration revision, and deployment identity in an append-only `order_workflow_migration_runs` row. A database trigger rejects any post-start order insert with null classification, closing the concurrent-insert gap before backfill starts.

Before the compatibility writer starts, code can roll back and additive objects remain inert. Once classified rows exist, rollback is code-only: the old version may read existing columns but must not overwrite them; schema downgrade refuses while migration/classification/audit rows exist.

### 3.2 High-watermark backfill and quarantine closure

At backfill start, capture the maximum existing `(created_at, id)` tuple using database-observed values as the immutable high-watermark in the migration-run row. Process only rows whose tuple is `<=` that watermark, ordered by `(created_at, id)`, in bounded `FOR UPDATE SKIP LOCKED` batches. Concurrent later inserts are already classified by the compatibility writer and are excluded from backfill.

`order_workflow_classifications(order_id PK, cohort, policy_version, access_mode, evidence_kind, evidence_reference, migration_run_id, classified_at, classified_by, notes_hash)` is append-only and has a composite FK/check requiring its values to equal the immutable order columns. Classification is total and positive:

- exact release/deployment, existing bridge provenance, and ownership evidence may classify `legacy_pre_bridge`;
- every historical row not deterministically resolvable is positively classified `legacy_ambiguous_quarantined` with `evidence_kind='migration_ambiguity_quarantine'`, migration run/reference, and notes hash; it is not guessed or left null;
- missing quote/reservation/attempt/capability/shipment records are never cohort evidence;
- no historical row is classified `domestic_checkout_v1`.

The classifier uses `INSERT ... ON CONFLICT (order_id) DO NOTHING`, then compares the existing immutable result with the deterministic candidate; exact replay succeeds and any mismatch aborts. Reruns resume from the last committed batch and reconcile counts rather than rewriting evidence. Classification rows and order cohort/policy/access fields reject update/delete. Backfill item inventory snapshots only when existing immutable order/catalog evidence proves the subject/policy; otherwise the entire order is quarantined rather than inventing item truth.

### 3.3 Cutover, validation, and exact fixtures

1. Reconcile exactly: `orders = classifications`, zero null cohort/policy/access rows, every pre-watermark row classified, every post-writer row classified at insert, and every ambiguous row in the positive quarantine cohort.
2. Validate all `NOT VALID` ownership/money/binding constraints; prove no enforced attempt lacks its selected estimate or exact coverage.
3. Set order cohort/policy/access columns `NOT NULL`; set item snapshot fields non-null only for enforced cohorts. Keep legacy/quarantine-compatible nullability where historical evidence cannot support values.
4. Record `classification_cutover_at`, validated constraint names, row counts, and high-watermark completion in the append-only migration run. Only then remove nullable-reader compatibility; missing-record fallback is forbidden.

Acceptance fixtures are exact: (a) evidenced pre-writer order -> `legacy_pre_bridge`; (b) ambiguous pre-writer order -> `legacy_ambiguous_quarantined` plus quarantine evidence; (c) insert immediately before watermark is backfilled once; (d) concurrent insert after writer start is writer-classified and skipped by backfill; (e) crash after one batch then rerun yields identical rows/hashes/counts; (f) changed rerun evidence aborts; (g) upgrade/downgrade/upgrade before writer start succeeds; (h) downgrade after classification data exists refuses without deleting anything; (i) code rollback/roll-forward preserves classifications and the upgraded writer resumes without duplicate evidence; (j) final `NOT NULL` validation succeeds with no guessed row.

### 3.4 Later contract and reversibility

Only after all deployed code uses the new model and validation is recorded may a separate approved contract migration archive old binding columns. Destructive downgrade/drop is never the rollback mechanism.

Safe rollback after compatibility-writer start is operational: gates remain/turn off for new enforced assignment while compatibility writing continues; existing `domestic_checkout_v1`, legacy, and quarantine cohorts retain immutable policy. Never reinterpret in-flight orders, delete evidence/capabilities/reservations, or restore pre-payment side effects.

## 4. Guest security contract

### Issuance and key rotation

- On guest order creation, generate a 32-byte CSPRNG secret and return the bounded row-ID-plus-secret credential once over TLS.
- Store HMAC-SHA-256(secret) using the deployment-managed checkout capability pepper selected by `pepper_key_version`; this key set is distinct from JWT/payment secrets. Configuration contains exactly one active version and at most one previous version during a bounded rotation window.
- New/rotated capabilities always use the active version. Verification uses only the stored row's declared version, never “try every key.” Previous-version rows remain valid only until their normal expiry or the rotation deadline. Removing/retiring a key makes rows with that version uniformly unavailable; retirement requires revoking/counting all unexpired rows first and is auditable.
- Never place raw credential, secret, digest, token fragment, email, or provider payload in URL/query, analytics, exception text, logs, traces, metrics labels, or outbox. Frontend keeps the credential only in memory or session storage and sends it in the scoped header.

### Verification and anti-enumeration

The only algorithm is: parse and length-bound the public row UUID plus 32-byte secret -> load capability by primary-key row ID -> obtain the one configured key matching stored `pepper_key_version` -> compute HMAC -> constant-time compare -> acquire the Section 5 coordinator/row locks -> validate exact scope, order, immutable original owner, current-owner projection, cohort, expiry, revocation, replacement, and lifecycle. There is no digest lookup and no alternate algorithm.

Malformed ID/secret, missing row, unknown/retired key version, wrong secret/scope/order/owner, claimed/revoked/replaced/expired credential all return the same generic `404 checkout not available`, response shape, cache policy, and bounded timing posture. The implementation performs a dummy HMAC and equivalent authorization work for pre-row failures and adds small fixed/jittered minimum latency outside the transaction; tests compare latency distributions within a documented tolerance, not exact nanoseconds. Rate limiting keys on a keyed HMAC of `(normalized network prefix, parsed row ID-or-fixed sentinel, route family)` with a dedicated rate-limit key; it never includes raw token, digest, email, order number, or other PII.

UUID/order number/email alone never authorizes any operation. Adversarial proofs cover malformed/oversized tokens, valid ID/wrong secret, swapped order/scope/owner, retired key, active/previous rotation, replay after claim/revocation, timing equivalence, rate-limit-key redaction, and application/database/log capture containing no raw credential or digest.

### Rotation/revocation

- Credential rotation creates a new active-key-version row and atomically revokes/links the old row; old credentials stop immediately.
- Revoke checkout scope on cancellation, successful claim, compromise, or terminal payment beyond recovery policy.
- Expiry is database-clock authoritative. Expired checkout capability cannot start an attempt; authenticated provider evidence may recover an already-started attempt under payment authorization rules.

### Claim

Claim is implemented in this milestone through `order_current_owners`; it is not an alternative. It requires an authenticated verified-email user plus a valid one-time `claim_order` capability—email equality alone is insufficient. The global lock order is used, Section 2.6 fields are written with database clock, all capabilities revoke atomically, immutable aggregate ownership remains unchanged, same-user/same-idempotency replay succeeds, and a different user gets a generic conflict.

## 5. Reservation state machine and locking

The only reservation lifecycle states are `active/released/consumed/expired`; transitions are one-way from `active`, and terminal-state replays are idempotent.

### States, effective claims, and transitions

A reservation protects availability while `state='active'` and either (a) `expires_at > clock_timestamp()`, or (b) it belongs through `payment_attempt_reservations` to an attempt in `call_started`/`abandoned_unknown`, or to verified evidence whose stock finalization/recovery remains unresolved and whose `authorization_deadline_at >= clock_timestamp()`. This **effective inventory claim** is used identically by selection, catalogue writes, reconciliation, and expiry; wall-clock expiry alone never frees stock attached to started/unknown/unresolved money.

| From | Command/event | To | Guard and effect |
|---|---|---|---|
| none | `select_checkout_estimate` | active | order/selection valid; all subjects locked; available = physical stock minus all effective claims; create exact coverage atomically |
| active | exact verified payment | consumed | exact membership; decrement physical stock once; persist payment/order/outbox atomically |
| active | cancel or terminal authenticated failure | released | no verified, started, unknown, or unresolved attempt; end claim only, never increment physical stock |
| active | expiry worker | expired | TTL elapsed and effective-claim predicate is false under locks; no stock mutation |
| active | late verified success | consumed or exception | serialize; consume if claim/reacquisition succeeds, otherwise preserve money truth and hold via exception |
| consumed | replay/cancel/failure | consumed | immutable; refund/restock is separate compensation |
| released/expired | duplicate terminal command | same | idempotent replay |

The expiry worker selects candidates but re-evaluates the effective predicate after the full coordinator lock. Protected expired rows remain `active` with an audit observation and next reconciliation time; they are terminalized only after provider reconciliation proves failure/no acceptance or the authorization/recovery policy closes. Unknown provider acceptance is never converted to failure by timeout alone. Reconciliation terminalizes the attempt first from authenticated evidence, then consumes or releases/expires reservations in the same ordered transaction.

### Coverage

- Product without detailed variant: reserve frozen `(product, product_id)` against `products.total_stock`.
- `ProductVariant`: reserve frozen `(product_variant, variant_id)` and include parent product coordinator key.
- `SizeStock`: reserve frozen `(size_stock, size_stock_id)` and include variation and parent product keys.
- Made-to-order: exact MTO coverage from the immutable order-item snapshot; no fake stock.
- Duplicate lines aggregate by frozen inventory subject for availability while retaining per-item reservation/coverage identity.

### One global lock order

Every selection, payment initialization, verification, terminal failure, cancellation, expiry, catalogue update, late recovery, claim, and reconciliation first builds the **complete** key set and calls the existing `coordinate_stock_payment_write` once. The database function's canonical ordering—`subject_kind COLLATE "C", subject_id`—is the sole global order; callers must not acquire overlapping business row locks before it. The complete namespace is `order`, `product`, `variation`, `product_variant`, `size_stock`, `reservation`, `payment_attempt`; capability/owner rows are locked only after the coordinator because they have no coordinator kind, in `(table name, UUID)` order. After coordinator acquisition, rows are locked in that same key order, then selection/coverage/membership/evidence/outbox rows by UUID. This replaces all prose orderings such as “order then attempt” or “catalogue rows first.”

Availability checks, effective-claim checks, inserts, terminalization, and stock mutation occur in one transaction. Unique idempotency identities replay the same result; changed fingerprints conflict. Serialization/deadlock retries are bounded at service boundary and leave no partial rows.

### Cancellation, late payment, and required races

Cancellation and expiry use the same complete coordinator set and effective-claim predicate. `call_started`/`abandoned_unknown` blocks release until authenticated reconciliation or policy closure. Late authenticated success always records money truth; inside recovery it consumes an effective claim or atomically reacquires without negative stock, otherwise emits `paid_stock_exception`; after deadline it emits `late_payment_exception`. Neither exception starts vendors.

Two-connection proofs are mandatory: last-unit selection versus selection; selection versus catalogue stock decrease/policy flip; expiry versus verification; cancellation versus provider-start; terminal failure versus late webhook; reconciliation versus catalogue delete/update; and two workers handling the same expired protected reservation. Each proof must force the lock wait, assert one legal winner/serialized outcome, no deadlock, no negative stock, no prematurely freed effective claim, and idempotent replay.

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

The guarantees are deliberately narrower than global “exactly once”:

1. **Atomic database event:** authenticated payment truth, exact stock consumption (or exception truth), order state, and one uniquely keyed outbox insertion commit in one PostgreSQL transaction or none commits.
2. **Database-derived commands are effectively once:** outbox replay may execute repeatedly, but each pickup/notification/MTO command has unique `(source_event_id, effect_kind, subject_id)` identity and converges to one durable database command.
3. **External delivery is not exactly once:** email/payment-provider acceptance is at-least-once when the adapter proves idempotency with a stable provider key; otherwise a timeout after send is `unknown_outcome`, is reconciled by provider/message identity, and is never blindly resent. Without provider idempotency or a queryable acceptance receipt, staff resolves the unknown outcome.

A worker claims with `FOR UPDATE SKIP LOCKED`, persists/replays database commands, and marks processed only after command persistence. Outbox failure leaves `post_payment_processing_pending`; replay never replays payment or stock consumption. Email is sent only from a durable notification delivery row carrying source identity, adapter idempotency capability, attempt number, provider/message identity when known, and `pending/sent/failed/unknown_outcome` state.

Crash-window tests cover: before atomic transaction commit (nothing); after payment evidence write but forced rollback (nothing); after atomic commit before worker claim (event remains); after worker claim before command commit (lease/replay); after command commit before outbox processed mark (unique command deduplicates); before external send (safe retry); provider accepted then client timed out (unknown, reconciliation/no blind retry); provider rejected with authenticated terminal response (bounded retry policy); and provider-idempotent retry returning the same message identity.

Final quote/booking is not emitted by this outbox event; later hub/package readiness drives it independently.

## 7. False-by-default gate and cohort matrix

Introduce `DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED: bool = False` plus a strict server-owned cohort allowlist/percentage policy. Existing DHL gates remain separate; this prerequisite gate must not imply provider calls.

| Case | New order cohort | Behavior |
|---|---|---|
| gate off | `legacy_pre_bridge` | established checkout remains available; no new prerequisites inferred; this is compatibility, not permission to reinterpret an enforced order |
| gate on + eligible authenticated domestic order | `domestic_checkout_v1` | estimate selection + complete coverage required before bridge initialization |
| gate on + eligible guest domestic order | `domestic_checkout_v1` | same, authorized by scoped guest capability |
| gate on + ineligible geography/currency/cohort | checkout unavailable; no order created | no silent compatibility downgrade after activation |
| historical evidenced order | `legacy_pre_bridge` | restrictive compatibility follows persisted cohort, never missing-record inference |
| historical ambiguous order | `legacy_ambiguous_quarantined` | staff-only audited read/cancel/refund/reconciliation; no new payment or fulfilment |
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
- **Payment failure:** authenticated terminal failure idempotently converges reservations to released if no unknown outcome remains; no vendor/fulfilment effects.
- **Payment late success:** record money truth; consume/reacquire only without oversell; otherwise exception outbox and fulfilment hold.
- **Estimate expiry:** cannot select; create a new superseding estimate. Existing selection remains valid only through reservation/payment windows encoded at selection; expiry semantics after selection must be explicit in service and tests.
- **Reservation expiry:** no new payment initialization; started payment remains in reconciliation/grace state; expiry worker cannot race terminal verification.
- **Cancellation:** before provider start releases; unknown/started blocks until reconciliation; after verified payment uses refund/compensation workflow and never reverses consumed audit state.
- **Final packed variance:** staff hold by safe default; no silent charge, refund, or shipment booking.

## 10. Milestones 2–5

Each milestone is independently inert and reversible by false-default gates/adapters: Milestone 2 adds no runtime route behavior; Milestone 3 routes execute only for explicitly assigned enforced cohorts while payment/provider transport remains disabled; Milestone 4 uses mocked/disabled external adapters and gate-off preserves in-flight recovery; Milestone 5 changes UI sequencing only against those gated APIs. Rollback means disabling new assignment/UI exposure while preserving immutable rows and recovery—not dropping schema, reclassifying orders, or restoring unsafe pre-payment side effects.

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

**Acceptance:** pre-writer upgrade/downgrade/upgrade succeeds and populated downgrade refuses safely; compatibility writer/high-watermark/concurrent inserts/idempotent reruns close every row into positive immutable classification, including `legacy_ambiguous_quarantined`; exact DDL/model parity; owner projection, composite topology, item inventory snapshot, money/binding matrix, capability key version, and direct-SQL constraints install inertly; gates remain false/empty; no runtime checkout behavior or missing-record inference changes.

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

**Acceptance:** enforced create-order has no decrement/pickup/notification; explicit selection creates all-or-none composite-owned coverage from frozen item policy; catalogue flips do not reinterpret orders; guest endpoints use the sole row-ID/HMAC/key-version protocol and canonical owner projection; direct SQL cross-links fail; the global coordinator order/effective-claim predicate prevents oversell or premature release in two-connection races; cancellation/expiry are idempotent; gates remain inert and quarantine is restrictive.

**Verification:**

- `cd shopsoma-backend && pytest -q tests/test_checkout_estimate_api.py tests/test_guest_checkout_capability.py tests/test_checkout_reservation_lifecycle.py tests/test_checkout_reservation_concurrency.py tests/test_order_creation_side_effect_gate.py`
- `cd shopsoma-backend && ruff check app tests && black --check app tests`

**Non-goals:** provider initialization/calls, final DHL quote, vendor work, frontend.

**Stop:** any enforced order can reach payment-ready without exact coverage; UUID/email authorizes guest access; stock can go negative; pre-payment side effect remains.

### Milestone 4: Payment bridge and atomic/effectively-once post-payment boundary

**Goal:** Bind initialization and verified-payment finalization to persisted cohort/selection/coverage and release post-payment work through a narrow durable outbox.

**Likely paths:**

- Modify `shopsoma-backend/app/services/payments/fulfilment_bridge.py`
- Modify `shopsoma-backend/app/api/v1/payments.py`
- Modify `shopsoma-backend/app/models/stock_payment_persistence.py`
- Create `shopsoma-backend/app/models/checkout_outbox.py`
- Create `shopsoma-backend/app/services/checkout/outbox.py`
- Modify vendor pickup/notification entry points currently invoked by `app/api/v1/orders.py`
- Add Alembic revision and future tests in Section 12

**Acceptance:** initialization uses only locked, two-decimal, `ROUND_HALF_UP` server total/currency and the cohort binding matrix; exact reservation membership required; verified payment truth/stock/outbox are one atomic database event; database commands are effectively once by unique source identity; external sends are at-least-once or reconciled unknown outcomes and never blindly retried; crash-window and boundary/overflow proofs pass; existing enforced cohorts remain recoverable when gate turns off.

**Verification:**

- `cd shopsoma-backend && pytest -q tests/test_checkout_payment_bridge_prerequisites.py tests/test_verified_payment_inventory.py tests/test_checkout_outbox_delivery_guarantees.py tests/test_checkout_late_payment.py tests/test_payment_fulfilment_bridge_contract.py`
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

**Acceptance:** no auto-selection; multiple options require a customer action; every endpoint uses the canonical current-owner/capability rule; guest credentials never enter URL/log output; stale/expiry/stock failures are truthful; provider widget receives quantized initialization amount/currency; authenticated, guest, claim/replay, NGN, and schema-compatible USD mocked journeys pass; all external adapters remain disabled.

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
| two carts reserve last unit | complete coordinator set plus effective-claim subtraction | one succeeds; one 409; no negative stock |
| partial multi-line reservation | one DB transaction + completeness check | full rollback |
| deadlock/serialization failure | canonical lock order, bounded service retry | clean retry then 409/503; no partial state |
| expiry races payment verification | sole coordinator `subject_kind COLLATE "C", subject_id` order; DB clock | one terminal path; success reconciled/exceptioned without oversell |
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
- `test_direct_sql_order_pointer_cannot_reference_another_order_selection`: absent composite order pointer.
- `test_direct_sql_coverage_cannot_cross_link_order_item_reservation_or_selection`: absent full composite ownership topology.
- `test_order_item_inventory_policy_snapshot_is_immutable`: absent frozen policy/source evidence.
- `test_catalogue_policy_flip_does_not_change_existing_order_coverage`: current mutable catalogue can be consulted.
- `test_reservation_requires_exactly_one_binding_family`: current reservation only supports final quote binding.
- `test_made_to_order_line_requires_explicit_non_stock_coverage`: absent coverage table.
- `test_money_scale_rounding_maximum_and_overflow_constraints`: absent canonical two-decimal boundary contract.
- `test_payment_attempt_binding_matrix_rejects_all_null_mixed_and_quarantine_forms`: absent cohort matrix.

### `shopsoma-backend/tests/test_checkout_prerequisite_migration.py`

- `test_expand_upgrade_downgrade_upgrade_preserves_legacy_rows`: absent revisions.
- `test_populated_classification_refuses_destructive_downgrade_and_roll_forward_is_stable`: absent rollback guard.
- `test_compatibility_writer_classifies_concurrent_insert_outside_backfill_watermark`: absent writer/cutover protocol.
- `test_backfill_crash_rerun_is_idempotent_and_changed_candidate_aborts`: absent immutable rerun contract.
- `test_constraints_install_not_valid_then_validate`: absent staged constraints.
- `test_populated_new_audit_tables_block_destructive_rollback`: absent safe rollback guard/runbook assertion.

### `shopsoma-backend/tests/test_order_workflow_classification.py`

- `test_missing_bridge_records_never_classifies_legacy_order`: current bridge falls back from missing attempt/selection.
- `test_positive_release_evidence_classifies_legacy_order`: absent classifier.
- `test_ambiguous_history_is_quarantined_not_guessed`: absent quarantine.
- `test_quarantined_order_has_positive_evidence_and_restrictive_behavior`: absent immutable quarantine cohort.
- `test_every_order_is_classified_at_final_not_null_cutover`: current historical representation is nullable.
- `test_gate_change_does_not_change_existing_order_cohort`: absent immutable cohort.

### `shopsoma-backend/tests/test_guest_checkout_capability.py`

- `test_guest_token_plaintext_is_returned_once_and_never_persisted`: absent capability.
- `test_uuid_or_email_without_capability_cannot_access_order`: current guest ownership is a passwordless user identity without this capability boundary.
- `test_capability_is_order_scope_and_ttl_bound`: absent binding.
- `test_wrong_expired_revoked_and_unknown_tokens_are_indistinguishable`: absent anti-enumeration.
- `test_row_id_then_hmac_protocol_rejects_malformed_oversized_and_swapped_tokens`: absent bounded sole algorithm.
- `test_active_previous_and_retired_pepper_versions_have_defined_behavior`: absent key-version rotation.
- `test_capability_failures_have_uniform_timing_and_rate_limit_keys_are_redacted`: absent timing/rate-limit posture.
- `test_no_raw_token_or_digest_reaches_logs_traces_metrics_or_outbox`: absent end-to-end redaction proof.
- `test_rotation_revokes_old_token_atomically`: absent rotation.
- `test_claim_requires_authenticated_user_and_one_time_claim_scope`: absent claim capability.
- `test_claim_revokes_all_guest_capabilities_without_restarting_checkout`: absent claim lifecycle.
- `test_claim_owner_projection_same_user_replays_and_different_user_conflicts`: absent canonical projection.
- `test_all_order_endpoints_use_current_owner_projection_after_claim`: existing routes use order customer identity.

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
- `test_effective_claim_protects_expired_started_unknown_and_unresolved_attempts`: absent effective predicate.
- `test_expiry_worker_terminalizes_only_after_reconciliation_or_policy_closure`: absent worker rule.

### `shopsoma-backend/tests/test_checkout_reservation_concurrency.py`

- `test_concurrent_selection_of_last_product_unit_has_one_winner`: current stock check is unlocked.
- `test_concurrent_product_variant_reservation_cannot_oversell`: absent order-first reservation flow.
- `test_concurrent_size_stock_reservation_uses_product_variation_size_lock_order`: absent flow.
- `test_multi_line_failure_rolls_back_every_reservation`: absent atomic selection/reservation.
- `test_deadlock_retry_exhaustion_leaves_no_partial_coverage`: absent bounded orchestration.
- `test_expiry_vs_verification_serializes_without_releasing_effective_claim`: absent two-connection proof.
- `test_catalogue_update_vs_selection_uses_same_global_coordinator_order`: absent unified order.
- `test_failure_vs_late_webhook_and_reconciliation_vs_catalogue_update_are_safe`: absent race proofs.

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
- `test_attempt_matrix_distinguishes_no_attempt_from_existing_legacy_bridge_attempt`: absent explicit matrix.
- `test_amount_is_quantized_round_half_up_and_provider_minor_units_match`: absent canonical rounding contract.

### `shopsoma-backend/tests/test_verified_payment_inventory.py`

- `test_verified_payment_consumes_and_decrements_each_subject_once`: current enforced prerequisite path absent.
- `test_duplicate_verification_does_not_double_decrement`: absent consumption integration.
- `test_failed_payment_releases_without_vendor_side_effect`: absent release integration.
- `test_amount_currency_reference_mismatch_changes_nothing`: bridge validation exists; atomic reservation/outbox assertion absent.

### `shopsoma-backend/tests/test_checkout_outbox_delivery_guarantees.py`

- `test_payment_stock_and_outbox_commit_atomically`: outbox absent.
- `test_duplicate_payment_evidence_inserts_one_start_order_event`: outbox absent.
- `test_worker_crash_replay_deduplicates_pickup_notification_and_mto_command`: absent durable effects.
- `test_outbox_payload_contains_no_token_provider_payload_or_pii`: outbox absent.
- `test_database_commands_are_effectively_once_by_unique_source_identity`: absent durable command identity.
- `test_external_unknown_acceptance_is_reconciled_not_blindly_retried`: absent delivery state contract.
- `test_each_payment_outbox_and_external_send_crash_window_converges_safely`: absent crash-window coverage.

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

## 13. Activation-only decisions and safe disabled defaults

These decisions do not alter Milestones 2–5 schema/security contracts and do not block inert implementation; they must be approved before any production cohort activation:

1. **Cohort eligibility:** exact domestic geography, account allowlist, order cap, and USD participation. Disabled default: empty allowlist, 0%, Nigeria/NGN eligibility only when later approved.
2. **Durations:** concrete estimate, capability read/claim, reservation, payment, authorization/recovery, and pepper-rotation windows within the locked schema bounds. Invalid/unset values fail closed.
3. **Packed variance:** commercial bearer and hold thresholds. Default: fulfilment hold/staff reconciliation; no silent charge/refund.
4. **Late paid/no-stock remedy:** refund versus substitution SLA. Default: hold/alert, no vendor start, no negative stock.
5. **Tax and FX activation policy:** finance-approved shipping-tax treatment and FX source/version. Existing server behavior is snapshotted; historical orders are never recomputed.
6. **External adapter guarantees:** provider-specific idempotency and acceptance-query evidence. Until proven per adapter, unknown outcomes require reconciliation/staff action and are not resent.

Schema-blocking choices are not deferred: ambiguous history uses `legacy_ambiguous_quarantined`; current ownership uses `order_current_owners`; inventory policy is frozen per item; money remains two-decimal `numeric(10,2)`/`ROUND_HALF_UP`; ineligible orders after activation are unavailable rather than silently downgraded.

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
