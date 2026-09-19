# DHL sandbox / shadow UAT preflight

Date: 2026-09-01
Lane: `/opt/data/projects/shopsoma-worktrees/dhl-sandbox-shadow-uat`
Base: `origin/develop`

## Objective
Implement the smallest safe **Phase 2C shadow, non-payment quote UAT** slice for ShopSoma DHL domestic sandbox.

## Frozen scope
Build a **staff-only/admin-triggered** DHL sandbox shadow quote path on top of the already-merged domestic rating persistence and capability gates.

This slice must:
- exercise sandbox-only DHL domestic rating for explicitly allowlisted sandbox cohorts;
- persist normalized, redacted evidence using the existing domestic rate / customer quote aggregates;
- keep customer checkout closed;
- avoid booking, label, pickup, movement, payment, or production-carrier exposure.

## Non-goals
- No customer-facing checkout activation.
- No payment-bearing traffic.
- No DHL booking, label creation, pickup scheduling, handoff, tracking, or returns.
- No production environment carrier calls.
- No new parallel admin tool/dashboard when the existing admin order detail surface can host the action.

## Boundary map
- Admin UI -> admin order API: trusted operator initiates a shadow quote run for one order/cohort.
- Admin order API -> DB: verifies order/cohort eligibility, identity, and immutable subject prerequisites.
- API/service -> DHL adapter: allowed only when workflow + provider-call gates are enabled, environment is sandbox, credentials exist, and the cohort is allowlisted.
- API/service -> normalized rate/customer quote persistence: store sanitized authoritative evidence only; never raw credentials or public PII.
- API -> admin UI: return redacted quote outcome/evidence summary suitable for operators only.

## Critical invariants
1. Customer checkout remains closed throughout Phases 2A-4.
2. Provider calls fail closed unless all existing sandbox gates pass.
3. Provider calls are sandbox-only; production must still fail closed.
4. The action is staff-only and attached to existing admin order surfaces.
5. The quote subject must be derived from existing authoritative package / intent / destination state, not ad-hoc client payload.
6. Evidence remains sanitized and persisted in existing normalized aggregates; no raw payload/credentials leak into API/UI.
7. No booking/movement side effects are introduced by the shadow quote path.
8. Idempotent re-run/replay behavior must preserve existing immutable evidence rules and avoid duplicate unsafe side effects.

## Acceptance criteria
- Admin can trigger a shadow quote from the existing admin order detail workflow.
- Non-admin callers are rejected.
- Ineligible orders/cohorts fail closed with clear operator-safe errors.
- When provider calls are disabled or sandbox requirements are not met, the path fails closed without transport.
- A successful sandbox quote persists normalized evidence and produces a redacted operator-facing summary.
- Repeated shadow runs follow the existing idempotency/immutability contracts rather than mutating prior evidence in place.
- Frontend shows a restricted operator control and the resulting redacted quote state/evidence summary.
- Tests cover: admin auth, fail-closed gating, successful sandbox run, and no customer-checkout exposure.

## Likely insertion points
Backend:
- `shopsoma-backend/app/api/v1/admin_orders.py`
- `shopsoma-backend/app/services/dhl/rating.py`
- existing quote/rate models + schemas
- backend tests around admin orders and DHL domestic rating

Frontend:
- `shopsoma-frontend/src/pages/admin/AdminOrderDetail.tsx`
- `shopsoma-frontend/src/services/adminOrderService.ts`

## Immediate next step
Implement the admin-triggered shadow quote vertical slice using existing admin order detail surfaces and current normalized DHL persistence models.
