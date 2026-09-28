# PR #204 image ownership verification

Scope: bind variation galleries to their product, bind vendor image association to a server-issued upload, correct the obsolete reset preflight assertion, preserve products created outside the reset snapshot, reconcile failed upload identities, and normalize admin editor preview URLs. PR targets `develop`; merge and deployment remain reviewer decisions.

## Local setup or run commands

From `shopsoma-backend/`, use Python with `requirements.txt` installed and a disposable PostgreSQL instance. Set `DATABASE_URL` and a local test `SECRET_KEY`; fixtures create and drop a process-specific database. Do not point tests at production.

```sh
python -m pytest tests/test_product_image_ownership.py tests/test_stock_payment_lock_coordinator.py tests/test_storage_key_consolidation_red.py tests/test_admin_product_images.py tests/test_admin_product_edit_boundaries.py tests/test_images.py tests/test_products.py tests/test_bulk_product_images.py -q
alembic heads
ruff check app/api/v1/admin.py app/api/v1/images.py app/api/v1/products.py app/models/product.py app/services/product_image_storage.py tests/test_product_image_ownership.py --select E9,F63,F7,F82
```

For the upload-reconciliation/editor follow-up, run:

```sh
# shopsoma-backend/
python -m pytest tests/test_product_image_ownership.py tests/test_admin_product_images.py tests/test_images.py -q
# shopsoma-frontend/
npm ci --no-audit --no-fund
npm test -- src/pages/admin/AdminProductEdit.images.test.tsx src/utils/productImages.test.ts --maxWorkers=1 --minWorkers=1
npx tsc -b
```

For a local browser preview, apply migrations to a disposable application database, run `uvicorn app.main:app --reload`, and run `npm run dev` from `shopsoma-frontend/` with the API base URL configured for that backend. Use synthetic vendor, admin and customer accounts. This change does not provide rendered-browser evidence.

## Local test steps

1. Upload two actual PNG files through the vendor API. Exercise product creation and standalone image association with valid payloads, mixed originals/thumbnails/key sets, missing keys, and omitted keys.
2. Create and edit variations using the same product's images, another product's images, and live unassociated uploads.
3. Delete a valid variation image as vendor and admin; check variation references and physical local files.
4. Check legacy external images, public moderation gating, anonymous/customer rejection, foreign vendor namespaces, admin URL immutability, and both CSV import modes.
5. Check single and batch upload-record commit failures both before persistence and after a durable commit whose acknowledgement is lost. Missing identities must reserve all uploaded keys in the cleanup ledger; durable identities must preserve objects without a cleanup row. Check catalog reset preflight failure.
6. In the admin editor, check a fresh local upload returned as `/uploads/...`, an existing absolute CDN URL, a thumbnail-only row and a missing-image placeholder. With Vite and the API on separate origins, image requests must use the API origin while the placeholder stays on Vite.
7. Start a reset with an empty and a populated catalog, then commit a new product after its snapshot: the new product, images, variants, variation sizes, featured reference and storage must survive.

## Expected local result

Valid same-product galleries remain editable. Invalid references return 409 without creating an image row or deleting either upload. All admin image original/thumbnail URL changes, including legacy rows, return 422; primary/order/alt-text edits still work. Deletion clears the owning variation gallery and leaves unrelated uploads intact. Pending products remain hidden publicly. Reset preflight failure preserves rows and storage.

## Staging test steps

After reviewers authorize merge and staging deployment:

1. Apply migration `v5w6x7y8z9a0` before rolling out the new backend to every instance. Do not keep old upload writers active alongside new association validators.
2. Create a single product and a variable product through the vendor form with fresh uploads. Reload vendor detail/edit and verify persistence.
3. As admin, upload, reorder, select primary and delete an image. Check that changing a legacy image URL through the API is rejected and its existing variation remains vendor-editable. Confirm moderation returns to pending. Reapprove through the existing workflow.
4. Verify cards/lists, product detail, selected-color galleries, hover images, cart/wishlist, vendor/admin dashboards, and featured storefront with the changed item and a previously working item.
5. Repeat malformed image/variation requests from the local matrix against staging using synthetic products. Verify no unrelated uploaded object is deleted.

## Expected staging result

Fresh vendor and admin uploads work with the configured object store/CDN. Image deletion leaves no selected-variation URL pointing to the deleted object. Unapproved products remain absent from customer surfaces. Malformed or cross-product references are rejected server-side.

## Regression checks and operating notes

- Admin image URLs are immutable for owned and legacy rows; replace images through upload/delete. Unchanged URLs can still accompany metadata updates.
- Reset affects the product IDs captured at its start; products created afterward are intentionally preserved. An empty snapshot retains the existing coordinator rejection (500) without deleting anything.
- Existing associated images need no backfill. Legacy external images remain supported; their URLs are never used to guess deletion keys.
- Unassociated uploads created before this migration have no trusted upload record and must be uploaded again. New managed uploads cannot be associated without their complete server-issued keys.
- CSV import supports external image URLs; managed upload URLs must use the upload/association workflow.
- The new table retains server-issued URL/key identities independently of product deletion; cleanup tombstones remain authoritative for reuse rejection.
- A failed upload-record commit returns an error, probes the authoritative identity after rollback and reserves exact uploaded keys for cleanup only when the identity is absent and no association/cleanup already owns them. A durable identity preserves its objects. If the database also prevents the recovery probe or cleanup write, automatic reconciliation cannot be guaranteed and operators must investigate; no deletion keys are guessed from public URLs.
- Preexisting cross-product variation URLs are rejected when resubmitted; this change does not rewrite historical gallery data.
- No new environment variables or frontend API fields. No changes to financial calculations, authorization roles or moderation approval rules.
- Automated HTTP tests are not rendered-browser or staging evidence. StarLord coordinates Product and independent NightWing QA; Groot reviews the additive persistence and rollout risk.

## Follow-up verification boundary

The editor regression uses rendered DOM assertions in jsdom; it does not prove browser image loading. The issue has no realized managed preview workspace at this verification run. Product/NightWing must execute the local preview steps and staging surface matrix above before acceptance. No shared image helper or other rendering surface changed in this follow-up.
