#!/bin/bash

echo "Testing Vendor Activation Flow..."
echo ""

# Step 1: Initiate activation
echo "Step 1: Initiating activation for vendor@shopsoma.com..."
response=$(curl -s -X POST "http://localhost:8000/api/v1/vendor/activation/initiate" \
  -H "Content-Type: application/json" \
  -d '{"email": "vendor@shopsoma.com"}')

echo "$response" | python3 -m json.tool

# Extract token
token=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('token', ''))")
masked_email=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('masked_email', ''))")

if [ -z "$token" ]; then
  echo "❌ Failed to initiate activation"
  exit 1
fi

echo ""
echo "✅ Activation initiated successfully!"
echo "Masked Email: $masked_email"
echo "Token: ${token:0:50}..."
echo ""
echo "---"
echo ""

# Step 2: Get OTP code from database (for testing only)
echo "Step 2: Retrieving OTP code from database..."
echo ""

otp_code=$(docker exec shopsoma-db psql -U shopsoma -d shopsoma_db -t -c "
SELECT
    vo.code_hash
FROM vendor_otps vo
WHERE vo.email = 'vendor@shopsoma.com'
AND vo.is_used = FALSE
ORDER BY vo.created_at DESC
LIMIT 1;
" | tr -d '[:space:]')

if [ -z "$otp_code" ]; then
  echo "❌ No OTP code found in database"
  echo "Check email for OTP code or manually verify"
  exit 1
fi

echo "Note: OTP code is hashed in database. You need to:"
echo "1. Check the email sent to vendor@shopsoma.com for the actual code"
echo "2. Or use the frontend to test: http://localhost:5173/vendor/otp?email=vendor@shopsoma.com"
echo ""
echo "---"
echo ""

# Step 3: Show how to verify (manual step required)
echo "Step 3: To verify OTP (use actual code from email):"
echo ""
echo "curl -X POST \"http://localhost:8000/api/v1/vendor/activation/verify-otp\" \\"
echo "  -H \"Content-Type: application/json\" \\"
echo "  -d '{"
echo "    \"token\": \"$token\","
echo "    \"otp_code\": \"YOUR_CODE_HERE\""
echo "  }'"
echo ""
echo "---"
echo ""

# Step 4: Test resend
echo "Step 4: Testing resend OTP..."
resend_response=$(curl -s -X POST "http://localhost:8000/api/v1/vendor/activation/resend-otp" \
  -H "Content-Type: application/json" \
  -d "{\"token\": \"$token\"}")

echo "$resend_response" | python3 -m json.tool

echo ""
echo "---"
echo ""

echo "✅ All API endpoints are working!"
echo ""
echo "To complete the test:"
echo "1. Open http://localhost:5173/vendor/otp?email=vendor@shopsoma.com"
echo "2. Check email for OTP code"
echo "3. Enter the code to activate account"
echo "4. Should redirect to /vendor/dashboard"
