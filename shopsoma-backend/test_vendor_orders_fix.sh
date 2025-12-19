#!/bin/bash

# Test vendor orders endpoint with search parameter
# This should now work (200 OK) instead of returning 403 Forbidden

# Get vendor token (replace with actual token from your session)
TOKEN="${VENDOR_TOKEN:-eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...}"

echo "Testing vendor orders endpoint..."
echo ""

# Test 1: Without search parameter
echo "1. Test without search parameter:"
curl -s -w "\nHTTP Status: %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/vendor/orders?page=1&page_size=20" \
  | head -20
echo ""
echo "---"
echo ""

# Test 2: With empty search parameter (this was causing 403)
echo "2. Test with empty search parameter (this was failing before):"
curl -s -w "\nHTTP Status: %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/vendor/orders?page=1&page_size=20&search=" \
  | head -20
echo ""
echo "---"
echo ""

# Test 3: With actual search query
echo "3. Test with search query:"
curl -s -w "\nHTTP Status: %{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/vendor/orders?page=1&page_size=20&search=SHP" \
  | head -20
echo ""

echo "If all tests return 200 OK (or 401 if token expired), the fix is working!"
