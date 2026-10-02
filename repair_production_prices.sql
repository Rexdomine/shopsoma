-- ==============================================================================
-- SQL Data Repair Script: Synchronize Single-Product Variant Prices
-- ==============================================================================
--
-- Background:
-- When vendors or admins edited the price of a single product (apparel with sizes),
-- a backend bug in _sync_inherited_variation_prices skipped updating product_variants
-- because the variants had size/color attributes and inherits_price=FALSE/NULL.
--
-- This script fixes existing desynchronized single products in the database
-- by updating product_variants.price to match products.base_price, and marking
-- inherits_price = TRUE so that all future edits propagate seamlessly.
-- ==============================================================================

BEGIN;

-- 1. Update the known desynchronized products on production:
--    - Dance dress (ID: aeee0e90-4e97-41ff-9bfd-805b9dfd6c08, base_price: 75.00, variants: 85.00)
--    - Muna Kaftan (ID: 066456e5-bc5c-412a-ace5-e8c47f55f0e0, base_price: 113.00, variants: 85.00)
--    - Eko Trousers (ID: 6d858415-0958-4036-af1a-45fd1a785f23, base_price: 100.00, variants: 97.00)
--    - Adaeze Trousers (ID: 8bba4cde-86a1-43e4-89bc-d128d4a8287f, base_price: 100.00, variants: 60.00)
UPDATE product_variants pv
SET price = p.base_price,
    inherits_price = TRUE,
    updated_at = NOW()
FROM products p
WHERE pv.product_id = p.id
  AND NOT EXISTS (
      SELECT 1 FROM variations v WHERE v.product_id = p.id
  )
  AND p.id IN (
      'aeee0e90-4e97-41ff-9bfd-805b9dfd6c08',
      '066456e5-bc5c-412a-ace5-e8c47f55f0e0',
      '6d858415-0958-4036-af1a-45fd1a785f23',
      '8bba4cde-86a1-43e4-89bc-d128d4a8287f'
  );

-- 2. Mark inherits_price = TRUE for all other single products without variations
--    where variant prices already match the product's base price:
UPDATE product_variants pv
SET inherits_price = TRUE,
    updated_at = NOW()
FROM products p
WHERE pv.product_id = p.id
  AND NOT EXISTS (
      SELECT 1 FROM variations v WHERE v.product_id = p.id
  )
  AND pv.price = p.base_price
  AND (pv.inherits_price IS NULL OR pv.inherits_price = FALSE);

COMMIT;
