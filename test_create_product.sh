#!/bin/bash

# Get token
TOKEN=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "vendor@shopsoma.com", "password": "vendor123"}' | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# Get category
CATEGORY_ID=$(curl -s "http://localhost:8000/api/v1/categories" | \
  python3 -c "import sys, json; print(json.load(sys.stdin)[0]['id'])")

# Create product
TIMESTAMP=$(date +%s)
curl -s -X POST "http://localhost:8000/api/v1/products" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"Test Single Product $TIMESTAMP\",
    \"description\": \"Testing single product creation\",
    \"base_price\": 25000,
    \"currency\": \"NGN\",
    \"total_stock\": 150,
    \"category_id\": \"$CATEGORY_ID\",
    \"status\": \"active\",
    \"product_type\": \"single\",
    \"fabric_composition\": \"100% Cotton - Soft\",
    \"care_instructions\": \"Hand wash cold\",
    \"made_to_order\": true,
    \"made_to_order_timeline\": \"Ships in 2-3 weeks\",
    \"variations\": [
      {
        \"title\": \"Test Single Product $TIMESTAMP (Orange)\",
        \"type\": \"color\",
        \"color_hex\": \"#FF5733\",
        \"is_active\": true,
        \"sizes\": [
          {\"size\": \"S\", \"stock\": 50},
          {\"size\": \"M\", \"stock\": 50},
          {\"size\": \"L\", \"stock\": 50}
        ]
      }
    ],
    \"images\": [
      {
        \"image_url\": \"https://via.placeholder.com/800/FF5733/FFFFFF\",
        \"is_primary\": true,
        \"display_order\": 0
      }
    ]
  }" | python3 -m json.tool
