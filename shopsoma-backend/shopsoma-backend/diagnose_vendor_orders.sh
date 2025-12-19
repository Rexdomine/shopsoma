#!/bin/bash

echo "============================================"
echo "Vendor Orders 403 Diagnostic"
echo "============================================"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "1. Checking if backend server is running..."
if ps aux | grep -q "[u]vicorn app.main:app"; then
    echo -e "${GREEN}✓ Backend server is running${NC}"
else
    echo -e "${RED}✗ Backend server is NOT running${NC}"
    echo "  Start it with: cd shopsoma-backend && source venv/bin/activate && uvicorn app.main:app --reload"
    exit 1
fi

echo ""
echo "2. Testing vendor orders endpoint..."
echo "   Checking what logs appear when you navigate to /vendor/orders"
echo ""
echo -e "${YELLOW}ACTION REQUIRED:${NC}"
echo "   1. Open your browser to: http://localhost:5173/vendor/orders"
echo "   2. Watch the terminal where uvicorn is running"
echo "   3. Look for these log patterns:"
echo ""
echo -e "   ${GREEN}GOOD (Expected):${NC}"
echo "      [get_current_vendor] User ID: ..."
echo "      [get_current_vendor] SUCCESS"
echo "      [get_vendor_profile] Looking for vendor..."
echo "      [get_vendor_profile] SUCCESS"
echo "      [get_approved_vendor] Checking approval..."    # ← This is missing!
echo "      [get_approved_vendor] SUCCESS"
echo "      [list_vendor_orders] ENDPOINT REACHED"
echo "      INFO: ... \"GET /api/v1/vendor/orders?page=1&page_size=20 HTTP/1.1\" 200 OK"
echo ""
echo -e "   ${RED}BAD (Current state):${NC}"
echo "      [get_vendor_profile] SUCCESS"
echo "      INFO: ... \"GET /api/v1/vendor/orders?page=1&page_size=20 HTTP/1.1\" 403 Forbidden"
echo "      (No [get_approved_vendor] or [list_vendor_orders] logs)"
echo ""
echo "3. If you see the BAD pattern, this tells us:"
echo "   - The request reaches the backend"
echo "   - FastAPI is rejecting it BEFORE running the dependency chain"
echo "   - Possible causes:"
echo "     a) Parameter validation failure"
echo "     b) Route matching issue"
echo "     c) Middleware blocking the request"
echo ""
echo "4. Check browser console for frontend errors:"
echo "   - Open DevTools (F12) → Console tab"
echo "   - Look for error messages with ❌ emoji"
echo ""
echo "Press ENTER when you're ready to continue..."
read

echo ""
echo "5. Checking route registration..."
grep -n "vendors.router" shopsoma-backend/app/main.py
echo ""

echo "6. Checking endpoint definition..."
grep -A 10 "@router.get(\"/orders\"" shopsoma-backend/app/api/v1/vendors.py | head -12
echo ""

echo "7. Checking dependency imports..."
grep "get_approved_vendor" shopsoma-backend/app/api/v1/vendors.py | head -3
echo ""

echo "============================================"
echo "Diagnostic complete!"
echo "============================================"
