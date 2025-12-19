# Current Status: Guest Cart Merge Issue

## Problem Statement
When a guest user adds items to their cart and then logs in from the checkout page, the cart appears empty after login, and the checkout total falls back to ₦2,000.

Backend logs show:
```
[Cart API] merge_guest_cart: user_id=8ecbe287-..., session_id=e6176a98-b0d1-4b3c-a138-e4ab152e8fe8
[Cart API] merge_guest_cart: Found 0 guest items for session e6176a98-b0d1-4b3c-a138-e4ab152e8fe8
```

## Root Cause Hypothesis
The frontend and backend are using **different session UUIDs**:

1. **Frontend** generates its own session ID and stores it in `localStorage` under key `shopsoma_cart_session`
2. **Frontend** sends this session ID in the `X-Session-ID` header on every request
3. **Backend** receives the header, BUT if the header is `None` or missing, it generates a NEW UUID
4. **Backend** stores cart items with the auto-generated session ID
5. **At merge time**, frontend sends its own session ID, but backend finds 0 items because they're stored under a different session ID

## What We've Done So Far

### 1. Fixed Cart Duplication Issue
- Created server-side merge endpoint that properly deduplicates by `(product_id, variant_id)`
- Removed broken client-side merge logic

### 2. Fixed Session ID Not Sent After Login
- Changed frontend to always send `X-Session-ID` header, even when authenticated
- Previously it only sent the header when NOT authenticated

### 3. Added Comprehensive Logging
To diagnose the session ID mismatch:

**Backend** ([cart.py:112-117](shopsoma-backend/app/api/v1/cart.py#L112-L117)):
```python
print(f"[Cart API] get_user_or_session_id: user_id={user_id}, received session_id={session_id}")
if not user_id and not session_id:
    session_id = str(uuid.uuid4())
    print(f"[Cart API] get_user_or_session_id: WARNING - No session_id provided, generated new one: {session_id}")
```

**Backend** ([cart.py:175](shopsoma-backend/app/api/v1/cart.py#L175)):
```python
print(f"[Cart API] add_to_cart: Using user_id={user_uuid}, session_id={sess_id}")
```

**Backend** ([cart.py:237](shopsoma-backend/app/api/v1/cart.py#L237)):
```python
print(f"[Cart API] add_to_cart created id={cart_item.id} qty={cart_item.quantity} user={user_uuid} session={cart_item.session_id}")
```

**Frontend** ([cartService.ts:39-41](shopsoma-frontend/src/services/cartService.ts#L39-L41)):
```typescript
if (sessionId) {
  headers['X-Session-ID'] = sessionId;
  console.log('[CartAPI] Sending X-Session-ID header:', sessionId);
} else {
  console.warn('[CartAPI] No session ID to send!');
}
```

## Next Steps - Manual Testing Required

### Testing Instructions
See detailed steps in [test_session_id_flow.md](test_session_id_flow.md)

**Quick test:**
1. Open browser with DevTools Console visible
2. Clear all site data
3. Add item to cart as guest
4. **Watch both browser console AND backend terminal**
5. Look for session UUID mismatches

### What to Look For

#### ✅ GOOD - Session IDs Match
```
Frontend Console: [CartAPI] Sending X-Session-ID header: abc-123-def
Backend Terminal:  [Cart API] get_user_or_session_id: user_id=None, received session_id=abc-123-def
Backend Terminal:  [Cart API] add_to_cart: Using user_id=None, session_id=abc-123-def
Backend Terminal:  [Cart API] add_to_cart created ... session=abc-123-def
```

#### ❌ BAD - Session ID Mismatch
```
Frontend Console: [CartAPI] Sending X-Session-ID header: abc-123-def
Backend Terminal:  [Cart API] get_user_or_session_id: user_id=None, received session_id=None
Backend Terminal:  [Cart API] get_user_or_session_id: WARNING - No session_id provided, generated new one: xyz-789-hij
Backend Terminal:  [Cart API] add_to_cart: Using user_id=None, session_id=xyz-789-hij
```

### Possible Issues to Check

1. **CORS**: Is the `X-Session-ID` header allowed?
2. **API Gateway/Proxy**: Is the header being stripped?
3. **Header Casing**: Is FastAPI looking for the wrong case?
4. **Frontend Header Config**: Is the header actually being added?

## Files Modified

### Backend
- [shopsoma-backend/app/api/v1/cart.py](shopsoma-backend/app/api/v1/cart.py)
  - Lines 112-117: Added logging to `get_user_or_session_id()`
  - Line 175: Added logging to `add_to_cart()` to show which session_id is being used
  - Line 237: Added logging to show session_id stored in database

### Frontend
- [shopsoma-frontend/src/services/cartService.ts](shopsoma-frontend/src/services/cartService.ts)
  - Lines 37-42: Always send X-Session-ID header (already fixed in previous iteration)
  - Lines 39-41: Added logging to show which session_id is being sent

## Database Query to Check Reality

Run this to see what's actually in the database:

```sql
-- Show all guest cart items
SELECT
    id,
    user_id,
    session_id,
    product_id,
    quantity,
    created_at
FROM cart_items
WHERE user_id IS NULL
ORDER BY created_at DESC
LIMIT 10;
```

Compare the `session_id` values in the database with what you see in the frontend console's localStorage.

## Current State
- ✅ Both frontend and backend servers are running
- ✅ Backend will auto-reload with new logging (FastAPI --reload mode)
- ✅ Frontend may need manual refresh to pick up changes
- ⏳ Waiting for manual testing to confirm session ID flow

## Expected Outcome After Fix
Once we identify and fix the session ID mismatch:
1. Guest adds items → items stored with frontend's session ID
2. Guest logs in → merge endpoint receives same session ID
3. Backend finds the items and transfers them to user
4. Cart shows correctly after login
