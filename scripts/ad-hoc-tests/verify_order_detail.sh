#!/bin/bash

# Simple verification script
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@shopsoma.com","password":"Admin123"}' | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

echo "Testing order detail endpoint..."
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/orders/790ff9e3-5e24-490c-bac2-849200a4ddfe" | \
  python3 -m json.tool | head -50

echo ""
echo "✅ If you see JSON output above with order details, the fix is working!"
