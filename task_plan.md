# Build admin product image management

## Goal
Open a fresh PR to `develop` that lets an authenticated admin manage a product’s existing vendor-uploaded gallery: add images, delete images, choose the primary image, and set image ordering. Rex alone merges; no deployment, staging/production data changes, or automatic merge.

## Classification
HEAVY: role-protected product/media persistence with browser upload → API → database → storage boundaries.

## Current Phase
in_progress — internal whole-PR hardening audit before one final Codex re-review.

## Next Step
Complete the frozen-candidate backend and frontend/cross-layer audits, consolidate only verified defects into a single remediation matrix, then add RED→GREEN regressions before making one bounded update.

## Milestones
1. **Preflight/discovery** — complete: established existing upload endpoint/service, admin authorization boundary, image invariants, and regression surfaces.
2. **Implementation and prior review remediation** — complete: admin image lifecycle, durable storage-key persistence/cleanup, and checkout gate removal are committed on the PR branch.
3. **Whole-PR internal invariant audit** — complete: independently verified material storage-key ownership, cleanup recovery, and frontend state-truth gaps; checkout minimum-gate removal remains internally consistent.
4. **Consolidated RED→GREEN remediation** — in_progress: first write regressions for verified findings, then minimally fix storage-key ownership/duplicate protection, cleanup recovery, primary-control semantics, and post-mutation refresh truth; rerun the complete focused matrix against isolated PostgreSQL.
5. **Independent confirmation and PR closeout** — pending: NightWing confirmation on the final public head, then one exact-SHA Codex request and CI reconciliation; Rex alone merges.

## Acceptance criteria
- Admin can view every product image, including an empty gallery state.
- Admin can upload one or more valid images through the existing storage/upload mechanism.
- Admin can delete an image with explicit confirmation; a failed deletion leaves UI/server state truthful.
- Admin can set exactly one image primary and reorder images deterministically.
- Product primary/order semantics remain compatible with customer gallery, cards, cart/order image selection, and vendor image flows.
- Backend authorizes admins server-side; vendors retain their current ownership-limited image routes.
- Invalid IDs, cross-product image IDs, storage/upload failure, concurrent gallery changes, and image cap behavior fail closed.
- Fresh PR targets `develop`; no merge/deploy/staging/production writes.

## Stateful preflight
- **Browser → API:** authenticated admin identity is server-authoritative; browser supplies product/image IDs, image URL/data from existing upload mechanism, intended primary/order.
- **API → storage:** existing uploader must complete before image URL persistence; failed upload must not create a dangling ProductImage row.
- **API → DB:** ProductImage rows are ordered by `display_order`; primary must remain deterministic and product-scoped. Mutations must not target another product.
- **Image lifecycle:** uploaded → persisted gallery image; primary/order mutable; deletion terminal for the DB row. Storage object deletion policy must follow existing product-image behavior.
- **Parity:** vendor and admin image routes share model/schema semantics but differ in authorization; public image readers rely on primary/fallback ordering.

## Constraints
- Use existing services/routes/components where possible; no new production dependency without approval.
- Preserve normal product category, Shop Edits, moderation, vendor ownership, and public approval visibility behavior.
- Drax implements one bounded milestone; NightWing is read-only independent QA.

## Follow-up: remove the checkout minimum-order gate

### Scope
Remove only the universal NGN 60,000 gate from the current PR. Customers must be able to continue from Cart and create/review a positive valid order below that value. No payment, provider, inventory, pricing, discount, tax, or shipping-rate policy is changed.

### Boundary map and invariants
- Cart browser → checkout navigation: no universal client-side amount gate.
- Review API and order-create API: no universal global minimum; server-owned product pricing, nonempty-cart, stock, and manual-pricing checks remain.
- Shipping: configured `min_order_value` and `max_order_value` eligibility remains a separate rule.
- Payment/provider, reservation, webhook, idempotency, and durable order state behavior remain unchanged.

### Acceptance and verification
- A valid NGN 50,000 order succeeds through both `/orders/review` and `/orders`.
- Static regression also confirms no retired identifier/message or Cart preflight remains.
- Run focused checkout test, adjacent shipping suite, frontend production build, Python compile, and whitespace check on isolated PostgreSQL.
- Independent NightWing must review the final verified state before commit/push. Rex alone merges; no deploy.