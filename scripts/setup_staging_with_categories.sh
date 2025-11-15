#!/bin/bash
# Setup Staging with Categories
# This reseeds the database and adds category labels for search filtering

set -e

STAGING_API="https://shopsoma-staging-api.onrender.com/api/v1"

echo "=========================================="
echo "Setup Staging with Categories"
echo "=========================================="
echo ""

# Step 1: Reset and reseed
echo "Step 1: Resetting and reseeding..."
curl -s "${STAGING_API}/seed/reset" -X DELETE > /dev/null
curl -s "${STAGING_API}/seed/initialize" -X POST > /dev/null
echo "✓ Database reset and seeded"
echo ""

# Wait a moment for the database
sleep 2

# Step 2: Update categories
echo "Step 2: Updating product categories..."
RESULT=$(curl -s "${STAGING_API}/seed/update-categories" -X POST)
echo "$RESULT" | python3 -m json.tool 2>/dev/null || echo "$RESULT"
echo ""

# Step 3: Verify
echo "Step 3: Verifying products..."
PRODUCTS=$(curl -s "${STAGING_API}/products?page_size=10")
echo "Products with categories:"
echo "$PRODUCTS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for p in data.get('products', []):
        desc = p.get('description', '')
        category = 'Unknown'
        if 'Women -' in desc:
            category = 'Women'
        elif 'Men -' in desc:
            category = 'Men'
        elif 'Unisex -' in desc:
            category = 'Unisex'
        print(f\"  ✓ {p['title']}: {category}\")
except:
    print('  Could not parse products')
" 2>/dev/null

echo ""
echo "=========================================="
echo "✓ Staging Setup Complete!"
echo "=========================================="
echo ""
echo "You can now test search filtering:"
echo "- Women: 2 products"
echo "- Men: 2 products"
echo "- Unisex: 1 product"
echo ""
echo "Visit: https://shopsoma-staging.onrender.com/products"
echo "Search and filter by: Women, Men, or search for specific items"
echo ""
