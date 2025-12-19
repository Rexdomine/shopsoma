# Real-time Status Update Debugging Guide

## Problem

Order tracking status indicators stuck on "Order Placed" and not updating in real-time when admin changes order status.

## Changes Made for Debugging

### Frontend Changes (`OrderTracking.tsx`)

#### 1. Comprehensive Logging

Added detailed console logs at every step:

```typescript
// When WebSocket update received
console.log('[OrderTracking] ===== WEBSOCKET UPDATE RECEIVED =====');
console.log('[OrderTracking] Raw data:', JSON.stringify(data, null, 2));
console.log('[OrderTracking] Fulfillment status:', data.fulfillment_status);
console.log('[OrderTracking] Previous status:', prevTracking.current_status);
console.log('[OrderTracking] Mapped status:', fulfillmentStatus, '→', currentStatus);
console.log('[OrderTracking] Updated tracking:', JSON.stringify(updatedTracking, null, 2));
console.log('[OrderTracking] ===== UPDATE COMPLETE =====');
```

#### 2. Error Handling

Added try-catch around WebSocket connection:

```typescript
try {
  websocketService.connect(orderId, token, handleOrderUpdate);
  setWsError(null);
  console.log('[OrderTracking] WebSocket connection initiated');
} catch (error) {
  console.error('[OrderTracking] WebSocket connection error:', error);
  setWsError('WebSocket connection failed');
  setIsConnectedToWebSocket(false);
}
```

#### 3. Fallback Polling Mechanism

Added 10-second polling as backup if WebSocket fails:

```typescript
const pollInterval = setInterval(async () => {
  if (!websocketService.isConnected()) {
    console.log('[OrderTracking] WebSocket not connected, polling for updates...');
    try {
      const data = await orderService.getOrderTracking(orderId);
      console.log('[OrderTracking] Polling update received:', data);
      setTracking(data);
    } catch (err) {
      console.error('[OrderTracking] Polling error:', err);
    }
  }
}, 10000); // Poll every 10 seconds
```

#### 4. Visual Error Indicators

Added amber "Polling for Updates" indicator when WebSocket fails:

```tsx
{wsError && (
  <div className="flex items-center gap-2 text-xs text-amber-600">
    <span className="relative flex h-2 w-2">
      <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
    </span>
    <span>Polling for Updates</span>
  </div>
)}
```

### Backend Changes (`admin_orders.py`)

#### Enhanced Logging

Added detailed broadcast logging:

```python
print(f"[WebSocket] ===== BROADCASTING ORDER UPDATE =====")
print(f"[WebSocket] Order ID: {order.id}")
print(f"[WebSocket] Fulfillment Status: {order.fulfillment_status.value}")
print(f"[WebSocket] Active Connections: {ws_manager.get_connection_count(str(order.id))}")
print(f"[WebSocket] Broadcast Data: {broadcast_data}")
# ...
print(f"[WebSocket] ✓ Broadcast complete for order {order.id}")
print(f"[WebSocket] =====================================")
```

#### Stack Trace on Error

Added traceback printing for errors:

```python
except Exception as e:
    print(f"[WebSocket] ✗ Failed to broadcast update: {str(e)}")
    import traceback
    traceback.print_exc()
```

## Debugging Steps

### Step 1: Check Browser Console

1. Open browser developer tools (F12)
2. Go to Console tab
3. Look for these log messages:

**Expected on page load**:
```
[OrderTracking] Connecting to WebSocket for order: <order-id>
[WebSocket] Connecting to: ws://localhost:8000/api/v1/ws/orders/...
[WebSocket] Connected successfully
[WebSocket] Connection established, initial status: {...}
```

**Expected when admin updates status**:
```
[OrderTracking] ===== WEBSOCKET UPDATE RECEIVED =====
[OrderTracking] Raw data: {
  "fulfillment_status": "in_transit",
  "payment_status": "paid",
  ...
}
[OrderTracking] Fulfillment status: in_transit
[OrderTracking] Previous status: order_placed
[OrderTracking] Mapped status: in_transit → in_transit
[OrderTracking] Updated tracking: {...}
[OrderTracking] ===== UPDATE COMPLETE =====
```

### Step 2: Check Backend Logs

**Expected when admin updates order**:
```
[WebSocket] ===== BROADCASTING ORDER UPDATE =====
[WebSocket] Order ID: <uuid>
[WebSocket] Fulfillment Status: in_transit
[WebSocket] Active Connections: 1
[WebSocket] Broadcast Data: {'fulfillment_status': 'in_transit', ...}
[WebSocket] ✓ Broadcast complete for order <uuid>
[WebSocket] =====================================
```

### Step 3: Common Issues & Solutions

#### Issue 1: No WebSocket Connection

**Symptoms**:
- Console shows: `[WebSocket] Connection closed` or `[WebSocket] Failed to connect`
- Amber "Polling for Updates" indicator instead of green "Live Updates Active"

**Check**:
1. Backend server running on port 8000?
   ```bash
   lsof -i :8000
   ```

2. WebSocket endpoint registered?
   - Check `shopsoma-backend/app/main.py` line 130
   - Should have: `app.include_router(websocket.router, prefix="/api/v1")`

**Solution**:
- Restart backend server
- Check CORS settings allow WebSocket connections
- Polling mechanism will take over (updates every 10 seconds)

#### Issue 2: Connected But No Updates

**Symptoms**:
- Green "Live Updates Active" shows
- No console logs when admin updates
- Backend shows "Active Connections: 0"

**Check**:
1. Is customer ID matching order?
   ```javascript
   // In browser console
   localStorage.getItem('token')
   ```

2. Backend broadcast logs:
   - Should show "Active Connections: 1" or more
   - If 0, no clients are subscribed

**Solution**:
- Refresh customer page
- Check JWT token is valid
- Verify order ID in URL matches order being updated

#### Issue 3: Receives Updates But Status Not Changing

**Symptoms**:
- Console shows: `[OrderTracking] ===== WEBSOCKET UPDATE RECEIVED =====`
- But UI doesn't update

**Check browser console for**:
```
[OrderTracking] Mapped status: in_transit → order_placed
```

If mapped status is wrong:
- Check `fulfillment_status` value in raw data
- Verify status mapping logic matches backend enum values

**Solution**:
- Check status mapping in `OrderTracking.tsx` lines 115-143
- Ensure backend sends lowercase status (e.g., `"in_transit"` not `"IN_TRANSIT"`)

#### Issue 4: Unknown Fulfillment Status

**Symptoms**:
```
[OrderTracking] Unknown fulfillment status: some_status
```

**Check**:
- What status did admin set?
- Is it in the mapping table?

**Solution**:
Add missing status to mapping logic

### Step 4: Verify Status Mapping

**Backend → Frontend Mapping Table**:

| Backend | Frontend | Expected |
|---------|----------|----------|
| `order_received` | `order_placed` | ✓ Step 1 |
| `preparing_for_pickup` | `in_transit` | ✓ Step 2 |
| `pickup_scheduled` | `in_transit` | ✓ Step 2 |
| `picked_up` | `in_transit` | ✓ Step 2 |
| `in_transit` | `in_transit` | ✓ Step 2 |
| `out_for_delivery` | `out_for_delivery` | ✓ Step 3 |
| `delivered` | `delivered` | ✓ Step 4 |
| `delivery_failed` | `delivery_failed` | ✓ Terminal |
| `returned` | `returned` | ✓ Terminal |
| `cancelled` | `cancelled` | ✓ Terminal |

## Testing Procedure

### Test 1: WebSocket Connection

1. Open order tracking page
2. Check browser console:
   ```
   ✓ [WebSocket] Connecting to: ws://...
   ✓ [WebSocket] Connected successfully
   ✓ [OrderTracking] WebSocket connection initiated
   ```
3. Check for green "Live Updates Active" indicator

### Test 2: Status Update

1. Keep tracking page open
2. As admin, change order status to `in_transit`
3. Check browser console:
   ```
   ✓ [OrderTracking] ===== WEBSOCKET UPDATE RECEIVED =====
   ✓ [OrderTracking] Fulfillment status: in_transit
   ✓ [OrderTracking] Mapped status: in_transit → in_transit
   ✓ [OrderTracking] ===== UPDATE COMPLETE =====
   ```
4. Check UI updated to Step 2

### Test 3: All Status Transitions

Test each transition:
```
order_received → in_transit → out_for_delivery → delivered
```

Each should:
- Show console logs
- Update progress bar immediately
- No page refresh needed

### Test 4: Terminal States

Test terminal states:
```
in_transit → delivery_failed
in_transit → cancelled
delivered → returned
```

Each should:
- Show alert banner (red/orange/gray)
- Show appropriate status badge
- Log terminal state detection

### Test 5: Fallback Polling

1. Stop backend server
2. Observe:
   ```
   [WebSocket] Connection closed
   [OrderTracking] WebSocket not connected, polling for updates...
   ```
3. Start backend server
4. Change order status
5. Within 10 seconds, status should update via polling

## Performance Monitoring

### WebSocket Health

**Good indicators**:
- ✅ Connection establishes in <1 second
- ✅ Updates appear instantly (<500ms)
- ✅ No reconnection attempts
- ✅ "Live Updates Active" stays green

**Warning signs**:
- ⚠️ Multiple reconnection attempts
- ⚠️ Updates delayed >2 seconds
- ⚠️ "Polling for Updates" appears
- ⚠️ Frequent disconnects

### Console Log Summary

**Healthy session**:
```
[WebSocket] Connecting to: ws://localhost:8000/...
[WebSocket] Connected successfully
[OrderTracking] WebSocket connection initiated
... (page idle) ...
[OrderTracking] ===== WEBSOCKET UPDATE RECEIVED =====
[OrderTracking] Mapped status: order_received → order_placed
[OrderTracking] ===== UPDATE COMPLETE =====
... (admin changes status) ...
[OrderTracking] ===== WEBSOCKET UPDATE RECEIVED =====
[OrderTracking] Mapped status: in_transit → in_transit
[OrderTracking] ===== UPDATE COMPLETE =====
```

**Problematic session**:
```
[WebSocket] Connecting to: ws://localhost:8000/...
[WebSocket] Connection closed: 1006
[WebSocket] Reconnecting in 1000ms (attempt 1/5)
[OrderTracking] WebSocket not connected, polling for updates...
[OrderTracking] Polling update received: {...}
```

## Quick Diagnostic Commands

### Check Backend Running
```bash
lsof -i :8000 | grep LISTEN
```

### Check Frontend Running
```bash
lsof -i :5173 | grep LISTEN
```

### Test WebSocket Manually
```javascript
// In browser console
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/orders/<order-id>?token=<jwt>');
ws.onopen = () => console.log('Connected');
ws.onmessage = (e) => console.log('Message:', e.data);
ws.onerror = (e) => console.error('Error:', e);
```

### Check Active Connections (Backend)
```python
# In admin_orders.py, temporary debug code
ws_manager = get_connection_manager()
print(f"Total connections: {ws_manager.get_connection_count()}")
print(f"Connections for order {order_id}: {ws_manager.get_connection_count(str(order_id))}")
```

## Expected Behavior Summary

### ✅ Working Correctly

1. **Page Load**:
   - Green "Live Updates Active" appears
   - Console shows successful WebSocket connection
   - Initial order status displays correctly

2. **Admin Updates Status**:
   - Backend logs broadcast
   - Frontend receives update within 500ms
   - Console shows mapped status
   - Progress bar updates immediately
   - No page refresh needed

3. **Terminal States**:
   - Alert banner appears
   - Correct color (red/orange/gray)
   - Status badge updates
   - Terminal state detected in logs

4. **Network Issues**:
   - Amber "Polling for Updates" appears
   - Status updates within 10 seconds
   - Graceful degradation

### ❌ Not Working - Debugging Needed

1. **No Updates at All**:
   - Check: WebSocket connection established?
   - Check: Backend broadcasting?
   - Check: Active connections > 0?

2. **Wrong Status Displayed**:
   - Check: Status mapping table
   - Check: Backend sending correct enum value
   - Check: Frontend receiving correct data

3. **Delayed Updates (>2 seconds)**:
   - Check: Network latency
   - Check: WebSocket still connected?
   - Check: Polling fallback active?

## Files Modified

| File | Purpose | Lines |
|------|---------|-------|
| `shopsoma-frontend/src/pages/orders/OrderTracking.tsx` | Added logging & polling | 52, 103-162, 166-196, 274-290 |
| `shopsoma-backend/app/api/v1/admin_orders.py` | Enhanced broadcast logging | 498-530 |

## Status: READY FOR DEBUGGING ✅

All logging and error handling in place. Follow the debugging steps above to identify and fix the issue preventing real-time status updates.

---

**Created**: December 17, 2025
**Purpose**: Debug real-time order status update issues
**Next Step**: Follow debugging procedure to identify root cause
