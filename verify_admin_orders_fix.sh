#!/bin/bash

# Verification Script for Admin Orders Model Fixes
# Date: December 13, 2025

echo "======================================================================"
echo "Admin Orders Model Fixes Verification"
echo "======================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Check that backend is running
echo "1. Checking backend health..."
HEALTH_RESPONSE=$(curl -s http://localhost:8000/healthz)
if echo "$HEALTH_RESPONSE" | grep -q "healthy"; then
    echo -e "${GREEN}✓ Backend is healthy${NC}"
else
    echo -e "${RED}✗ Backend is not running or unhealthy${NC}"
    echo "   Please start the backend first"
    exit 1
fi
echo ""

# 2. Verify model files exist
echo "2. Verifying model files..."
MODELS=(
    "shopsoma-backend/app/models/user.py"
    "shopsoma-backend/app/models/address.py"
    "shopsoma-backend/app/models/vendor.py"
)

for model in "${MODELS[@]}"; do
    if [ -f "$model" ]; then
        echo -e "${GREEN}✓ Found ${model}${NC}"
    else
        echo -e "${RED}✗ Missing ${model}${NC}"
    fi
done
echo ""

# 3. Verify API file has been updated
echo "3. Verifying admin_orders.py has fixes..."
ADMIN_ORDERS="shopsoma-backend/app/api/v1/admin_orders.py"

# Check for build_vendor_info fix (business_phone)
if grep -q "business_phone" "$ADMIN_ORDERS"; then
    echo -e "${GREEN}✓ build_vendor_info uses business_phone${NC}"
else
    echo -e "${RED}✗ build_vendor_info still has wrong field name${NC}"
fi

# Check for error handling in build_customer_info
if grep -q "except AttributeError as e:" "$ADMIN_ORDERS"; then
    echo -e "${GREEN}✓ Error handling added to build functions${NC}"
else
    echo -e "${RED}✗ Error handling missing${NC}"
fi

# Check for vendor.user relationship loading
if grep -q "selectinload(Vendor.user)" "$ADMIN_ORDERS"; then
    echo -e "${GREEN}✓ Vendor.user relationship is loaded in query${NC}"
else
    echo -e "${RED}✗ Vendor.user relationship not loaded${NC}"
fi

# Check for full_name in search (not first_name/last_name)
if grep -q "User.full_name.ilike" "$ADMIN_ORDERS"; then
    echo -e "${GREEN}✓ Search filter uses full_name${NC}"
else
    echo -e "${YELLOW}⚠ Search filter may still use first_name/last_name${NC}"
fi
echo ""

# 4. Check Model Schemas
echo "4. Checking model schemas..."

# User model - should have full_name
if grep -q "full_name = Column" "shopsoma-backend/app/models/user.py"; then
    echo -e "${GREEN}✓ User model has full_name field${NC}"
fi

# Address model - should have phone_number
if grep -q "phone_number = Column" "shopsoma-backend/app/models/address.py"; then
    echo -e "${GREEN}✓ Address model has phone_number field${NC}"
fi

# Vendor model - should have business_phone
if grep -q "business_phone = Column" "shopsoma-backend/app/models/vendor.py"; then
    echo -e "${GREEN}✓ Vendor model has business_phone field${NC}"
fi
echo ""

# 5. Summary
echo "======================================================================"
echo -e "${GREEN}Verification Complete!${NC}"
echo "======================================================================"
echo ""
echo "Next Steps:"
echo "1. Start the frontend:"
echo "   cd shopsoma-frontend && npm run dev"
echo ""
echo "2. Navigate to: http://localhost:5173/admin/orders"
echo ""
echo "3. Click 'View' on any order to test the fix"
echo ""
echo "Expected Result:"
echo "   ✓ Order detail page loads"
echo "   ✓ Customer info displays (parsed from full_name)"
echo "   ✓ Address info displays (with combined address lines)"
echo "   ✓ Vendor info displays (with business_phone and user email)"
echo "   ✓ No AttributeError in backend logs"
echo ""
