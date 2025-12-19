#!/bin/bash

# ShipBubble API Key Test Script
# Tests if your ShipBubble API key is working

echo "🔑 ShipBubble API Key Test"
echo "=========================="
echo ""

# Check if .env file exists
if [ ! -f "shopsoma-backend/.env" ]; then
  echo "❌ Error: .env file not found at shopsoma-backend/.env"
  exit 1
fi

# Extract API key from .env
API_KEY=$(grep "SHIPBUBBLE_API_KEY" shopsoma-backend/.env | cut -d '=' -f2)

if [ -z "$API_KEY" ]; then
  echo "❌ Error: SHIPBUBBLE_API_KEY not found in .env file"
  exit 1
fi

echo "📋 API Key Found: ${API_KEY:0:20}..."
echo ""

# Test 1: Create Address
echo "📋 Test 1: Creating test address in ShipBubble..."
CREATE_RESPONSE=$(curl -s -X POST "https://api.shipbubble.com/v1/addresses/create" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $API_KEY" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "phone": "+2348000000000",
    "address": "123 Test Street",
    "city": "Lagos",
    "state": "Lagos",
    "country": "Nigeria",
    "postal_code": "100001"
  }')

# Check response
if echo "$CREATE_RESPONSE" | grep -q "code"; then
  # Extract address code
  ADDRESS_CODE=$(echo $CREATE_RESPONSE | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('data', {}).get('code', ''))" 2>/dev/null || echo "")

  if [ -n "$ADDRESS_CODE" ]; then
    echo "   ✅ Success! Address created with code: $ADDRESS_CODE"
    echo "   📊 Response: $CREATE_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CREATE_RESPONSE"
  else
    echo "   ⚠️  Response received but no address code found"
    echo "   📊 Response: $CREATE_RESPONSE"
  fi
elif echo "$CREATE_RESPONSE" | grep -qi "unauthorized\|invalid\|authentication"; then
  echo "   ❌ Authentication failed!"
  echo "   📊 Response: $CREATE_RESPONSE"
  echo ""
  echo "   Possible reasons:"
  echo "   1. API key not activated in ShipBubble dashboard"
  echo "   2. Invalid or expired API key"
  echo "   3. Incorrect API key format"
  echo ""
  echo "   Actions to take:"
  echo "   1. Login to https://shipbubble.com"
  echo "   2. Go to Settings → API Keys"
  echo "   3. Ensure API access is enabled"
  echo "   4. Copy the correct API key to .env"
  exit 1
else
  echo "   ⚠️  Unexpected response from ShipBubble API"
  echo "   📊 Response: $CREATE_RESPONSE"
fi

echo ""

# Test 2: Check API Status
echo "📋 Test 2: Checking ShipBubble API status..."
STATUS_RESPONSE=$(curl -s -X GET "https://api.shipbubble.com/v1/health" \
  -H "Authorization: Bearer $API_KEY" 2>&1)

if [ $? -eq 0 ]; then
  echo "   ✅ ShipBubble API is reachable"
else
  echo "   ⚠️  Could not reach ShipBubble API"
  echo "   Check your internet connection"
fi

echo ""
echo "========================================="
echo ""

# Summary
if [ -n "$ADDRESS_CODE" ]; then
  echo "✅ API Key Test: PASSED"
  echo ""
  echo "Your ShipBubble API key is working correctly!"
  echo "You can now use ShipBubble for shipping rates."
  echo ""
  echo "Next steps:"
  echo "1. Enable ShipBubble in Admin Settings"
  echo "2. Test checkout with real shipping addresses"
else
  echo "❌ API Key Test: FAILED"
  echo ""
  echo "Your ShipBubble API key is not working."
  echo ""
  echo "To fix this:"
  echo "1. Visit: https://shipbubble.com/login"
  echo "2. Go to: Settings → API Keys"
  echo "3. Enable API access for your account"
  echo "4. Copy the new API key"
  echo "5. Update SHIPBUBBLE_API_KEY in shopsoma-backend/.env"
  echo "6. Run this test again"
fi
