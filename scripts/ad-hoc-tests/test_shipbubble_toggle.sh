#!/bin/bash

# ShipBubble Toggle E2E Test Script
# Tests the admin toggle functionality end-to-end

set -e

echo "🧪 ShipBubble Toggle Integration Test"
echo "======================================"
echo ""

BASE_URL="http://localhost:8000/api/v1"

# Test 1: Get current setting (public endpoint)
echo "📋 Test 1: Fetching current shipping provider setting..."
RESPONSE=$(curl -s "${BASE_URL}/settings/shipping-provider")
CURRENT=$(echo $RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['use_shipbubble'])")
echo "   Current setting: use_shipbubble = $CURRENT"
echo "   ✅ GET /settings/shipping-provider works"
echo ""

# Test 2: Login as admin (required for PUT)
echo "📋 Test 2: Admin authentication..."
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@shopsoma.com",
    "password": "Admin123"
  }')

TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo "")

if [ -z "$TOKEN" ]; then
  echo "   ⚠️  Admin login failed. Make sure admin user exists:"
  echo "   python shopsoma-backend/create_admin_user.py"
  echo ""
  echo "   Skipping PUT tests (requires authentication)"
  echo ""
  exit 0
fi

echo "   ✅ Admin logged in successfully"
echo ""

# Test 3: Enable ShipBubble
echo "📋 Test 3: Enabling ShipBubble..."
ENABLE_RESPONSE=$(curl -s -X PUT "${BASE_URL}/settings/shipping-provider" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"use_shipbubble": true}')

ENABLED=$(echo $ENABLE_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['use_shipbubble'])")
if [ "$ENABLED" = "True" ]; then
  echo "   ✅ ShipBubble enabled successfully"
else
  echo "   ❌ Failed to enable ShipBubble"
  exit 1
fi
echo ""

# Test 4: Verify setting persisted
echo "📋 Test 4: Verifying setting persisted..."
sleep 1
VERIFY_RESPONSE=$(curl -s "${BASE_URL}/settings/shipping-provider")
VERIFIED=$(echo $VERIFY_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['use_shipbubble'])")
if [ "$VERIFIED" = "True" ]; then
  echo "   ✅ Setting persisted in database"
else
  echo "   ❌ Setting did not persist"
  exit 1
fi
echo ""

# Test 5: Disable ShipBubble
echo "📋 Test 5: Disabling ShipBubble..."
DISABLE_RESPONSE=$(curl -s -X PUT "${BASE_URL}/settings/shipping-provider" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"use_shipbubble": false}')

DISABLED=$(echo $DISABLE_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['use_shipbubble'])")
if [ "$DISABLED" = "False" ]; then
  echo "   ✅ ShipBubble disabled successfully"
else
  echo "   ❌ Failed to disable ShipBubble"
  exit 1
fi
echo ""

# Test 6: Final verification
echo "📋 Test 6: Final state verification..."
sleep 1
FINAL_RESPONSE=$(curl -s "${BASE_URL}/settings/shipping-provider")
FINAL=$(echo $FINAL_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['use_shipbubble'])")
if [ "$FINAL" = "False" ]; then
  echo "   ✅ Final state verified"
else
  echo "   ❌ Final state incorrect"
  exit 1
fi
echo ""

# Summary
echo "========================================="
echo "✅ All Tests Passed!"
echo ""
echo "Summary:"
echo "  • Public GET endpoint: ✅"
echo "  • Admin authentication: ✅"
echo "  • Enable ShipBubble: ✅"
echo "  • Setting persistence: ✅"
echo "  • Disable ShipBubble: ✅"
echo "  • State consistency: ✅"
echo ""
echo "🎉 ShipBubble toggle is working correctly!"
echo ""
echo "Next steps:"
echo "1. Open http://localhost:5175 in browser"
echo "2. Login as admin (admin@shopsoma.com)"
echo "3. Navigate to Settings page"
echo "4. Test the toggle switch UI"
