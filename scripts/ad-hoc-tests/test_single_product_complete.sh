#!/bin/bash

# Test Single Product Size/Color/Stock Capture - Complete End-to-End Test
# This script tests the complete flow from upload to display

echo "========================================="
echo "Single Product Size/Color/Stock Test"
echo "========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Login as vendor
echo "Step 1: Logging in as vendor..."
LOGIN_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "vendor@shopsoma.com",
    "password": "vendor123"
  }')

TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
  echo -e "${RED}✗ Login failed${NC}"
  echo "Response: $LOGIN_RESPONSE"
  exit 1
fi

echo -e "${GREEN}✓ Login successful${NC}"
echo ""

# Step 2: Get vendor ID
echo "Step 2: Getting vendor information..."
VENDOR_INFO=$(curl -s -X GET "http://localhost:8000/api/v1/vendors/me" \
  -H "Authorization: Bearer $TOKEN")

VENDOR_ID=$(echo $VENDOR_INFO | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

if [ -z "$VENDOR_ID" ]; then
  echo -e "${RED}✗ Failed to get vendor ID${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Vendor ID: $VENDOR_ID${NC}"
echo ""

# Step 3: Get a category ID
echo "Step 3: Getting category ID..."
CATEGORIES=$(curl -s "http://localhost:8000/api/v1/categories")
CATEGORY_ID=$(echo $CATEGORIES | python3 -c "import sys, json; cats = json.load(sys.stdin); print(cats[0]['id'] if cats else '')" 2>/dev/null)

if [ -z "$CATEGORY_ID" ]; then
  echo -e "${RED}✗ Failed to get category${NC}"
  exit 1
fi

echo -e "${GREEN}✓ Category ID: $CATEGORY_ID${NC}"
echo ""

# Step 4: Create test single product with size/color/stock
echo "Step 4: Creating single product with size/color/stock..."
TIMESTAMP=$(date +%s)
PRODUCT_TITLE="Test Single Product $TIMESTAMP"

CREATE_RESPONSE=$(curl -s -X POST "http://localhost:8000/api/v1/products" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"title\": \"$PRODUCT_TITLE\",
    \"description\": \"Testing single product size/color/stock capture\",
    \"base_price\": 25000,
    \"currency\": \"NGN\",
    \"total_stock\": 150,
    \"category_id\": \"$CATEGORY_ID\",
    \"status\": \"active\",
    \"product_type\": \"single\",
    \"fabric_composition\": \"100% Cotton - Soft and breathable\",
    \"care_instructions\": \"Hand wash cold. Do not bleach. Lay flat to dry.\",
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
        \"image_url\": \"https://via.placeholder.com/800x1200/FF5733/FFFFFF?text=Test+Product\",
        \"is_primary\": true,
        \"display_order\": 0
      }
    ]
  }")

PRODUCT_ID=$(echo $CREATE_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

if [ -z "$PRODUCT_ID" ]; then
  echo -e "${RED}✗ Failed to create product${NC}"
  echo "Response: $CREATE_RESPONSE"
  exit 1
fi

echo -e "${GREEN}✓ Product created successfully${NC}"
echo -e "  Product ID: ${YELLOW}$PRODUCT_ID${NC}"
echo -e "  Product Title: ${YELLOW}$PRODUCT_TITLE${NC}"
echo ""

# Step 5: Verify product data in API response
echo "Step 5: Verifying product data..."
PRODUCT_DATA=$(curl -s "http://localhost:8000/api/v1/products/$PRODUCT_ID")

echo ""
echo "=== Product Data Verification ==="
echo ""

# Check basic fields
TITLE=$(echo $PRODUCT_DATA | python3 -c "import sys, json; print(json.load(sys.stdin).get('title', 'MISSING'))")
echo "Title: $TITLE"

PRODUCT_TYPE=$(echo $PRODUCT_DATA | python3 -c "import sys, json; print(json.load(sys.stdin).get('product_type', 'MISSING'))")
echo "Product Type: $PRODUCT_TYPE"

FABRIC=$(echo $PRODUCT_DATA | python3 -c "import sys, json; print(json.load(sys.stdin).get('fabric_composition', 'MISSING'))")
echo "Fabric Composition: $FABRIC"

CARE=$(echo $PRODUCT_DATA | python3 -c "import sys, json; print(json.load(sys.stdin).get('care_instructions', 'MISSING'))")
echo "Care Instructions: $CARE"

MADE_TO_ORDER=$(echo $PRODUCT_DATA | python3 -c "import sys, json; print(json.load(sys.stdin).get('made_to_order', 'MISSING'))")
echo "Made to Order: $MADE_TO_ORDER"

TIMELINE=$(echo $PRODUCT_DATA | python3 -c "import sys, json; print(json.load(sys.stdin).get('made_to_order_timeline', 'MISSING'))")
echo "Timeline: $TIMELINE"

# Check variations
echo ""
echo "=== Variations Check ==="
VARIATION_COUNT=$(echo $PRODUCT_DATA | python3 -c "import sys, json; data = json.load(sys.stdin); print(len(data.get('variations', [])))")
echo "Variation Count: $VARIATION_COUNT"

if [ "$VARIATION_COUNT" = "1" ]; then
  echo -e "${GREEN}✓ Variation exists${NC}"

  VARIATION_TITLE=$(echo $PRODUCT_DATA | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['variations'][0]['title'])")
  echo "  Title: $VARIATION_TITLE"

  COLOR_HEX=$(echo $PRODUCT_DATA | python3 -c "import sys, json; data = json.load(sys.stdin); print(data['variations'][0]['color_hex'])")
  echo "  Color: $COLOR_HEX"

  SIZE_STOCKS=$(echo $PRODUCT_DATA | python3 -c "import sys, json; data = json.load(sys.stdin); sizes = data['variations'][0].get('size_stocks', []); print(', '.join([f\"{s['size']}: {s['stock']}\" for s in sizes]))")
  echo "  Size Stocks: $SIZE_STOCKS"
else
  echo -e "${RED}✗ No variations found${NC}"
fi

# Check auto-generated variants
echo ""
echo "=== Auto-Generated Variants Check ==="
VARIANT_COUNT=$(echo $PRODUCT_DATA | python3 -c "import sys, json; data = json.load(sys.stdin); print(len(data.get('variants', [])))")
echo "Variant Count: $VARIANT_COUNT"

if [ "$VARIANT_COUNT" -gt "0" ]; then
  echo -e "${GREEN}✓ Variants auto-generated${NC}"
  echo $PRODUCT_DATA | python3 -c "
import sys, json
data = json.load(sys.stdin)
for v in data.get('variants', []):
    print(f\"  - {v.get('color', 'N/A')} / {v.get('size', 'N/A')} / Stock: {v.get('stock', 0)}\")
"
else
  echo -e "${RED}✗ No variants found${NC}"
fi

echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo ""

# Run validation checks
CHECKS_PASSED=0
CHECKS_TOTAL=0

# Check 1: Product type is single
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if [ "$PRODUCT_TYPE" = "single" ]; then
  echo -e "${GREEN}✓${NC} Product type is 'single'"
  CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
  echo -e "${RED}✗${NC} Product type should be 'single', got: $PRODUCT_TYPE"
fi

# Check 2: Fabric composition saved
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if [ "$FABRIC" != "MISSING" ] && [ "$FABRIC" != "None" ]; then
  echo -e "${GREEN}✓${NC} Fabric composition saved"
  CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
  echo -e "${RED}✗${NC} Fabric composition not saved"
fi

# Check 3: Care instructions saved
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if [ "$CARE" != "MISSING" ] && [ "$CARE" != "None" ]; then
  echo -e "${GREEN}✓${NC} Care instructions saved"
  CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
  echo -e "${RED}✗${NC} Care instructions not saved"
fi

# Check 4: Made to order saved
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if [ "$MADE_TO_ORDER" = "True" ]; then
  echo -e "${GREEN}✓${NC} Made to order flag saved"
  CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
  echo -e "${RED}✗${NC} Made to order flag not saved"
fi

# Check 5: Variation exists
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if [ "$VARIATION_COUNT" = "1" ]; then
  echo -e "${GREEN}✓${NC} Variation created for single product"
  CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
  echo -e "${RED}✗${NC} Variation not created (count: $VARIATION_COUNT)"
fi

# Check 6: Size stocks exist
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
SIZE_STOCK_COUNT=$(echo $PRODUCT_DATA | python3 -c "import sys, json; data = json.load(sys.stdin); print(len(data['variations'][0].get('size_stocks', [])))" 2>/dev/null || echo "0")
if [ "$SIZE_STOCK_COUNT" = "3" ]; then
  echo -e "${GREEN}✓${NC} Size stocks created (S, M, L)"
  CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
  echo -e "${RED}✗${NC} Size stocks not created (count: $SIZE_STOCK_COUNT)"
fi

# Check 7: Color hex saved
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if [ "$COLOR_HEX" = "#FF5733" ]; then
  echo -e "${GREEN}✓${NC} Color hex saved correctly"
  CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
  echo -e "${RED}✗${NC} Color hex not saved (got: $COLOR_HEX)"
fi

# Check 8: Variants auto-generated
CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
if [ "$VARIANT_COUNT" = "3" ]; then
  echo -e "${GREEN}✓${NC} Variants auto-generated from variations (3 size variants)"
  CHECKS_PASSED=$((CHECKS_PASSED + 1))
else
  echo -e "${RED}✗${NC} Variants not auto-generated (count: $VARIANT_COUNT)"
fi

echo ""
echo "========================================="
if [ $CHECKS_PASSED -eq $CHECKS_TOTAL ]; then
  echo -e "${GREEN}ALL CHECKS PASSED ($CHECKS_PASSED/$CHECKS_TOTAL)${NC}"
  echo ""
  echo "✅ Single product size/color/stock capture is working correctly!"
  echo ""
  echo "Next Steps:"
  echo "1. View in admin dashboard: http://localhost:5173/admin/products/$PRODUCT_ID"
  echo "2. View in vendor dashboard: http://localhost:5173/vendor/products"
  echo "3. View on product page: http://localhost:5173/products/$PRODUCT_ID"
else
  echo -e "${RED}SOME CHECKS FAILED ($CHECKS_PASSED/$CHECKS_TOTAL)${NC}"
  echo ""
  echo "❌ Please review the failed checks above"
fi
echo "========================================="
echo ""
echo "Product ID for testing: $PRODUCT_ID"
echo "Product Title: $PRODUCT_TITLE"
echo ""
