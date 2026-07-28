# DHL domestic hub-only runbook

## Status and authority

This is the authoritative operational runbook for the Phase 2A/2B Nigerian domestic DHL design. The pure contracts in `app/services/fulfillment/`, the transition policy in `app/services/fulfillment/transitions.py`, and the provider-neutral shipping contracts remain implementation truth. This document does not activate provider calls or production traffic.

The design is fail-closed: DHL is only the outbound last-mile carrier from a ShopSoma hub. Any ambiguity about origin, custody, domestic service, account billing, or evidence stops implementation or activation rather than falling back to vendor-origin DHL.

## Authoritative topology and responsibility

**Vendor -> independent inbound -> ShopSoma hub -> DHL last mile -> Nigerian customer**

The legs and responsibilities are deliberately separate:

1. A vendor prepares paid items and declares readiness.
2. An independent inbound leg/provider moves those items from the vendor to the selected ShopSoma hub. This is not a DHL outbound shipment.
3. The ShopSoma hub receives, reconciles, QCs, packs, measures, and seals the customer parcel, records custody and evidence, and becomes the server-owned outbound origin.
4. DHL last mile begins at the ShopSoma hub only and ends with the Nigerian customer.

DHL never receives a vendor-origin quote, pickup, shipment, or handoff. No vendor address may be substituted for the server-owned hub origin. DHL booking, label, collection, movement, claims, and returns belong only to the sealed hub-origin outbound shipment.

## Data ownership matrix

- **Vendor readiness — vendor / ShopSoma order service:** paid-order notification, preparation acknowledgement, readiness checklist, operations/SLA-policy block reason, and readiness timestamp. The vendor does not own block transitions, carrier movement, or hub QC truth.
- **Independent inbound leg — operations / inbound provider:** provider identity, route, acceptance, vendor handoff, cost, tracking/reference, delay/loss/damage evidence, claims, and receipt destination. It remains distinct from DHL outbound data.
- **Hub receipt and processing — ShopSoma hub roles/services:** item and quantity reconciliation; partial/complete receipt; custody timestamps; QC decisions and evidence; quarantine/remediation; package composition and immutable package version; final metric weight/dimensions; seal, unseal, and reseal audit; and custody through verified DHL handoff.
- **DHL outbound — ShopSoma shipment services / DHL adapter and events:** hub-origin quote, service assumptions, shipment intent, booking, private label metadata, collection acceptance, verified handoff, DHL tracking events, exceptions, returns, and outbound claims. DHL outbound quote ownership starts only from final hub parcel facts.
- **Customer milestones — ShopSoma derived view:** customer-safe progress derived from authoritative payment, vendor, inbound, hub, and outbound states. Customers and operators cannot directly set a milestone.

Every write requires the actor, source event/command, idempotency key, aggregate version, timestamp, and the transition policy's required guards/evidence. Corrections do not overwrite custody history.

## State and actor authority

`transitions.py` is authoritative; this is an operational summary, not a second transition matrix.

- **Quote:** checkout creates an active server quote. The system timer may expire it; customer/operations may cancel it before confirmed payment; the payment worker consumes it on the first valid payment.
- **Payment attempt:** checkout initializes persisted attempts. Only authenticated payment-gateway events or the payment worker confirm/fail them. Finance/operations own approved refund paths; the worker reconciles idempotent void/refund results.
- **Vendor preparation:** the order service notifies the vendor only after verified payment. The vendor may only acknowledge, start preparing, or mark ready. Only ShopSoma operations or the server SLA policy may place a block; only ShopSoma operations may resolve blocked to preparing or ready. Vendor reports may provide evidence for an operations decision but cannot execute either transition.
- **Independent inbound:** operations plans the transfer only after payment and vendor readiness. The inbound provider/operations attest acceptance and vendor handoff; only the inbound provider attests movement. Hub operators record partial or complete receipt and condition evidence; an evidenced hub receipt is authoritative even when the latest provider status is delayed, so it may advance directly from delayed to partial or complete receipt. This movement is never DHL `in transit`.
- **Hub:** hub services derive receipt/QC queues and cohort readiness. Assigned hub operators perform QC, package recording, measurement, and sealing. The audited package version, composition, and active seal are bound to quote, booking, label, handoff, and evidence; `DomesticRateRequest` and every returned `DomesticRate` carry the same immutable `PackageRef`, so a rate cannot be detached from the package ID, version, measurements, composition, or seal it priced. A changed composition or seal fails closed and requires a new audited version and new rate. QC admin owns failed-QC remediation; a hub supervisor alone authorizes pre-handoff unseal. Shipping policy derives DHL readiness only for a valid destination, final package/rate, active seal, and no shipping exception.
- **DHL outbound:** shipment-intent/service actors create one hub-origin intent and booking. The DHL adapter supplies label/cancellation results. Operations schedules accepted hub collection. Only a verified DHL event records acceptance handoff, carrier movement, out-for-delivery, delivery, exception, and return movement. Completing a return is instead a ShopSoma hub command that requires both verified DHL return evidence and the ShopSoma hub return receipt. Carrier-only DHL movement starts after verified DHL handoff; operations cannot manually assert it.

All transitions require optimistic concurrency, evidence, and an idempotency key. External events are unique by `(source, event_id)` as well as idempotency key. A duplicate is resolved before validating the aggregate's already-advanced or terminal state and must match the durably persisted original aggregate identity, machine, prior state, action, external identity, idempotency key, destination, and result version; the aggregate's current version/state must prove it reached that persisted result. Only then may the policy return the matching durably persisted transition result with recursively immutable replay metadata and no repeated side effect. A duplicate without that durable result, or any illegal, stale, unsupported, mismatched, misrouted, or under-evidenced new transition, fails closed.

### Payment and quote timing

- T0 is quote creation. There is a **30-minute quote and payment-initialization window**: payment initialization must begin before quote expiry.
- A persisted eligible payment attempt keeps that attempt eligible through **T0+45**, even though the quote's new-attempt window closes at 30 minutes. Exact payment success inside that grace is verified while order and stock locks are held.
- After the grace, a proved late exact payment requires **atomic stock reacquisition** under order/stock locks before confirmation. If stock cannot be reacquired, request an **idempotent void or refund**, verify the provider result, and escalate exhausted reconciliation to finance.
- There is **no prepayment stock decrement** and **no prepayment vendor work**. Vendor notification and independent inbound planning begin only after exact payment confirmation.

## Feature gates, rollout, and rollback

The three current gates default to `false` and prerequisites only narrow capability:

- `DHL_DOMESTIC_WORKFLOW_ENABLED=false` — enables provider-neutral v2 workflow handling, not provider calls by itself.
- `DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED=false` — effective only when workflow is enabled.
- `DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=false` — effective only with workflow enabled, configured credentials, and `DHL_ENVIRONMENT=sandbox`. Domestic provider calls are effective only in the sandbox environment: Phase 2B sandbox isolation is enforced in code by the capability evaluator, and production fails closed even when every gate is enabled and DHL is fully configured.
- `DHL_DOMESTIC_SANDBOX_COHORT_IDS=` — comma-separated canonical UUIDs for synthetic, explicitly approved sandbox-only fulfillment cohorts. An empty, malformed, duplicate, or non-matching allowlist fails closed before transport.

A **separate domestic checkout gate** is planned; do not overload these backend capability gates to expose checkout. Delivery and activation are deliberately phased:

1. Phase 2A — contracts, persistence, payment, hub operations, mock adapter, and UI; no live provider calls.
2. Phase 2B — restricted sandbox connectivity and evidence; no production traffic or customer payment.
3. Phase 2C — shadow, non-payment quote UAT only.
4. Phase 3 — booking, labels, ShopSoma-hub collection handoff, and recovery.
5. Phase 4 — carrier tracking and operational exceptions.
6. Phase 5 — controlled payment-bearing customer pilot.
7. Phase 6 — broader production activation.

Apply the activation gates in this order, using explicit allowlisted cohorts and stopping unless each preceding acceptance phase passes:

1. Keep every gate false.
2. Enable the internal workflow with a fake provider.
3. Establish restricted sandbox connectivity.
4. Enable provider calls only for the restricted sandbox cohort.
5. Run shadow quotes.
6. Keep domestic checkout false throughout Phases 2A–4.
7. Phase 5 is the first customer canary; do not permit customer or payment-bearing traffic earlier.

Rollback reverses activation while preserving safe recovery:

1. Disable new domestic checkout first.
2. Disable the provider-call gate second.
3. Preserve workflow, reads, and operations for in-flight v2 orders, including receipt, QC, handoff, tracking, exception, refund, return, and reconciliation. In-flight orders remain operable throughout rollback.
4. Never route v2 orders into legacy unsafe creation; version and provider assignments remain immutable.
5. Reconcile provider-side objects, including ambiguous quotes, bookings, labels, collections, cancellations, and returns.
6. Only then pause the workflow when no in-flight order depends on it and an equivalent safe operational path is proven.

If that final condition is not met, freeze new work and continue recovery for existing orders. Rollback never rewrites v2 orders into an unsafe legacy flow.

## Sandbox setup, secrets, and evidence

MyDHL authorization credentials are distinct from portal login. Use environment variables or the deployment secret manager only. **No credentials in Git, docs, chat, logs, screenshots, fixtures, tickets, or evidence bundles.** Rotate immediately on suspected exposure, revoke affected access, sanitize retained artifacts, and record the incident without secret values.

Credential names only:

```dotenv
DHL_ENABLED
DHL_ENVIRONMENT
DHL_API_USERNAME
DHL_API_PASSWORD
DHL_EXPORT_ACCOUNT_NUMBER
DHL_IMPORT_ACCOUNT_NUMBER
DHL_REQUEST_TIMEOUT_SECONDS
DHL_DOMESTIC_WORKFLOW_ENABLED
DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED
DHL_DOMESTIC_PROVIDER_CALLS_ENABLED
DHL_DOMESTIC_SANDBOX_COHORT_IDS
```

Use synthetic Nigerian addresses and non-customer contact details approved for testing. Do not log request/response bodies. Store sanitized acceptance evidence outside Git; redact credentials, authorization headers, account numbers, personal data, labels, barcodes, full addresses, phones, emails, and provider references before sharing.

## Official DHL facts and domestic stop gate

Current official source: [DHL Express MyDHL API](https://developer.dhl.com/api-reference/dhl-express-mydhl-api).

Facts stated on that official page:

- MyDHL API requires a **DHL Express customer account**.
- Sign in to the developer portal and select **Get Access**; a DHL consultant supplies access credentials.
- API authentication uses **Basic Auth**.
- The dedicated test environment endpoint is `https://express.api.dhl.com/mydhlapi/test`.
- The test quota is **500 calls/day**.
- The production endpoint is `https://express.api.dhl.com/mydhlapi`, but **production is prohibited in Phase 2A and Phase 2B**. Do not place production credentials or traffic there.
- The official page describes MyDHL as best for time-definite international shipments.

Therefore Nigerian domestic capability, a usable domestic service, **product N**, hub pickup/collection, the ShopSoma hub's serviceability, and account billing/rating are **UNVERIFIED assumptions**. Product N remains unverified; this runbook does not claim it is supported or confirmed. Each assumption is a hard stop gate requiring **written DHL/account confirmation or sandbox evidence** tied to ShopSoma's account before coding the DHL adapter behavior or activating provider/checkout calls. Conflicting manuals, collections, examples, or verbal statements do not override the official schema plus account-specific evidence.

## Customer milestones

Use exactly these customer-safe names, derived from authoritative states:

1. **Payment confirmed**
2. **Vendor preparing**
3. **Moving to ShopSoma**
4. **Received by ShopSoma**
5. **Quality check**
6. **Packed / ready**
7. **DHL collected**
8. **In transit**
9. **Out for delivery**
10. **Delivered**
11. **Exception**

Honesty rules:

- Independent inbound movement displays **Moving to ShopSoma**, never DHL **In transit**.
- **DHL collected** requires verified acceptance handoff; later DHL movement/delivery requires matching carrier events.
- A **partial receipt** remains **Moving to ShopSoma** and may show reconciled received/total counts; it is not **Received by ShopSoma** until complete.
- Any payment reconciliation, vendor block, inbound loss/damage, failed/remediating QC, or outbound exception/return overrides apparent success with **Exception**.
- Multi-cohort orders display the **slowest non-cancelled cohort**. Exclude a cancelled cohort only after its refund and item/stock disposition are recorded. Never imply all items progressed because a faster cohort did.

## Sandbox acceptance matrix

Use synthetic data and retain sanitized request/result evidence for every row. A phase passes only when expected status, idempotency/replay behavior, privacy, and recovery are demonstrated within quota.

### Phase A — account and rating assumptions

- Portal access/Get Access, consultant credentials, Basic Auth success/failure, quota awareness.
- Hub address serviceability and canonical account/shipper identity.
- Nigerian hub-to-customer valid, invalid, incomplete, and unsupported addresses.
- Final metric package rate success, no-service result, timeout, `401`, `403`, `429`, and `5xx` handling.
- Written/account or sandbox proof for domestic service/product, hub collection, payer/account billing, currency, taxes/surcharges, and cutoff/date semantics.

### Phase B — booking and label

- Exactly one booking for one immutable package version/seal/idempotency key.
- Replay and ambiguous-timeout reconciliation without duplicate shipment.
- Private label receipt, type/format validation, storage, redaction, and access expiry.
- Invalid package/service/account and changed package version fail closed.
- Provider cancellation/void capability is separately evidenced; never infer it from pickup cancellation.

### Phase C — handoff and movement

- Hub collection acceptance and scheduling use the hub address only.
- Matching shipment/package/seal and signed handoff or verified DHL event before collection.
- No carrier movement before handoff; duplicate/out-of-order events are replay-safe.
- In-transit, out-for-delivery, delivery, delayed/exception, and unsupported checkpoint behavior is customer-honest.

### Phase D — recovery, claims, and return

- Booking/label success followed by collection failure and safe cancellation/rebooking policy.
- Timeout/rate-limit/provider outage recovery within quota and bounded retry rules.
- Lost/damaged/exception claim ownership, sanitized evidence, escalation, and customer communication.
- Return start and completion require DHL evidence plus ShopSoma hub return receipt.
- Refund/void reconciliation failure escalates to finance without duplicate compensation.

There is **no real customer or payment canary** before booking, label, handoff, and recovery phases all pass, privacy/legal approval is recorded, monitoring and support ownership exist, and explicit launch approval is granted. Phase 2A/2B remain sandbox-only regardless of matrix completion.

## Stop and rollback triggers

Stop new quote/booking work, disable the narrowest initiating gate, preserve in-flight recovery, and open an incident for any of the following:

- domestic service/product N, hub serviceability/pickup, or account billing remains unverified or contradicts observed results;
- production endpoint/credential use, credential exposure, personal-data leakage, public evidence, or unsafe logging;
- vendor-origin DHL data or an origin not equal to the immutable server-owned hub;
- quote/payment timing or stock reacquisition violates the 30/45-minute policy;
- duplicate charge, shipment, label, collection, refund, or non-idempotent side effect;
- booking without the exact final package version and active seal, or movement without verified handoff;
- false customer milestone, cross-cohort overstatement, untracked partial receipt, or event-order corruption;
- quota exhaustion, sustained timeout/rate-limit/error threshold, monitoring gap, or inability to reconcile provider truth;
- evidence retention/access lacks privacy or legal approval, or operators cannot safely complete in-flight orders.

Rollback never deletes audit/evidence history, reassigns a v2 order to legacy fulfillment, or strands an order. Keep receipt, QC, customer-safe status, claims, compensation, and return operations available while new initiation is off.

## Evidence privacy and retention

Operational evidence belongs in access-controlled **private object storage**, encrypted in transit and at rest. Grant least privilege and expose artifacts only through **short-lived signed URLs** with access audit. There is **no public evidence**, public bucket, public label, or public QC/custody artifact.

Evidence includes receipts, QC decisions/media, package measurements/composition, seal/unseal records, labels, handoff proof, carrier events, claims, and return receipts. Store structured metadata separately from sensitive objects; customer views receive only customer-safe detail.

Retention is subject to legal approval and documented per evidence class before activation. Legal/privacy owners must approve deletion holds, claims/payment retention, data-subject handling, and regional requirements. Corrections are **append-only corrections** linked to the original record with actor, time, reason, and replacement; never silently edit or erase custody history.

## Superseded instructions

**Vendor-site mobile QC and direct DHL pickup are superseded.** Earlier vendor-origin language, examples, mobile inspection plans, fulfillment-origin choices, or direct-carrier handoff guidance are non-authoritative and must not be operated. There is no active instruction for vendor-site ShopSoma QC or vendor-origin DHL quoting, booking, collection, shipment, label, handoff, tracking, or claims.

The only active model is independent inbound to the ShopSoma hub, followed by hub receipt/reconciliation/QC/packing/measurement/sealing and then hub-origin DHL last mile. If another document, ticket, collection, or example conflicts, stop and use this hub-only topology plus implementation contracts.

## Relevant implementation truth

- `shopsoma-backend/app/services/fulfillment/contracts.py`
- `shopsoma-backend/app/services/fulfillment/transitions.py`
- `shopsoma-backend/app/services/shipping/contracts.py`
- `shopsoma-backend/app/services/shipping/capabilities.py`
- `shopsoma-backend/app/core/config.py`
- `shopsoma-backend/app/services/dhl/client.py`
