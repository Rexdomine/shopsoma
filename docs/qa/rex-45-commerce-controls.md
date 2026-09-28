# Stripe and USD controls — review handoff

## Scope and acceptance

Two independent flags (`stripe_enabled`, `usd_switching_enabled`) use the existing `app_settings` table. Absent or malformed values mean off. Public GET `/settings/public/commerce-features` exposes only these booleans; admin PUT `/settings/admin/commerce-features` requires both explicit booleans and the existing admin dependency. Controls are on Admin Settings → Currency and save immediately.

Stripe off prevents new initialization and new/replacement payment attempts, including direct requests. An already-started idempotent attempt can replay; an open browser can reopen its existing intent. Verification, webhooks and reconciliation remain ungated. Paystack behavior is unchanged.

USD off normalizes both client stores, their setters/hydration, new order reviews and new order creation to NGN. Existing conversion code converts product source amounts. Product currency, committed order snapshots, receipt/accounting data and explicit historical currency formatting are unchanged. Public flags are not persisted in browser storage; they refresh at startup, window focus and every 60 seconds. Server gates apply on each new order/payment request. Existing committed USD orders remain USD. With USD on and Stripe off, USD checkout explains that no supported method is available and directs shoppers to NGN/Paystack.

No schema migration, backfill, provider configuration or new environment variable. No merge or deployment authorized by this handoff.

## Local setup/run commands

From the task branch based on `origin/develop` revision `673638630b06e3cc5dd9573179077905054369e5` (merged into the repair branch):

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
npm test -- src/store/commerceFeatures.test.tsx src/store/commerceSurfaces.test.tsx src/components/admin/__tests__/CommerceFeatureSettings.test.tsx src/pages/admin/AdminSettings.test.tsx src/pages/checkout/Checkout.test.tsx src/utils/checkoutCapability.test.ts
npm run build
```

Backend, from `shopsoma-backend`, with the virtual environment activated:

```sh
SECRET_KEY=local-test-only DATABASE_URL=postgresql://localhost/unused python -m pytest --confcutdir=tests/commerce_features tests/commerce_features -q
python -m compileall -q app/api/v1/settings.py app/api/v1/orders.py app/api/v1/payments.py app/services/commerce_features.py app/services/payments/fulfilment_bridge.py
```

Backend: 15 tests pass, exercising real settings ORM persistence across request sessions, all four combinations, public safe fields, unauthenticated/customer/vendor write rejection, strict validation, malformed defaults, new Stripe rejection and original-attempt replay. These are isolated tests; PostgreSQL locking, triggers and live payment integrations were not exercised.

Repair verification: 112 frontend tests pass across six focused suites, including six new ordering regressions and the checkout capability helper suite. Two guest-capability storage-key assertions fail on both the repaired candidate and an untouched actual develop `673638630b06e3cc5dd9573179077905054369e5` worktree with:

```sh
npm test -- src/pages/checkout/Checkout.test.tsx -t 'preserves its capability|keeps a guest Paystack capability'
```

Those assertions expect `shopsoma_checkout_capability:order-1`; the baseline stores normalized uppercase identifiers. No unrelated fix was included. Frontend build and backend syntax checks pass. DOM tests are not browser screenshots or browser QA evidence.

## Expected local result / browser checklist

Browser testing was NOT performed: Paperclip returned `currentExecutionWorkspace=null`, with no managed preview URL or browser tool. StarLord should provision/route a managed local preview for Product and NightWing ([REX-48](/REX/issues/REX-48)), using this branch and commands above. Do not connect a preview to production providers or customer data.

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

NightWing's independent re-review is tracked in [REX-48](/REX/issues/REX-48) through StarLord; Product receives the managed preview through StarLord. Architecture can review technical payment-attempt risk. No specialist security or AI-evaluation approval is claimed. Any qualified security review needed for payment/auth changes must be routed by StarLord. Known pre-existing guest-capability test failures remain explicitly separate from this implementation.


## REX-47 repair and reproducible environment handoff

### Local setup or run commands

The repair was developed in `.worktrees/rex-47`, branch `bugfix/rex-47-stale-commerce`, separate from the concurrently held checkout. The candidate includes a normal merge of develop `673638630b06e3cc5dd9573179077905054369e5`; no shared history was rewritten. The final task comment records the exact repair commit and publication status.

The backend requirements installed successfully on Python 3.13 in a new isolated environment. If this runner lacks ensurepip, the following is the tested bootstrap alternative, from repository root. Use a disposable local test environment only:

```sh
python3 -m venv --without-pip "$PAPERCLIP_RUN_SCRATCH_DIR/backend-venv"
curl -fsS https://bootstrap.pypa.io/get-pip.py -o "$PAPERCLIP_RUN_SCRATCH_DIR/get-pip.py"
"$PAPERCLIP_RUN_SCRATCH_DIR/backend-venv/bin/python" "$PAPERCLIP_RUN_SCRATCH_DIR/get-pip.py"
"$PAPERCLIP_RUN_SCRATCH_DIR/backend-venv/bin/pip" install -r shopsoma-backend/requirements.txt
cd shopsoma-backend
SECRET_KEY=local-test-only DATABASE_URL=postgresql://localhost/unused "$PAPERCLIP_RUN_SCRATCH_DIR/backend-venv/bin/python" -m pytest --confcutdir=tests/commerce_features tests/commerce_features -q
```

The resolved dependency snapshot and exact baseline/candidate test evidence are attached to [REX-47](/REX/issues/REX-47). Run scratch environments expire; recreate dependencies from the commands and snapshot, not an old virtualenv path. The isolated backend suite uses temporary SQLite, synthetic role objects, and mocked payment provider boundaries. It does not create real customer accounts or call live providers.

### Local test steps

Run the frontend and backend commands above. Ordering coverage explicitly controls promise completion: A starts, B starts, B disables, A enables; latest refresh error followed by stale success; stale error after newer success; late success/error after an admin save; and a rendered admin toggle save followed by a stale background result. Confirm a subsequent fresh read still applies.

### Expected local result

All 12 store tests and all 4 admin commerce component tests pass. Six new regressions cover both direct store ordering and the actual admin save integration. The full focused frontend command reports 112 passed, 2 failed; do not label that command green. The two failing guest assertions directly inspect lowercase `order-1`; the existing helper normalizes writes and reads to `ORDER-1`, supports legacy-key migration, and its six tests pass. This is evidence of stale assertions, not certification of the guest browser retry path: those failing tests stop before their later assertions. Backend: 15 passed. Production frontend build passes.

### Staging test steps and expected staging result

No staging execution or deployment occurred. After authorized review/merge, repeat the existing desktop/mobile checklist and simulate delayed public settings responses overlapping a later disabled response or completed admin save. Both preference stores and browser storage must remain NGN when USD is disabled; stale errors must not undo a saved independent Stripe flag. Existing financial values and server provider gates must remain unchanged.

### Regression checks and access limitations

Inspected App startup/focus/60-second scheduling, admin save/load behavior, both currency/preference stores, settings service contracts, backend feature tests, and guest capability save/load helpers. The only production-code change is a runtime revision counter in currencyStore; each refresh and authoritative application invalidates earlier reads. Success and error handlers check that revision. No persistent fields, API contracts, migrations, provider gates, or historical accounting calculations changed.

Paperclip heartbeat-context returned `currentExecutionWorkspace: null` on this run, so there is no workspace ID for `/api/execution-workspaces/{id}/runtime-services/start`, no registered frontend/backend service, and no browser URL. No unmanaged server was started. Browser, real PostgreSQL/Redis, synthetic browser accounts and staging are unverified. StarLord must route creation of an isolated managed execution workspace with local PostgreSQL/Redis, synthetic admin/customer/vendor data, and provider stubs before NightWing/Product browser review. Use Paperclip runtime service controls to launch the existing frontend/backend commands and publish the resulting URLs as runtime-service work products; do not point the preview at production credentials/data or live provider endpoints. Reviewers obtain access through that managed workspace, not through agent-local scratch paths. This missing preview does not constitute release approval.
