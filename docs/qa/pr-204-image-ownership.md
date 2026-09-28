# PR #204 image ownership verification

Scope: bind variation galleries to their product, bind vendor image association to a server-issued upload, correct the obsolete reset preflight assertion, preserve products created outside the reset snapshot, reconcile failed upload identities, and normalize admin editor/detail preview URLs and keep detail thumbnails/lightbox in one order. PR targets `develop`; merge and deployment remain reviewer decisions.

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
npm test -- src/pages/admin/AdminProductActions.test.tsx src/pages/admin/AdminProductEdit.images.test.tsx src/utils/productImages.test.ts --maxWorkers=1 --minWorkers=1
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
7. In admin detail, use an API gallery whose primary row appears later and whose display order differs from response order. Open the main image and each thumbnail, navigate both directions with controls/keyboard, and confirm the enlarged image matches. Check local original/thumbnail URLs, a thumbnail-only row, an existing absolute CDN URL, and an empty image row; placeholders stay on the frontend origin.
8. Start a reset with an empty and a populated catalog, then commit a new product after its snapshot: the new product, images, variants, variation sizes, featured reference and storage must survive.

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

The editor regression uses rendered DOM assertions in jsdom; it does not prove browser image loading. The issue has no realized managed preview workspace at this verification run. Product/NightWing must execute the local preview steps and staging surface matrix above before acceptance. The detail page now shares one ordered array between its main image, thumbnails and lightbox; all three normalize persisted URLs before applying the frontend placeholder. No shared image helper changed. Focused admin actions/editor/image utility suites: 55 passed; TypeScript and diff checks passed. Backend code is unchanged by this gallery follow-up; the prior 100-pass PostgreSQL evidence remains applicable, with latest-head CI still required.

## Vendor gallery and cart fallback follow-up

- Success condition: repeated variation originals render once in vendor detail without changing the shared helper or gallery order. Cart, add-to-bag and edit-variant each try the normalized original after thumbnail failure, then stop at the frontend placeholder; changed sources reset the attempt.
- Inspected vendor create payload, vendor service/types, cart store, the four render paths and existing ProductCard fallback. Vendor detail deduplicates normalized source/original identities locally. No backend, API, database, pricing or shared-helper change.
- Local commands (`shopsoma-frontend/`): `npm test -- src/tests/productImageConsumers.test.tsx src/pages/admin/AdminProductActions.test.tsx src/pages/admin/AdminProductEdit.images.test.tsx src/utils/productImages.test.ts --maxWorkers=1 --minWorkers=1`; `npx tsc -b`.
- Local tests: overlapping product/variation originals (relative and absolute), thumbnail aliases, repeated variation-only images, primary ordering, existing external images, empty gallery, each consumer's thumbnail/original/placeholder error chain and image replacement. Expected: one vendor tile per image; valid originals survive thumbnail errors; placeholder errors do not retry forever.
- Staging steps: create a variable product with shared images, reload vendor detail, verify one tile per image. In cart and both modals block a thumbnail request in browser developer tools; verify the original loads, then block both URLs and verify the local placeholder. Repeat with a previously working single product.
- Expected staging result: actual images load from the API/CDN origin, no duplicate vendor tiles, and no recurring placeholder requests. Regression checks: admin main/thumbnail/lightbox ordering, cards/hover, detail selections, wishlist and storefront matrix above.
- These are synthetic DOM regressions, not real browser/network evidence. Product/NightWing must still run the reproducible browser/staging checks through StarLord.


## Whole-PR inspection follow-up (2026-09-28)

The consolidated review and open findings live on the implementation issue in document `whole-pr-review`. No further manual Codex request is authorized; NightWing owns the next request after independent review.

- Fixed local variant-upload compensation: if cleanup itself raises, retain every attempted exact key on the original HTTP error for durable retry. Regression covers thumbnail, medium and large failure stages with both partial cleanup results and cleanup exceptions. Local RED: 3 failed / 4 passed; GREEN: 7 passed.
- Advanced six migration test head expectations to `v5w6x7y8z9a0`, preserving the parent chain and existing safeguards. Five database-independent graph tests reproduced failures and then passed. The domestic-rate test imports full application fixtures and remains for PostgreSQL CI.
- This heartbeat runtime has no PostgreSQL server or full backend environment. Isolated Python dependencies allowed the real image-service unit tests and Alembic graph tests to execute; this is not a new PostgreSQL lifecycle run. Earlier PostgreSQL evidence remains historical, not verification of this new head.
- Open caller regression: vendor Duplicate copies managed image URLs without keys; ownership validation correctly rejects those requests. Groot/StarLord must settle ownership-safe copying versus a changed draft UX before implementation closes. Never fix this by reusing keys or weakening validation.

Focused commands with normal repository dependencies (`shopsoma-backend/`):

```sh
python -m pytest tests/test_image_service_cleanup_metadata.py -q
python -m pytest tests/test_phase_2a_migration_graph.py tests/test_checkout_prerequisite_migration.py tests/test_customer_shipping_quote_migration.py tests/test_domestic_rate_migration.py tests/test_lane_3c_migration.py tests/test_lane_3d_migration.py -q
```

For a database-free service/graph check, use `python -m pytest --noconftest` and select only service unit tests or graph test node IDs; set synthetic `SECRET_KEY`, `DATABASE_URL`, `USE_LOCAL_STORAGE=true` and a disposable `LOCAL_UPLOAD_DIR`. Do not interpret this as running database fixtures or migration upgrade/downgrade cycles.

QA order: run the focused local commands; inject a variant-generation error plus cleanup failure and verify retry-key retention; expect the original 500 with exact attempted keys and one linear migration head. After an authorized staging rollout, repeat a failed upload with controlled storage failure and observe cleanup-ledger retry completion. Recheck successful vendor/admin uploads, legacy image deletion, same-product variations and all existing preview surfaces. Browser/staging and managed-storage fault injection remain unverified.

## Ownership-safe Duplicate batch (2026-09-28)

The accepted REX-26 design resolves the open Duplicate finding above. The backend
now owns `POST /products/{product_id}/duplicate`: approved/completed vendors may
duplicate their own product into an unfeatured, pending-moderation draft. The
shared graph builder preserves normal create validation. No new database
migration, environment variable, or private response field is introduced.

Managed originals, thumbnails and all persisted derivatives receive independent
UUID keys. Gallery order, alt text, primary flags, variation URL order, currency,
product type and variation size inventory are preserved. Single-product stock
resets to zero; made-to-order products preserve their timeline and zero inventory.
SKU/history/moderation decisions are not copied. External legacy URLs remain
external references without storage IO; inconsistent or keyless managed sources
require repair/re-upload.

### Local setup/run commands

Use Python 3.11, `requirements.txt`, disposable PostgreSQL 17 and synthetic
`SECRET_KEY`/`DATABASE_URL` settings; set `USE_LOCAL_STORAGE=true` and a disposable
`LOCAL_UPLOAD_DIR`. Test fixtures create/drop a separate process-specific database.

```sh
# shopsoma-backend/
python -m pytest tests/test_product_duplication.py tests/test_image_copy.py tests/test_product_image_ownership.py tests/test_admin_product_images.py tests/test_stock_payment_lock_coordinator.py tests/test_products.py tests/test_image_service_cleanup_metadata.py -q
ruff check app/services/product_creation.py app/services/product_duplication.py app/services/image_service.py app/api/v1/products.py tests/test_product_duplication.py tests/test_image_copy.py --select E9,F63,F7,F82
# shopsoma-frontend/
npm test -- src/pages/vendor/VendorProductDuplicate.test.tsx src/services/__tests__/productDuplicate.test.ts src/tests/productImageConsumers.test.tsx src/utils/productImages.test.ts
npx tsc -b
```

For Product/NightWing's reproducible preview, migrate a **separate disposable
application database** with `alembic upgrade head`, run the backend with
`uvicorn app.main:app --reload`, and run the frontend with `npm run dev` using its
local API URL setting. Use synthetic approved/completed vendor, customer and admin
accounts. This is a setup handoff, not a deployed preview or browser-verification
claim.

### Local test steps

1. Duplicate single, USD variable, NGN and made-to-order products from both list
   and detail buttons. Verify immediate pending state, one request for repeated
   clicks, edit navigation and subsequent editing of copied variation galleries.
2. Duplicate a 10-image gallery with four objects per image. Compare bytes, order,
   alt text, primary flag, variation gallery mapping and distinct source/copy keys.
   Check null thumbnails and thumbnails equal to originals.
3. Delete a source image, then separately delete a copied image. Verify the other
   product's files survive. Confirm the duplicate remains absent from public detail.
4. Reject missing/foreign products, anonymous/customer/admin callers and
   unapproved/incomplete vendors before copying. Reject malformed galleries,
   mixed URLs, shared keys, cleanup tombstones and keyless managed images.
5. Inject copy failure/acknowledgement loss, graph/serialization failure,
   commit failures before/after durability, unavailable recovery DB and cleanup
   recording failure. Exercise cleanup worker retries and a concurrent source
   catalog writer.

### Expected local result

A complete private draft with independent files, or an explicit failure without a
partial product graph. Durable commits retain their files and can return their
saved result after a lost acknowledgement. Authoritatively absent writes reserve
only attempted, unowned, never-consumed destination keys in the existing cleanup
ledger. Unknown outcomes retain objects for reconciliation. Source files and
unrelated ownership remain intact. Both controls show reconciliation advice after
network/server uncertainty and never automatically retry the POST.

### Staging test steps

After separately authorized merge/deployment, ship backend endpoint before the
new frontend caller. Retain all earlier PR ownership migration requirements.
NightWing should repeat the matrix using the configured storage provider/CDN,
verify copy permissions and derivative metadata, and measure 10-image latency
before agreeing a client timeout. Validate real image loading and both Duplicate
buttons, then source/copy deletion, edits and all independent rendering surfaces
listed above. Use controlled synthetic data for failure drills.

### Expected staging result

Originals/thumbnails persist after reload, correct variations/sizes/currency
remain editable, one product's image deletion leaves the other intact, and pending
duplicates remain private. Provider permissions and latency meet the agreed
release criteria. No staging/provider performance result is claimed by local tests.

### Regression checks and operating limits

- Ordinary create/edit/upload, admin image operations, moderation, catalog
  coordination and cleanup worker remain covered. No order/payment/payout writes
  or historical currency conversion are added.
- Source and destination catalog locks precede sorted storage locks. Source edits
  and deletes wait during copying. At most 40 objects are copied; provider IO uses
  a separate client with 5-second connect, 15-second read and two total attempts.
  Copy orchestration stops starting new objects after a 120-second budget.
- Existing 10-second frontend timeout is preserved. Slow provider outcomes can
  therefore be uncertain; refresh the product list before retrying. Automatic
  retries (including auth retry for this POST) are disabled. Intentional later
  requests create separate drafts; no exactly-once claim.
- Process crashes/cancellation during external IO can leave unowned objects.
  Restricted logs include source/destination correlation IDs and counts. Retain
  unknown objects for operator reconciliation; never delete by age or guessed URL.
  Cleanup waits for the existing durable cleanup worker.
- Roll back endpoint/caller together or disable Duplicate; never remove ownership
  guards to restore the former URL-only caller.
- DOM/API tests do not establish rendered-browser, provider, staging, specialist
  security or independent QA approval. StarLord coordinates Product/NightWing;
  NightWing owns the next manual Codex request.

Local evidence for this batch: 187 backend regressions passed in 156.65 seconds;
the final duplication-only rerun passed all 32 tests after adding explicit admin
and cleanup-ownership boundaries. Maximum local gallery (40 small objects)
completed in 0.217 seconds, measured inside the HTTP regression; this is not a
provider latency estimate. The four focused frontend files passed 21 tests; the
corrected service test and TypeScript check were rerun successfully. New Python
modules/tests passed full F/E9 lint; all changed runtime files passed focused
E9/F63/F7/F82 lint. Latest pushed-head CI remains a separate gate.
