#!/bin/bash

echo "Testing Vendor Login..."
echo ""

# Test login
response=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "vendor@shopsoma.com",
    "password": "vendor123"
  }')

echo "Login Response:"
echo "$response" | python3 -m json.tool

echo ""
echo "---"
echo ""

# Extract access token
access_token=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))")

if [ -n "$access_token" ]; then
  echo "✅ Login successful! Access token obtained."
  echo ""
  echo "Testing /auth/me endpoint..."

  me_response=$(curl -s -X GET "http://localhost:8000/api/v1/auth/me" \
    -H "Authorization: Bearer $access_token")

  echo "$me_response" | python3 -m json.tool

  echo ""
  echo "---"
  echo ""
  echo "Testing /vendor/profile endpoint..."

  vendor_response=$(curl -s -X GET "http://localhost:8000/api/v1/vendor/profile" \
    -H "Authorization: Bearer $access_token")

  echo "$vendor_response" | python3 -m json.tool
else
  echo "❌ Login failed!"
fi
