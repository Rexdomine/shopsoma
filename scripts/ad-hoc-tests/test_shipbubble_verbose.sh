#!/bin/bash

# Verbose ShipBubble API Test

API_KEY=$(grep "SHIPBUBBLE_API_KEY" shopsoma-backend/.env | cut -d '=' -f2)

echo "Testing ShipBubble API..."
echo "API Key: ${API_KEY:0:20}..."
echo ""

curl -v -X POST "https://api.shipbubble.com/v1/addresses/create" \
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
  }' 2>&1
