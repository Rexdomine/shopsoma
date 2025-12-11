# Testing Vendor Orders Auth Fix

## The Bug
`orderService.ts` was using wrong localStorage key for auth token:
- **Used**: `'access_token'` ❌
- **Correct**: `'shopsoma_access_token'` ✅

Result: No Authorization header sent → 403 Forbidden

## The Fix
Changed from custom axios instance to shared `api` instance that uses correct storage key.

## How to Test

### Step 1: Clear browser cache (important!)
1. Open DevTools (F12)
2. Right-click the refresh button → "Empty Cache and Hard Reload"
   OR
3. Close and reopen the browser tab

### Step 2: Navigate to vendor orders
1. Go to: `http://localhost:5173/vendor/orders`
2. Wait for page to load

### Step 3: Check Network Tab
Open DevTools → Network tab → Find `/api/v1/vendor/orders` request

**Before fix** (you saw this):
```
Request Headers:
Accept: application/json
Origin: http://localhost:5173
(NO Authorization header)
```

**After fix** (you should see):
```
Request Headers:
Accept: application/json
Authorization: Bearer eyJhbGc...  ← THIS SHOULD NOW APPEAR!
Origin: http://localhost:5173
```

### Step 4: Check Server Logs
You should now see the FULL dependency chain:
```
[get_current_vendor] User ID: 6190c4db-3d83-47ba-9e08-770df1173729, Email: dominusparte@gmail.com, Role: vendor
[get_current_vendor] SUCCESS: User has VENDOR role
[get_vendor_profile] Looking for vendor with user_id: 6190c4db-3d83-47ba-9e08-770df1173729
[get_vendor_profile] User email: dominusparte@gmail.com, Role: vendor
[get_vendor_profile] SUCCESS: Found vendor Kester Club (id: 10b8fc3b-bc09-4d8a-90f4-d400dbb39268)
[get_approved_vendor] Checking approval for vendor: Kester Club  ← THIS IS NEW!
[get_approved_vendor] Vendor ID: 10b8fc3b-bc09-4d8a-90f4-d400dbb39268, Approved: True
[get_approved_vendor] SUCCESS: Vendor is approved  ← THIS IS NEW!
[list_vendor_orders] ENDPOINT REACHED - Vendor: Kester Club, Page: 1, Search: ''  ← THIS IS NEW!
INFO: 127.0.0.1:xxxxx - "GET /api/v1/vendor/orders?page=1&page_size=20 HTTP/1.1" 200 OK  ← 200 NOT 403!
```

### Step 5: Check UI
- ✅ "Unable to Load Orders" message should disappear
- ✅ Orders list should appear (or "No orders found" if empty)
- ✅ No more 403 errors in console

## Expected Results
- **Status**: 200 OK (was 403 Forbidden)
- **Response**: JSON with orders array
- **UI**: Orders list displayed
- **Logs**: All dependency checks passing

## If It Still Doesn't Work
1. Check localStorage in DevTools:
   - Application tab → Local Storage → `http://localhost:5173`
   - Verify `shopsoma_access_token` exists and has a value
2. Try logging out and back in to get fresh token
3. Share the NEW server logs and network tab screenshot

