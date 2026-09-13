# Manual shipping: configuration and acceptance testing

## Scope

Admin Settings controls one selected provider: **Manual rates**, **ShipBubble**, or **DHL**. Manual is the default when no provider has been configured. Existing provider settings remain visible; selecting manual explicitly overrides DHL for new quotes.

ShipBubble is shown but unavailable because the secure checkout does not have durable ShipBubble quote support. DHL remains subject to its existing sandbox readiness gates. This change does not activate either carrier, book shipments, buy labels, change payment verification, or deploy anything. Operations must arrange manual delivery separately through the established fulfilment process.

No database migration or new environment variable is required.

## Configure rates

1. Sign in as an administrator and open **Admin → Settings**.
2. Under **Shipping Provider**, choose **Manual rates**. Confirm the saved selection after reloading.
3. Under **Manual shipping rates**, add a rate with:
   - A customer-facing name and optional description.
   - Country and optional state. A blank state covers all states in that country.
   - Price in NGN; **0 is genuinely free delivery**.
   - Optional minimum and maximum order subtotal, in NGN and inclusive.
   - Minimum and maximum delivery days.
   - Active status, priority (lower first), and optional default.
4. Save, reload, and confirm the persisted values.
5. Use **Preview saved rates** with a destination and subtotal. For example, a Lagos-only NGN 2,500 rate should appear for Lagos but not Abuja.
6. Edit, set default, or deactivate existing rates as needed. Deactivation retains historical references and removes the rate from new quotes. Editing an inactive rate can reactivate it.

Country/state comparisons ignore case and surrounding whitespace; `NG` and `Nigeria` are equivalent. Country-wide and state-specific rates can both match. There is only one default; it is preferred in previews, followed by priority and stable identity ordering. Secure checkout still requires an explicit customer selection.

Prices and thresholds are stored in NGN. USD orders use the server's authoritative exchange rate. Client-submitted prices are not trusted. Invalid price precision, negative values, and crossed minimum/maximum ranges are rejected.

## Customer checkout

The existing checkout rollout configuration determines which flow is used; selecting manual shipping does not alter that rollout:

- **Legacy / production-default flow:** address → eligible manual rates → order review → server-priced order → existing payment flow.
- **Fully enrolled sandbox domestic flow:** address → unpaid prerequisite order → persisted delivery estimate → explicit option selection → existing payment flow. The frontend skips the obsolete preliminary rate calculation when the server confirms full domestic enrollment.
- Partial sandbox cohorts retain their existing preliminary sequence. No production secure-checkout activation is introduced.

For the sandbox flow, existing settings are `DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED=true`, `DOMESTIC_CHECKOUT_COHORT_PERCENTAGE=100`, a non-production application environment, `DHL_ENVIRONMENT=sandbox`, and the established guest capability pepper/version. Carrier calls may remain disabled. Apply these settings only in an authorized test environment.

Unsupported destinations or subtotals fail closed: no free shipping or carrier fallback is invented. If an unpaid prerequisite order was saved but delivery options failed, retry against that order or use the visible start-again action to choose another address.

Already-issued secure estimates retain their original amount until their existing server expiry. Admin rate edits affect new estimates, not issued selections or historical orders. Legacy order creation revalidates the current rate and subtotal. Existing payment and order recovery safeguards remain in place.

## Acceptance checklist

Use an isolated local database or an authorized staging build, never production data for fixtures.

- [ ] Admin selection and create/edit/default/deactivate actions survive reload.
- [ ] Lagos and Abuja rates match only eligible destinations; a country-wide rate matches both.
- [ ] Zero-cost rates remain zero; inactive, out-of-range, malformed and wrong-destination rates cannot be selected for a new order.
- [ ] Registered and guest customers can add a product with no variant, choose an address, and select the configured manual rate.
- [ ] Products with real variant UUIDs continue to submit their variant identity.
- [ ] Displayed shipping and payable total agree with the persisted order/selection API response, in NGN and USD.
- [ ] Non-admin configuration writes are rejected; unavailable provider selection and legacy pricing bypasses are rejected.
- [ ] Issued estimate replay/selection remains immutable after a rate edit/deactivation or provider change.
- [ ] Expired or stale checkout subjects still require recovery/reselection through existing safeguards.
- [ ] Manual mode makes no carrier calls. Any payment test uses separately authorized test gateway credentials.

## Automated checks

From `shopsoma-backend`, using explicitly isolated test configuration:

```sh
python -m pytest tests/test_manual_shipping_launch.py tests/test_checkout_estimate_api.py tests/test_dhl_checkout_gate.py -q --no-cov
python -m pytest tests/ -v --cov=app --cov-report=term-missing
```

From `shopsoma-frontend`:

```sh
npm test
npm run build
npm run lint
```

Node versions with experimental native WebStorage may require `NODE_OPTIONS=--no-experimental-webstorage` for jsdom tests. Prevent `load_dotenv()` from discovering unrelated parent-directory credentials when running isolated worktrees; use a local inert `.env` and explicitly supplied test settings. Do not commit local environment files.

## Rollout and rollback

Review and merge the PR into `develop`, deploy through the normal authorized process, then repeat the admin-to-checkout acceptance checklist on that exact deployed build. Configure real launch coverage and prices before accepting customer orders. This PR does not seed commercial rates.

Changing a rate or provider does not reprice existing orders. If coverage is wrong, correct or deactivate the affected rate and verify a fresh checkout. Do not enable an unavailable provider as a workaround. Live carrier/payment activation and production deployment are separate decisions.
