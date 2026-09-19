#!/bin/bash

# Test the restore store endpoint

# Admin login credentials
ADMIN_EMAIL="admin@shopsoma.com"
ADMIN_PASSWORD="admin123"

# Vendor ID to restore (Kester Club)
VENDOR_ID="10b8fc3b-bc09-4d8a-90f4-d400dbb39268"

echo "🔐 Logging in as admin..."
LOGIN_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}")

echo "Login response: $LOGIN_RESPONSE"

# Extract access token
ACCESS_TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$ACCESS_TOKEN" ]; then
  echo "❌ Failed to get access token"
  exit 1
fi

echo "✅ Logged in successfully"
echo ""

echo "📋 Checking vendor status before restore..."
VENDOR_BEFORE=$(curl -s -X GET "http://localhost:8000/api/v1/admin/vendors/$VENDOR_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "Vendor before restore:"
echo $VENDOR_BEFORE | python3 -m json.tool | grep -E "(business_name|store_active|store_deleted_at)"
echo ""

echo "🔄 Restoring vendor store..."
RESTORE_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/admin/vendors/$VENDOR_ID/restore" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "Restore response:"
echo $RESTORE_RESPONSE | python3 -m json.tool
echo ""

echo "📋 Checking vendor status after restore..."
VENDOR_AFTER=$(curl -s -X GET "http://localhost:8000/api/v1/admin/vendors/$VENDOR_ID" \
  -H "Authorization: Bearer $ACCESS_TOKEN")

echo "Vendor after restore:"
echo $VENDOR_AFTER | python3 -m json.tool | grep -E "(business_name|store_active|store_deleted_at)"
echo ""

echo "✅ Test complete!"
