#!/bin/bash

# Simplified Single Product Size/Color/Stock Test
# Tests the complete flow from creation to verification

echo "========================================="
echo "Single Product Size/Color/Stock Test"
echo "========================================="
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Step 1: Login as vendor
echo "Step 1: Logging in as vendor..."
LOGIN_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "vendor@shopsoma.com", "password": "vendor123"}')

TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo -e "${RED}✗ Login failed${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Login successful${NC}"
echo ""

# Step 2: Get a category
echo "Step 2: Getting category..."
CATEGORIES=$(curl -s "http://localhost:8000/api/v1/categories")
CATEGORY_ID=$(echo $CATEGORIES | python3 -c "import sys, json; cats = json.load(sys.stdin); print(cats[0]['id'] if cats else '')" 2>/dev/null)

if [ -z "$CATEGORY_ID" ]; then
  echo -e "${RED}✗ No categories found${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Category ID: $CATEGORY_ID${NC}"
echo ""

# Step 3: Create test single product
echo "Step 3: Creating single product..."
TIMESTAMP=$(date +%s)
PRODUCT_TITLE="Test Single $TIMESTAMP"

CREATE_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/products" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"$PRODUCT_TITLE\",
    \"description\": \"Testing single product with sizes and color\",
    \"base_price\": 25000,
    \"currency\": \"NGN\",
    \"total_stock\": 150,
    \"category_id\": \"$CATEGORY_ID\",
    \"status\": \"active\",
    \"product_type\": \"single\",
    \"fabric_composition\": \"100% Cotton - Soft and breathable\",
    \"care_instructions\": \"Hand wash cold. Do not bleach.\",
    \"made_to_order\": true,
    \"made_to_order_timeline\": \"Ships in 2-3 weeks\",
    \"variations\": [
      {
        \"title\": \"$PRODUCT_TITLE (Orange)\",
        \"type\": \"color\",
        \"color_hex\": \"#FF5733\",
        \"is_active\": true,
        \"sizes\": [
          { \"size\": \"S\", \"stock\": 50 },
          { \"size\": \"M\", \"stock\": 50 },
          { \"size\": \"L\", \"stock\": 50 }
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
  }")

PRODUCT_ID=$(echo $CREATE_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

if [ -z "$PRODUCT_ID" ]; then
  echo -e "${RED}✗ Failed to create product${NC}"
  echo "Response:"
  echo $CREATE_RESPONSE | python3 -m json.tool
  exit 1
fi

echo -e "${GREEN}✓ Product created${NC}"
echo -e "  ID: ${YELLOW}$PRODUCT_ID${NC}"
echo ""

# Step 4: Retrieve and verify product
echo "Step 4: Verifying product data..."
sleep 1
PRODUCT=$(curl -s "http://localhost:8000/api/v1/products/$PRODUCT_ID")

echo ""
echo "=== VERIFICATION RESULTS ==="
echo ""

# Extract fields
TITLE=$(echo $PRODUCT | python3 -c "import sys, json; print(json.load(sys.stdin).get('title', 'MISSING'))")
TYPE=$(echo $PRODUCT | python3 -c "import sys, json; print(json.load(sys.stdin).get('product_type', 'MISSING'))")
FABRIC=$(echo $PRODUCT | python3 -c "import sys, json; d = json.load(sys.stdin); print(d.get('fabric_composition', 'MISSING'))")
CARE=$(echo $PRODUCT | python3 -c "import sys, json; d = json.load(sys.stdin); print(d.get('care_instructions', 'MISSING'))")
MTO=$(echo $PRODUCT | python3 -c "import sys, json; print(json.load(sys.stdin).get('made_to_order', False))")
VAR_COUNT=$(echo $PRODUCT | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('variations', [])))")
VARIANT_COUNT=$(echo $PRODUCT | python3 -c "import sys, json; print(len(json.load(sys.stdin).get('variants', [])))")

# Test results
PASSED=0
TOTAL=0

# Test 1: Product type
TOTAL=$((TOTAL + 1))
if [ "$TYPE" = "single" ]; then
  echo -e "${GREEN}✓${NC} Product type: single"
  PASSED=$((PASSED + 1))
else
  echo -e "${RED}✗${NC} Product type: $TYPE (expected: single)"
fi

# Test 2: Fabric composition
TOTAL=$((TOTAL + 1))
if [[ "$FABRIC" == *"Cotton"* ]]; then
  echo -e "${GREEN}✓${NC} Fabric composition: saved"
  PASSED=$((PASSED + 1))
else
  echo -e "${RED}✗${NC} Fabric composition: $FABRIC"
fi

# Test 3: Care instructions
TOTAL=$((TOTAL + 1))
if [[ "$CARE" == *"wash"* ]]; then
  echo -e "${GREEN}✓${NC} Care instructions: saved"
  PASSED=$((PASSED + 1))
else
  echo -e "${RED}✗${NC} Care instructions: $CARE"
fi

# Test 4: Made to order
TOTAL=$((TOTAL + 1))
if [ "$MTO" = "True" ]; then
  echo -e "${GREEN}✓${NC} Made to order: True"
  PASSED=$((PASSED + 1))
else
  echo -e "${RED}✗${NC} Made to order: $MTO"
fi

# Test 5: Variation created
TOTAL=$((TOTAL + 1))
if [ "$VAR_COUNT" = "1" ]; then
  echo -e "${GREEN}✓${NC} Variation created: 1"
  PASSED=$((PASSED + 1))

  # Check variation details
  VAR_TITLE=$(echo $PRODUCT | python3 -c "import sys, json; d = json.load(sys.stdin); print(d['variations'][0]['title'])")
  VAR_COLOR=$(echo $PRODUCT | python3 -c "import sys, json; d = json.load(sys.stdin); print(d['variations'][0]['color_hex'])")
  SIZE_COUNT=$(echo $PRODUCT | python3 -c "import sys, json; d = json.load(sys.stdin); print(len(d['variations'][0].get('size_stocks', [])))")

  echo "    Title: $VAR_TITLE"
  echo "    Color: $VAR_COLOR"
  echo "    Size Stocks: $SIZE_COUNT"

  # Test 6: Size stocks
  TOTAL=$((TOTAL + 1))
  if [ "$SIZE_COUNT" = "3" ]; then
    echo -e "${GREEN}✓${NC} Size stocks created: 3 (S, M, L)"
    PASSED=$((PASSED + 1))

    # Show size stocks
    echo $PRODUCT | python3 -c "
import sys, json
d = json.load(sys.stdin)
for s in d['variations'][0].get('size_stocks', []):
    print(f'      {s[\"size\"]}: {s[\"stock\"]} units')
"
  else
    echo -e "${RED}✗${NC} Size stocks: $SIZE_COUNT (expected 3)"
  fi
else
  echo -e "${RED}✗${NC} Variation count: $VAR_COUNT (expected 1)"
  TOTAL=$((TOTAL + 1))
fi

# Test 7: Auto-generated variants
TOTAL=$((TOTAL + 1))
if [ "$VARIANT_COUNT" = "3" ]; then
  echo -e "${GREEN}✓${NC} Auto-generated variants: 3"
  PASSED=$((PASSED + 1))

  echo $PRODUCT | python3 -c "
import sys, json
d = json.load(sys.stdin)
for v in d.get('variants', []):
    print(f'    - {v.get(\"color\", \"N/A\")} / {v.get(\"size\", \"N/A\")} / {v.get(\"stock\", 0)} units')
"
else
  echo -e "${RED}✗${NC} Auto-generated variants: $VARIANT_COUNT (expected 3)"
fi

echo ""
echo "========================================="
if [ $PASSED -eq $TOTAL ]; then
  echo -e "${GREEN}✅ ALL TESTS PASSED ($PASSED/$TOTAL)${NC}"
  echo ""
  echo "Single product size/color/stock is working!"
  echo ""
  echo "View this product:"
  echo "  Frontend: http://localhost:5173/products/$PRODUCT_ID"
  echo "  Admin: http://localhost:5173/admin/products"
  echo "  Vendor: http://localhost:5173/vendor/products"
else
  echo -e "${YELLOW}⚠️  SOME TESTS FAILED ($PASSED/$TOTAL)${NC}"
fi
echo "========================================="
echo ""
