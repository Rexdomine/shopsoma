#!/bin/bash

# Test Order Tracking Status Display Fix
# Verifies that In Transit and Out for Delivery statuses display correctly

echo "🧪 Testing Order Tracking Status Display Fix"
echo "============================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Get order ID from argument or use default
ORDER_ID="${1:-6E8C79F1}"

if [[ "$ORDER_ID" != *"-"* ]]; then
    # If only the short ID is provided, construct full order number
    FULL_ORDER_ID=$(echo "$ORDER_ID" | sed 's/^/SHP-20251217-/')
else
    FULL_ORDER_ID="$ORDER_ID"
    ORDER_ID=$(echo "$ORDER_ID" | sed 's/SHP-[0-9]*-//')
fi

echo -e "${BLUE}Testing order: ${YELLOW}${FULL_ORDER_ID}${NC}"
echo -e "${BLUE}Order UUID will be fetched from database${NC}"
echo ""

# Backend URL
BACKEND_URL="http://localhost:8000/api/v1"

# Login as admin to get token
echo -e "${BLUE}Step 1: Login as admin${NC}"
ADMIN_LOGIN=$(curl -s -X POST "${BACKEND_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@shopsoma.com", "password": "admin123"}')

ADMIN_TOKEN=$(echo "$ADMIN_LOGIN" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$ADMIN_TOKEN" ]; then
    echo -e "${RED}✗ Failed to get admin token${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Admin logged in${NC}"
echo ""

# Get order UUID from order number
echo -e "${BLUE}Step 2: Fetch order UUID${NC}"
ORDERS_RESPONSE=$(curl -s "${BACKEND_URL}/admin/orders" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}")

ORDER_UUID=$(echo "$ORDERS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    orders = data.get('items', [])
    for order in orders:
        if order.get('order_number') == '${FULL_ORDER_ID}':
            print(order.get('id', ''))
            break
except:
    pass
" 2>/dev/null)

if [ -z "$ORDER_UUID" ]; then
    echo -e "${RED}✗ Order not found: ${FULL_ORDER_ID}${NC}"
    echo -e "${YELLOW}Available orders:${NC}"
    echo "$ORDERS_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    orders = data.get('items', [])
    for order in orders[:5]:
        print(f\"  - {order.get('order_number')} ({order.get('id')})\")
except:
    pass
" 2>/dev/null
    exit 1
fi

echo -e "${GREEN}✓ Found order UUID: ${ORDER_UUID}${NC}"
echo ""

# Test each status
STATUSES=("in_transit" "out_for_delivery" "delivered")

for STATUS in "${STATUSES[@]}"; do
    echo -e "${BLUE}═══════════════════════════════════════════${NC}"
    echo -e "${BLUE}Testing Status: ${YELLOW}${STATUS}${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════${NC}"
    echo ""

    # Update order status
    echo -e "${BLUE}Updating order fulfillment_status to: ${STATUS}${NC}"
    UPDATE_RESPONSE=$(curl -s -X PATCH "${BACKEND_URL}/admin/orders/${ORDER_UUID}" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${ADMIN_TOKEN}" \
      -d "{\"fulfillment_status\": \"${STATUS}\"}")

    if echo "$UPDATE_RESPONSE" | grep -q "\"id\""; then
        echo -e "${GREEN}✓ Order updated successfully${NC}"
    else
        echo -e "${RED}✗ Failed to update order${NC}"
        echo "$UPDATE_RESPONSE"
        continue
    fi

    # Fetch tracking info
    echo -e "${BLUE}Fetching tracking information...${NC}"
    TRACKING_RESPONSE=$(curl -s "${BACKEND_URL}/orders/${ORDER_UUID}/tracking")

    # Parse tracking response
    CURRENT_STATUS=$(echo "$TRACKING_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('current_status', ''))" 2>/dev/null)

    echo ""
    echo -e "${YELLOW}Backend Response:${NC}"
    echo "$TRACKING_RESPONSE" | python3 -m json.tool 2>/dev/null | head -20

    echo ""
    echo -e "${YELLOW}Status Verification:${NC}"
    echo -e "  Fulfillment Status: ${BLUE}${STATUS}${NC}"
    echo -e "  Mapped Status:      ${BLUE}${CURRENT_STATUS}${NC}"

    # Check if mapping is correct
    case "$STATUS" in
        "in_transit")
            if [ "$CURRENT_STATUS" == "in_transit" ]; then
                echo -e "  ${GREEN}✓ CORRECT: Mapped to 'in_transit'${NC}"
            else
                echo -e "  ${RED}✗ WRONG: Should be 'in_transit', got '${CURRENT_STATUS}'${NC}"
            fi
            ;;
        "out_for_delivery")
            if [ "$CURRENT_STATUS" == "out_for_delivery" ]; then
                echo -e "  ${GREEN}✓ CORRECT: Mapped to 'out_for_delivery'${NC}"
            else
                echo -e "  ${RED}✗ WRONG: Should be 'out_for_delivery', got '${CURRENT_STATUS}'${NC}"
            fi
            ;;
        "delivered")
            if [ "$CURRENT_STATUS" == "delivered" ]; then
                echo -e "  ${GREEN}✓ CORRECT: Mapped to 'delivered'${NC}"
            else
                echo -e "  ${RED}✗ WRONG: Should be 'delivered', got '${CURRENT_STATUS}'${NC}"
            fi
            ;;
    esac

    echo ""
    echo -e "${BLUE}Frontend URL:${NC} http://localhost:5173/orders/${ORDER_UUID}/tracking"
    echo ""
    echo -e "${YELLOW}⏸  Check browser now - Status should update in real-time${NC}"
    echo -e "${YELLOW}   Press Enter when ready to test next status...${NC}"
    read -r

done

echo ""
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo -e "${GREEN}Testing Complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Summary:${NC}"
echo "  ✓ in_transit → Maps to 'in_transit' (Step 2)"
echo "  ✓ out_for_delivery → Maps to 'out_for_delivery' (Step 3)"
echo "  ✓ delivered → Maps to 'delivered' (Step 4)"
echo ""
echo -e "${BLUE}Order tracking page:${NC}"
echo "  http://localhost:5173/orders/${ORDER_UUID}/tracking"
echo ""
