# Implementation Guide - Three Critical Fixes

**Date**: December 16, 2025
**Status**: 📋 READY TO IMPLEMENT

---

## EXECUTIVE SUMMARY

I've investigated all three issues you reported. Here's what I found:

### Issue #1: Pickup Scheduling Modal - DESIGN DECISION NEEDED ⚠️
**Status**: We REMOVED the pickup section in the previous fix. Now you want it back.

**Question for you**: Do you want:
- **Option A**: Bring back the full pickup management section we just removed?
- **Option B**: Add a simpler "Set Pickup Window" button that only appears when "Pickup Scheduled" is selected?

**Recommendation**: Option B - simpler and cleaner UX

---

### Issue #2: Vendor Dashboard Not Syncing - ROOT CAUSE IDENTIFIED ✅
**Problem**: Vendor sees `pickup.status` (logistics workflow) instead of `order.fulfillment_status` (unified status)

**File**: `shopsoma-frontend/src/pages/vendor/VendorOrderDetail.tsx`

**Current Code** (WRONG):
```typescript
function ShippingStatusCard({ pickup }: { pickup: VendorPickup | null }) {
  // Uses pickup.status - only shows logistics status
  const getStatusLabel = (status: PickupStatus): string => {
    //... maps PickupStatus enum
  }
}
```

**Needs To Be**:
```typescript
function ShippingStatusCard({ order }: { order: VendorOrder }) {
  // Use order.fulfillment_status - shows unified order status
  const getStatusLabel = (status: string): string => {
    //... map FulfillmentStatus values
  }
}
```

**Impact**: This is why vendor doesn't see status changes from admin!

---

### Issue #3: Email Notifications - NEEDS LIVE TESTING 🔍
**Backend Status**: ✅ Properly configured
- Brevo SDK installed
- API key configured
- Notification service calls email service
- All statuses configured to send emails

**Why you might not be receiving emails**:
1. Emails going to spam folder
2. Invalid/test Brevo API key
3. Silent email service failure
4. Need to watch backend logs during test

**Next Step**: Run backend with visible logs and test

---

## DETAILED FIX #1: Vendor Dashboard Sync

### Files to Modify
1. `shopsoma-frontend/src/pages/vendor/VendorOrderDetail.tsx`

### Implementation Steps

**Step 1**: Update `ShippingStatusCard` component signature

**Current (line 34)**:
```typescript
function ShippingStatusCard({ pickup }: { pickup: VendorPickup | null }) {
```

**New**:
```typescript
function ShippingStatusCard({ order, pickup }: {
  order: VendorOrder;
  pickup: VendorPickup | null
}) {
```

**Step 2**: Replace status mapping function

**Replace this** (lines 69-81):
```typescript
const getStatusLabel = (status: PickupStatus): string => {
  const labelMap: Record<PickupStatus, string> = {
    scheduled: 'Pickup Scheduled',
    in_transit: 'In Transit to QC',
    delivered_to_qc: 'Delivered to QC Center',
    qc_approved: 'QC Approved',
    qc_rejected: 'QC Rejected',
    shipped_to_customer: 'Shipped to Customer',
    completed: 'Delivered',
    cancelled: 'Cancelled',
  };
  return labelMap[status] || status;
};
```

**With this**:
```typescript
const getStatusLabel = (status: string): string => {
  const labelMap: Record<string, string> = {
    'order_received': 'New Order - Start Preparing',
    'preparing_for_pickup': 'Pack Order - Awaiting Rider',
    'pickup_scheduled': 'Pickup Scheduled',
    'picked_up': 'Items Picked Up Successfully',
    'in_transit': 'Order In Transit to Customer',
    'out_for_delivery': 'Out for Delivery',
    'delivered': 'Delivered Successfully',
    'delivery_failed': 'Delivery Failed - Action Required',
    'returned': 'Order Returned',
    'cancelled': 'Order Cancelled',
  };
  return labelMap[status] || status.replace('_', ' ').toUpperCase();
};
```

**Step 3**: Update progress calculation

**Replace this** (lines 55-67):
```typescript
const getPickupProgress = (status: PickupStatus): number => {
  const progressMap: Record<PickupStatus, number> = {
    scheduled: 10,
    in_transit: 30,
    delivered_to_qc: 50,
    qc_approved: 70,
    qc_rejected: 50,
    shipped_to_customer: 85,
    completed: 100,
    cancelled: 0,
  };
  return progressMap[status] || 0;
};
```

**With this**:
```typescript
const getOrderProgress = (status: string): number => {
  const progressMap: Record<string, number> = {
    'order_received': 5,
    'preparing_for_pickup': 15,
    'pickup_scheduled': 25,
    'picked_up': 40,
    'in_transit': 60,
    'out_for_delivery': 80,
    'delivered': 100,
    'delivery_failed': 80,
    'returned': 50,
    'cancelled': 0,
  };
  return progressMap[status] || 0;
};
```

**Step 4**: Update status usage in component

**Change line 98** from:
```typescript
const progress = getPickupProgress(pickup.status);
const isRejected = pickup.status === 'qc_rejected';
const isCancelled = pickup.status === 'cancelled';
```

**To**:
```typescript
const progress = getOrderProgress(order.fulfillment_status);
const isRejected = order.fulfillment_status === 'returned';
const isCancelled = order.fulfillment_status === 'cancelled';
```

**Step 5**: Update component call (line 603)

**From**:
```typescript
<ShippingStatusCard pickup={primaryPickup} />
```

**To**:
```typescript
<ShippingStatusCard order={order} pickup={primaryPickup} />
```

---

## DETAILED FIX #2: Pickup Scheduling Modal (SIMPLIFIED VERSION)

### Option B: Simple Pickup Window Modal

**File**: `shopsoma-frontend/src/pages/admin/AdminOrderDetail.tsx`

**Add this state** (after line 50):
```typescript
const [showPickupScheduleModal, setShowPickupScheduleModal] = useState(false);
const [pickupWindowData, setPickupWindowData] = useState({
  pickup_window_start: '',
  pickup_window_end: '',
  courier_name: '',
  rider_id: '',
});
```

**Add this handler** (after handleUpdateStatus function):
```typescript
const handleSchedulePickup = async () => {
  if (!order || !pickupWindowData.pickup_window_start || !pickupWindowData.pickup_window_end) {
    error('Please select both start and end times for pickup window');
    return;
  }

  try {
    setUpdating(true);

    // First update the order status to PICKUP_SCHEDULED
    await updateOrderStatus(order.id, {
      fulfillment_status: 'pickup_scheduled',
      admin_notes: `Pickup scheduled: ${new Date(pickupWindowData.pickup_window_start).toLocaleString()} - ${new Date(pickupWindowData.pickup_window_end).toLocaleTimeString()}`
    });

    // If order has pickups, update the first one with the window
    if (order.pickups && order.pickups.length > 0) {
      await updatePickupStatus(order.id, order.pickups[0].id, {
        pickup_window_start: new Date(pickupWindowData.pickup_window_start).toISOString(),
        pickup_window_end: new Date(pickupWindowData.pickup_window_end).toISOString(),
        courier_name: pickupWindowData.courier_name,
        rider_id: pickupWindowData.rider_id,
      });
    }

    success('Pickup scheduled successfully');
    setShowPickupScheduleModal(false);
    setPickupWindowData({ pickup_window_start: '', pickup_window_end: '', courier_name: '', rider_id: '' });
    await loadOrder();
  } catch (err) {
    console.error('Failed to schedule pickup:', err);
    error('Failed to schedule pickup');
  } finally {
    setUpdating(false);
  }
};
```

**Modify handleUpdateStatus** to show modal when "Pickup Scheduled" is selected:
```typescript
const handleUpdateStatus = async () => {
  if (!order || !newStatus || newStatus === order.fulfillment_status) return;

  // If changing to PICKUP_SCHEDULED, show modal first
  if (newStatus === 'pickup_scheduled') {
    setShowPickupScheduleModal(true);
    setEditingStatus(false);
    return;
  }

  // ... rest of existing code
};
```

**Add modal JSX** (before Cancel Order Modal):
```typescript
{/* Pickup Scheduling Modal */}
{showPickupScheduleModal && (
  <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
    <div className="bg-white rounded-lg p-6 max-w-md w-full">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Schedule Pickup</h3>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Pickup Window Start *
          </label>
          <input
            type="datetime-local"
            value={pickupWindowData.pickup_window_start}
            onChange={(e) => setPickupWindowData({ ...pickupWindowData, pickup_window_start: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Pickup Window End *
          </label>
          <input
            type="datetime-local"
            value={pickupWindowData.pickup_window_end}
            onChange={(e) => setPickupWindowData({ ...pickupWindowData, pickup_window_end: e.target.value })}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Courier Name (Optional)
          </label>
          <input
            type="text"
            value={pickupWindowData.courier_name}
            onChange={(e) => setPickupWindowData({ ...pickupWindowData, courier_name: e.target.value })}
            placeholder="e.g., DHL Express"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Rider ID (Optional)
          </label>
          <input
            type="text"
            value={pickupWindowData.rider_id}
            onChange={(e) => setPickupWindowData({ ...pickupWindowData, rider_id: e.target.value })}
            placeholder="e.g., RD-12345"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          />
        </div>
      </div>

      <div className="flex gap-3 mt-6">
        <button
          onClick={handleSchedulePickup}
          disabled={updating}
          className="flex-1 px-4 py-2 bg-[#105E53] text-white rounded-lg hover:bg-[#0d4a41] disabled:opacity-50"
        >
          {updating ? 'Scheduling...' : 'Schedule Pickup'}
        </button>
        <button
          onClick={() => {
            setShowPickupScheduleModal(false);
            setNewStatus(order?.fulfillment_status || '');
          }}
          disabled={updating}
          className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
        >
          Cancel
        </button>
      </div>
    </div>
  </div>
)}
```

---

## DETAILED FIX #3: Email Notifications Debug

### Testing Script

Create `test_email_notifications.sh`:
```bash
#!/bin/bash

echo "📧 Testing Email Notifications"
echo "================================"
echo ""

# Start backend with visible logs
cd shopsoma-backend
. venv/bin/activate

echo "Starting backend with logs visible..."
echo "Watch for 'Email sent successfully' messages"
echo ""

# Start uvicorn
uvicorn app.main:app --reload --port 8000
```

### Manual Testing Steps

1. **Terminal 1**: Run test script
   ```bash
   chmod +x test_email_notifications.sh
   ./test_email_notifications.sh
   ```

2. **Terminal 2**: Watch for these log patterns:
   - ✅ `INFO: Email sent successfully to customer@example.com`
   - ✅ `INFO: Email sent successfully to vendor@example.com`
   - ❌ `WARNING: Email send skipped`
   - ❌ `ERROR: Failed to send email`

3. **Browser**: Update order status
   - Go to http://localhost:5174/admin/orders
   - Click "View" on any order
   - Change status from "Order Received" to "Delivered"
   - Watch Terminal 1 for email logs

4. **Check Email**:
   - Primary inbox
   - Spam folder
   - Promotions tab (Gmail)

### If Emails Still Not Working

**Check Brevo Dashboard**:
1. Go to https://www.brevo.com/
2. Login
3. Navigate to "Statistics" → "Email"
4. Look for recent send attempts
5. Check for bounces or errors

**Verify API Key**:
```bash
cd shopsoma-backend
. venv/bin/activate
python -c "
from app.core.config import settings
print(f'API Key: {settings.BREVO_API_KEY[:20]}...')
print(f'Sender Email: {settings.BREVO_SENDER_EMAIL}')
"
```

---

## TESTING CHECKLIST

### Pre-Implementation
- [ ] Backup current code
- [ ] Commit all changes to git
- [ ] Note current working state

### Fix #1 Testing (Vendor Dashboard)
- [ ] Start backend: `uvicorn app.main:app --reload`
- [ ] Open vendor dashboard in browser
- [ ] Note current shipping status
- [ ] In admin dashboard, change order status
- [ ] Refresh vendor page
- [ ] **Expected**: Status updates to match admin change
- [ ] Test all status transitions:
  - Order Received → Preparing
  - Preparing → Pickup Scheduled
  - Pickup Scheduled → Picked Up
  - Picked Up → In Transit
  - In Transit → Out for Delivery
  - Out for Delivery → Delivered

### Fix #2 Testing (Pickup Scheduling)
- [ ] Navigate to admin order detail
- [ ] Change status dropdown to "Pickup Scheduled"
- [ ] **Expected**: Modal appears with pickup window fields
- [ ] Fill in start time (e.g., tomorrow 9:00 AM)
- [ ] Fill in end time (e.g., tomorrow 12:00 PM)
- [ ] Add courier name (optional)
- [ ] Click "Schedule Pickup"
- [ ] **Expected**: Status updates, modal closes
- [ ] Check vendor dashboard
- [ ] **Expected**: Vendor sees pickup window times

### Fix #3 Testing (Email Notifications)
- [ ] Start backend with logs: `uvicorn app.main:app --reload`
- [ ] Update order status
- [ ] Watch terminal for "Email sent successfully"
- [ ] Check email inbox (including spam)
- [ ] Test bidirectional status changes:
  - Forward: Order Received → Delivered
  - Backward: Delivered → In Transit
- [ ] **Expected**: Emails sent in both directions

---

## ROLLBACK PLAN

If anything breaks:

```bash
# Restore from git
git stash
git checkout HEAD -- shopsoma-frontend/src/pages/vendor/VendorOrderDetail.tsx
git checkout HEAD -- shopsoma-frontend/src/pages/admin/AdminOrderDetail.tsx

# Or restore from backup files created earlier
cp VendorOrderDetail.tsx.backup VendorOrderDetail.tsx
cp AdminOrderDetail.tsx.backup AdminOrderDetail.tsx
```

---

## PRIORITY ORDER

1. **FIRST**: Fix #1 (Vendor Dashboard) - Most critical, blocks vendor operations
2. **SECOND**: Fix #3 (Email Debug) - Important for notifications
3. **THIRD**: Fix #2 (Pickup Modal) - Nice to have, improves UX

---

## NEXT STEPS

**Ready for implementation?**

I can implement these fixes for you now, or you can implement them yourself using this guide.

Which would you prefer?
- [ ] Implement all three fixes automatically
- [ ] Implement Fix #1 only (vendor dashboard sync)
- [ ] I'll implement myself using this guide
- [ ] Need clarification on something first

Let me know and I'll proceed accordingly!
