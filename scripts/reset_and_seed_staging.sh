#!/bin/bash
# Reset and Reseed Staging Database
# This ensures staging has the same products as the seed data

set -e

STAGING_API="https://shopsoma-staging-api.onrender.com/api/v1"

echo "=========================================="
echo "Reset & Reseed Staging Database"
echo "=========================================="
echo ""

# Step 1: Check API health
echo "Step 1: Checking staging API health..."
if curl -s "${STAGING_API}/health" | grep -q "healthy"; then
    echo "✓ Staging API is healthy"
else
    echo "✗ Staging API is not responding"
    echo "Please check if the staging deployment is online"
    exit 1
fi
echo ""

# Step 2: Reset database
echo "Step 2: Resetting staging database..."
echo "This will delete all existing products..."
RESET_RESPONSE=$(curl -s -w "\n%{http_code}" "${STAGING_API}/seed/reset" -X DELETE)
RESET_CODE=$(echo "$RESET_RESPONSE" | tail -n1)
RESET_BODY=$(echo "$RESET_RESPONSE" | sed '$d')

if [ "$RESET_CODE" = "200" ]; then
    echo "✓ Database reset successful"
    echo "$RESET_BODY" | python3 -m json.tool 2>/dev/null || echo "$RESET_BODY"
else
    echo "⚠ Reset returned HTTP $RESET_CODE"
    echo "$RESET_BODY"
    echo "Continuing anyway..."
fi
echo ""

# Step 3: Seed database
echo "Step 3: Seeding staging database..."
echo "Creating demo products with variants..."
SEED_RESPONSE=$(curl -s -w "\n%{http_code}" "${STAGING_API}/seed/initialize" -X POST)
SEED_CODE=$(echo "$SEED_RESPONSE" | tail -n1)
SEED_BODY=$(echo "$SEED_RESPONSE" | sed '$d')

if [ "$SEED_CODE" = "200" ]; then
    echo "✓ Seed completed successfully"
    echo "$SEED_BODY" | python3 -m json.tool 2>/dev/null || echo "$SEED_BODY"
else
    echo "✗ Seed failed with HTTP $SEED_CODE"
    echo "$SEED_BODY"
    exit 1
fi
echo ""

# Step 4: Verify
echo "Step 4: Verifying products..."
PRODUCTS=$(curl -s "${STAGING_API}/products?page_size=20")
COUNT=$(echo "$PRODUCTS" | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('products', [])))" 2>/dev/null || echo "0")

echo "✓ Found $COUNT products in staging"
echo ""

if [ "$COUNT" -gt "0" ]; then
    echo "Product list:"
    echo "$PRODUCTS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for i, p in enumerate(data.get('products', []), 1):
        print(f\"{i}. {p['title']} - ₦{p['base_price']}\")
except:
    pass
" 2>/dev/null
fi

echo ""
echo "=========================================="
echo "✓ Staging Database Sync Complete!"
echo "=========================================="
echo ""
echo "Staging now has $COUNT products"
echo "Visit: https://shopsoma-staging.onrender.com/products"
echo ""
