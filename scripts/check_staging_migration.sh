#!/bin/bash
# Check if cart tables exist on staging

STAGING_API="https://shopsoma-staging-api.onrender.com/api/v1"

echo "=========================================="
echo "Checking Staging Migration Status"
echo "=========================================="
echo ""

# Test cart endpoint
echo "Testing cart endpoint..."
CART_RESPONSE=$(curl -s -w "\n%{http_code}" "${STAGING_API}/cart" -H "X-Session-ID: test-123")
CART_CODE=$(echo "$CART_RESPONSE" | tail -n1)
CART_BODY=$(echo "$CART_RESPONSE" | sed '$d')

if [ "$CART_CODE" = "200" ]; then
    echo "✓ Cart tables exist and endpoint is working!"
    echo "$CART_BODY" | python3 -m json.tool 2>/dev/null || echo "$CART_BODY"
else
    echo "✗ Cart endpoint not working (HTTP $CART_CODE)"
    echo "$CART_BODY"
    echo ""
    echo "Migration may not have been applied yet."
    echo "Run 'alembic upgrade head' on staging via Render shell."
fi

echo ""
echo "=========================================="
