#!/bin/bash

# Test Product Deletion Fix
# This script tests that deleted (archived) products don't appear in vendor's product list

echo "=== Product Deletion Test ==="
echo ""

# Configuration
BASE_URL="http://localhost:8000/api/v1"
VENDOR_EMAIL="vendor@shopsoma.com"
VENDOR_PASSWORD="your_password_here"  # Replace with actual password

echo "Step 1: Login as vendor"
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${VENDOR_EMAIL}\",\"password\":\"${VENDOR_PASSWORD}\"}")

TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ Login failed"
  echo "Response: $LOGIN_RESPONSE"
  exit 1
fi

echo "✅ Login successful"
echo ""

echo "Step 2: Get products list BEFORE deletion"
PRODUCTS_BEFORE=$(curl -s -X GET "${BASE_URL}/products" \
  -H "Authorization: Bearer ${TOKEN}")

PRODUCT_COUNT_BEFORE=$(echo $PRODUCTS_BEFORE | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('items', [])))" 2>/dev/null)

echo "Products count before: $PRODUCT_COUNT_BEFORE"
echo ""

# Get first product ID
PRODUCT_ID=$(echo $PRODUCTS_BEFORE | python3 -c "import sys, json; items = json.load(sys.stdin).get('items', []); print(items[0]['id'] if items else '')" 2>/dev/null)

if [ -z "$PRODUCT_ID" ]; then
  echo "❌ No products found to delete"
  exit 1
fi

echo "Step 3: Delete product $PRODUCT_ID"
DELETE_RESPONSE=$(curl -s -w "\n%{http_code}" -X DELETE "${BASE_URL}/products/${PRODUCT_ID}" \
  -H "Authorization: Bearer ${TOKEN}")

HTTP_CODE=$(echo "$DELETE_RESPONSE" | tail -n1)

if [ "$HTTP_CODE" -eq 204 ]; then
  echo "✅ Delete request successful (HTTP 204)"
else
  echo "❌ Delete failed with HTTP code: $HTTP_CODE"
  echo "Response: $(echo "$DELETE_RESPONSE" | head -n -1)"
  exit 1
fi
echo ""

echo "Step 4: Get products list AFTER deletion"
PRODUCTS_AFTER=$(curl -s -X GET "${BASE_URL}/products" \
  -H "Authorization: Bearer ${TOKEN}")

PRODUCT_COUNT_AFTER=$(echo $PRODUCTS_AFTER | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('items', [])))" 2>/dev/null)

echo "Products count after: $PRODUCT_COUNT_AFTER"
echo ""

echo "Step 5: Verify product is not in list"
DELETED_PRODUCT_EXISTS=$(echo $PRODUCTS_AFTER | python3 -c "import sys, json; items = json.load(sys.stdin).get('items', []); print('yes' if any(p['id'] == '${PRODUCT_ID}' for p in items) else 'no')" 2>/dev/null)

if [ "$DELETED_PRODUCT_EXISTS" == "no" ]; then
  echo "✅ PASS: Deleted product NOT in list (as expected)"
  echo "✅ Product count decreased from $PRODUCT_COUNT_BEFORE to $PRODUCT_COUNT_AFTER"
else
  echo "❌ FAIL: Deleted product STILL in list"
  exit 1
fi

echo ""
echo "=== All tests passed! ==="
