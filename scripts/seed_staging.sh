#!/bin/bash
# Seed Staging Database with Products
# This script triggers the seed endpoint on staging

set -e

STAGING_API="https://shopsoma-staging-api.onrender.com/api/v1"

echo "=========================================="
echo "Seeding Staging Database"
echo "=========================================="
echo ""

# Check if staging API is healthy
echo "Checking staging API health..."
if curl -s "${STAGING_API}/health" | grep -q "healthy"; then
    echo "✓ Staging API is healthy"
else
    echo "✗ Staging API is not responding"
    exit 1
fi

echo ""
echo "Triggering seed endpoint..."
echo "This will create demo products in the staging database."
echo ""

# Call the seed endpoint (if it exists)
RESPONSE=$(curl -s -w "\n%{http_code}" "${STAGING_API}/seed/products" -X POST)
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "201" ]; then
    echo "✓ Seed completed successfully"
    echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
elif [ "$HTTP_CODE" = "404" ]; then
    echo "⚠ Seed endpoint not found"
    echo "The staging environment needs to have the seed endpoint enabled"
    echo ""
    echo "Alternative: Run seed script directly on staging:"
    echo "1. SSH into staging server"
    echo "2. Run: python shopsoma-backend/seed_products.py"
else
    echo "✗ Seed failed with HTTP $HTTP_CODE"
    echo "$BODY"
    exit 1
fi

echo ""
echo "=========================================="
echo "Verifying products..."
echo "=========================================="

# Fetch and display products
PRODUCTS=$(curl -s "${STAGING_API}/products?page_size=20")
COUNT=$(echo "$PRODUCTS" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('products', [])))" 2>/dev/null || echo "0")

echo "✓ Found $COUNT products in staging"
echo ""

if [ "$COUNT" -gt "0" ]; then
    echo "Product list:"
    echo "$PRODUCTS" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for i, p in enumerate(data.get('products', [])[:10], 1):
    print(f\"{i}. {p['title']} - ₦{p['base_price']}\")
if len(data.get('products', [])) > 10:
    print(f'... and {len(data.get(\"products\", [])) - 10} more')
" 2>/dev/null || echo "Could not parse products"
fi

echo ""
echo "Done!"
