#!/bin/bash
# Update "Queen of green" product with complete information

echo "🔄 Updating 'Queen of green' product with complete information..."

# Set database connection
export DATABASE_URL="postgresql://shopsoma:shopsoma_dev_password@localhost:5432/shopsoma_db"

# Update the product
psql "$DATABASE_URL" << EOF
-- Update Queen of green product
UPDATE products
SET
  care_instructions = 'Hand wash cold separately. Do not bleach. Lay flat to dry. Cool iron if needed. Do not dry clean.',
  fabric_composition = '100% Premium Cotton. Ethically sourced and sustainably produced. Soft, breathable fabric with natural texture.',
  made_to_order = true,
  made_to_order_timeline = 'Ships in 2-3 weeks',
  updated_at = NOW()
WHERE title = 'Queen of green';

-- Verify the update
SELECT
  title,
  care_instructions IS NOT NULL as has_care,
  fabric_composition IS NOT NULL as has_fabric,
  made_to_order,
  made_to_order_timeline
FROM products
WHERE title = 'Queen of green';
EOF

echo ""
echo "✅ Product updated successfully!"
echo "🎉 Reload the product detail page to see the changes!"
echo ""
echo "Test URL: http://localhost:5173/products/474d3368-3979-4142-aa3a-df7755d7f23f"
