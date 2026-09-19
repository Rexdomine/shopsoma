# DHL Checkout Bridge Implementation Plan

> **For Hermes:** Use the plan task-by-task; keep the existing checkout UI structure and styles unchanged.

**Goal:** Add a disabled-by-default, staging/sandbox-only DHL checkout bridge that lets checkout select a persisted DHL quote option and keeps the final amount server-owned.

**Architecture:** Add a server-owned checkout quote session/intent boundary rather than creating an unpaid order before shipping selection. The endpoint will accept the existing checkout subject (items, address, currency), create/reuse a gated quote session, return redacted DHL options, and accept an idempotent selection. Order review/create will consume the selected server-side quote identity, never a client amount. Existing legacy shipping remains the fallback while the gate is off.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, PostgreSQL, React/TypeScript/Vite, Vitest/Pytest.

---

## Acceptance criteria

- `DHL_DOMESTIC_CHECKOUT_ENABLED` defaults false and is effective only when domestic workflow is enabled, environment is sandbox, provider calls are not production-enabled, and the configured test cohort/gate permits it.
- Gate-off checkout is byte-for-byte behavior-compatible with the existing legacy shipping flow.
- Gate-on staging checkout requests a DHL quote after address selection, shows the existing shipping-step UI structure with DHL options, and selects by quote/option identity.
- Review and order creation resolve shipping cost from persisted quote evidence; client-supplied DHL amounts are ignored/rejected.
- Quote creation/selection retries converge by idempotency key; expired/superseded quotes cannot be selected.
- No DHL production URL or production activation is introduced.
- Existing checkout, payment, and legacy shipping tests remain green.

## Preflight boundary map

- Browser → checkout API: cart item IDs, address identity/data, currency, quote/option identity; no price authority.
- Checkout API → DB: quote session, immutable quote/option/selection evidence, order totals.
- Checkout API → DHL evidence: only through existing provider-neutral persisted rating/evidence path; provider calls remain sandbox-gated.
- Payment API → order: payment amount comes from server-created order truth.
- Feature gate → all paths: checkout, review, order creation, and payment truth use the same effective gate.

## Tasks

### Task 1: Freeze the gate and public checkout contract

Files:
- Modify `shopsoma-backend/app/core/config.py`
- Modify `shopsoma-backend/app/services/shipping/capabilities.py`
- Add focused capability tests under `shopsoma-backend/tests/`

Add a `DHL_DOMESTIC_CHECKOUT_ENABLED: bool = False` setting and expose an effective boolean only when workflow is enabled, the environment is `sandbox`, and the provider/evidence prerequisites are satisfied. Preserve the current legacy path when false.

### Task 2: Add the durable checkout quote-session boundary

Files:
- Add model/migration only if an existing durable quote-session identity cannot be reused safely.
- Add `shopsoma-backend/app/schemas/checkout_shipping.py`.
- Add `shopsoma-backend/app/services/shipping/checkout_quotes.py`.
- Add `shopsoma-backend/app/api/v1/checkout_shipping.py` and register it.
- Add tests for ownership, replay, expiry, and gate-off behavior.

The boundary must bind the cart/address/currency fingerprint to the authoritative server subject and return only redacted quote options. It must not expose raw provider payloads or accept a price from the browser.

### Task 3: Make review/order creation consume the selected quote identity

Files:
- Modify `shopsoma-backend/app/schemas/order.py`.
- Modify `shopsoma-backend/app/api/v1/orders.py`.
- Modify related service/payment truth tests.

Add an optional quote-selection identity field. When the checkout gate is on, resolve cost and currency from the persisted selected option and reject missing, expired, mismatched, or unselected identities. When off, retain `shipping_rate_id` behavior exactly.

### Task 4: Wire the existing checkout shipping step without redesign

Files:
- Modify `shopsoma-frontend/src/services/checkoutService.ts`.
- Modify `shopsoma-frontend/src/services/shippingQuoteService.ts` only for the checkout endpoint contract.
- Modify `shopsoma-frontend/src/pages/checkout/Checkout.tsx`.
- Add/update focused checkout tests.

Keep the established shipping-step markup, classes, labels, and summary layout. Add only the state/effects/API calls needed to request and select DHL options when the backend indicates the feature is enabled. Send quote/option IDs to review and create; never send a DHL amount as truth. Preserve the current legacy code path when disabled.

### Task 5: Verify focused and full gates

Run frontend typecheck/tests and backend focused tests, then the canonical backend and frontend suites available in the worktree. Exercise gate-off fallback and sandbox gate-on quote selection using test doubles; do not call DHL production.

### Task 6: Review diff and document staging activation

Confirm no established UI redesign, no production gate path, no credentials, and no provider production URL. Record exact environment variable names and staging-only activation instructions without values.
