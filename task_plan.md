# Admin Account Lifecycle Controls Implementation Plan

> **For Hermes:** Use TDD for each behavioral change; this PR intentionally excludes test-data purge and real-account erasure.

**Goal:** Deliver reversible, audited admin lifecycle controls for users and vendors, with server-side enforcement that deactivated vendors cannot sell or appear publicly.

**Architecture:** Add a single backend lifecycle service and explicit admin endpoints for account and storefront state transitions. Public catalog and checkout paths will consume a shared sellability predicate so deactivation cannot be bypassed by stale UI state. Admin UI adds per-record and bulk reversible operations with per-target results.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, React/TypeScript/Vite, pytest, Vitest.

---

## Current Phase
in_progress — commit and PR publication

## Next Step
Commit the validated reversible lifecycle changes, publish the branch, and open a focused PR against `develop` without merge/deployment.

## Phases
1. complete — Create isolated feature worktree from merged `origin/develop` (`ab1ac34c`).
2. in_progress — Map existing state, public/checkout boundaries, audit model, and test conventions.
3. pending — RED/GREEN backend lifecycle service and explicit single/bulk admin contracts.
4. pending — RED/GREEN enforcement for public discovery, cart, and checkout.
5. pending — RED/GREEN Admin Users/Vendors lifecycle and bulk-action UI.
6. pending — Focused regression matrix, production build, review, PR, and hosted validation.

## Invariants
- Deactivating a vendor account is reversible and preserves catalog, orders, payouts, fulfillment, and audit history.
- A deactivated vendor cannot authenticate for new work, appear in public discovery, or receive a new order, including from a stale cart/direct API call.
- Reversing deactivation does not override KYC, store-deleted, onboarding, or compliance states.
- Every admin lifecycle transition stores actor, target, action, previous/new state, timestamp, and reason.
- Bulk lifecycle changes are two-phase: validate all structural/authorization inputs first; then return an explicit result for every selected ID. Permanent deletion is excluded.
- Admins cannot deactivate themselves; no endpoint exposes an unsafe generic hard delete as a normal lifecycle operation.

## Scope Boundary
Included: vendor/user deactivate/reactivate, vendor store close/reopen where existing semantics apply, audit event, safe public/checkout enforcement, Admin UI and reversible bulk actions.

Excluded: test-data marker, full data purge, media-cleanup outbox, real-user anonymization/erasure; those are PRs 2 and 3.

## Decisions
- Start from current `origin/develop`, not the old PR branch; PR #151 is merged.
- Base branch is `develop`; Rex alone merges.
- No deployment, production/staging data mutation, auto-merge, or direct base-branch push.

## Errors
- `hermes-plan-bootstrap` is unavailable on this host (`command not found`); continuity files were created manually instead.
