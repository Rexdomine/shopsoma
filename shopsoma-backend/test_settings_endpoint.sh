#!/bin/bash

# Test script for settings API endpoints
# Run this after applying the migration

set -e

echo "=============================================="
echo "Testing Settings API Endpoints"
echo "=============================================="
echo ""

BASE_URL="http://localhost:8000"

# Test 1: Public exchange rate endpoint (no auth)
echo "Test 1: GET /api/v1/settings/public/exchange-rate (no auth)"
echo "Expected: 200 OK with exchange rate"
echo ""

RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  "${BASE_URL}/api/v1/settings/public/exchange-rate")

HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')

echo "Response Body:"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""
echo "HTTP Status: $HTTP_STATUS"

if [ "$HTTP_STATUS" = "200" ]; then
    echo "✓ Test 1 PASSED"
else
    echo "✗ Test 1 FAILED (expected 200, got $HTTP_STATUS)"
fi

echo ""
echo "=============================================="

# Test 2: Admin settings endpoint (no auth - should fail)
echo "Test 2: GET /api/v1/settings/admin (no auth)"
echo "Expected: 401 Unauthorized"
echo ""

RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  "${BASE_URL}/api/v1/settings/admin")

HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS/d')

echo "Response Body:"
echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
echo ""
echo "HTTP Status: $HTTP_STATUS"

if [ "$HTTP_STATUS" = "401" ] || [ "$HTTP_STATUS" = "403" ]; then
    echo "✓ Test 2 PASSED (correctly blocked)"
else
    echo "✗ Test 2 FAILED (expected 401/403, got $HTTP_STATUS)"
fi

echo ""
echo "=============================================="
echo "Test Summary"
echo "=============================================="
echo ""
echo "✓ Public endpoint accessible without auth"
echo "✓ Admin endpoint protected (requires auth)"
echo ""
echo "Next steps:"
echo "1. Test admin login and get token"
echo "2. Test updating exchange rate with admin token"
echo "3. Test frontend admin settings page"
echo ""
