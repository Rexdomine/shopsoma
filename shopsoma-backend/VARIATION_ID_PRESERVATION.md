# Stable Variation ID Preservation Architecture

## Background & Problem Statement
In earlier iterations of Shopsoma, updating a product with variations via `PUT /api/v1/products/{product_id}` executed a destructive replacement:
```python
await db.execute(select(Variation).where(Variation.product_id == product_id))
for existing_variation in product.variations:
    await db.delete(existing_variation)
```
This cascade-deleted all existing `Variation` and `SizeStock` records and re-inserted new records with generated UUIDs. This caused several critical issues:
1. **Loss of Stable Identity**: External references (order history, pending cart items, inventory logs, and frontend selection state) lost identity parity with persisted entities.
2. **Untouched-Variation Corruption**: Editing a single variation inadvertently mutated all other variations on the product by regenerating their IDs, resetting `created_at` timestamps, and causing unnecessary database churn.
3. **Admin Contract Asymmetry**: The admin product update schema (`AdminProductUpdate`) forbade variation payloads entirely, forcing reliance on legacy `ProductVariant` endpoints that do not map to the new `variations` and `size_stocks` relational schema.

## Architectural Decision

### 1. Stable Identity Policy
- Every `Variation` row has a persistent, immutable primary key `id: UUID`.
- Every nested `SizeStock` row has a persistent, immutable primary key `id: UUID` governed by the `(variation_id, size)` unique constraint.
- Database migrations are **not required** because existing `variations.id` and `size_stocks.id` UUID primary keys already provide full unique identity.

### 2. In-Place Persistence & Synchronization
When a product or variation update is processed:
1. **Identity Resolution**:
   - Incoming variation payloads with an explicit `id` are matched against the product's persisted variations (`Variation.product_id == product.id`).
   - If an explicit `id` is supplied that does not belong to the target product, the request is rejected with `404 Not Found` (or `422 Unprocessable Entity`).
   - If a variation payload omits an `id`, the backend matches against existing product variations by normalized title and type (`(normalize_color_value(title), type)`) to preserve stable identity across clients that do not track IDs.
   - If no existing variation matches the payload, a new `Variation` entity is instantiated.
2. **Untouched-Variation Preservation**:
   - In single-variation update endpoints (`PUT /api/v1/products/{product_id}/variations/{variation_id}` and `PUT /api/v1/admin/products/{product_id}/variations/{variation_id}`), only the designated variation and its size stocks are locked and modified. All other variations on the product remain completely untouched.
   - In full product synchronization (`PUT /api/v1/products/{product_id}` and `PUT /api/v1/admin/products/{product_id}`), existing variations present in the payload are updated in place, retaining their original `id` and `created_at`. Only variations explicitly omitted from a full variation replacement are deleted.
3. **Nested Size Stock In-Place Matching**:
   - For each variation, nested size stock updates match existing `SizeStock` entries by `size` (which is unique per variation).
   - Existing size stock rows retain their `id` and have their `stock` quantity updated.
   - New sizes are added as new `SizeStock` rows.
   - Removed sizes are removed without affecting unchanged size stocks.

### 3. Scoped Variation Images vs. Product Gallery
- Product-level gallery images are managed via `ProductImage` (`product_images` table).
- Variation images are stored as an array of URLs in `Variation.images` (`JSONB`).
- **Scoped Action Invariant**:
  - Adding or removing an image on a variation modifies only `variation.images`.
  - It **never** alters, reorders, or deletes rows from `product.images` (the parent product gallery).
  - It **never** mutates images on untouched variations.
- **Image Ownership Invariant**:
  - Any image URL associated with a variation must belong to the parent product (verified via `lock_and_validate_variation_image_urls`).
  - Attempting to associate an image URL that belongs to another product or an unowned upload is rejected with `409 Conflict`.

### 4. Separation from Legacy `ProductVariant` Endpoints
- The legacy `product_variants` table and its endpoints:
  - `/api/v1/products/{product_id}/variants`
  - `/api/v1/products/{product_id}/variants/{variant_id}`
  - `/api/v1/admin/products/{product_id}/variants`
  - `/api/v1/admin/products/{product_id}/variants/{variant_id}`
  remain strictly separate. They serve single-product variants and backward compatibility.
- Variable product variation operations use dedicated variation endpoints and schemas:
  - `/api/v1/products/{product_id}/variations`
  - `/api/v1/products/{product_id}/variations/{variation_id}`
  - `/api/v1/admin/products/{product_id}/variations`
  - `/api/v1/admin/products/{product_id}/variations/{variation_id}`
  as well as the top-level product update payloads with variation support.

### 5. Moderation & Auditability
- Vendor edits to any variation (title, pricing, stock, images) invoke `mark_product_content_pending(db, product_id)`, advancing the revision timestamp and reverting the moderation state to `pending`. This prevents unmoderated changes from leaking into customer-facing storefronts.
- Admin edits preserve the administrator's authoritative revisions while keeping public approval filtering intact.
