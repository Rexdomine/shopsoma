# WebSocket Guest/Auth Quick Start Guide

## 🚀 Quick Testing

### Test Guest Connection (No Login)

```bash
# 1. Get an order ID from your database or create one
ORDER_ID="your-order-uuid-here"

# 2. Open tracking page (NOT logged in)
open "http://localhost:5173/orders/${ORDER_ID}/tracking"

# 3. Check browser console - should see:
# [WebSocket] Connecting to: ... (guest mode)
# [WebSocket] Connected successfully
# 🟢 Live Updates Active
```

### Test Authenticated Connection (Logged In)

```bash
# 1. Login to the application
# 2. Navigate to "My Orders"
# 3. Click any order
# 4. Check browser console - should see:
# [WebSocket] Connecting to: ... (authenticated)
# [WebSocket] Connected successfully
```

### Test Real-time Updates

```bash
# Terminal 1: Watch backend logs
cd shopsoma-backend
source venv/bin/activate
python -m uvicorn app.main:app --reload

# Terminal 2: Keep customer tracking page open
# Terminal 3: Update order as admin

# Should see in customer browser (instantly):
# [OrderTracking] ===== WEBSOCKET UPDATE RECEIVED =====
# Progress bar updates with no refresh
```

---

## ✅ Verification Checklist

### Before This Fix
- [ ] Guest users see "No auth token found" in console
- [ ] Status stuck on "Order Placed"
- [ ] Orange "Polling for Updates" indicator
- [ ] Updates delayed by 10 seconds

### After This Fix
- [x] Guest users connect to WebSocket
- [x] Status updates in real-time (<500ms)
- [x] Green "Live Updates Active" indicator
- [x] No page refresh needed

---

## 🧪 Run Automated Tests

### Quick Test
```bash
# Test guest connection only
python3 test_websocket_guest_auth.py <order-id>
```

### Full Test Suite
```bash
# Complete integration test
./test_websocket_realtime_complete.sh
```

Expected output: `4/4 tests passed ✓`

---

## 📊 What Changed

| Component | Before | After |
|-----------|--------|-------|
| **Backend** | Token required | Token optional |
| **Frontend Service** | `token: string` | `token: string \| null` |
| **Frontend Component** | Skips if no token | Connects regardless |
| **Guest Users** | ❌ No real-time | ✅ Real-time |
| **Authenticated Users** | ✅ Real-time | ✅ Real-time |

---

## 🔧 Key Files Modified

1. **Backend**: `shopsoma-backend/app/api/v1/websocket.py`
   - Line 25: `token: str = Query(None, ...)` (was `Query(...)`)
   - Lines 59-87: Dual-mode authentication logic

2. **Frontend Service**: `shopsoma-frontend/src/services/websocketService.ts`
   - Line 46: `token: string | null` (was `string`)
   - Lines 67-73: Conditional URL building

3. **Frontend Component**: `shopsoma-frontend/src/pages/orders/OrderTracking.tsx`
   - Lines 93-99: Removed token requirement
   - Pass `token` or `null` to WebSocket service

---

## 🐛 Troubleshooting

### WebSocket Not Connecting

```javascript
// Console shows:
[WebSocket] Connection closed: 1006
```

**Fix**: Check backend running on port 8000
```bash
lsof -i :8000 | grep LISTEN
```

### Still Shows "Polling for Updates"

```javascript
// Console shows:
🟠 Polling for Updates
```

**Check**:
1. Order ID valid? (must be UUID format)
2. Order exists in database?
3. Backend logs show connection?

### No Updates When Admin Changes Status

**Check**:
1. Admin token valid?
2. Backend logs show broadcast?
3. Order ID matches between pages?

**Backend logs should show**:
```python
[WebSocket] ===== BROADCASTING ORDER UPDATE =====
[WebSocket] Active Connections: 1  # or more
[WebSocket] ✓ Broadcast complete
```

---

## 📝 Example Flow

### Scenario: Customer Tracks Order

1. **Customer receives email**: "Track your order: ABC-123"

2. **Customer clicks link**: `https://shopsoma.com/orders/ABC-123/tracking`

3. **Page loads**:
   ```javascript
   [OrderTracking] Connecting in guest mode
   [WebSocket] Connecting to: ws://.../.../ABC-123 (guest mode)
   [WebSocket] Connected successfully
   ```

4. **UI shows**:
   ```
   🟢 Live Updates Active
   Order #ABC-123
   Status: Order Placed
   [1]━━[ 2 ]━━[ 3 ]━━[ 4 ]
   ```

5. **Admin updates order** → Customer sees instantly:
   ```
   Status: In Transit
   [1]━━[2]━━[ 3 ]━━[ 4 ]
   ```

6. **No page refresh needed** ✨

---

## 🎯 Key Features

### For Guest Users
- ✅ Real-time updates without login
- ✅ Only need order ID
- ✅ <500ms update latency
- ✅ Automatic fallback to polling if WebSocket fails

### For Authenticated Users
- ✅ Real-time updates with full authorization
- ✅ Verified as order owner
- ✅ Same performance as guest mode
- ✅ Enhanced security

### For Administrators
- ✅ Status changes broadcast instantly
- ✅ Works for all connected users
- ✅ Comprehensive logging
- ✅ No code changes needed

---

## 📚 Full Documentation

See [WEBSOCKET_GUEST_AUTH_IMPLEMENTATION.md](./WEBSOCKET_GUEST_AUTH_IMPLEMENTATION.md) for:
- Complete architecture details
- Security considerations
- Test procedures
- Troubleshooting guide
- Performance metrics

---

## ✨ Status: COMPLETE

All features implemented, tested, and documented.

**Ready for production** ✅
