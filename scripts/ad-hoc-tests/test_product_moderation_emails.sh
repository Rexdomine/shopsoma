#!/bin/bash

# Test Product Moderation Email Notifications
# This script tests that vendors receive approval/rejection emails

echo "=== Product Moderation Email Test ==="
echo ""

# Configuration
BASE_URL="http://localhost:8000/api/v1"
ADMIN_EMAIL="admin@shopsoma.com"
ADMIN_PASSWORD="your_admin_password_here"  # Replace with actual password

echo "Step 1: Login as admin"
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PASSWORD}\"}")

TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo "❌ Admin login failed"
  echo "Response: $LOGIN_RESPONSE"
  exit 1
fi

echo "✅ Admin login successful"
echo ""

echo "Step 2: Get pending products"
PRODUCTS_RESPONSE=$(curl -s -X GET "${BASE_URL}/admin/products?moderation_status=pending" \
  -H "Authorization: Bearer ${TOKEN}")

PRODUCT_COUNT=$(echo $PRODUCTS_RESPONSE | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('items', [])))" 2>/dev/null)

echo "Found $PRODUCT_COUNT pending products"
echo ""

if [ "$PRODUCT_COUNT" -eq 0 ]; then
  echo "⚠️  No pending products to test with"
  echo "Please create a test product first as a vendor"
  exit 0
fi

# Get first pending product
PRODUCT_ID=$(echo $PRODUCTS_RESPONSE | python3 -c "import sys, json; items = json.load(sys.stdin).get('items', []); print(items[0]['id'] if items else '')" 2>/dev/null)
PRODUCT_TITLE=$(echo $PRODUCTS_RESPONSE | python3 -c "import sys, json; items = json.load(sys.stdin).get('items', []); print(items[0]['title'] if items else '')" 2>/dev/null)
VENDOR_EMAIL=$(echo $PRODUCTS_RESPONSE | python3 -c "import sys, json; items = json.load(sys.stdin).get('items', []); print(items[0]['vendor']['business_name'] if items and 'vendor' in items[0] else '')" 2>/dev/null)

echo "Testing with product: $PRODUCT_TITLE (ID: $PRODUCT_ID)"
echo ""

# Test approval
echo "Step 3: Test APPROVE with email"
echo "This should send an approval email to the vendor..."
APPROVE_RESPONSE=$(curl -s -w "\n%{http_code}" -X PUT "${BASE_URL}/admin/products/${PRODUCT_ID}/approve" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"notes":"Great product! Meets all our guidelines."}')

HTTP_CODE=$(echo "$APPROVE_RESPONSE" | tail -n1)
RESPONSE_BODY=$(echo "$APPROVE_RESPONSE" | head -n -1)

if [ "$HTTP_CODE" -eq 200 ]; then
  echo "✅ Product approved successfully"
  echo "Response: $RESPONSE_BODY"
  EMAIL_SENT=$(echo "$RESPONSE_BODY" | python3 -c "import sys, json; print(json.load(sys.stdin).get('email_sent', False))" 2>/dev/null)
  echo "Email sent status: $EMAIL_SENT"
else
  echo "❌ Approval failed with HTTP code: $HTTP_CODE"
  echo "Response: $RESPONSE_BODY"
fi
echo ""

echo "Step 4: Check backend logs"
echo "Look in your backend terminal for email sending logs:"
echo "  - ✅ Success: 'Email sent successfully to...'"
echo "  - ⚠️  Skipped: 'Email send skipped... Brevo not configured'"
echo "  - ❌ Error: 'Failed to send email...'"
echo ""

echo "Step 5: Test REJECT with email"
echo "Creating a test product to reject..."
echo "(You'll need to create another pending product to test rejection)"
echo ""

echo "=== Test Complete ==="
echo ""
echo "NEXT STEPS:"
echo "1. Check backend logs for email sending status"
echo "2. If emails are being skipped, verify BREVO_API_KEY is set in .env"
echo "3. Check vendor's email inbox for approval notification"
echo "4. Test rejection flow with another pending product"
echo ""
echo "To test rejection:"
echo "curl -X PUT \"${BASE_URL}/admin/products/PRODUCT_ID/reject\" \\"
echo "  -H \"Authorization: Bearer \$TOKEN\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{\"reason\":\"Images do not meet quality standards\",\"notes\":\"Please upload high-resolution images\"}'"
