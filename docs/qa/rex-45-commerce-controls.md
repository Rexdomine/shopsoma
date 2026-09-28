# Stripe and USD controls — review handoff

## Scope and acceptance

Two independent flags (`stripe_enabled`, `usd_switching_enabled`) use the existing `app_settings` table. Absent or malformed values mean off. Public GET `/settings/public/commerce-features` exposes only these booleans; admin PUT `/settings/admin/commerce-features` requires both explicit booleans and the existing admin dependency. Controls are on Admin Settings → Currency and save immediately.

Stripe off prevents new initialization and new/replacement payment attempts, including direct requests. An already-started idempotent attempt can replay; an open browser can reopen its existing intent. Verification, webhooks and reconciliation remain ungated. Paystack behavior is unchanged.

USD off normalizes both client stores, their setters/hydration, new order reviews and new order creation to NGN. Existing conversion code converts product source amounts. Product currency, committed order snapshots, receipt/accounting data and explicit historical currency formatting are unchanged. Public flags are not persisted in browser storage; they refresh at startup, window focus and every 60 seconds. Server gates apply on each new order/payment request. Existing committed USD orders remain USD. With USD on and Stripe off, USD checkout explains that no supported method is available and directs shoppers to NGN/Paystack.

No schema migration, backfill, provider configuration or new environment variable. No merge or deployment authorized by this handoff.

## Local setup/run commands

From the task branch based on `origin/develop` revision `d0d7676`:

```sh
cd shopsoma-frontend
npm ci
npm run dev -- --host 127.0.0.1
```

In another terminal, use a local test PostgreSQL/Redis environment and the repository `.env.example` (test credentials only):

```sh
cd shopsoma-backend
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1
```

This agent reused existing frontend dependencies via a worktree symlink. The runner lacks ensurepip; backend dependencies were installed in a run-owned scratch virtual environment using PyPA's pip bootstrap. No system packages were changed. The focused settings suite below uses a temporary SQLite file and does not connect to the configured PostgreSQL URL.

## Local tests and evidence

Frontend, from `shopsoma-frontend`:

```sh
npm test -- src/store/commerceFeatures.test.tsx src/store/commerceSurfaces.test.tsx src/components/admin/__tests__/CommerceFeatureSettings.test.tsx src/pages/admin/AdminSettings.test.tsx src/pages/checkout/Checkout.test.tsx
npm run build
```

Backend, from `shopsoma-backend`, with the virtual environment activated:

```sh
SECRET_KEY=local-test-only DATABASE_URL=postgresql://localhost/unused python -m pytest --confcutdir=tests/commerce_features tests/commerce_features -q
python -m compileall -q app/api/v1/settings.py app/api/v1/orders.py app/api/v1/payments.py app/services/commerce_features.py app/services/payments/fulfilment_bridge.py
```

Backend: 15 tests pass, exercising real settings ORM persistence across request sessions, all four combinations, public safe fields, unauthenticated/customer/vendor write rejection, strict validation, malformed defaults, new Stripe rejection and original-attempt replay. These are isolated tests; PostgreSQL locking, triggers and live payment integrations were not exercised.

Frontend: 100 tests pass across the focused suites (98 store/admin/checkout plus 2 header/cart tests); two existing guest-capability storage-key assertions fail. Both failures were reproduced in an untouched `d0d7676` worktree with:

```sh
npm test -- src/pages/checkout/Checkout.test.tsx -t 'preserves its capability|keeps a guest Paystack capability'
```

Those assertions expect `shopsoma_checkout_capability:order-1`; the baseline stores normalized uppercase identifiers. No unrelated fix was included. Frontend build and backend syntax checks pass. DOM tests are not browser screenshots or browser QA evidence.

## Expected local result / browser checklist

Browser testing was NOT performed: Paperclip returned `currentExecutionWorkspace=null`, with no managed preview URL or browser tool. StarLord should provision/route a managed local preview for Product and NightWing (existing REX-46), using this branch and commands above. Do not connect a preview to production providers or customer data.

At desktop (1440px) and mobile (390px):

1. As admin, test off/off, on/off, off/on and on/on. Reload and sign in again; saved values must survive. Deny writes from guest, customer and vendor sessions.
2. Seed saved USD preferences and sign in as a returning customer. With USD off, confirm header, shared switchers, checkout and profile preference controls do not expose USD while loading or after a failed flag request. Confirm both NGN and original USD products convert correctly in cards, detail, cart and new checkout. Do not merely compare currency symbols.
3. With USD enabled, choose USD, reload and verify it restores only after settings permit it. Toggle off in a separate admin session; refocus the shopper window and verify NGN. In an unfocused open tab, allow up to 60 seconds for visual refresh.
4. Stripe off hides its new-payment option. Attempt initialization through a stale client/direct API request and confirm rejection before provider creation. NGN Paystack must still work. USD on/Stripe off must show the NGN/Paystack guidance.
5. Initialize a Stripe test payment, then turn Stripe off. Close/reopen the existing intent, complete verification and replay its webhook; confirm exactly one payment/order fulfilment. Retry a failed or expired attempt and confirm it cannot allocate a new Stripe attempt while off.
6. Compare a historical USD order, receipt, commissions and payouts before/after switching off. Stored currency and amounts must be identical. Existing order display must not relabel USD as NGN.

## Staging steps and expected result

Only after reviewer-approved merge, deploy via the established staging workflow. Repeat the browser checklist with staging test accounts and payment test mode, including fresh sessions, network failure, stale preferences, duplicate callbacks/webhooks and expired attempts. Expected: identical flag behavior, no duplicated financial effects, Paystack available for NGN, and historical financial truth unchanged. Staging remains unverified.

## Regression checks and review ownership

NightWing's independent QA is tracked in REX-46 through StarLord; Product receives the managed preview through StarLord. Architecture can review technical payment-attempt risk. No specialist security or AI-evaluation approval is claimed. Any qualified security review needed for payment/auth changes must be routed by StarLord. Known pre-existing guest-capability test failures remain explicitly separate from this implementation.
