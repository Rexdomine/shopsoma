# ShopSoma — Payment Bridge Canonical Gate Stabilization

Last verified: 2026-08-15
Branch: `fix/payment-bridge-canonical-gate-stabilization`
Repair parent: `116616897085b0ca1999223d3173661f58538e41`

## Milestone 3 closure checkpoint

The recovered Milestone 3 implementation now covers the order-first domestic checkout prerequisite path: persisted static estimate/options, explicit selection, server-owned totals, complete stock-managed/made-to-order coverage, non-decrementing stock reservations, and order-bound guest capabilities stored only as versioned HMAC digests. The false-default gate leaves ordinary orders on `legacy_pre_bridge` behavior.

Production boundaries remain inert for enforced orders: no Payment, VendorPickup, VendorNotification, email/provider/DHL call, fulfilment action, or physical stock decrement occurs before the prerequisite branch returns.

## Milestone 3 NightWing repair checkpoint

The two blocking review findings are repaired without changing M2 migrations or triggers. Saved shipping addresses now require an authenticated exact owner, guest checkout rejects every pre-existing email identity before writes, authenticated orders receive no guest secret, and new guest orders retain one-time plaintext/digest-only capability behavior.

Selection now uses the documented lock order `order -> shipping address -> order items -> owner/capability -> coordinator -> inventory -> estimate -> option`. After every potentially waiting lock is held, the route expires/reloads the authoritative order aggregate, rechecks destination and order snapshot hashes, then samples PostgreSQL `clock_timestamp()` before any prerequisite mutation.

## Verified gates

- New ownership negatives and real PostgreSQL address/item lock-wait regressions plus same-order convergence: 7 passed.
- Complete `tests/test_checkout_estimate_api.py`: 14 passed.
- Exact prior M2 preservation selection (checkout prerequisite migration/models; stock payment persistence/coordinator/blockers; orders/admin deletion; guest capability): 107 passed.
- Black check, Flake8 fatal selections `E9,F63,F7,F82`, compileall, and `git diff --check`: passed on all changed Python paths.
- Final changed-path, secret/private-key/plaintext, and forbidden production-boundary scans: passed with zero hits.

## Safety boundary

Do not push, mutate a PR, merge, deploy, run a production migration, call a carrier/provider, perform a DHL action, or activate any feature without Rex's explicit approval. Canonical sequence remains 2A-3D followed by 2A-4A; do not infer macro-phase jumps.

## NightWing M5 final repair checkpoint (uncommitted)

The bounded M5 repair now rejects Paystack whenever the canonical order currency is not NGN, including `domestic_checkout_v1`, before payment-attempt or provider/session creation. Checkout also fails closed before either provider UI opens when gateway/currency compatibility is invalid or the canonical decimal amount does not exactly match its safe integer two-decimal minor-unit value.

Frontend focused and full verification is green: Checkout 11/11, full Vitest 43/43, TypeScript/Vite build, and ESLint (0 errors; 252 existing warnings). Changed Python files pass Black, fatal Flake8 (`E9,F63,F7,F82`), compileall, diff, changed-path, and added-line secret/live-provider scans.

Backend route/contract execution remains unverified locally because PostgreSQL is unavailable (`127.0.0.1:5432` refused), Docker has no daemon/socket, and the bundled PostgreSQL runtime requires a guarded inherited library path. Do not commit this repair until the new enforced-USD Paystack route regression and complete payment bridge contract suite pass against PostgreSQL.
