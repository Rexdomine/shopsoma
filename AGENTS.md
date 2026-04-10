# AGENTS.md

# Shopsoma Repository Guidelines for Codex and Engineering Agents

This file defines how coding agents must operate in the Shopsoma codebase.

Shopsoma is a production-oriented multi-vendor fashion marketplace with:
- a React + TypeScript + Vite frontend in `shopsoma-frontend/`
- a FastAPI + Python backend in `shopsoma-backend/`
- PostgreSQL as the primary database
- SQLAlchemy + Alembic for persistence and migrations
- Redis + Celery for background jobs
- Stripe and Paystack for payments
- vendor onboarding, product management, orders, payouts, and admin operations

The goal of every change is to produce the smallest safe improvement that solves the requested task without breaking nearby flows.

---

## 1) Core Working Principles

- Treat every task as work on a real production codebase.
- Prefer small, safe, incremental changes over large rewrites.
- Preserve existing architecture and patterns unless explicitly instructed otherwise.
- Do not introduce parallel implementations when an existing store, service, endpoint, schema, or component already exists.
- Do not “clean up” unrelated code while fixing a targeted bug or building a narrow feature.
- Minimize assumptions. If an assumption is necessary, choose the safest one and state it clearly in your task summary.
- Prioritize correctness, safety, maintainability, and compatibility over cleverness.

---

## 2) Repository Structure

### Monorepo Layout

- `shopsoma-frontend/` — React + TypeScript + Vite application
- `shopsoma-backend/` — FastAPI + SQLAlchemy backend
- `docs/` — supporting documentation
- `AGENTS.md` — this file

### Frontend Structure

Primary areas:
- `shopsoma-frontend/src/pages/` — route-level pages
- `shopsoma-frontend/src/components/` — reusable UI and domain components
- `shopsoma-frontend/src/router/` — route configuration
- `shopsoma-frontend/src/store/` — Zustand state stores
- `shopsoma-frontend/src/context/` — app/auth context
- `shopsoma-frontend/src/services/` and/or `src/api/` — API access layer
- `shopsoma-frontend/src/types/` — TypeScript types
- `shopsoma-frontend/src/utils/` — helpers
- `shopsoma-frontend/public/` — static assets

### Backend Structure

Primary areas:
- `shopsoma-backend/app/api/v1/` — FastAPI route handlers
- `shopsoma-backend/app/services/` — business logic
- `shopsoma-backend/app/models/` — SQLAlchemy models
- `shopsoma-backend/app/schemas/` — request/response schemas
- `shopsoma-backend/app/core/` — config, database, security, app internals
- `shopsoma-backend/app/tasks/` — Celery tasks
- `shopsoma-backend/app/middleware/` — middleware
- `shopsoma-backend/tests/` — pytest tests
- `shopsoma-backend/alembic/versions/` — migrations

---

## 3) Mandatory Workflow for Every Task

## Step 1: Understand Before Editing

Before changing code:
- restate the task in your own words
- identify the likely affected files
- inspect the current implementation first
- determine whether the logic already exists elsewhere
- identify any related models, schemas, stores, endpoints, or components
- identify downstream areas that may be affected

Never start coding from assumptions when the repo likely already contains the relevant logic.

## Step 2: Define Acceptance Criteria

For every non-trivial task, define concrete acceptance criteria such as:
- given X, when Y, then Z
- expected success case
- expected validation/error case
- any role-specific behavior
- any admin/vendor/customer differences
- any currency/payment/order side effects

## Step 3: Make a Narrow Plan

Before editing, briefly list:
- files to inspect
- files to update
- whether database changes are needed
- whether API contract changes are needed
- whether tests must be added or updated
- which nearby flows must not break

## Step 4: Implement the Smallest Safe Change

Make the narrowest change that fully solves the task.
Do not refactor unrelated code.
Do not rename or move files unless required by the task.

## Step 5: Self-Check Before Finishing

Before concluding:
- review imports and exports
- review async/await correctness
- review typing and null handling
- review permission/role checks
- review API response shapes
- review edge cases
- review whether any existing flow could regress

---

## 4) Shopsoma Architecture Rules

Respect the responsibility boundaries of the codebase:

### Frontend Owns
- UI rendering
- route composition
- client state
- interaction handling
- calling APIs
- display formatting
- loading and error states

### Backend Owns
- business rules
- permissions and role enforcement
- database writes and reads
- payment verification
- webhook handling
- order state transitions
- onboarding truth
- admin/vendor/customer data boundaries

### Database Owns
- transactional truth
- relationships
- persisted state
- audit-relevant values such as order totals, payout amounts, commission values, and original currency fields

Never move business-critical logic entirely into the frontend if it belongs on the backend.

---

## 5) Mandatory Inspection Before Editing

Before editing, inspect the relevant existing implementation first.

At minimum, check:
- current route/page/component involved
- current API/service involved
- current schema/model involved
- current store/context involved
- current tests covering the area
- any existing helper/util already performing part of the task

Do not create:
- duplicate API clients
- duplicate stores
- duplicate helpers
- duplicate schemas
- duplicate business logic paths

Prefer extending existing code over creating a second competing implementation.

---

## 6) High-Risk Areas Requiring Extra Care

The following areas are high risk and must be treated conservatively:

- payment initialization and verification
- Stripe and Paystack integrations
- webhooks and retry handling
- order totals and pricing math
- commission and payout calculations
- shipping costs and discounts
- currency conversion and currency display
- vendor onboarding and activation gating
- authentication and authorization
- role-protected routes
- admin approval flows
- product create/edit flows
- product images and uploads
- order lifecycle and fulfillment status changes

For changes in high-risk areas:
- make the smallest possible change
- avoid refactoring unrelated code
- preserve backward compatibility unless explicitly told otherwise
- add or update tests
- include manual QA notes if automated coverage is not sufficient

---

## 7) Currency Rules

Shopsoma supports NGN and USD.

Currency logic must be handled carefully across:
- products
- cart
- checkout
- orders
- receipts
- emails
- vendor reporting
- admin reporting
- payout-related calculations

Rules:
- do not assume all prices are NGN
- do not assume display currency equals stored transactional currency
- preserve original transactional values where needed
- do not silently convert stored order math unless explicitly required
- keep price formatting concerns separate from persisted financial calculations
- verify consistency between frontend display logic and backend calculation logic
- check product currency, subtotal, total, commission, and payout behavior together when working on pricing-related tasks

Any task involving monetary values must inspect all relevant layers before editing.

---

## 8) Payment and Webhook Rules

Payments are critical and must remain verifiable and idempotent.

Rules:
- never trust client-side payment success alone
- preserve server-side verification
- preserve webhook signature verification
- avoid duplicate order creation
- avoid duplicate payment recording
- avoid double fulfillment on webhook retries
- preserve payment metadata needed for reconciliation and debugging
- maintain safe behavior for retries, late webhooks, and partial failures

For payment-related work, always think through:
- initialization
- redirect/callback path
- verification path
- webhook path
- retry/duplicate event path
- failure path

Do not remove safeguards just to make local testing easier.

---

## 9) Order, Commission, and Payout Rules

Order and payout logic must remain mathematically consistent.

Rules:
- do not alter order totals casually
- do not recompute historical order values differently unless explicitly requested
- preserve snapshot-style order item data where the system already uses it
- keep commission math aligned with stored commission rates
- keep vendor payout math aligned with order item financial fields
- do not mix product display pricing logic with finalized order accounting logic

For any order-related change, verify:
- subtotal
- shipping
- discount
- tax
- total
- payment status
- fulfillment status
- vendor payout
- commission amount

---

## 10) Vendor Onboarding Rules

Vendor onboarding is stateful and must reflect backend truth.

Important patterns:
- onboarding completion is not just a UI concept
- onboarding-related access should be driven by backend state and persisted flags
- vendor activation, brand info completion, payout setup, and approval-related conditions must remain consistent

Rules:
- do not hardcode onboarding completion purely in the frontend
- do not bypass backend gating checks for convenience
- verify whether the expected behavior is:
  - block action
  - guide action
  - or allow action with warning
- when adjusting onboarding UX, inspect existing vendor fields, endpoints, and route guards first

---

## 11) Authentication and Authorization Rules

Roles and access boundaries matter.

Rules:
- do not trust frontend-only role checks
- backend must remain authoritative for protected actions
- do not widen admin access accidentally
- do not expose vendor-only or admin-only data to customers
- preserve route protection on the frontend and permission checks on the backend
- if changing auth/session behavior, inspect both frontend and backend paths

Always consider:
- customer
- vendor
- admin
- unauthenticated user

for any feature touching permissions.

---

## 12) Frontend / Backend Contract Rules

When an API contract changes:
- update backend request/response schemas first
- keep status codes explicit
- keep validation behavior explicit
- update frontend consumers in the same task
- update types/interfaces in the same task
- avoid silent field renames
- avoid returning inconsistent shapes for similar endpoints

If you must rename a field:
- update all known consumers
- update schema definitions
- update mapping utilities
- update tests

Do not leave half-migrated response shapes in the repo.

---

## 13) Database Change Rules

For any schema change:
- update the SQLAlchemy model(s)
- create or update the Alembic migration
- ensure existing data remains valid where possible
- prefer additive migrations over destructive changes
- call out any backfill requirement clearly
- avoid destructive column drops/renames unless explicitly requested
- preserve production safety

Rules:
- never change database schema in code without a migration
- never invent fields in handlers/services that do not exist in models and migrations
- do not bypass model/schema alignment
- do not manually patch DB logic in multiple places when a model change is the real fix

If data migration is needed, state:
- what existing rows need updating
- whether the migration is safe online
- whether deployment order matters

---

## 14) Service and Business Logic Rules

Business logic belongs in the right layer.

Rules:
- keep route handlers thin where possible
- keep domain logic in services or existing business-logic layers
- avoid embedding complex business rules directly in UI components
- do not scatter the same logic across multiple endpoints/pages
- prefer existing service patterns over creating ad hoc logic in handlers

Before creating a new service/helper:
- check whether one already exists
- check whether extending an existing one is simpler and safer

---

## 15) Frontend Implementation Rules

When editing frontend code:
- preserve existing routing patterns
- preserve existing layout patterns
- keep components focused and reusable
- do not create massive page components if smaller reusable parts already exist
- keep loading, empty, success, and error states explicit
- maintain accessibility where practical
- preserve mobile/responsive behavior unless the task explicitly changes layout
- keep state close to where it belongs unless shared state is clearly needed

If a Zustand store already owns the concern, do not introduce duplicate local/global state without strong reason.

---

## 16) Backend Implementation Rules

When editing backend code:
- keep FastAPI routes focused on IO and orchestration
- keep data validation in schemas where appropriate
- keep persistence aligned with SQLAlchemy models
- preserve async patterns
- handle exceptions deliberately
- do not swallow critical errors silently
- keep security-sensitive logic explicit

When changing endpoints:
- review auth requirements
- review response shape
- review transaction boundaries
- review rollback behavior
- review any background-job side effects

---

## 17) File and Scope Control

Unless explicitly requested, do not:
- rename files for style only
- move modules into a new architecture
- reformat unrelated files
- replace working libraries
- add large abstractions for small tasks
- “fix” unrelated lint issues outside the requested area
- change environment variable names casually
- widen CORS or auth rules casually

Keep diffs tight and intentional.

---

## 18) Configuration and Secrets

Rules:
- never commit real secrets
- use `.env.example` as the reference for expected variables
- do not hardcode credentials, API keys, or secrets
- do not hardcode production URLs in code unless that is already the established pattern and the task requires it
- preserve environment-based config behavior
- call out any new env variable explicitly

Be especially careful around:
- database URLs
- JWT secrets
- Stripe/Paystack keys
- webhook secrets
- S3/object storage credentials
- email provider keys

---

## 19) Testing Expectations

Testing is required for non-trivial changes.

### Frontend
When changing frontend behavior, add or update tests where appropriate.
Use the repo’s frontend testing setup and patterns.

Minimum expectations for meaningful frontend changes:
- validate core rendering behavior
- validate key interaction flow
- validate loading/error state if relevant
- validate route/guard behavior if relevant

### Backend
For backend changes, add or update pytest coverage where appropriate.

Minimum expectations for meaningful backend changes:
- success path
- validation/failure path
- permission path if roles matter
- edge case for business logic if relevant

### Manual QA
For:
- payment changes
- order changes
- currency changes
- onboarding changes
- admin workflow changes

include a short manual QA checklist even if automated tests are added.

Always state:
- what was tested
- what was not tested
- exact commands to run

---

## 20) Commands and Development Expectations

### Frontend
Run from `shopsoma-frontend/`:
- `npm install`
- `npm run dev`
- `npm run build`
- `npm run lint`
- `npm test`

### Backend
Run from `shopsoma-backend/`:
- `python3 -m venv venv && source venv/bin/activate`
- `pip install -r requirements.txt`
- `uvicorn app.main:app --reload`
- `pytest`
- `pytest --cov=app tests/`
- `black app/ tests/`
- `ruff check app/ tests/`
- `alembic upgrade head`

### Docker
Where relevant, use local Docker services for:
- PostgreSQL
- Redis
- backend
- Celery worker
- Celery beat

Do not claim something is tested if it was not actually run.

If execution is not possible in the current environment, say so clearly.

---

## 21) Pull Request and Commit Expectations

Use conventional commits such as:
- `feat:`
- `fix:`
- `docs:`
- `refactor:`
- `test:`
- `chore:`
- `perf:`
- `debug:`

PRs should include:
- a short summary of what changed
- why the change was needed
- testing notes
- screenshots for UI changes where relevant
- migration notes if schema changed
- new env vars if added
- rollout considerations if applicable

---

## 22) Git Operations

Default rule:
- use normal git CLI workflow for branches, commits, pushes, merges, and rebases unless explicitly instructed otherwise

Do not create unnecessary branches or rewrite history casually.
Do not mix multiple unrelated fixes in one changeset.

---

## 23) What To Look At First by Task Type

### If the task is about vendor dashboard
Inspect first:
- vendor pages in frontend
- relevant vendor components
- vendor stores/context if applicable
- backend vendor endpoints
- vendor model fields related to state or gating

### If the task is about pricing or currency
Inspect first:
- frontend currency store
- price formatting helpers
- product model currency field
- cart and checkout logic
- order creation logic
- receipt/email rendering
- any vendor/admin reporting surfaces involved

### If the task is about onboarding
Inspect first:
- vendor onboarding pages
- route guards/layout behavior
- vendor-related backend endpoints
- persisted vendor onboarding fields
- dashboard behavior for incomplete accounts

### If the task is about payments
Inspect first:
- payment initialization endpoint(s)
- checkout page flow
- verification endpoint(s)
- webhook handlers
- order/payment persistence logic
- any related email/order-success flows

### If the task is about admin operations
Inspect first:
- protected admin routes/pages
- backend admin endpoints
- role enforcement
- audit-relevant fields
- side effects such as approval, payout, or moderation state

---

## 24) Shopsoma-Specific Warnings

- Do not assume all products or orders are NGN-only.
- Do not bypass backend onboarding or approval truth with frontend-only logic.
- Do not weaken payment verification.
- Do not widen CORS or role permissions without explicit instruction.
- Do not introduce duplicate state when a Zustand store or backend field already owns the concern.
- Do not mix display formatting logic with persisted accounting logic.
- Do not create alternate versions of the same endpoint/service just to ship faster.
- Do not silently change financial behavior in historical orders.
- Do not use mock data in real flows unless explicitly requested for development-only purposes.

---

## 25) Expected Response Format for Agent Work

When completing a task, structure your response like this:

1. Task understanding
2. Acceptance criteria
3. Files inspected
4. Implementation plan
5. Code changes
6. Tests added or updated
7. Manual QA steps
8. Risks or follow-up notes

Keep it concise but explicit.

---

## 26) Definition of Done

A task is not done unless:
- the requested behavior is implemented
- the change is scoped correctly
- related contracts are kept consistent
- tests are added or updated where appropriate
- manual QA notes are provided for sensitive flows
- migrations are included for schema changes
- new env vars are documented
- no unrelated refactor has been bundled into the task

---

## 27) Final Rule

Your job is not to impress with clever rewrites.

Your job is to make safe, correct, production-appropriate changes that fit Shopsoma’s existing architecture and do not break nearby commerce flows.

### Product Moderation Visibility Rule
Customer-facing product queries and detail access must never expose unapproved vendor products.
A product is only customer-visible when it satisfies the platform’s approved/public conditions.
Vendor and admin views may access pending products according to role, but customer flows must remain moderation-safe.

## Shopsoma Development Workflow

Shopsoma changes follow a local-first workflow:

1. Implement and test locally first
2. Verify the affected flow manually on the local environment
3. Run relevant automated tests locally where applicable
4. Push only after local verification passes
5. Deploy to the staging branch/environment for live testing
6. Validate the full user flow in staging before considering the task complete

Agents must optimize for this workflow:
- prefer changes that are easy to verify locally
- provide exact local run commands
- provide a staging QA checklist for any meaningful feature or bug fix
- clearly separate “locally verified” from “needs staging verification”

## Required QA Format

For every meaningful Shopsoma task, provide QA in this order:
- Local setup or run commands
- Local test steps
- Expected local result
- Staging test steps
- Expected staging result
- Regression checks

## Field Default, Validation, and Multi-Flow Safety

When changing any form field default, fallback, auto-fill behavior, derived value, or clearing behavior, you must inspect every place that depends on that field before completing the task.

Always review:
- state initialization
- controlled input behavior
- useEffect/defaulting logic
- validation logic
- submit handler conditions
- payload construction
- edit-mode hydration
- display/resolution helpers

If the page supports multiple workflows or modes (for example: single product vs variable product), validation must be scoped to the correct flow.
Do not require a field globally if it is only relevant to one mode.

A form-related task is not complete until you verify:
- the original bug is fixed
- no sibling flow is broken
- no new hidden submission blocker has been introduced
- create and edit flows still work as expected

## Debug Before Generalizing

When a bug appears on one surface but not another, do not immediately extract or broaden a shared fix.

First inspect the exact runtime data for the broken surface and confirm:
- the actual object shape
- the exact field path used at render time
- why the working surface succeeds
- why the broken surface fails

Only after confirming the real runtime difference should shared logic be introduced or updated.

Do not mark image/data rendering fixes complete until both:
- the originally broken item is verified
- one previously working item is rechecked for regression

## No Shared Refactor Without Runtime Proof

Do not convert a local fix into shared utility logic unless the runtime data shape has been verified across all affected surfaces.

## Surface Consistency Rule

When fixing data rendering bugs across multiple UI surfaces, do not assume a fix in one surface applies everywhere.
Explicitly verify all independent render paths, including:
- cards/lists
- detail pages
- dashboards
- featured/spotlight sections
- hover states
- gallery/selected-image state

Do not mark image/data rendering work complete until each surface is checked for its own render path.