# Admin Orders - Testing Guide

**Date**: December 12, 2025
**Status**: ✅ Ready for Testing
**Frontend URL**: http://localhost:5173
**Backend URL**: http://localhost:8000

---

## Pre-Testing Verification

### ✅ Server Status

**Frontend**:
```bash
# Check if running
curl -I http://localhost:5173/

# Expected: HTTP/1.1 200 OK
```

**Backend**:
```bash
# Check if running
curl http://localhost:8000/healthz

# Expected: {"status": "healthy"}
```

### ✅ Code Verification

All import errors have been fixed:
- ✅ Type imports separated from value imports
- ✅ Naming conflicts resolved
- ✅ TypeScript compilation successful
- ✅ No build errors

---

## Test Scenarios

### 1. Page Load Test

**Test**: Navigate to admin orders page

**Steps**:
1. Open browser to `http://localhost:5173/admin/orders`
2. Login as admin if needed

**Expected Results**:
- ✅ Page loads without errors
- ✅ No import errors in console
- ✅ OrderStats component displays (8 stat cards)
- ✅ OrderFilters component displays (search bar)
- ✅ Order table renders (even if empty)
- ✅ Loading states work properly

**If No Orders Exist**:
- Table should show "No orders found"
- Statistics should show zeros
- Filters should still be functional

---

### 2. Statistics Dashboard Test

**Test**: Verify order statistics display

**Elements to Check**:
- □ Total Revenue (green)
- □ Average Order (blue)
- □ Today's orders (purple)
- □ Pending Orders (yellow)
- □ Processing Orders (orange)
- □ Shipped Orders (blue)
- □ Delivered Orders (green)
- □ Cancelled Orders (red)

**Interaction**:
- Stats should update when filters are applied
- Numbers should format correctly (currency, integers)
- Colors should match status types

---

### 3. Filter System Test

**Test**: Apply various filters

#### Search Filter
**Steps**:
1. Type in search box: order number, customer name, or email
2. Results should filter in real-time

**Expected**:
- ✅ Debounced search (not instant, waits for typing to stop)
- ✅ Results match search query
- ✅ Active filter tag appears below search

#### Payment Status Filter
**Test Values**:
- "All payments" (default)
- "Pending"
- "Paid"
- "Failed"
- "Refunded"

**Expected**:
- ✅ Orders filter by payment status
- ✅ Active filter tag appears
- ✅ Can clear filter individually

#### Fulfillment Status Filter
**Test Values**:
- "All orders" (default)
- "Pending"
- "Processing"
- "Shipped"
- "Delivered"
- "Cancelled"

**Expected**:
- ✅ Orders filter by fulfillment status
- ✅ Active filter tag appears
- ✅ Can clear filter individually

#### Date Range Filter
**Steps**:
1. Click "Show filters"
2. Select "Date From"
3. Select "Date To"

**Expected**:
- ✅ Orders filter by date range
- ✅ "Date To" cannot be before "Date From"
- ✅ Active filter tags appear
- ✅ Can clear each date independently

#### Combined Filters
**Steps**:
1. Apply search + payment status + date range
2. All filters should work together

**Expected**:
- ✅ All filters apply simultaneously (AND logic)
- ✅ All active filter tags visible
- ✅ "Clear all" button appears
- ✅ Clicking "Clear all" removes all filters

---

### 4. Bulk Actions Test

**Test**: Select and update multiple orders

**Steps**:
1. Select individual orders using checkboxes
2. OR click "Select All" checkbox in header

**Expected**:
- ✅ Bulk actions bar appears when orders selected
- ✅ Shows count: "X orders selected"
- ✅ "Clear" button deselects all

#### Bulk Status Update
**Steps**:
1. Select 2+ orders
2. Choose new status from dropdown
3. Optionally add notes
4. Click "Apply"

**Expected**:
- ✅ Success toast notification
- ✅ Orders refresh with new status
- ✅ Selection clears after update
- ✅ Statistics update

---

### 5. Order List Display Test

**Test**: Verify order table rendering

**Columns to Check**:
- □ Checkbox (select)
- □ Order number
- □ Customer (name + email)
- □ Amount (formatted currency)
- □ Payment status (colored badge)
- □ Fulfillment status (colored badge)
- □ Details (vendor count, item count)
- □ Date (formatted)
- □ Actions (View button)

**Status Badge Colors**:
- Pending payment: Amber
- Paid: Green
- Failed: Red
- Refunded: Gray
- Pending fulfillment: Yellow
- Processing: Blue
- Shipped: Purple
- Delivered: Green
- Cancelled: Red

---

### 6. Pagination Test

**Test**: Navigate through pages (if >20 orders)

**Elements**:
- Previous/Next buttons
- Page numbers (shows first 5)
- "Showing X to Y of Z results"

**Expected**:
- ✅ Default 20 orders per page
- ✅ Previous disabled on first page
- ✅ Next disabled on last page
- ✅ Page numbers clickable
- ✅ Current page highlighted
- ✅ Selection doesn't persist across pages

---

### 7. CSV Export Test

**Test**: Export orders to CSV

**Steps**:
1. Apply filters (optional)
2. Click "Export CSV" button

**Expected**:
- ✅ Button shows "Exporting..." during download
- ✅ CSV file downloads
- ✅ Filename: `orders_YYYY-MM-DD.csv`
- ✅ Contains filtered orders (or all if no filters)
- ✅ Success toast notification

**CSV Should Contain**:
- Order number
- Customer name
- Customer email
- Total amount
- Payment status
- Fulfillment status
- Created date
- Vendor count
- Item count

---

### 8. Order Detail Navigation Test

**Test**: Navigate to order detail page

**Steps**:
1. Click "View →" on any order row

**Expected**:
- ✅ Navigates to `/admin/orders/{order-id}`
- ✅ Order detail page loads
- ✅ No import errors
- ✅ Back button returns to order list

---

### 9. Order Detail Page Test

**Test**: View complete order information

**Sections to Check**:
- □ Order header (number, status badges, dates)
- □ Customer information
- □ Shipping address
- □ Billing address
- □ Order items table
- □ Pricing breakdown
- □ Action buttons

---

### 10. Order Status Update Test

**Test**: Update order fulfillment status

**Steps**:
1. Open order detail
2. Click "Edit Status"
3. Select new status
4. Add optional notes
5. Click "Update"

**Expected**:
- ✅ Modal appears with status dropdown
- ✅ Can add admin notes
- ✅ Success toast after update
- ✅ Order refreshes with new status
- ✅ Delivered timestamp sets when status = "delivered"

---

### 11. Shipping Info Update Test

**Test**: Update shipping information

**Steps**:
1. Open order detail
2. Click "Edit Shipping"
3. Update delivery provider, tracking number, estimated date
4. Click "Save"

**Expected**:
- ✅ Form pre-fills with existing data
- ✅ All fields editable
- ✅ Success toast after save
- ✅ Order refreshes with new shipping info
- ✅ Cancel button discards changes

---

### 12. Cancel Order Test

**Test**: Cancel an order with reason

**Steps**:
1. Open order detail
2. Click "Cancel Order"
3. Enter cancellation reason
4. Choose whether to refund
5. Click "Cancel Order"

**Expected**:
- ✅ Confirmation modal appears
- ✅ Reason field is required
- ✅ Refund checkbox available
- ✅ Order status changes to "cancelled"
- ✅ Cancelled timestamp set
- ✅ Success toast notification

---

### 13. Process Refund Test

**Test**: Process full or partial refund

**Steps**:
1. Open paid order detail
2. Click "Process Refund"
3. Choose "Full" or "Partial"
4. If partial, enter amount
5. Enter reason
6. Click "Process Refund"

**Expected**:
- ✅ Modal appears
- ✅ Amount validation (partial can't exceed total)
- ✅ Reason is required
- ✅ Payment status updates to "refunded"
- ✅ Success toast notification

---

### 14. Error Handling Test

**Test**: Verify error scenarios

#### Network Errors
**Steps**:
1. Stop backend server
2. Try to load orders page

**Expected**:
- ✅ Error toast notification
- ✅ Graceful error message
- ✅ No page crash

#### Missing Order
**Steps**:
1. Navigate to `/admin/orders/invalid-id`

**Expected**:
- ✅ Shows "Order not found"
- ✅ "Back to orders" button works

#### Invalid Filters
**Steps**:
1. Apply filters with no results

**Expected**:
- ✅ Shows "No orders found"
- ✅ Clear filters works

---

### 15. Loading States Test

**Test**: Verify loading indicators

**Check**:
- □ Initial page load shows skeleton/loading
- □ Statistics show loading state (pulsing cards)
- □ Filter changes show loading
- □ Bulk actions show "Updating..."
- □ Export shows "Exporting..."
- □ Status updates show loading

---

### 16. Responsive Design Test

**Test**: Check mobile/tablet layouts

**Breakpoints**:
- Mobile: < 640px
- Tablet: 640px - 1024px
- Desktop: > 1024px

**Expected**:
- ✅ Sidebar responsive
- ✅ Table scrolls horizontally on mobile
- ✅ Filters stack on mobile
- ✅ Stat cards stack properly
- ✅ Action buttons accessible

---

### 17. Permission Test

**Test**: Verify admin-only access

**Steps**:
1. Logout
2. Try to access `/admin/orders` directly

**Expected**:
- ✅ Redirects to login page
- ✅ After login, redirects back to orders

**As Non-Admin User**:
1. Login as regular user or vendor
2. Try to access `/admin/orders`

**Expected**:
- ✅ Blocked or redirected
- ✅ Error message shown

---

## Browser Compatibility Test

Test in multiple browsers:
- □ Chrome/Chromium
- □ Firefox
- □ Safari
- □ Edge

**Expected**: Works consistently across all browsers

---

## Performance Test

### Load Time
- Initial page load: < 1 second
- Statistics load: < 500ms
- Filter update: < 300ms
- Pagination: < 200ms

### Network
- Check Network tab in DevTools
- API calls should be efficient
- No excessive re-fetching

---

## Console Check

**Throughout all tests, check browser console**:
- ✅ No import errors
- ✅ No React errors
- ✅ No 404s for components
- ✅ No type errors

---

## Common Issues & Solutions

### Issue: Import Errors Still Appear
**Solution**: Hard refresh browser (Ctrl+Shift+R or Cmd+Shift+R)

### Issue: Server Not on Port 5173
**Solution**:
```bash
lsof -ti:5173 | xargs kill -9
PORT=5173 npm run dev
```

### Issue: Statistics Show 0
**Solution**: Create test orders or seed database

### Issue: Components Not Rendering
**Solution**: Check browser console for specific error

---

## Test Data Setup

If database is empty, you can:

1. **Use Existing Seed Script** (if available):
```bash
cd shopsoma-backend
python seed_demo_orders.py
```

2. **Create Test Order via Frontend**:
- Login as customer
- Add products to cart
- Complete checkout

3. **Create Order via API**:
```bash
curl -X POST http://localhost:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {token}" \
  -d '{...order data...}'
```

---

## Success Criteria

All tests should pass with:
- ✅ No console errors
- ✅ All components render correctly
- ✅ All interactions work as expected
- ✅ Data displays accurately
- ✅ Loading states show appropriately
- ✅ Error handling works gracefully
- ✅ Responsive design works on all screen sizes
- ✅ Performance is acceptable

---

## Reporting Issues

If you find bugs, document:
1. Steps to reproduce
2. Expected behavior
3. Actual behavior
4. Browser and version
5. Console errors (if any)
6. Network requests (if relevant)

---

## Next Steps After Testing

1. ✅ Verify all features work
2. ✅ Fix any bugs found
3. ✅ Add automated tests (Vitest + React Testing Library)
4. ✅ Performance optimization if needed
5. ✅ Deploy to staging
6. ✅ Final QA
7. ✅ Production deployment

---

**Status**: ✅ Ready for Testing
**Last Updated**: December 12, 2025
**Frontend**: http://localhost:5173/admin/orders
**Backend**: http://localhost:8000

Happy Testing! 🚀
