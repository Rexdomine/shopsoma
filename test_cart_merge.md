# Cart Merge Fix - Test Checklist

## Changes Made

### Backend: `/Users/rex/Documents/Shopsoma/shopsoma-backend/app/api/v1/cart.py`
- **Added `POST /api/v1/cart/merge-guest-cart` endpoint** - Handles server-side cart merge
  - Fetches guest cart items by `session_id` where `user_id IS NULL`
  - Fetches user's existing cart items
  - For matching `(product_id, variant_id)` pairs: merges quantities into user's cart
  - For non-matching items: transfers ownership from guest to user
  - Deletes guest cart items after merge
  - Returns the merged cart
- **Enhanced logging** - Added debug logs showing user_id and session_id at merge start

### Frontend: `/Users/rex/Documents/Shopsoma/shopsoma-frontend/src/services/cartService.ts`
- **CRITICAL FIX: Always send X-Session-ID header** - Fixed line 37 to always send session ID
  - **Before**: `if (sessionId && !token)` - only sent session ID for guests
  - **After**: `if (sessionId)` - always sends session ID, even after login
  - This allows merge-guest-cart to receive the guest session ID after authentication

- **Updated `syncWithServer()` method** - Now calls backend merge endpoint instead of client-side merge
  - Calls `mergeGuestCartOnServer()` which invokes `POST /cart/merge-guest-cart`
  - Clears local session ID after successful merge to prevent re-merge on refresh
  - Falls back to `fetchServerCart()` if merge fails

- **Added `mergeGuestCartOnServer()` method** - Calls the new backend merge endpoint

- **Removed `mergeLocalAndServerCart()` method** - Replaced with server-side merge

## Test Scenarios

### Test 1: Guest adds item, logs in at checkout
**Steps:**
1. Clear all cookies/localStorage
2. As guest: Add 1 product (variant X), quantity 9
3. Verify cart shows: 1 item, qty 9, correct total (e.g., ₦60,300)
4. Click "Proceed to Checkout"
5. Click "Sign In" and log in with valid credentials
6. Should redirect back to `/checkout`

**Expected Result:**
- Cart shows: 1 item, qty 9, same total (₦60,300)
- NO duplicate items
- NO quantity increase beyond 9

### Test 2: User with existing cart logs out, adds as guest, logs back in
**Steps:**
1. Log in as user
2. Add product A (variant X), quantity 2
3. Log out
4. As guest: Add same product A (variant X), quantity 3
5. Click "Proceed to Checkout"
6. Log in with same user credentials

**Expected Result:**
- Cart shows: 1 item (product A, variant X), qty 5 (2 + 3)
- Total reflects qty 5
- NO duplicate line items

### Test 3: Refresh after login doesn't re-merge
**Steps:**
1. Complete Test 1 or Test 2
2. After landing on checkout with merged cart, press F5/refresh page
3. Check cart contents

**Expected Result:**
- Cart remains the same
- Quantities don't increase again
- NO duplicates created

### Test 4: Guest with empty cart logs in (user has items)
**Steps:**
1. Log in as user who has items in cart
2. Note cart contents (e.g., 2 items)
3. Log out
4. As guest: Don't add anything to cart
5. Go to checkout and log in

**Expected Result:**
- User's original cart is preserved
- No changes to cart

### Test 5: Pure guest checkout (no login)
**Steps:**
1. As guest: Add items to cart
2. Proceed to checkout
3. Don't log in, continue as guest

**Expected Result:**
- Guest cart works normally
- No changes to behavior

### Test 6: Pure logged-in user (never guest)
**Steps:**
1. Log in from home page
2. Add items to cart
3. Proceed to checkout

**Expected Result:**
- User cart works normally
- No changes to behavior

## How to Verify in Browser Console

During login flow, check browser console for:
```
[CartAPI] syncWithServer: Merged cart successfully
[CartAPI] Merged guest cart on server: <N> items
```

Backend logs should show:
```
[Cart API] merge_guest_cart: Found <N> guest items for session <session_id>
[Cart API] merge_guest_cart: Merged <X> items, transferred <Y> items
```

## Root Cause Analysis

### Issue 1: Cart Duplication (FIXED)
**Problem:** Frontend's `mergeLocalAndServerCart()` compared:
- `localItem.id` (composite string like `"product123_variant456"`)
- `serverItem.id` (UUID from database)

These never matched, so every local item was added to server cart as a new item, creating duplicates.

**Solution:** Server-side merge endpoint properly compares `(product_id, variant_id)` tuples to identify matching items and merge quantities atomically in a single database transaction.

### Issue 2: Session ID Not Sent After Login (FIXED)
**Problem:** Frontend only sent X-Session-ID header when NOT authenticated (`if (sessionId && !token)`)

**Solution:** Changed to always send session ID header (`if (sessionId)`)

### Issue 3: Guest Items Not Found During Merge (INVESTIGATING)
**Problem:** `merge_guest_cart` receives session_id but finds 0 guest items

**Hypothesis:** Frontend and backend may be using different session UUIDs:
- Frontend generates and stores its own session ID
- Backend may be generating a different session ID when frontend's ID isn't received
- Cart items stored under backend's ID, merge looks for frontend's ID

**Added Logging:**
- Backend logs: received session_id, used session_id, stored session_id
- Frontend logs: sent session_id
- See [test_session_id_flow.md](test_session_id_flow.md) for debugging steps
