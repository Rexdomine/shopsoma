# Pickup Window Display - Debugging Guide

**Date**: December 17, 2025
**Issue**: Vendor dashboard shows "Actual Pickup 13/12/2025" instead of the pickup window (start/end times) set on admin dashboard
**Status**: Debugging in progress with comprehensive logging

---

## CURRENT STATUS

### What's Working ✅
- Vendor business name now displays correctly ("Kester Club")
- Order data is being fetched successfully
- Modal opens and displays order status

### What's NOT Working ❌
- Pickup window (start/end times) not displaying
- Still shows "Actual Pickup 13/12/2025" instead

---

## DEBUGGING SETUP COMPLETE ✅

### Added Error Handling & Logging

#### 1. Frontend Logging - Order Fetch with Pickup Data
**File**: [`VendorOrderDetail.tsx:266-279`](shopsoma-frontend/src/pages/vendor/VendorOrderDetail.tsx#L266-L279)

```typescript
// Debug pickup window data
console.log('[VendorOrderDetail] Number of items:', data.items?.length);
if (data.items && data.items.length > 0) {
  const firstItem = data.items[0];
  console.log('[VendorOrderDetail] First item pickup data:', firstItem.pickup);
  if (firstItem.pickup) {
    console.log('[VendorOrderDetail] pickup_window_start:', firstItem.pickup.pickup_window_start);
    console.log('[VendorOrderDetail] pickup_window_end:', firstItem.pickup.pickup_window_end);
    console.log('[VendorOrderDetail] scheduled_pickup_date:', firstItem.pickup.scheduled_pickup_date);
    console.log('[VendorOrderDetail] actual_pickup_date:', firstItem.pickup.actual_pickup_date);
  } else {
    console.warn('[VendorOrderDetail] ⚠️ First item has no pickup data');
  }
}
```

**Purpose**: Logs the pickup data from the first item to verify if pickup window fields are present in API response

#### 2. Frontend Logging - Pickup Window Conditional Rendering
**File**: [`VendorOrderDetail.tsx:141-148`](shopsoma-frontend/src/pages/vendor/VendorOrderDetail.tsx#L141-L148)

```typescript
{(() => {
  console.log('[ShippingStatusCard] Checking pickup window conditions:');
  console.log('[ShippingStatusCard] pickup exists:', !!pickup);
  console.log('[ShippingStatusCard] pickup.pickup_window_start:', pickup?.pickup_window_start);
  console.log('[ShippingStatusCard] pickup.pickup_window_end:', pickup?.pickup_window_end);
  console.log('[ShippingStatusCard] Will show pickup window?', !!(pickup && pickup.pickup_window_start && pickup.pickup_window_end));
  return null;
})()}
```

**Purpose**:
- Shows if pickup object exists
- Shows the actual values of pickup_window_start and pickup_window_end
- Shows whether the conditional will render the pickup window section
- Identifies if the issue is missing data or rendering logic

---

## HOW TO DEBUG

### Step 1: Open Browser DevTools
```
1. Navigate to vendor order detail page
2. Press F12 (or Cmd+Option+I on Mac)
3. Go to Console tab
4. Clear console (Ctrl+L / Cmd+K)
```

### Step 2: View an Order
```
1. Login as vendor: http://localhost:5173/vendor/login
2. Go to orders: http://localhost:5173/vendor/orders
3. Click "View" on any order with "Pickup Scheduled" status
4. Click "View More" on the Order Status card
```

### Step 3: Check Console Logs

Look for these log messages in order:

#### Expected Log Sequence

**When order is fetched**:
```
[VendorOrderDetail] Fetched order data: {id: '...', order_number: '...', vendor_business_name: 'Kester Club', ...}
[VendorOrderDetail] vendor_business_name in response: "Kester Club"
[VendorOrderDetail] Number of items: 1
[VendorOrderDetail] First item pickup data: {id: '...', pickup_window_start: '...', pickup_window_end: '...', ...}
[VendorOrderDetail] pickup_window_start: "2024-12-20T09:00:00Z"
[VendorOrderDetail] pickup_window_end: "2024-12-20T12:00:00Z"
[VendorOrderDetail] scheduled_pickup_date: "2024-12-20T09:00:00Z"
[VendorOrderDetail] actual_pickup_date: null
```

**When modal opens (click "View More")**:
```
[ShippingStatusCard] Checking pickup window conditions:
[ShippingStatusCard] pickup exists: true
[ShippingStatusCard] pickup.pickup_window_start: "2024-12-20T09:00:00Z"
[ShippingStatusCard] pickup.pickup_window_end: "2024-12-20T12:00:00Z"
[ShippingStatusCard] Will show pickup window? true
```

#### If pickup_window fields are NULL/UNDEFINED

**When order is fetched**:
```
[VendorOrderDetail] Fetched order data: {id: '...', ...}
[VendorOrderDetail] Number of items: 1
[VendorOrderDetail] First item pickup data: {id: '...', ...}
[VendorOrderDetail] pickup_window_start: null
[VendorOrderDetail] pickup_window_end: null
[VendorOrderDetail] scheduled_pickup_date: "2024-12-13T00:00:00Z"
[VendorOrderDetail] actual_pickup_date: "2024-12-13T00:00:00Z"
```

**When modal opens**:
```
[ShippingStatusCard] Checking pickup window conditions:
[ShippingStatusCard] pickup exists: true
[ShippingStatusCard] pickup.pickup_window_start: null
[ShippingStatusCard] pickup.pickup_window_end: null
[ShippingStatusCard] Will show pickup window? false  ← THIS IS WHY IT'S NOT SHOWING
```

---

## DIAGNOSTIC SCENARIOS

### Scenario 1: Backend not returning pickup_window fields

**Symptoms**:
```
[VendorOrderDetail] pickup_window_start: undefined
[VendorOrderDetail] pickup_window_end: undefined
```

**Diagnosis**: Backend API endpoint not including these fields in response

**Fix**: Verify backend code at [`shopsoma-backend/app/api/v1/vendors.py:475-476`](shopsoma-backend/app/api/v1/vendors.py#L475-L476)

**Test API Directly**:
```bash
# Get vendor token first (login)
TOKEN="your-vendor-jwt-token"

# Test the endpoint
curl -X GET "http://localhost:8000/api/v1/vendors/orders/790ff9e3-5e24-490c-bac2-849200a4ddfe" \
  -H "Authorization: Bearer $TOKEN" \
  | python -m json.tool
```

**Expected Response**:
```json
{
  "id": "790ff9e3-5e24-490c-bac2-849200a4ddfe",
  "items": [
    {
      "pickup": {
        "pickup_window_start": "2024-12-20T09:00:00Z",  // ← Should be present
        "pickup_window_end": "2024-12-20T12:00:00Z",    // ← Should be present
        "scheduled_pickup_date": "2024-12-20T09:00:00Z",
        "actual_pickup_date": null
      }
    }
  ]
}
```

---

### Scenario 2: Database has NULL values for pickup_window

**Symptoms**:
```
[VendorOrderDetail] pickup_window_start: null
[VendorOrderDetail] pickup_window_end: null
[ShippingStatusCard] Will show pickup window? false
```

**Diagnosis**: Admin never set pickup window, or it wasn't saved to database

**Fix**: Check admin dashboard pickup scheduling flow

**Verify Database Directly**:
```bash
cd shopsoma-backend
export DATABASE_URL="postgresql://shopsoma:shopsoma_dev_password@localhost:5432/shopsoma_db"
export PGPASSWORD="shopsoma_dev_password"

psql -h localhost -U shopsoma -d shopsoma_db -c "
SELECT
  vp.id,
  vp.order_id,
  vp.pickup_window_start,
  vp.pickup_window_end,
  vp.scheduled_pickup_date,
  vp.actual_pickup_date
FROM vendor_pickups vp
WHERE vp.order_id = '790ff9e3-5e24-490c-bac2-849200a4ddfe';
"
```

**Expected Output**:
```
                  id                  |              order_id               |  pickup_window_start  |   pickup_window_end   | scheduled_pickup_date | actual_pickup_date
--------------------------------------+-------------------------------------+-----------------------+-----------------------+-----------------------+--------------------
 abc123...                            | 790ff9e3-5e24-490c-bac2-849200a4ddfe | 2024-12-20 09:00:00+00 | 2024-12-20 12:00:00+00 | 2024-12-20 09:00:00+00 | (null)
```

**If pickup_window_start and pickup_window_end are NULL**:
- Admin didn't set pickup window when scheduling
- Check admin dashboard code for pickup window form inputs
- Verify admin API endpoint saves pickup_window_start and pickup_window_end

---

### Scenario 3: Admin sets pickup window but it's not saved

**Symptoms**:
- Admin dashboard shows pickup window form
- Admin enters start/end times and clicks save
- Database still has NULL values
- Vendor sees "Actual Pickup" instead of pickup window

**Diagnosis**: Admin API endpoint not saving pickup_window fields

**Fix**: Check admin pickup scheduling endpoint

**Files to Check**:
1. **Admin frontend form**: Where admin sets pickup window
2. **Admin API endpoint**: `/api/v1/admin/orders/{order_id}/pickup-schedule` (or similar)
3. **Backend pickup update logic**: Verify it saves pickup_window_start and pickup_window_end

---

### Scenario 4: TypeScript interface mismatch

**Symptoms**:
```
[VendorOrderDetail] First item pickup data: {...}
[VendorOrderDetail] pickup_window_start: undefined  ← Field exists in API but undefined in frontend
```

**Diagnosis**: Frontend TypeScript interface doesn't match backend response

**Fix**: Check [`shopsoma-frontend/src/services/orderService.ts`](shopsoma-frontend/src/services/orderService.ts) VendorPickup interface

**Should have**:
```typescript
export interface VendorPickup {
  id: string;
  order_type: string;
  scheduled_pickup_date: string | null;
  actual_pickup_date: string | null;
  pickup_window_start: string | null;  // ← Should be present
  pickup_window_end: string | null;    // ← Should be present
  pickup_address: string | null;
  courier_name: string | null;
  rider_id: string | null;
  logistics_partner: string | null;
  tracking_number: string | null;
  status: string;
  // ... rest of fields
}
```

---

## TESTING CHECKLIST

### Test 1: Verify API Response
- [ ] Open Network tab in DevTools
- [ ] View order detail page
- [ ] Find request to `/api/v1/vendors/orders/{id}`
- [ ] Click on request > Preview/Response tab
- [ ] Expand `items[0].pickup` object
- [ ] **Expected**: `pickup_window_start` and `pickup_window_end` fields present with values or null

### Test 2: Check Console Logs
- [ ] View order detail page
- [ ] Check console for: `[VendorOrderDetail] pickup_window_start: ...`
- [ ] Check console for: `[VendorOrderDetail] pickup_window_end: ...`
- [ ] **Expected**: Values should match what's in API response

### Test 3: Modal Rendering
- [ ] Click "View More" on Order Status card
- [ ] Check console for: `[ShippingStatusCard] Will show pickup window? ...`
- [ ] If `true`: Pickup window section should render
- [ ] If `false`: Check why pickup_window_start or pickup_window_end is missing

### Test 4: Database Verification
- [ ] Run SQL query to check pickup_window values
- [ ] **Expected**: If admin set pickup window, fields should have datetime values, not NULL

---

## NEXT STEPS BASED ON CONSOLE OUTPUT

### If you see: `pickup_window_start: null` and `pickup_window_end: null`
❌ **Database has no pickup window data**
- Admin never set pickup window, or it wasn't saved
- Check admin dashboard pickup scheduling flow
- Verify admin API endpoint saves these fields
- Test by setting pickup window from admin dashboard

### If you see: `pickup_window_start: undefined` and `pickup_window_end: undefined`
❌ **Backend not returning the fields**
- Check backend endpoint returns these fields
- Verify backend code at vendors.py:475-476
- Restart backend server if recently modified
- Test API directly with curl

### If you see: `pickup_window_start: "2024-12-20T09:00:00Z"` but `Will show pickup window? false`
⚠️ **Conditional rendering issue**
- Data is present but not rendering
- Check for type mismatch (string vs Date)
- Verify conditional logic in VendorOrderDetail.tsx:149
- Check for truthy/falsy value issues

### If you see: `Will show pickup window? true` but no pickup window displays
⚠️ **Rendering issue**
- Conditional is passing but component not rendering
- Check React DevTools for component tree
- Verify no CSS hiding the element
- Check for JavaScript errors in console

---

## COMMON FIXES

### Fix 1: Admin Doesn't Save Pickup Window

**Check Admin Dashboard Pickup Scheduling**:
```bash
cd shopsoma-frontend
grep -rn "pickup_window" src/pages/admin/
```

**Ensure Admin Form Has These Inputs**:
```typescript
<input type="datetime-local" name="pickup_window_start" />
<input type="datetime-local" name="pickup_window_end" />
```

**Ensure Admin API Sends These Fields**:
```typescript
await updateOrderPickup(orderId, {
  pickup_window_start: formData.pickup_window_start,
  pickup_window_end: formData.pickup_window_end,
  // ... other fields
});
```

### Fix 2: Backend Doesn't Save Pickup Window

**Check Admin API Endpoint**:
```bash
cd shopsoma-backend
grep -rn "pickup_window" app/api/v1/admin.py
```

**Ensure Endpoint Updates These Fields**:
```python
pickup.pickup_window_start = pickup_data.get('pickup_window_start')
pickup.pickup_window_end = pickup_data.get('pickup_window_end')
db.commit()
```

### Fix 3: Frontend Interface Missing Fields

**Update VendorPickup Interface**:
```typescript
export interface VendorPickup {
  // ... existing fields
  pickup_window_start: string | null;
  pickup_window_end: string | null;
}
```

**Restart Frontend Dev Server**:
```bash
cd shopsoma-frontend
# Kill server (Ctrl+C)
npm run dev
```

---

## RELATED DOCUMENTATION

- **Vendor Business Name Fix**: [VENDOR_PICKUP_STATUS_DISPLAY_FIX.md](VENDOR_PICKUP_STATUS_DISPLAY_FIX.md)
- **Previous Debugging Guide**: [VENDOR_PICKUP_STATUS_DEBUGGING.md](VENDOR_PICKUP_STATUS_DEBUGGING.md)
- **Customer Email Fixes**: [CUSTOMER_EMAIL_SECOND_FIX_COMPLETE.md](CUSTOMER_EMAIL_SECOND_FIX_COMPLETE.md)

---

**Status**: ✅ Comprehensive debugging enabled for pickup window display

Now when you view an order and click "View More", check the browser console to see:
1. Whether pickup_window_start and pickup_window_end are in the API response
2. Whether they're null or have values
3. Whether the conditional rendering will show the pickup window section
4. This will pinpoint exactly why the pickup window isn't displaying!
