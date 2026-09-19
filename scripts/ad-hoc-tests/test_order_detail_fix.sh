#!/bin/bash

echo "🧪 Testing Order Detail Endpoint Fix"
echo "====================================="
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

# Get list of orders to find a valid order ID
echo "2. Getting list of orders..."
ORDERS_RESPONSE=$(curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/orders?page=1&page_size=1")

ORDER_ID=$(echo "$ORDERS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if data.get('orders') and len(data['orders']) > 0:
        print(data['orders'][0]['id'])
    else:
        print('')
except:
    print('')
" 2>/dev/null)

if [ -z "$ORDER_ID" ]; then
    echo "❌ No orders found in the system"
    exit 1
fi

echo "✅ Found order ID: $ORDER_ID"
echo ""

# Test order detail endpoint
echo "3. Testing /admin/orders/{order_id} endpoint..."
DETAIL_RESPONSE=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/orders/$ORDER_ID")

HTTP_CODE=$(echo "$DETAIL_RESPONSE" | tail -n1)
BODY=$(echo "$DETAIL_RESPONSE" | head -n-1)

if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ SUCCESS: Order detail endpoint returned 200"
    echo ""
    echo "Response preview (first 500 chars):"
    echo "${BODY:0:500}..."
    echo ""

    # Check if response has key fields
    HAS_ORDER_NUMBER=$(echo "$BODY" | python3 -c "import sys, json; data=json.load(sys.stdin); print('yes' if 'order_number' in data else 'no')" 2>/dev/null)
    HAS_CUSTOMER=$(echo "$BODY" | python3 -c "import sys, json; data=json.load(sys.stdin); print('yes' if 'customer' in data else 'no')" 2>/dev/null)
    HAS_ITEMS=$(echo "$BODY" | python3 -c "import sys, json; data=json.load(sys.stdin); print('yes' if 'items' in data else 'no')" 2>/dev/null)

    echo "Response structure validation:"
    echo "  - Has order_number: $HAS_ORDER_NUMBER"
    echo "  - Has customer: $HAS_CUSTOMER"
    echo "  - Has items: $HAS_ITEMS"
else
    echo "❌ FAILED: Order detail endpoint returned $HTTP_CODE"
    echo ""
    echo "Full error response:"
    echo "$BODY"
fi
echo ""

echo "====================================="
if [ "$HTTP_CODE" = "200" ]; then
    echo "✅ Order Detail Fix Verified"
else
    echo "❌ Order Detail Fix Failed"
fi
echo ""
echo "Next steps:"
echo "1. Open http://localhost:5174/admin/orders in your browser"
echo "2. Click 'View' on any order"
echo "3. Verify the order detail page displays correctly"
