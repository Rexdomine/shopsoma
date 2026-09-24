# Admin product View/Edit route repair

## Root cause and scope

The admin list links were valid, but the detail/edit pages read through `GET /products/{id}` (the storefront endpoint). That endpoint deliberately hides non-active or non-approved products. A resulting load failure caused each page to navigate back to the list, appearing to reload it. Edit also submitted to `PUT /products/{id}`, which requires vendor authorization rather than administrator authorization.

The pages now use the existing admin-only product endpoints. Load errors remain visible on the requested page; save validation errors retain the form. The admin detail endpoint now uses the shared product response contract with eager-loaded relationships, rather than a hand-built response referencing the nonexistent `ProductVariant.is_active` attribute. The admin update endpoint accepts an explicit validated field allow-list rather than arbitrary mapped attributes. The UI's nonexistent `inventory_quantity` editor was removed; `total_stock` remains.

Delete, Approve and Deny routes/buttons are unchanged. This repair includes the additive Alembic revisions `b8c9d0e1f2a3` and `c9d0e1f2a3b4`: the first adds the nullable `product_variants.inherits_price` marker and conservatively classifies existing generic rows as explicit; the second adds nullable `product_variants.inherits_stock` and intentionally leaves existing rows unknown because axis-less variants may carry explicit inventory. Only rows explicitly marked as inheriting stock are synchronized from `Product.total_stock`. Apply both migrations before deploying code that reads or writes these ORM fields; they are additive and require no product-data backfill. Existing scalar stock editing remains an absolute value update; full concurrency-safe catalog/variant editing is separate work.

## Boundaries and failure behavior

- Browser admin pages → authenticated admin API → product row.
- Anonymous users, customers and vendors cannot use these admin read/write routes.
- Pending/rejected draft products remain unavailable through the public storefront endpoint.
- Ordinary edits preserve moderation and featuring; featuring remains available only through the existing dedicated admin action.
- Required-field nulls, unknown fields, invalid categories and inconsistent compare-at/base prices fail before commit.
- Product writes commit once. No provider/outbox/queue side effects are introduced. A lost response still requires read-back before an operator retries; no new automatic mutation retry is added.
- Backend response compatibility must be deployed before (or atomically with) frontend changes. The PUT acknowledgement retains its existing message/product_id shape.

## Verification

Executed locally against the disposable PostgreSQL database configured for this worktree:

```sh
env -i PATH=/opt/data/tmp/resend-test-venv/bin:/usr/local/bin:/usr/bin:/bin HOME=/opt/data DATABASE_URL="$TEST_DATABASE_URL" SECRET_KEY=local-only-resend-regression-secret ENVIRONMENT=test USE_LOCAL_STORAGE=true ALLOW_LOCAL_STORAGE_IN_NON_DEV=true /opt/data/tmp/resend-test-venv/bin/python -m pytest -q tests/test_admin_product_edit_boundaries.py tests/test_product_schema_pricing.py tests/test_product_variants.py tests/test_cart.py
# 105 passed
python3 -m compileall -q app tests
 git diff --check
# passed
```

The final pricing matrix covers inherited regular/sale combinations, axis-less and size/color rows, matching and nonmatching variations, explicit stock/price ownership, and admin/vendor direct-edit authority. It also covers production creation of inherited axis-less stock and rejection of non-positive admin variant prices before synchronization. Broad repository flake8 still reports pre-existing legacy-file violations; the changed code has no new syntax or diff-check failures.

Frontend (Node 22 for Vitest):

```sh
npx vitest run src/pages/admin/AdminProductActions.test.tsx src/pages/admin/AdminOrderDetail.test.tsx --pool=forks --poolOptions.forks.singleFork
# 7 passed, including 6 View/Edit regressions
npm run lint -- --quiet
npm run build
# passed (build includes TypeScript checking)
```

A temporary local browser fixture rendered the actual admin list/detail/edit components with an isolated Axios adapter. Clicking View displayed a pending product; returning to the list and clicking Edit, changing title and saving used `GET/PUT /admin/products/{id}` and updated the fixture. No live product was modified. This is local UI evidence, not hosted end-to-end verification.

## Post-deploy manual checklist

1. As an administrator, open View and Edit for a pending/draft product and an active/approved product.
2. Save an authorized test product edit and reopen it to verify persisted values.
3. Confirm a missing product presents a visible error and an explicit Back to Products button.
4. Confirm invalid edits show readable errors and retain input.
5. Confirm non-admin access remains forbidden and public pending/draft products remain hidden.
6. Smoke-check the unchanged Delete/Approve/Deny flows only with explicitly authorized disposable products.

No hosted deployment or live administrator session was used for write verification. Merge/deployment requires owner approval.
