#!/bin/bash

# Admin Orders Import Fix - Verification Script
# This script verifies the fix for the OrderStats import error

echo "=================================================="
echo "Admin Orders Import Fix - Verification"
echo "=================================================="
echo ""

cd /Users/rex/Documents/Shopsoma/shopsoma-frontend

echo "1️⃣  Checking TypeScript compilation..."
echo "--------------------------------------------------"
if npx tsc --noEmit --skipLibCheck 2>&1 | grep -q "error"; then
    echo "❌ TypeScript errors found"
    npx tsc --noEmit --skipLibCheck
    exit 1
else
    echo "✅ TypeScript compilation successful"
fi
echo ""

echo "2️⃣  Checking component files exist..."
echo "--------------------------------------------------"
components=(
    "src/components/admin/OrderStats.tsx"
    "src/components/admin/OrderFilters.tsx"
    "src/components/admin/BulkOrderActions.tsx"
    "src/pages/admin/AdminOrders.tsx"
    "src/pages/admin/AdminOrderDetail.tsx"
    "src/services/adminOrderService.ts"
)

all_exist=true
for component in "${components[@]}"; do
    if [ -f "$component" ]; then
        echo "✅ $component"
    else
        echo "❌ $component NOT FOUND"
        all_exist=false
    fi
done

if [ "$all_exist" = false ]; then
    echo ""
    echo "❌ Some component files are missing"
    exit 1
fi
echo ""

echo "3️⃣  Checking export patterns..."
echo "--------------------------------------------------"

# Check OrderStats component has default export
if grep -q "export default function OrderStats" src/components/admin/OrderStats.tsx; then
    echo "✅ OrderStats.tsx has default export"
else
    echo "❌ OrderStats.tsx missing default export"
    exit 1
fi

# Check OrderFilters component has default export
if grep -q "export default function OrderFilters" src/components/admin/OrderFilters.tsx; then
    echo "✅ OrderFilters.tsx has default export"
else
    echo "❌ OrderFilters.tsx missing default export"
    exit 1
fi

# Check BulkOrderActions component has default export
if grep -q "export default function BulkOrderActions" src/components/admin/BulkOrderActions.tsx; then
    echo "✅ BulkOrderActions.tsx has default export"
else
    echo "❌ BulkOrderActions.tsx missing default export"
    exit 1
fi

# Check OrderStats interface is exported from service
if grep -q "export interface OrderStats" src/services/adminOrderService.ts; then
    echo "✅ OrderStats interface exported from adminOrderService.ts"
else
    echo "❌ OrderStats interface missing from adminOrderService.ts"
    exit 1
fi
echo ""

echo "4️⃣  Checking import statements..."
echo "--------------------------------------------------"

# Check AdminOrders imports
if grep -q "import OrderStats from '../../components/admin/OrderStats'" src/pages/admin/AdminOrders.tsx; then
    echo "✅ AdminOrders.tsx imports OrderStats component"
else
    echo "❌ AdminOrders.tsx missing OrderStats import"
    exit 1
fi

if grep -q "OrderStats as OrderStatsType" src/pages/admin/AdminOrders.tsx; then
    echo "✅ AdminOrders.tsx imports OrderStats type with alias"
else
    echo "❌ AdminOrders.tsx missing OrderStats type import"
    exit 1
fi
echo ""

echo "5️⃣  Checking Vite cache..."
echo "--------------------------------------------------"
if [ -d "node_modules/.vite" ]; then
    echo "⚠️  Vite cache exists (will be cleared)"
    rm -rf node_modules/.vite
    echo "✅ Vite cache cleared"
else
    echo "✅ Vite cache already clear"
fi
echo ""

echo "6️⃣  Checking dev server status..."
echo "--------------------------------------------------"
if curl -s http://localhost:5173/ > /dev/null 2>&1; then
    echo "✅ Dev server is running on http://localhost:5173"
else
    echo "⚠️  Dev server is not running"
    echo "   Start it with: npm run dev"
fi
echo ""

echo "=================================================="
echo "✅ All Checks Passed!"
echo "=================================================="
echo ""
echo "Next Steps:"
echo "1. Open http://localhost:5173/admin/orders in your browser"
echo "2. Press Ctrl+Shift+R (or Cmd+Shift+R on Mac) to hard refresh"
echo "3. Clear browser cache if error persists"
echo ""
echo "If you still see the error:"
echo "- Open DevTools (F12)"
echo "- Go to Application tab"
echo "- Clear storage"
echo "- Hard refresh again"
echo ""
