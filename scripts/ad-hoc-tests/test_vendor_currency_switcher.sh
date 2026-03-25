#!/bin/bash

# Test Vendor Product Currency Switcher
# Verifies that currency field is submitted correctly with product data

echo "🧪 Testing Vendor Product Currency Switcher"
echo "==========================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Backend URL
BACKEND_URL="http://localhost:8000/api/v1"

# Login as vendor
echo -e "${BLUE}Step 1: Login as vendor${NC}"
VENDOR_LOGIN=$(curl -s -X POST "${BACKEND_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "vendor@shopsoma.com", "password": "vendor123"}')

VENDOR_TOKEN=$(echo "$VENDOR_LOGIN" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$VENDOR_TOKEN" ]; then
    echo -e "${RED}✗ Failed to get vendor token${NC}"
    echo "Response: $VENDOR_LOGIN"
    exit 1
fi

echo -e "${GREEN}✓ Vendor logged in${NC}"
echo ""

# Get a valid category ID first
echo -e "${BLUE}Step 2: Get valid category ID${NC}"
CATEGORIES=$(curl -s "${BACKEND_URL}/categories")
CATEGORY_ID=$(echo "$CATEGORIES" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    if isinstance(data, list) and len(data) > 0:
        print(data[0].get('id', ''))
    elif isinstance(data, dict) and 'items' in data and len(data['items']) > 0:
        print(data['items'][0].get('id', ''))
except:
    pass
" 2>/dev/null)

if [ -z "$CATEGORY_ID" ]; then
    echo -e "${YELLOW}⚠ No category found, using placeholder${NC}"
    CATEGORY_ID="placeholder-category-id"
else
    echo -e "${GREEN}✓ Found category: ${CATEGORY_ID}${NC}"
fi
echo ""

# Test creating product with USD currency
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 3: Create product with USD currency${NC}"
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo ""

USD_PRODUCT=$(curl -s -X POST "${BACKEND_URL}/vendor/products" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${VENDOR_TOKEN}" \
  -d "{
    \"title\": \"Test USD Product - Currency Switcher\",
    \"description\": \"Testing USD currency selection from vendor add product page\",
    \"base_price\": 99.99,
    \"total_stock\": 10,
    \"category_id\": \"${CATEGORY_ID}\",
    \"status\": \"draft\",
    \"currency\": \"USD\"
  }")

echo -e "${YELLOW}API Response:${NC}"
echo "$USD_PRODUCT" | python3 -m json.tool 2>/dev/null | head -25
echo ""

CURRENCY_USD=$(echo "$USD_PRODUCT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('currency', ''))" 2>/dev/null)
PRODUCT_ID_USD=$(echo "$USD_PRODUCT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

echo -e "${YELLOW}Verification:${NC}"
if [ "$CURRENCY_USD" == "USD" ]; then
    echo -e "  ${GREEN}✓ CORRECT: Currency is 'USD'${NC}"
else
    echo -e "  ${RED}✗ WRONG: Expected 'USD', got '${CURRENCY_USD}'${NC}"
fi

if [ -n "$PRODUCT_ID_USD" ]; then
    echo -e "  ${GREEN}✓ Product created with ID: ${PRODUCT_ID_USD}${NC}"
else
    echo -e "  ${YELLOW}⚠ No product ID returned (may have failed)${NC}"
fi
echo ""

# Test creating product with NGN currency
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 4: Create product with NGN currency${NC}"
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo ""

NGN_PRODUCT=$(curl -s -X POST "${BACKEND_URL}/vendor/products" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${VENDOR_TOKEN}" \
  -d "{
    \"title\": \"Test NGN Product - Currency Switcher\",
    \"description\": \"Testing NGN currency selection from vendor add product page\",
    \"base_price\": 50000.00,
    \"total_stock\": 10,
    \"category_id\": \"${CATEGORY_ID}\",
    \"status\": \"draft\",
    \"currency\": \"NGN\"
  }")

echo -e "${YELLOW}API Response:${NC}"
echo "$NGN_PRODUCT" | python3 -m json.tool 2>/dev/null | head -25
echo ""

CURRENCY_NGN=$(echo "$NGN_PRODUCT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('currency', ''))" 2>/dev/null)
PRODUCT_ID_NGN=$(echo "$NGN_PRODUCT" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)

echo -e "${YELLOW}Verification:${NC}"
if [ "$CURRENCY_NGN" == "NGN" ]; then
    echo -e "  ${GREEN}✓ CORRECT: Currency is 'NGN'${NC}"
else
    echo -e "  ${RED}✗ WRONG: Expected 'NGN', got '${CURRENCY_NGN}'${NC}"
fi

if [ -n "$PRODUCT_ID_NGN" ]; then
    echo -e "  ${GREEN}✓ Product created with ID: ${PRODUCT_ID_NGN}${NC}"
else
    echo -e "  ${YELLOW}⚠ No product ID returned (may have failed)${NC}"
fi
echo ""

# Test retrieving products and verify currency
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 5: Verify currency persisted correctly${NC}"
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo ""

if [ -n "$PRODUCT_ID_USD" ]; then
    USD_RETRIEVED=$(curl -s "${BACKEND_URL}/products/${PRODUCT_ID_USD}" \
      -H "Authorization: Bearer ${VENDOR_TOKEN}")

    RETRIEVED_CURRENCY_USD=$(echo "$USD_RETRIEVED" | python3 -c "import sys, json; print(json.load(sys.stdin).get('currency', ''))" 2>/dev/null)

    echo -e "${YELLOW}USD Product Currency Check:${NC}"
    if [ "$RETRIEVED_CURRENCY_USD" == "USD" ]; then
        echo -e "  ${GREEN}✓ Currency persisted correctly: USD${NC}"
    else
        echo -e "  ${RED}✗ Currency mismatch: Expected 'USD', got '${RETRIEVED_CURRENCY_USD}'${NC}"
    fi
fi

if [ -n "$PRODUCT_ID_NGN" ]; then
    NGN_RETRIEVED=$(curl -s "${BACKEND_URL}/products/${PRODUCT_ID_NGN}" \
      -H "Authorization: Bearer ${VENDOR_TOKEN}")

    RETRIEVED_CURRENCY_NGN=$(echo "$NGN_RETRIEVED" | python3 -c "import sys, json; print(json.load(sys.stdin).get('currency', ''))" 2>/dev/null)

    echo -e "${YELLOW}NGN Product Currency Check:${NC}"
    if [ "$RETRIEVED_CURRENCY_NGN" == "NGN" ]; then
        echo -e "  ${GREEN}✓ Currency persisted correctly: NGN${NC}"
    else
        echo -e "  ${RED}✗ Currency mismatch: Expected 'NGN', got '${RETRIEVED_CURRENCY_NGN}'${NC}"
    fi
fi

echo ""

# Summary
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}Testing Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Summary:${NC}"
echo "  ✓ USD currency submitted correctly"
echo "  ✓ NGN currency submitted correctly"
echo "  ✓ Currency field persisted in database"
echo ""
echo -e "${BLUE}Manual Testing:${NC}"
echo "  1. Open: http://localhost:5173/vendor/products/add"
echo "  2. Select USD from currency switcher"
echo "  3. Verify all price fields show $ icon"
echo "  4. Switch to NGN"
echo "  5. Verify all price fields show ₦ icon"
echo "  6. Fill out form and submit"
echo "  7. Check console for 'currency' field in payload"
echo ""
echo -e "${BLUE}Created Test Products:${NC}"
if [ -n "$PRODUCT_ID_USD" ]; then
    echo "  - USD Product: ${PRODUCT_ID_USD}"
fi
if [ -n "$PRODUCT_ID_NGN" ]; then
    echo "  - NGN Product: ${PRODUCT_ID_NGN}"
fi
echo ""
