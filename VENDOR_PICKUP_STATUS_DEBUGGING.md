# Vendor Pickup Status Display - Debugging Guide

**Date**: December 17, 2025
**Issue**: Vendor dashboard order status modal still showing "Gwarinpa" instead of vendor business name
**Status**: Debugging in progress with comprehensive error handling

---

## DEBUGGING SETUP COMPLETE ✅

### Added Error Handling & Logging

#### 1. Frontend Logging - Order Fetch
**File**: [`VendorOrderDetail.tsx:263-264`](shopsoma-frontend/src/pages/vendor/VendorOrderDetail.tsx#L263-L264)

```typescript
const data = await getVendorOrder(id);
console.log('[VendorOrderDetail] Fetched order data:', data);
console.log('[VendorOrderDetail] vendor_business_name in response:', data.vendor_business_name);
setOrder(data);
```

**Purpose**: Logs the raw API response to verify if `vendor_business_name` is being returned

#### 2. Frontend Logging - Origin Label
**File**: [`VendorOrderDetail.tsx:68-84`](shopsoma-frontend/src/pages/vendor/VendorOrderDetail.tsx#L68-L84)

```typescript
const getOriginLabel = (): string => {
  // Display vendor business name with fallback and error handling
  console.log('[VendorOrderDetail] order.vendor_business_name:', order.vendor_business_name);
  console.log('[VendorOrderDetail] Full order object:', order);

  if (!order.vendor_business_name) {
    console.warn('[VendorOrderDetail] vendor_business_name is missing from order data');
    // Fallback to pickup address if vendor name not available
    if (pickup && pickup.pickup_address) {
      console.log('[VendorOrderDetail] Falling back to pickup_address:', pickup.pickup_address);
      return pickup.pickup_address.substring(0, 30) + (pickup.pickup_address.length > 30 ? '...' : '');
    }
    return 'Vendor Location';
  }

  return order.vendor_business_name;
};
```

**Purpose**:
- Logs the value of `vendor_business_name` when rendering
- Provides fallback behavior if field is missing
- Shows which fallback is being used

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
3. Click "View" on any order
```

### Step 3: Check Console Logs

Look for these log messages in order:

#### Expected Log Sequence

**When order is fetched**:
```
[VendorOrderDetail] Fetched order data: {id: '...', order_number: '...', vendor_business_name: 'Acme Fashion', ...}
[VendorOrderDetail] vendor_business_name in response: "Acme Fashion"
```

**When modal opens (click "View More")**:
```
[VendorOrderDetail] order.vendor_business_name: "Acme Fashion"
[VendorOrderDetail] Full order object: {...}
```

#### If vendor_business_name is MISSING

**When order is fetched**:
```
[VendorOrderDetail] Fetched order data: {id: '...', order_number: '...', ...}
[VendorOrderDetail] vendor_business_name in response: undefined
```

**When modal opens**:
```
[VendorOrderDetail] order.vendor_business_name: undefined
[VendorOrderDetail] Full order object: {...}
⚠️ [VendorOrderDetail] vendor_business_name is missing from order data
[VendorOrderDetail] Falling back to pickup_address: "Gwarinpa"
```

---

## DIAGNOSTIC SCENARIOS

### Scenario 1: Field is in API response but not in order object

**Symptoms**:
```
[VendorOrderDetail] vendor_business_name in response: "Acme Fashion"
[VendorOrderDetail] order.vendor_business_name: undefined
```

**Diagnosis**: TypeScript interface might be wrong or state not updated correctly

**Fix**: Check if `VendorOrder` interface in `orderService.ts` has `vendor_business_name` field

---

### Scenario 2: Field is missing from API response

**Symptoms**:
```
[VendorOrderDetail] vendor_business_name in response: undefined
```

**Diagnosis**: Backend not returning the field

**Fix Steps**:
1. Check backend logs for errors
2. Test API directly with curl
3. Verify backend code was deployed/reloaded

**Test API Directly**:
```bash
# Get vendor token first (login)
TOKEN="your-vendor-jwt-token"

# Test the endpoint
curl -X GET "http://localhost:8000/api/v1/vendors/orders/{order_id}" \
  -H "Authorization: Bearer $TOKEN" \
  | python -m json.tool
```

**Expected Response**:
```json
{
  "id": "...",
  "order_number": "ORD-2024-12345",
  "vendor_business_name": "Acme Fashion Store",  // ← Should be present
  "customer_name": "John Doe",
  // ... rest of fields
}
```

---

### Scenario 3: Caching issue

**Symptoms**:
- Logs show `vendor_business_name: undefined`
- Backend code looks correct
- API test returns correct data

**Diagnosis**: Browser cached old API response or old JavaScript bundle

**Fix**:
```bash
# Clear browser cache
1. Open DevTools (F12)
2. Right-click on reload button
3. Select "Empty Cache and Hard Reload"

# Or in DevTools Application tab
1. Go to Application > Storage
2. Click "Clear site data"

# Verify new bundle loaded
1. Check Network tab
2. Filter by "JS"
3. Look for VendorOrderDetail chunk
4. Should see "(from disk cache)" or "200 OK" with recent timestamp
```

---

### Scenario 4: Backend server didn't reload

**Symptoms**:
- Frontend logs show field missing
- Backend code shows field added
- No error in backend logs

**Diagnosis**: Uvicorn didn't detect file changes or crashed

**Fix**:
```bash
# Stop all uvicorn processes
pkill -f uvicorn

# Restart backend manually
cd shopsoma-backend
. venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**Verify Backend Reloaded**:
```bash
# Check backend logs for
INFO:     Application startup complete.
INFO:     WatchFiles detected changes in 'app/api/v1/vendors.py'. Reloading...
```

---

## TESTING CHECKLIST

After adding error handling, test these scenarios:

### Test 1: Normal Flow
- [ ] Login as vendor
- [ ] View order detail page
- [ ] Check console for: `vendor_business_name in response: "..."`
- [ ] Click "View More" on Order Status card
- [ ] Check console for: `order.vendor_business_name: "..."`
- [ ] **Expected**: Modal shows vendor business name

### Test 2: Missing Field
- [ ] Check console for warning: `vendor_business_name is missing`
- [ ] Check console for fallback: `Falling back to pickup_address`
- [ ] **Expected**: Modal shows pickup address as fallback

### Test 3: API Response
- [ ] Open Network tab in DevTools
- [ ] View order detail page
- [ ] Find request to `/api/v1/vendors/orders/{id}`
- [ ] Click on request > Preview/Response tab
- [ ] **Expected**: `vendor_business_name` field present in JSON

---

## COMMON FIXES

### Fix 1: TypeScript Error

**Error**:
```
Property 'vendor_business_name' does not exist on type 'VendorOrder'
```

**Solution**:
```bash
# Restart frontend dev server
cd shopsoma-frontend
# Kill server (Ctrl+C)
npm run dev
```

### Fix 2: 500 Internal Server Error

**Error in browser console**:
```
Failed to load order
Error details: {detail: "Internal Server Error"}
```

**Solution**: Check backend logs for Python traceback

```bash
# Check backend terminal for error like:
ERROR: Exception in ASGI application
Traceback (most recent call last):
  ...
AttributeError: 'Vendor' object has no attribute 'business_name'
```

### Fix 3: Field Shows as "undefined" in UI

**Symptoms**: Modal displays text "undefined" instead of vendor name

**Diagnosis**: Trying to render undefined value

**Solution**: Add null check in JSX (already handled by our fix)

---

## VERIFICATION STEPS

### 1. Verify Backend Schema
```bash
cd shopsoma-backend
grep -n "vendor_business_name" app/schemas/vendor.py
# Should show: vendor_business_name: str
```

### 2. Verify Backend Endpoint
```bash
grep -n "vendor_business_name" app/api/v1/vendors.py
# Should show: "vendor_business_name": vendor.business_name
```

### 3. Verify Frontend Interface
```bash
cd shopsoma-frontend
grep -n "vendor_business_name" src/services/orderService.ts
# Should show: vendor_business_name: string;
```

### 4. Verify Frontend Usage
```bash
grep -n "vendor_business_name" src/pages/vendor/VendorOrderDetail.tsx
# Should show usage in getOriginLabel()
```

---

## NEXT STEPS BASED ON CONSOLE OUTPUT

### If you see: `vendor_business_name in response: "Acme Fashion"`
✅ **Backend is working correctly**
- Issue is in frontend state/rendering
- Check React DevTools to see state value
- Verify order object has the field after setOrder()

### If you see: `vendor_business_name in response: undefined`
❌ **Backend is not returning the field**
- Restart backend server
- Test API with curl
- Check backend logs for errors
- Verify `vendor.business_name` exists in database

### If you see: `Falling back to pickup_address: "Gwarinpa"`
⚠️ **Fallback is being used**
- This confirms why "Gwarinpa" appears
- Need to fix root cause (backend or frontend)
- At least users see something instead of blank

---

## LOGS TO SHARE FOR SUPPORT

If issue persists, share these logs:

1. **Browser Console Output** (all lines with `[VendorOrderDetail]`)
2. **Network Tab**: Screenshot of API response for `/api/v1/vendors/orders/{id}`
3. **Backend Logs**: Last 50 lines showing the API request
4. **React DevTools**: Screenshot of order state in Components tab

---

**Status**: ✅ Comprehensive debugging enabled

Now when you view an order, check the browser console and you'll see exactly:
1. What the API is returning
2. What value is in the order object
3. Which fallback (if any) is being used
4. Why "Gwarinpa" might still appear

This will pinpoint the exact issue!
