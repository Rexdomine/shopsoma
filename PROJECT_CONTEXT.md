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

## NightWing M5 final committed repair checkpoint

Committed candidate `a5ae7a42d8a7c0049158421deabb4271f09c5533` rejects Paystack whenever the canonical order currency is not NGN, including `domestic_checkout_v1`, before payment-attempt or provider/session creation. Checkout also fails closed before either provider UI opens when gateway/currency compatibility is invalid or the canonical decimal amount does not exactly match its safe integer two-decimal minor-unit value.

Frontend focused and full verification is green: Checkout 11/11, full Vitest 43/43, TypeScript/Vite build, and ESLint (0 errors; 252 existing warnings). Changed Python files pass Black, fatal Flake8 (`E9,F63,F7,F82`), compileall, diff, changed-path, and added-line secret/live-provider scans.

Backend PostgreSQL verification is green on this lineage: the genuine enforced-USD Paystack production-route regression passed with zero provider calls, zero payment attempts, and zero payment rows; the complete payment bridge contract passed 128/128. No live payment-provider or DHL call occurred.

## DHL sandbox shadow UAT checkpoint

Fresh lane: `feat/dhl-sandbox-shadow-uat` in worktree `/opt/data/projects/shopsoma-worktrees/dhl-sandbox-shadow-uat`.

Implemented an admin-only DHL sandbox shadow-quote slice that reuses existing checkout capability fingerprinting and sandbox gating instead of adding any new secret surface. The backend service now derives request composition from authoritative `HubPackageItem` rows on the ready package, enforces the configured DHL sandbox cohort allowlist, uses the checkout capability active pepper/version as the HMAC identity source, and persists `DomesticRateAttempt`, `DomesticRateResponse`, and `DomesticRateOffer` rows with the repo’s lawful immutable lifecycle pattern (pending claim insert, SQL terminal update, then response/offers bound to the trigger-generated completion txid). The admin orders API now exposes `POST /api/v1/admin/orders/{order_id}/shadow-quote`, and the admin frontend includes a bounded “Run DHL Sandbox Shadow Quote” action plus a compact result summary card.

Independent review found and fixed two initial follow-ups before handoff: the admin rerun path now uses a unique per-run idempotency key to avoid collisions, and the new test fake now matches the service’s adapter method name. A later exact-environment rerun surfaced and repaired three more candidate issues before final handoff: `admin_orders.py` now uses the lane’s module-level settings pattern instead of a missing `get_settings` import, the service now inserts and flushes the pending `DomesticRateAttempt` before calling the DHL adapter and records `call_started_at` immediately before the provider boundary, and the resolved/attempt destination country code now comes from the authoritative outbound intent instead of a hardcoded `NG`.

Bounded verification status on this machine: the correct backend Python environment for this lane was restored locally with `uv venv .venv` + `uv pip install -r requirements.txt`. For the DB gate, a private user-space PostgreSQL 17 cluster was bootstrapped under `/opt/data/tmp/pg-bootstrap` and started on `127.0.0.1:5432`, allowing the repo’s real disposable test-database fixtures to run unchanged. Touched backend files pass `.venv/bin/python -m py_compile`, and the bounded DB-backed verification slice is green with `.venv/bin/python -m pytest -q tests/test_admin_shadow_quote.py tests/test_dhl_domestic_rating.py` (`76 passed`). That exact-environment rerun surfaced and fixed two final candidate defects before handoff: the shadow-quote service now orders active `HubPackageSeal` rows by the real `applied_at` field instead of a nonexistent `created_at`, and the canonical DHL sandbox `ACCOUNT_ALIAS` is now `dhl-ng-sandbox` consistently in both the adapter and direct contract tests. Fresh independent read-only NightWing review on the final candidate returned `PASS WITH NOTES` with no blocking issues; the only follow-up notes were optional extra coverage for adapter-failure, non-ready-package, and admin-RBAC denial paths. No live DHL/provider call was made during implementation, verification, or review.
