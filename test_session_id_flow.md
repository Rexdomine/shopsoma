# Session ID Flow Debugging

## Changes Made

### Backend: [cart.py](shopsoma-backend/app/api/v1/cart.py)

Added comprehensive logging to track session ID flow:

1. **`get_user_or_session_id()` function** (lines 112, 117):
   - Logs received session_id from X-Session-ID header
   - Warns when generating a new session_id

2. **`add_to_cart()` function** (lines 175, 237):
   - Logs the session_id being used
   - Logs the session_id stored in the created cart item

### Frontend: [cartService.ts](shopsoma-frontend/src/services/cartService.ts)

Added logging to track outgoing session IDs (lines 39, 41):
- Logs X-Session-ID header value being sent
- Warns if no session ID exists

## Test Steps

### Step 1: Clear All Data
1. Open browser DevTools (F12)
2. Go to Application tab → Storage → Clear site data
3. Close and reopen browser
4. Navigate to http://localhost:5173

### Step 2: Add Item as Guest
1. Browse to a product page
2. Click "Add to Cart"
3. **Check Browser Console** - look for:
   ```
   [CartAPI] Sending X-Session-ID header: <some-uuid>
   ```
4. **Check Backend Terminal** - look for:
   ```
   [Cart API] get_user_or_session_id: user_id=None, received session_id=<same-uuid>
   [Cart API] add_to_cart: Using user_id=None, session_id=<same-uuid>
   [Cart API] add_to_cart created id=<cart-item-id> qty=1 user=None session=<same-uuid>
   ```

### Step 3: Verify Cart
1. Click on cart icon
2. Should see the item in cart
3. **Check Browser Console**:
   ```
   [CartAPI] Sending X-Session-ID header: <same-uuid-from-step-2>
   ```
4. **Check Backend Terminal**:
   ```
   [Cart API] get_user_or_session_id: user_id=None, received session_id=<same-uuid>
   [Cart API] get_cart user=None session=<same-uuid> items=1
   ```

### Step 4: Proceed to Checkout and Login
1. Click "Proceed to Checkout"
2. Click "Sign In"
3. Login with valid credentials
4. After redirect back to checkout:

5. **Check Browser Console** - look for:
   ```
   [CartAPI] Sending X-Session-ID header: <same-uuid-from-step-2>
   [CartAPI] syncWithServer: Merged cart successfully
   ```

6. **Check Backend Terminal** - look for:
   ```
   [Cart API] merge_guest_cart: user_id=<user-uuid>, session_id=<same-uuid-from-step-2>
   [Cart API] merge_guest_cart: Found 1 guest items for session <same-uuid>
   [Cart API] merge_guest_cart: Merged 0 items, transferred 1 items
   ```

## Expected vs Actual

### Expected Behavior (GOOD)
All logs show the **same session UUID** throughout:
- Frontend generates UUID once (e.g., `abc-123`)
- All requests send X-Session-ID: `abc-123`
- Backend receives and uses `abc-123`
- Cart items stored with session_id = `abc-123`
- Merge finds items with session_id = `abc-123`

### Possible Bug Scenario (BAD)
Frontend and backend use **different session UUIDs**:
- Frontend sends X-Session-ID: `abc-123`
- But backend generates new UUID: `def-456` (WARNING log appears)
- Cart items stored with session_id = `def-456`
- At merge, frontend sends `abc-123`
- Merge finds 0 items because they're under `def-456`

## Key Questions to Answer

1. ✅ Is frontend generating and storing a session ID?
2. ✅ Is frontend sending X-Session-ID header on every request?
3. ❓ Is backend receiving the header?
4. ❓ Is backend using the received session ID or generating a new one?
5. ❓ Are cart items stored with the same session_id that frontend is using?
6. ❓ At merge time, does the session_id match what's in the database?

## Database Query to Check

Run this in your database to see what session IDs actually exist:

```sql
SELECT id, user_id, session_id, product_id, quantity, created_at
FROM cart_items
WHERE user_id IS NULL
ORDER BY created_at DESC
LIMIT 10;
```

This will show you:
- What session_id values are actually stored
- Compare with the session_id from frontend console

## Next Steps Based on Findings

### If "WARNING - No session_id provided" appears:
**Problem**: Frontend not sending X-Session-ID header
**Fix**: Check api.ts interceptors or header configuration

### If backend receives different session_id than frontend sends:
**Problem**: Header not being transmitted properly
**Fix**: Check CORS, proxy config, or header casing

### If session_id matches but items not found:
**Problem**: Database query issue in merge_guest_cart
**Fix**: Check the WHERE clause in merge_guest_cart query
