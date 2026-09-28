# DHL shipment operations

Scope: the existing protected admin order page now consumes a read-only `dhl_operations` projection and the existing booking, binary label, handoff and tracking contracts. No migration or new configuration. No merge, deployment or production DHL activation is included.

The projection reads explicit safe columns in one PostgreSQL statement snapshot. It never calls the provider, acquires booking locks or mutates claims. Booking history is independent of current ready packages. Missing/ambiguous bindings, cancellation, handed-off custody, active bookings and inconsistent/uncertain records fail closed. Eligibility does not guarantee provider availability; existing write gates remain authoritative.

DHL pickup booking is unavailable. `app/services/dhl/shipments.py` sends `pickup.isRequested=False`; generic vendor pickup scheduling is a separate operation.

## Operating notes

- Select a ready hub package explicitly when there are multiple; source intent, seal, version and hub only from backend facts.
- Select a persisted booking to download its label, record actual hub-to-DHL handoff, or refresh tracking. Label creation does not establish collection. Handoff requires verified collection tracking and valid custody, enforced by the existing service.
- Mutations require confirmation. Requests retain a single caller idempotency key; no timeout retry is automated.
- A local unresolved-command marker is written before mutations. An ambiguous outcome blocks further mutations even after reload or empty read results. Only the confirmed response plus successful backend refresh clears the marker automatically. No shipment/evidence payload is stored in browser storage. Server guards remain authoritative across browsers and racing administrators.
- A persisted unknown or expired pending claim requires authorized review/recovery. GET does not transition it. The panel does not add reconciliation/recovery commands or a local lock-reset button. A local marker left by an ambiguous request requires separately authorized operational resolution; reloading or clearing storage is not evidence of provider absence.
- Handoff counterparty/evidence remain transient form values sent to the protected endpoint, never logged by this component. Errors use fixed messages instead of provider exceptions.

## Verification recorded locally

- TDD before implementation: 6 failures (five missing services plus missing panel), 1 existing test passed. The initial duplicate `--run` CLI invocation was corrected and is not red evidence.
- Focused frontend suite: 16 passing tests (five service, eleven order page). Includes exact multi-package command, confirmation/cancellation, duplicate click, success, unknown/timeout reload, binary label, handoff privacy, tracking, storage failure and cancelled-order behavior.
- Isolated projection tests: 26 passing using `--noconftest`; these exercise the projector and compiled SQL without PostgreSQL or application fixtures. Two warnings reflect the incomplete pytest-asyncio installation.
- Frontend build passed after correcting test-query typing. Full frontend lint: zero errors, 290 warnings. New component/tests focused lint passed.
- Full backend requirements could not install because of disk capacity. The full DHL suite stopped in collection (`jwt` missing); isolated existing static contracts also stopped in collection (`email_validator` missing). These suites are NOT passes.
- Admin route integration assertions added, not yet executed. No rendered-browser QA, screenshots, provider calls or staging checks completed. Paperclip reported `currentExecutionWorkspace: null`, so no managed preview runtime was available.

## Required QA continuation

1. Local setup/run commands:
   - Frontend: `npm ci`; `npm test -- src/services/__tests__/adminDhlOperations.test.ts src/pages/admin/AdminOrderDetail.test.tsx`; `npm run lint`; `npm run build`.
   - Backend, in an isolated complete environment: `pip install -r requirements.txt`; `pytest tests/test_admin_orders.py tests/test_dhl_operations.py tests/test_dhl_phase4_booking.py tests/test_dhl_phase4_static_contracts.py` with synthetic PostgreSQL configuration.
   - The recorded isolated unit command was `.venv/bin/python -m pytest --noconftest tests/test_dhl_operations.py -q` with a synthetic local database URL and test secret. It makes no database connection.
   - Provision a Paperclip-managed runtime for this exact branch/worktree before browser QA; run frontend Vite and the backend with approved synthetic fixtures through those runtime controls.
2. Local steps: test zero/one/multiple packages, missing seal/intent/quote, retired/invalidated bindings, old booking history after handoff, live/expired pending, unknown, reconciled success/failure, cancelled orders and guard inconsistencies. In two admin sessions test duplicate booking and timeout/reload. Download binary label, validate/submit private handoff, and refresh tracking. Verify customer/vendor/anonymous denial and cross-order isolation.
3. Expected local result: exact backend bindings, all unsafe retries blocked, no private fields/label bytes in detail JSON, zero GET writes/provider calls, no N+1 queries, fixed messages and accurate refreshed states. Capture actual rendered screenshots and network evidence using synthetic data.
4. Staging steps: after Rex merges and an authorized staging deployment, repeat the browser matrix with the approved DHL sandbox cohort only. No production activation.
5. Expected staging result: same persisted state, permissions, privacy, idempotency and unavailable-pickup behavior.
6. Regression checks: order currency/accounting, generic pickup scheduling, shadow quotes, role guards, handoff custody chain, label authorization, existing booking concurrency/idempotency tests. NightWing independently verifies through the existing dependent QA issue; StarLord coordinates Product preview and review.

PR must target `develop`; request Codex review and record CI/mergeability after managed GitHub access is restored. Only Rex merges. This document is a partial verification handoff, not completion or QA certification.
