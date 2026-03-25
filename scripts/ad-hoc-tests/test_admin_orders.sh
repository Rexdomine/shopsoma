#!/bin/bash

echo "🧪 Testing Admin Orders Endpoints with Authentication"
echo "======================================================"
echo ""

# Get admin token
echo "1. Getting admin access token..."
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@shopsoma.com","password":"Admin123"}')

TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "❌ Failed to get access token"
    echo "   Response: $LOGIN_RESPONSE"
    exit 1
fi

echo "✅ Access token obtained"
echo ""

# Test orders stats endpoint
echo "2. Testing /admin/orders/stats endpoint..."
STATS_RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/orders/stats")

HTTP_CODE=$(echo "$STATS_RESPONSE" | tail -n1)
BODY=$(echo "$STATS_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ SUCCESS: Stats endpoint returned 200"
    echo "   Response: $BODY"
else
    echo "❌ FAILED: Stats endpoint returned $HTTP_CODE"
    echo "   Response: $BODY"
fi
echo ""

# Test orders list endpoint
echo "3. Testing /admin/orders list endpoint..."
LIST_RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/orders?page=1&page_size=20")

HTTP_CODE=$(echo "$LIST_RESPONSE" | tail -n1)
BODY=$(echo "$LIST_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ SUCCESS: Orders list endpoint returned 200"
    echo "   Response (first 500 chars): ${BODY:0:500}..."
else
    echo "❌ FAILED: Orders list endpoint returned $HTTP_CODE"
    echo "   Response: $BODY"
fi
echo ""

echo "======================================================"
echo "✅ Admin Orders Enum Fix Testing Complete"
echo ""
echo "Next steps:"
echo "1. Login to admin dashboard at http://localhost:5173/login"
echo "2. Email: admin@shopsoma.com"
echo "3. Password: Admin123"
echo "4. Navigate to Orders page"
echo "5. Verify orders load without errors"
