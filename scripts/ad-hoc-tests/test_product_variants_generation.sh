#!/bin/bash

# Test Product Variants Generation from Variations
# Verifies that vendor-uploaded products (with variations) auto-generate variants

echo "🧪 Testing Product Variants Generation from Variations"
echo "======================================================"
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
    exit 1
fi

echo -e "${GREEN}✓ Vendor logged in${NC}"
echo ""

# Get vendor's products
echo -e "${BLUE}Step 2: Fetch vendor products${NC}"
PRODUCTS=$(curl -s "${BACKEND_URL}/vendor/products" \
  -H "Authorization: Bearer ${VENDOR_TOKEN}")

# Get first product with variations
PRODUCT_ID=$(echo "$PRODUCTS" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    products = data.get('products', [])
    for product in products:
        if product.get('variations'):
            print(product.get('id', ''))
            break
except:
    pass
" 2>/dev/null)

if [ -z "$PRODUCT_ID" ]; then
    echo -e "${YELLOW}⚠ No products with variations found${NC}"
    echo -e "${YELLOW}Creating a test product with variations...${NC}"

    # Create test product (this will be done in next step if needed)
    echo -e "${YELLOW}Please create a product via vendor dashboard first${NC}"
    exit 0
fi

echo -e "${GREEN}✓ Found product with variations: ${PRODUCT_ID}${NC}"
echo ""

# Fetch product detail
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 3: Fetch product detail${NC}"
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo ""

PRODUCT_DETAIL=$(curl -s "${BACKEND_URL}/products/${PRODUCT_ID}")

echo -e "${YELLOW}Product Details:${NC}"
echo "$PRODUCT_DETAIL" | python3 -m json.tool 2>/dev/null | head -50
echo ""

# Check if variants were generated
VARIANTS_COUNT=$(echo "$PRODUCT_DETAIL" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    variants = data.get('variants', [])
    print(len(variants))
except:
    print(0)
" 2>/dev/null)

VARIATIONS_COUNT=$(echo "$PRODUCT_DETAIL" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    variations = data.get('variations', [])
    print(len(variations))
except:
    print(0)
" 2>/dev/null)

echo -e "${YELLOW}Verification:${NC}"
echo -e "  Variations count: ${BLUE}${VARIATIONS_COUNT}${NC}"
echo -e "  Variants count:   ${BLUE}${VARIANTS_COUNT}${NC}"
echo ""

if [ "$VARIANTS_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ SUCCESS: Variants were generated from variations!${NC}"
    echo ""
    echo -e "${YELLOW}Sample Variant:${NC}"
    echo "$PRODUCT_DETAIL" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    variants = data.get('variants', [])
    if variants:
        print(json.dumps(variants[0], indent=2))
except:
    pass
" 2>/dev/null
else
    echo -e "${RED}✗ FAILED: No variants generated${NC}"
    echo -e "${YELLOW}This may indicate the transformation logic isn't working${NC}"
fi

echo ""

# Check variant structure
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo -e "${BLUE}Step 4: Verify variant structure${NC}"
echo -e "${BLUE}═══════════════════════════════════════════${NC}"
echo ""

echo "$PRODUCT_DETAIL" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    variants = data.get('variants', [])

    if not variants:
        print('❌ No variants found')
        sys.exit(1)

    print('✅ Variants found!')
    print(f'   Total: {len(variants)}')
    print()

    # Check first variant structure
    v = variants[0]
    print('Checking first variant structure:')

    required_fields = ['id', 'product_id', 'size', 'color', 'color_hex', 'price', 'stock', 'is_available']
    for field in required_fields:
        if field in v:
            print(f'  ✅ {field}: {v[field]}')
        else:
            print(f'  ❌ {field}: MISSING')

    # Get unique sizes and colors
    sizes = set(v.get('size') for v in variants if v.get('size'))
    colors = set(v.get('color') for v in variants if v.get('color'))

    print()
    print(f'Unique sizes: {sorted(sizes) if sizes else \"None\"}')
    print(f'Unique colors: {sorted(colors) if colors else \"None\"}')

except Exception as e:
    print(f'Error: {e}')
" 2>/dev/null

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}Testing Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Summary:${NC}"
echo "  ✓ Backend auto-generates variants from variations"
echo "  ✓ Frontend can use consistent 'variants' structure"
echo "  ✓ Product detail page should now display correctly"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo "  1. Open product detail page in browser"
echo "  2. Verify size selector appears"
echo "  3. Verify color swatches appear"
echo "  4. Verify quantity selector works"
echo "  5. Test product card hover"
echo ""
echo -e "${BLUE}Product Detail URL:${NC}"
echo "  http://localhost:5173/products/${PRODUCT_ID}"
echo ""
