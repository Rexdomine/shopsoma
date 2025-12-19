#!/bin/bash
# Test cart functionality on staging

STAGING_URL="https://shopsoma-staging.onrender.com"

echo "=========================================="
echo "Testing Staging Cart Functionality"
echo "=========================================="
echo ""

# Check if staging is accessible
echo "1. Checking if staging site is accessible..."
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$STAGING_URL")
if [ "$RESPONSE" = "200" ]; then
    echo "✓ Staging site is accessible (HTTP $RESPONSE)"
else
    echo "✗ Staging site returned HTTP $RESPONSE"
    exit 1
fi

echo ""
echo "2. Checking for cart-related JavaScript files..."
# Check if cart store is being loaded
CART_STORE=$(curl -s "$STAGING_URL" | grep -o "cartStore" | head -1)
if [ -n "$CART_STORE" ]; then
    echo "✓ Cart store reference found in HTML"
else
    echo "⚠ Cart store reference not found in HTML (might be in bundled JS)"
fi

echo ""
echo "3. Deployment Info:"
echo "   - Frontend URL: $STAGING_URL"
echo "   - Latest commit: $(git log origin/develop --oneline -1)"
echo ""
echo "=========================================="
echo "Manual Testing Required:"
echo "=========================================="
echo "1. Open $STAGING_URL in your browser"
echo "2. Open browser DevTools (F12) and go to Console tab"
echo "3. Navigate to a product page"
echo "4. Select size and color"
echo "5. Click 'Add to Bag'"
echo "6. Check for any error messages in console"
echo "7. Check if cart icon shows item count"
echo ""
echo "If you see errors, please share them for debugging."
echo "=========================================="
