# Findings — Admin Account Lifecycle Controls

## User-approved direction
- Deliver PR 1 now: reversible user/vendor lifecycle controls and bulk reversible actions.
- After review and Rex-authorized merge, proceed to PR 2 (test-data classification/complete purge), then PR 3 (guarded real-account erasure/anonymization).
- Vendor deactivation must remove products from public visibility and prevent new sales while preserving historical business records.

## Baseline discovered before implementation
- `User.is_active` already exists and authentication dependencies reject inactive users.
- `Vendor` has `store_active`, `store_paused_at`, and `store_deleted_at`; these must not be conflated with account deactivation.
- `app/api/v1/admin.py` already contains a single-user status endpoint and an unsafe generic hard-delete endpoint.
- `AdminUsers.tsx` currently exposes single-user status/delete affordances; Admin Vendors has no equivalent complete lifecycle/bulk workflow.
- The current hard-delete path removes customer order/payment/return rows and cascades a vendor’s catalog; it is unsuitable as normal production lifecycle behavior.
- Some vendor-owned rows have `RESTRICT` relations (notably payment/pickup-related paths), confirming deletion cannot be assumed complete or safe without a dedicated purge design.
- Public discovery originally applied seller/store filters inconsistently. This PR now centralizes product/customer sellability (product active + moderation-approved; vendor approved, completed onboarding, active/non-deleted store; linked vendor user active) and applies it to product list/detail, designers, cart add, checkout review/creation, and wishlist read/add. Stale cart quantity/read/guest-merge and checkout-estimate boundaries remain to be assessed before PR closure.
- `Vendor` already supports vendor-initiated pause/activate and soft store deletion. Admin account deactivation must remain distinct from those states: it changes `User.is_active` and must not mutate store fields, while all public/new-sale eligibility must require both account and store eligibility.
- `AuditLog` supports actor user ID, action, target entity ID/type, old/new JSON values, timestamp, IP and user agent. It is currently not written by lifecycle endpoints and can be used without a new schema migration for PR 1.
- Existing backend tests use async API fixtures and an isolated PostgreSQL database; `test_admin_delete_user.py` documents the unsafe current hard-delete behavior and must be superseded for PR 1 scope rather than expanded.

## Safety boundaries
- This PR performs no destructive account or product deletion.
- No test/seed data, Render configuration, external provider data, or real user data will be modified.
- Any bulk mutation must have a full request preflight and explicit per-target result.
