# ShopSoma — Payment Bridge Canonical Gate Stabilization

Last verified: 2026-08-15
Branch: `fix/payment-bridge-canonical-gate-stabilization`
Parent: `95c62c46d8e9519c7ccc20340c7d3dc5a3a53527`

## Milestone 3 closure checkpoint

The recovered Milestone 3 implementation now covers the order-first domestic checkout prerequisite path: persisted static estimate/options, explicit selection, server-owned totals, complete stock-managed/made-to-order coverage, non-decrementing stock reservations, and order-bound guest capabilities stored only as versioned HMAC digests. The false-default gate leaves ordinary orders on `legacy_pre_bridge` behavior.

Production boundaries remain inert for enforced orders: no Payment, VendorPickup, VendorNotification, email/provider/DHL call, fulfilment action, or physical stock decrement occurs before the prerequisite branch returns.

## Verified gates

- `tests/test_checkout_estimate_api.py`: 9 passed.
- M2 preservation selection (checkout prerequisite migration/models; stock payment persistence/coordinator/blockers; orders/admin deletion; guest capability): 107 passed.
- Black check, Flake8 fatal selections `E9,F63,F7,F82`, compileall, and `git diff --check`: passed on all changed Python paths.
- Final scope/path and redacted secret/plaintext scans are required immediately before the single local child commit.

## Safety boundary

Do not push, mutate a PR, merge, deploy, run a production migration, call a carrier/provider, perform a DHL action, or activate any feature without Rex's explicit approval. Canonical sequence remains 2A-3D followed by 2A-4A; do not infer macro-phase jumps.
