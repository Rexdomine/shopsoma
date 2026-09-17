# Progress — Admin Account Lifecycle Controls

## 2026-09-17 — Setup
- User approved the phased lifecycle plan and authorized implementation of PR 1 only.
- Fetched `origin`; confirmed PR #151 is merged and `origin/develop` is `ab1ac34c5d563139171fa123a43ab8ad8d5b6d38`.
- Created isolated worktree:
  - Path: `/opt/data/projects/shopsoma-worktrees/admin-account-lifecycle-controls`
  - Branch: `feat/admin-account-lifecycle-controls`
  - Base: `origin/develop`
- Inspected existing account status/delete endpoints, `User`/`Vendor` models, vendor list response, and relationship constraints.
- Attempted `hermes-plan-bootstrap --title "Build Admin Account Lifecycle Controls"`; it failed because the command is not installed. Created `task_plan.md`, `findings.md`, and `progress.md` directly instead.

- Added RED regression `test_deactivating_vendor_hides_products_from_public_catalog`; it failed as expected because a deactivated vendor's product was still returned by `/api/v1/products`.
- Implemented the first public-sellability enforcement in `app/api/v1/products.py`: public list/detail now require approved, completed-onboarding, active/non-deleted store and active vendor account.
- Re-ran the regression GREEN: passed.
- Added RED regression `test_deactivating_user_writes_lifecycle_audit_event`; it failed as expected because no audit event was persisted.
- Implemented transactionally coupled `AuditLog` creation in `PUT /admin/users/{user_id}/status` with actor, target, activation action, and old/new active state.
- Re-ran `tests/test_vendor_account_lifecycle.py -q`: 2 passed.

- Added RED regression for bulk deactivation; initial route design conflicted with the existing dynamic user-update route and returned `422`. Moved the endpoint to unambiguous `PUT /admin/users/status/bulk`, then verified GREEN.
- Added a distinct RED regression proving duplicate IDs must be rejected before mutation; it failed (`200`) before the duplicate preflight was added, then passed after the minimal guard.

- Added RED/GREEN preflight regressions for a batch containing a missing ID (initially raised `KeyError`) and a batch containing the acting admin (initially returned `200`). Both now fail closed without mutations.

- Added RED/GREEN public-designer discovery regression; `/api/v1/designers` now applies the same account/store/onboarding eligibility rule instead of exposing merely approved vendors.

- Added reusable `app/services/vendor_visibility.py` customer-sellability predicate and applied it to public products, cart add, order review, and order creation.
- RED/GREEN regressions now prove a deactivated vendor’s product is rejected by direct cart submission, checkout review, and final order creation; focused safety suite currently has 10 passing regressions across lifecycle/public/cart/checkout paths.

- Added RED/GREEN seller-eligibility regressions for wishlist read/add, stale-cart read and quantity update, plus pre-payment checkout-estimate creation after a vendor account deactivation.
- Applied the shared customer-sellability predicate to wishlist read/add and cart read; cart quantity updates now revalidate the stored product before mutation. Checkout-estimate creation revalidates seller eligibility before authorization and again after its commit/reload boundary, before estimate work.
- UI TDD: added Admin Users regression proving a failed bulk deactivation retains selection, emits accessible error feedback, and prevents selection of the acting admin. Fixed the observed unhandled-rejection/self-selection defects; applied the same guarded error/selection flow to Admin Vendors.
- Backend safety suite now includes wishlist, stale cart mutation/read, and checkout-estimate seller revalidation; all focused checks are green.
- Surrounding backend Admin/vendor/onboarding regression set: 9 passed.
- Full frontend suite: 140 passed, 1 failed in untouched `src/pages/checkout/Checkout.test.tsx` guest Paystack capability session-storage assertion; implementation-specific frontend tests and production build pass. Treat this as a baseline gate pending independent diagnosis, not as lifecycle evidence.
- Published commit `857e6f119fd8a3833a2be980999e35e108877afa` on `feat/admin-account-lifecycle-controls` and opened PR #152 against `develop`: https://github.com/Rexdomine/shopsoma/pull/152.
- Requested exact-head Codex review with `@codex review`. Hosted checks were queued/in progress at publication; no merge, deployment, or production/staging data mutation occurred.
- Adversarial UI review follow-up: added explicit vendor account-state labels, acting-admin protection and duplicate-submit locking for individual vendor status actions, accessible API-detail errors, and current-result-set selection scoping. Focused frontend lifecycle tests: 4 passed; build passed. The full focused backend matrix: 50 passed.
