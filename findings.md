# Findings — admin product image management

## User request
Admins need product-gallery controls on the admin product edit page: upload additional images, delete images, select a primary image, and reorder the remaining images. A new PR must target `develop`; Rex merges after staging testing.

## Existing implementation
- `AdminProductEdit.tsx:364-395` renders an image gallery as read-only and explicitly directs admins to vendors.
- `Product.images` is ordered by `ProductImage.display_order` (`app/models/product.py:154-159`). Public readers generally use `is_primary`, then fall back to the first ordered image.
- Existing vendor routes in `app/api/v1/products.py` provide image creation/deletion but use `get_completed_vendor` and ownership checks; they cannot be reused unchanged for admins.
- `ProductImageUpdate` already defines `display_order` and `is_primary`, but no inspected image update route exists yet.
- Existing create/delete image writes call `mark_product_content_pending`, so image mutation can affect moderation state. This must be preserved deliberately and tested.

## Boundary/invariant ledger
- Admin authorization must be server-side (`get_current_admin`), never inferred from frontend routing.
- Every image mutation is product-scoped; an image ID belonging to another product must reject/404.
- Primary selection must leave exactly one primary image when images remain. Reordering must produce stable non-negative order without relying on UI index alone.
- Upload result storage must succeed before a ProductImage row is persisted. The existing uploader/storage service is the canonical boundary to reuse.
- Image deletion must not silently create a stale primary/fallback state.
- Vendor routes and new admin routes must preserve their distinct authorization contracts while yielding compatible ProductImage data.

## Existing upload and test seams
- Frontend `productService.uploadImage()` and `uploadImages()` use `/images/upload` and `/images/upload/batch`; this is the existing storage path to reuse, not a new uploader.
- Existing vendor product-image routes provide add/delete but no update/reorder endpoint. Their ownership guard cannot be used for admins.
- `ProductImageUpdate` already supports `display_order` and `is_primary`, allowing a focused admin image-update/reorder contract rather than a migration.
- Existing backend coverage is concentrated in `tests/test_products.py::TestProductImages`; frontend admin page coverage is in `AdminProductActions.test.tsx`.

## Evidence limits
No staging/production write or privileged admin session is authorized for discovery. Browser QA will use local/mock or dedicated test fixtures and must not leave production data behind.

## Internal hardening strategy — 2026-09-25
- The automatic closeout cron is paused while this whole-PR audit runs; no further Codex request may occur until one consolidated internally reviewed candidate is pushed.
- Canonical candidate at audit start: `e91dd4a5a265f1bc4c1bfc299c0f12aba5098f07`, branch and remote aligned, clean worktree.
- Audit is two independent lanes: (1) backend storage/DB/authorization/order invariants, and (2) frontend/API-contract/cross-layer parity.
- Any validated gap must first have a focused failing regression, then a minimal fix, then be included in the final exact-head focused verification matrix.
- After the two independent audits, the checkout removal remains internally consistent: the retired universal gate is absent from Cart, review, and create; shipping-rate-specific eligibility remains intentionally separate.
- **Verified blocker: storage ownership/reuse.** Vendor association only rejects a repeated key within the same product, allowing a shared object key to be attached to a second product and later deleted by either lifecycle. Admin JSON creation accepts caller-provided `storage_keys`, allowing arbitrary/reused objects to enter the cleanup path. The remediation must prohibit admin caller-supplied keys and enforce a single globally owned key association through the vendor/legacy path, with a concurrency-safe persistence design.
- **Verified blocker: recovery gap.** `product_image_storage_cleanups` durably records failed keys but has no consumer/reconciler. The remediation needs an idempotent claimed retry path, explicit resolution semantics, and a scheduled/operational invocation consistent with existing worker patterns. Merely persisting a row is not recovery.
- **Verified UX defects.** The UI offers reorder controls on the primary image even though the API pins primary at index zero, and update/delete report the mutation as failed if only the read-after-write refresh fails. The UI must either prevent that invalid reorder action and distinguish saved-versus-refresh-pending state, or implement a different coherent primary/order contract.
- **Risk accepted as deliberately safe legacy behavior:** URL guessing is not permitted for rows predating `storage_keys`; legacy rows cannot be automatically deleted from storage without authoritative keys. This must be documented/reconciled rather than guessed.

## Variant cleanup remediation
- `ImageService` upload results now carry private `_storage_keys` metadata containing the original plus every generated variant key for both local and S3/R2 storage; public URL/result fields remain unchanged.
- Admin upload compensation consumes that explicit list, retains a narrow legacy fallback for older mocked results, and logs cleanup failures without replacing the original persistence exception.
- Added regression coverage for DB-commit failure cleanup and direct local-storage metadata coverage. Backend integration execution remains blocked by the unavailable isolated PostgreSQL listener.

## NightWing remediation evidence
- Added `POST /admin/products/{product_id}/images/upload`; it uses `get_current_admin`, validates product existence and the ten-image cap before calling `image_service`, persists `ProductImage`, marks content pending, and compensates uploaded storage keys if persistence fails.
- The frontend now uses `adminService.uploadProductImage(productId, file)` directly; vendor-only `/images/upload` remains unchanged.
- Frontend focused test: `AdminProductEdit.images.test.tsx` — 2 passed.
- Backend focused integration tests were added but could not collect because the configured PostgreSQL test bootstrap could not connect to `localhost:5432` (connection refused). Python compilation and `git diff --check` passed.
- TypeScript check was attempted and exited 1 without diagnostics; rerun in a fully configured frontend environment before merge.
## Storage lifecycle blocker remediation
- Added nullable PostgreSQL JSONB `product_images.storage_keys` plus Alembic migration `r7s8t9u0v1w2_add_product_image_storage_keys.py`.
- Admin server-owned uploads persist the complete private `_storage_keys` set (original and every generated variant); the response schema does not expose it.
- Admin deletion copies exact keys before commit, commits row deletion first, then calls `image_service.delete_images`. Post-commit physical deletion errors are logged with product/image/key diagnostics and do not restore or retry the DB row.
- Legacy/vendor rows with NULL `storage_keys` are deleted from the database without URL guessing or prefix deletion; their historical storage objects remain a known safe limitation.
- Added regressions for exact key persistence, exact post-commit deletion, and storage failure leaving the row deleted.
