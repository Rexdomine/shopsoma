#!/bin/bash

# Test script to verify enum migration fix
# This script tests that the API endpoints no longer throw 500 errors

echo "🧪 Testing Enum Migration Fix"
echo "================================"
echo ""

BASE_URL="http://localhost:8000/api/v1"

# Test 1: Admin Orders Stats (should return 401, not 500)
echo "Test 1: Admin Orders Stats Endpoint"
echo "------------------------------------"
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/admin/orders/stats")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "200" ]; then
    echo "✅ PASS: Received HTTP $HTTP_CODE (not 500)"
    echo "   Response: $BODY"
else
    echo "❌ FAIL: Received HTTP $HTTP_CODE (expected 401 or 200, not 500)"
    echo "   Response: $BODY"
fi
echo ""

# Test 2: Admin Orders List (should return 401, not 500)
echo "Test 2: Admin Orders List Endpoint"
echo "------------------------------------"
RESPONSE=$(curl -s -w "\n%{http_code}" "$BASE_URL/admin/orders?page=1&page_size=20")
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "200" ]; then
    echo "✅ PASS: Received HTTP $HTTP_CODE (not 500)"
    echo "   Response: $BODY"
else
    echo "❌ FAIL: Received HTTP $HTTP_CODE (expected 401 or 200, not 500)"
    echo "   Response: $BODY"
fi
echo ""

# Test 3: Check for old enum references in code
echo "Test 3: Verify No Old Enum References in Code"
echo "-----------------------------------------------"
cd shopsoma-backend
OLD_REFS=$(grep -r "FulfillmentStatus\.\(PENDING\|PROCESSING\|SHIPPED\)" app/api/v1/ || true)

if [ -z "$OLD_REFS" ]; then
    echo "✅ PASS: No old enum references found in API code"
else
    echo "❌ FAIL: Found old enum references:"
    echo "$OLD_REFS"
fi
echo ""

echo "================================"
echo "✅ Enum Migration Fix Tests Complete"
echo ""
echo "Next steps:"
echo "1. Login to admin dashboard with valid credentials"
echo "2. Navigate to Orders page"
echo "3. Verify orders load without errors"
echo "4. Check that order statistics display correctly"
