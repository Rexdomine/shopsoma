# Product images in bulk CSV imports

## Vendor guide

Both **Single Products CSV** and **Variant Products CSV** accept these optional columns:

```text
image_1_url,image_2_url,image_3_url,image_4_url,image_5_url
```

Use direct, publicly accessible HTTPS image links from a host you control or are permitted to use. Local paths, file uploads, and sharing-page links are not substitutes for direct image URLs. Replace sample photographs with your own product photographs before publishing.

- Leave all image cells blank to import without images. Existing CSVs without these columns remain supported.
- Up to five unique images are attached to each product's gallery. The first nonblank URL encountered is the primary image. Remaining images keep CSV encounter order (rows, then numbered columns).
- For a variable product, put the images on its first row and leave later size rows blank. Repeating the same URLs on later rows is also supported; exact duplicates are attached only once.
- Every size row of a variable product must keep the same `product_title`, `category_slug`, and `currency`, and the same product SKU. A different category creates a different product group.
- Images belong to the whole product, not individual colors or sizes.
- Use your spreadsheet's CSV export to quote cells correctly, especially URLs containing commas.
- Images remain hosted at the supplied URLs. ShopSoma does not download, copy, resize, or permanently store the image files during this import. Keep those URLs available; expiring links and hosts that block external display can produce broken images later.
- URL validation checks format and obvious unsafe/local targets, not reachability, image content, licensing, or whether a host will allow display. A successful import is not proof of remote image availability.
- Invalid image fields return row/column validation errors before product insertion. Correct the file and retry. Do not blindly re-upload after an ambiguous timeout: check your product list first, since a successful commit may have occurred before the response was lost.

## Engineering preflight and invariants

### Boundaries and authority

1. Vendor browser → existing authenticated CSV endpoint: the vendor submits untrusted CSV strings; existing vendor eligibility and ownership checks remain authoritative.
2. CSV parser → database: validated URLs become existing `ProductImage` rows associated with newly created products. No new schema, permission, storage configuration, queue, or worker.
3. Shopper/vendor browser → external image host: existing image components display the stored URL. The host controls future availability and receives normal browser requests. The import endpoint never fetches the URL or resolves DNS.

### Lifecycle and atomicity

`received → parsed/validated → product + image rows in one transaction → committed → response`.

Invalid rows stop the batch before durable insertion. A database failure before commit must roll back product and image rows together via the existing session lifecycle. Image ordering and a single primary image are deterministic per product; duplicate URLs must not create duplicate image records within one import.

### Identity and retry rules

Product identity remains the existing product SKU and, for variable grouping, title/category/currency. No new idempotency contract is claimed. Exact URL strings after permitted whitespace handling are the per-product deduplication key; URLs are not downloaded or rewritten. Existing duplicate-SKU rules continue to apply on retries.

### Crash windows

- Before validation/persistence: no durable product or image rows.
- During writes, before commit: rollback removes both product and image rows.
- After commit, before HTTP delivery: records may exist; vendor must check the catalog before retrying.
- External image host failure: does not alter import transaction state. No server fetch means no provider-success/local-commit ambiguity and no download retry machinery.

### Time and expiry

No new lease, timeout, cron, or cache expiry. External signed image URLs can expire independently, so durable publicly hosted URLs are recommended.

### Parity surfaces

- Frontend optional sample headers vs existing required headers: legacy CSVs must still pass.
- Single vs variable import: same URL validation and five-image limit.
- All variable rows vs one product gallery: deduplicate and enforce aggregate limit before writes.
- `ProductImage` persistence vs frontend gallery/primary-image resolution: use existing fields and preserve primary/display ordering.

## QA checklist

### Local commands

From `shopsoma-backend`, run `python -m pytest tests/test_bulk_product_upload.py tests/test_bulk_product_images.py tests/test_products.py tests/test_product_variants.py tests/test_product_schema_pricing.py -q` against an explicitly isolated PostgreSQL test database, never a live database.

From `shopsoma-frontend`, run `npx --yes --package=node@20 node node_modules/vitest/vitest.mjs run src/components/vendor/__tests__/BulkUploadModal.csv.test.ts --maxWorkers=2 --minWorkers=1`, `npx tsc --noEmit -p tsconfig.json`, `npm run lint -- --quiet`, and `npm run build`.

Local candidate verification: 154 backend tests and 8 frontend component tests passed, along with TypeScript, ESLint, production build, and `git diff --check`. Both CSVs captured from the actual browser download action also imported successfully against isolated PostgreSQL (two additional local smoke cases). The modal was checked at 390×844: vertical scrolling reached the upload action with no horizontal overflow. These are local results, not staging/deployment evidence.

### Local/staging steps

After Rex merges and staging deploys this PR:

1. Download both sample files from the modal and verify all five optional image columns are present.
2. Use fresh SKUs and known staging category slugs. Supply two working HTTPS image URLs and upload a single product.
3. Open its product details, refresh, and verify the first image is primary and the gallery order persists.
4. Upload a variable product with two size rows: images on the first row, blank on the second. Verify one gallery, not duplicated images. Repeat with identical URLs on both rows using a fresh SKU.
5. Upload a legacy CSV without image columns; it must still work.
6. Try an unsafe URL and a grouped variable product exceeding five unique images; expect actionable row-level errors and no products from that failed batch.
7. Confirm existing manually uploaded product images still display. For variable products without color-specific images, selecting a color must retain the product-level gallery fallback.

Expected result: images persist with product ownership and order; invalid image data does not partially import products. Hosted runtime verification requires the merged deployment and is not implied by local tests.
