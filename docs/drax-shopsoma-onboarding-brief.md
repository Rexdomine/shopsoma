# Drax Shopsoma Onboarding Brief

_Last updated: 2026-06-15_

## Purpose

This brief gives Drax and NightWing a reusable project map for Shopsoma so future work can start from verified repo context instead of rediscovery. Shopsoma is Rex's production-oriented multi-vendor African fashion e-commerce marketplace.

## Non-negotiable operating rules

1. **Every Shopsoma feature, bug fix, update, documentation/process change, or production-facing task must be completed through a GitHub PR.**
2. **Every PR must target `develop` only.** Do not open feature/update PRs into `main` unless Rex explicitly changes the release process.
3. **Start every task branch from latest `origin/develop`.**
4. **Never leave completed Shopsoma work only in the local workspace.** If work is done, it must be committed, pushed, and opened as a PR for that exact task.
5. **Do not push directly to `develop` or `main`.**
6. **Drax owns implementation quality. NightWing owns independent QA/review before handoff.**
7. **Final handoffs must include `NightWing’s review note`.**

Recommended branch names:

- `feature/<short-feature>`
- `fix/<short-bug>`
- `docs/<short-doc-change>`
- `chore/<short-maintenance>`

## Workspace and repository

- Local workspace: `/opt/data/projects/shopsoma`
- Remote: `https://github.com/Rexdomine/shopsoma.git`
- Integration branch: `develop`
- Production branch: `main`
- Current onboarding PR branch: `docs/drax-onboarding`

## Product summary

Shopsoma is a React + FastAPI marketplace connecting African fashion designers/vendors with global buyers. Core domains include:

- customer storefront, product browsing, wishlist, cart, checkout, order tracking, profile, returns;
- vendor onboarding, activation, dashboard, product/catalog management, orders, analytics, earnings, payouts;
- admin management for users, vendors, vendor applications, products, orders, returns, payouts, settings;
- payments through Stripe and Paystack;
- shipping/rates through local rules and ShipBubble integration;
- email/newsletter/notification workflows;
- image upload/storage via local dev storage or S3-compatible storage.

## Repository structure

```text
shopsoma/
├── AGENTS.md                         # Canonical engineering/agent rules
├── README.md                         # Project overview and branch workflow
├── docs/                             # Architecture/deployment/business docs
├── notes/                            # Operational notes
├── scripts/                          # Utility and staging/ad-hoc scripts
├── shopsoma-backend/                 # FastAPI + SQLAlchemy backend
└── shopsoma-frontend/                # React + Vite + TypeScript frontend
```

## Canonical docs and rules to read before coding

- `AGENTS.md`
- `README.md`
- `docs/shopsoma_technical_guide.md`
- `docs/DEPLOYMENT_GUIDE.md`
- `docs/CI_CD_PIPELINE.md`
- `docs/database_schema.md`
- `shopsoma-backend/README.md`
- `shopsoma-frontend/README.md`

## Backend map

Backend root: `shopsoma-backend/`

Stack:

- FastAPI `0.115.0`
- Python 3.11 in docs/Dockerfile, but CI/Render currently reference Python 3.9.x
- SQLAlchemy 2 async engine + PostgreSQL
- Alembic migrations
- Pydantic v2 settings/schemas
- JWT auth with `python-jose`
- Stripe SDK and Paystack HTTP integration
- Redis/Celery dependencies exist, but current critical checkout/payment/webhook flows are documented as synchronous/not Celery-dependent

Key files:

- App entry: `shopsoma-backend/app/main.py`
- Config: `shopsoma-backend/app/core/config.py`
- Database/session: `shopsoma-backend/app/core/database.py`
- Auth dependencies: `shopsoma-backend/app/api/dependencies.py`
- JWT/security: `shopsoma-backend/app/core/security.py`
- API routers: `shopsoma-backend/app/api/v1/`
- Models: `shopsoma-backend/app/models/`
- Schemas: `shopsoma-backend/app/schemas/`
- Services: `shopsoma-backend/app/services/`
- Tests: `shopsoma-backend/tests/`
- Migrations: `shopsoma-backend/alembic/versions/`

Important routers:

- `app/api/v1/auth.py` — signup/login/magic links/password reset/account claim/email verification/token refresh.
- `app/api/v1/products.py` — product catalog, vendor products, variants, images, moderation, bulk upload.
- `app/api/v1/cart.py` — guest/authenticated carts and coupon handling.
- `app/api/v1/orders.py` — order review/create/detail/tracking/cancel; high-risk pricing, stock, commission, guest account logic.
- `app/api/v1/payments.py` — Stripe/Paystack initialize, verify, webhooks.
- `app/api/v1/vendors.py` — large vendor domain router: profile, products, orders, analytics, earnings, payouts, store status.
- `app/api/v1/vendor_activation.py` — vendor OTP/password activation.
- `app/api/v1/vendor_applications.py` — vendor application submission/admin approval.
- `app/api/v1/admin.py` — large legacy/admin catch-all; high regression risk.
- `app/api/v1/admin_orders.py`, `admin_returns.py`, `admin_payouts.py` — newer focused admin routers.
- `app/api/v1/settings.py` — app settings, exchange rate, featured rotation, commission/payout settings.
- `app/api/v1/shipping_rates.py` — shipping rates and ShipBubble/local calculation.
- `app/api/v1/images.py` — image upload/storage.
- `app/api/v1/seed.py` — seed/reset endpoints; treat as high risk if exposed.

Backend test commands:

```bash
cd /opt/data/projects/shopsoma/shopsoma-backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v
ruff check app/ tests/
black --check app/ tests/
alembic upgrade heads
```

Targeted backend checks for high-risk work:

```bash
pytest tests/test_orders.py tests/test_cart.py tests/test_guest_account_claim_payment.py -v
pytest tests/test_admin_orders.py tests/test_admin_payouts.py tests/test_vendor_payouts.py -v
pytest tests/test_products.py tests/test_product_variants.py tests/test_bulk_product_upload.py -v
pytest tests/test_production_hardening.py tests/test_auth_tokens.py tests/test_password_reset.py -v
```

## Frontend map

Frontend root: `shopsoma-frontend/`

Stack:

- React `19.2.0`
- TypeScript `~5.9.3`
- Vite `5.4.10`
- React Router DOM `6.26.2`
- Zustand
- Axios
- Tailwind CSS
- Vitest + Testing Library + jsdom
- Stripe React/JS packages

Key files:

- App bootstrap: `shopsoma-frontend/src/main.tsx`, `src/App.tsx`
- Routes/constants: `src/router/index.tsx`, `src/config/constants.ts`
- Shared API client: `src/services/api.ts`
- Auth context: `src/context/AuthContext.tsx`
- Vendor context: `src/context/VendorContext.tsx`
- Cart store: `src/store/cartStore.ts`
- Currency/preference stores: `src/store/currencyStore.ts`, `src/store/preferenceStore.ts`
- Customer pages: `src/pages/products/`, `src/pages/cart/`, `src/pages/checkout/`, `src/pages/orders/`, `src/pages/profile/`
- Vendor pages: `src/pages/vendor/`
- Admin pages: `src/pages/admin/`
- Layouts: `src/components/layout/`, `src/components/vendor/`, `src/components/admin/`

Important route surfaces:

- Customer/storefront: `/`, `/products`, `/products/:id`, `/cart`, `/checkout`, `/order-success`, `/track/:orderId`, profile routes.
- Auth: `/login`, `/register`, `/forgot-password`, `/reset-password`, `/verify-email`, `/claim-account`.
- Vendor onboarding/auth: `/vendor/login`, `/vendor/signup`, `/vendor/otp`, `/vendor/set-password`.
- Vendor app: `/vendor/dashboard`, products, orders, analytics, collections, settings, earnings/withdrawals.
- Admin app: users, products, returns, vendor applications, vendors, settings, orders, payouts.

Frontend commands:

```bash
cd /opt/data/projects/shopsoma/shopsoma-frontend
npm ci
npm test
npm run lint
npm run build
npm run dev
```

Known frontend risks:

- Dependencies were not installed during onboarding, so `npm test` and `npm run lint` failed with missing local binaries.
- `ProtectedRoute` redirects admins to `/admin/dashboard`, but that route was not found in the router.
- Several admin sidebar links point to routes not found in the router.
- Many vendor/profile routes depend on page/layout behavior and are not all route-level protected.
- `checkoutService.ts` and `paymentService.ts` use local Axios clients rather than the shared `services/api.ts` refresh/error behavior.
- `websocketService.ts` constructs a localhost-style `:8000` WebSocket URL that may not work in staging/production.
- Backup files exist in `src/` and should not be expanded further.

## CI, deployment, and operations

CI file: `.github/workflows/ci.yml`

Current CI jobs:

- backend CI with PostgreSQL service, Python 3.9, pytest/coverage/flake8;
- frontend CI with Node 18, `npm ci`, lint, typecheck, build;
- Trivy security scan.

Important CI risk:

- Several checks are soft/non-blocking via `continue-on-error` or `|| echo`. A green CI run may not prove tests/lint/typecheck/security actually passed. Drax must run and report local verification, not rely only on CI.

Staging deployment:

- `render.yaml`
- Backend: `shopsoma-staging-api`, branch `develop`, health `/api/v1/health`.
- Frontend: `shopsoma-staging`, branch `develop`, static site, `VITE_API_BASE_URL=https://shopsoma-staging-api.onrender.com/api/v1`.
- Merge to `develop` is expected to auto-deploy to staging through Render.

Production deployment:

- `.github/workflows/deploy-production.yml` creates a GitHub Release on version tags.
- Production Render blueprint is example-only in `render.production.yaml.example`.
- Do not assume production deployment is automatic without verifying actual Render setup.

## High-risk areas requiring extra care

Always inspect frontend + backend + tests together before editing these flows:

- authentication, token refresh, role-protected routes;
- vendor onboarding/activation/application approval;
- product create/edit/delete, variants, images, bulk upload;
- cart sync, guest cart, checkout;
- order totals, currency conversion/display, stock decrement, commission snapshots, payouts;
- Stripe/Paystack payment initialization, verification, and webhooks;
- shipping rates, ShipBubble, pickup/delivery statuses;
- admin destructive actions, cancellations, refunds, bulk status updates;
- migrations and settings/business config.

## Drax task workflow for Shopsoma

For every implementation/update task:

1. Sync repo and start from `origin/develop`.
2. Create a dedicated branch.
3. Restate the task and acceptance criteria.
4. Inspect relevant current files before editing.
5. Make the smallest safe change only.
6. Add/update tests for non-trivial behavior.
7. Run targeted verification and broader checks where practical.
8. Commit with conventional commit format.
9. Push branch and open PR into `develop`.
10. Include PR body sections:
    - Summary
    - Safety/Scope
    - Verification/Test Plan
    - NightWing QA plan or result
    - Deployment/Operations notes
11. Engage NightWing for independent QA/review before final handoff.
12. Final response to Rex must include PR link, test evidence, merge target, and `NightWing’s review note`.

## NightWing QA protocol for Shopsoma

NightWing should verify:

- PR base is `develop`;
- changed files match the requested scope;
- no unrelated cleanup or accidental secrets are included;
- tests/lint/build evidence is adequate for touched areas;
- UX flows have visible loading/error/success states;
- auth/role restrictions are preserved;
- payment/order/currency/admin changes have focused regression coverage;
- migrations/env changes include rollback/deployment notes;
- staging verification is done after merge when applicable.

## Current onboarding findings to address in future PRs

These are not fixed by this onboarding PR; they are known areas for future scoped work:

- normalize Python/Node versions across docs, CI, Docker, and Render;
- make CI fail on real test/lint/typecheck/security failures;
- review unprotected seed/reset endpoints and staging destructive scripts;
- review frontend protected route gaps and missing admin dashboard route;
- consolidate frontend API client usage for checkout/payment flows;
- fix production/staging WebSocket URL construction;
- review Docker Compose env duplication and frontend Docker `nginx.conf` reference;
- replace production-noisy debug `console.log`/`print` usage with structured logging where needed;
- create/verify CODEOWNERS, branch protection, and PR template if Rex wants stronger repo governance.
