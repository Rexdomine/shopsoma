# Three Critical Fixes - Implementation Plan

**Date**: December 16, 2025
**Status**: 📋 READY FOR IMPLEMENTATION

---

## Issues Identified

### Issue #1: Pickup Scheduling Modal Missing ⚠️
**Problem**: When admin selects "Pickup Scheduled" status, there's no UI to set pickup time window

**Root Cause**: We removed the entire pickup section in the previous fix. Now need to add it back ONLY for setting pickup windows when status changes to "Pickup Scheduled"

**Impact**: Vendors can't see when pickups are scheduled

---

### Issue #2: Vendor Dashboard Not Syncing ❌
**Problem**: Vendor shipping status card doesn't update when admin changes order status

**Root Cause**: Vendor dashboard uses `pickup.status` (vendor pickup workflow) instead of `order.fulfillment_status` (unified status)

**Location**: `VendorOrderDetail.tsx` line 34-98 (`ShippingStatusCard` component)

**Current Code**:
```typescript
function ShippingStatusCard({ pickup }: { pickup: VendorPickup | null }) {
  // Uses pickup.status - WRONG!
  const getStatusLabel = (status: PickupStatus): string => {
    // Maps PickupStatus enum
  }
}
```

**Should Be**:
```typescript
function ShippingStatusCard({ order }: { order: VendorOrder }) {
  // Use order.fulfillment_status - CORRECT!
  const getStatusLabel = (status: FulfillmentStatus): string => {
    // Map FulfillmentStatus enum
  }
}
```

---

### Issue #3: Email Notifications Not Sending ❌
**Problem**: No emails received when changing order status during testing

**Investigation Results**:
- ✅ Brevo SDK installed and configured
- ✅ Email service enabled
- ✅ Notification service properly calls email service
- ✅ Status messages configured for all statuses

**Possible Causes**:
1. **Spam folder**: Emails may be going to spam
2. **Brevo API key invalid**: Need to verify in Brevo dashboard
3. **Email service error silently failing**: Need to check backend logs
4. **Async error not being caught**: Exception happening in background

**Next Steps**:
1. Start backend with visible logs (not redirected to /dev/null)
2. Update order status
3. Watch for email-related log messages
4. Check Brevo dashboard for send attempts

---

## Implementation Plan

### Fix #1: Add Pickup Scheduling Modal

**Approach**: Add a conditional modal that appears ONLY when status is changed to "Pickup Scheduled"

**Files to Modify**:
1. `shopsoma-frontend/src/pages/admin/AdminOrderDetail.tsx`
   - Add pickup scheduling modal state
   - Show modal when "Pickup Scheduled" is selected
   - Call API to save pickup window

2. `shopsoma-backend/app/api/v1/admin_orders.py`
   - Verify pickup scheduling endpoint exists
   - Accept pickup_window_start and pickup_window_end

**New Modal Flow**:
```
Admin selects "Pickup Scheduled"
  ↓
Before saving, show modal:
  - Pickup Window Start (datetime)
  - Pickup Window End (datetime)
  - Courier Name (optional)
  - Rider ID (optional)
  ↓
Save both status AND pickup details
  ↓
Vendor sees pickup window in their dashboard
```

---

### Fix #2: Update Vendor Dashboard to Use Unified Status

**Files to Modify**:
1. `shopsoma-frontend/src/pages/vendor/VendorOrderDetail.tsx`
   - Change `ShippingStatusCard` to accept `order` instead of `pickup`
   - Use `order.fulfillment_status` instead of `pickup.status`
   - Map FulfillmentStatus to vendor-friendly labels

**Status Mapping**:
```typescript
const getVendorStatusLabel = (status: FulfillmentStatus): string => {
  const map = {
    order_received: "New Order - Start Preparing",
    preparing_for_pickup: "Pack Order - Awaiting Rider",
    pickup_scheduled: "Pickup Scheduled",
    picked_up: "Items Picked Up Successfully",
    in_transit: "Order in Transit to Customer",
    out_for_delivery: "Out for Delivery",
    delivered: "Delivered Successfully",
    delivery_failed: "Delivery Failed",
    returned: "Order Returned",
    cancelled: "Order Cancelled"
  };
  return map[status] || status;
};
```

---

### Fix #3: Debug Email Notifications

**Testing Steps**:
1. Start backend with logs visible
2. Update order status from "Order Received" to "Delivered"
3. Check backend logs for:
   ```
   INFO: Email sent successfully to customer@example.com
   INFO: Email sent successfully to vendor@example.com
   ```
4. If no logs, check for errors:
   ```
   WARNING: Email send skipped
   ERROR: Failed to send email
   ```

**Verification Script**:
```bash
# Test email sending directly
cd shopsoma-backend
. venv/bin/activate
python -c "
from app.services.email_service import EmailService
from app.core.config import settings
import asyncio

async def test():
    service = EmailService()
    result = await service.send_email(
        to_email='test@example.com',
        subject='Test Email',
        body='This is a test email from Shopsoma'
    )
    print(f'Email sent: {result}')

asyncio.run(test())
"
```

---

## Testing Checklist

### Test #1: Pickup Scheduling
- [ ] Navigate to admin order detail
- [ ] Change status to "Pickup Scheduled"
- [ ] **Expected**: Modal appears with pickup window fields
- [ ] Fill in pickup window (start & end time)
- [ ] Save
- [ ] **Expected**: Pickup details saved to database
- [ ] Navigate to vendor dashboard
- [ ] **Expected**: Vendor sees pickup window

### Test #2: Vendor Dashboard Sync
- [ ] Open vendor order detail page
- [ ] Note current shipping status
- [ ] In another tab, open admin dashboard
- [ ] Change order status (e.g., "In Transit" → "Delivered")
- [ ] Refresh vendor page
- [ ] **Expected**: Shipping status updates to "Delivered Successfully"

### Test #3: Email Notifications
- [ ] Start backend with logs visible: `uvicorn app.main:app --reload`
- [ ] Update order status
- [ ] **Expected**: See "Email sent successfully" in logs
- [ ] Check email inbox (including spam folder)
- [ ] **Expected**: Email received with order update

---

## Priority Order

**High Priority** (Blocking vendor operations):
1. Fix #2: Vendor Dashboard Sync
2. Fix #1: Pickup Scheduling Modal

**Medium Priority** (Important but has workaround):
3. Fix #3: Email Notifications Debug

---

## Technical Details

### Vendor Order API Response
```json
{
  "id": "order-uuid",
  "order_number": "SHP-20251216-ABC123",
  "fulfillment_status": "in_transit",  ← This is what vendor should display
  "pickups": [{
    "id": "pickup-uuid",
    "status": "in_transit",  ← This is logistics-only status
    "pickup_window_start": "2025-12-17T09:00:00Z",
    "pickup_window_end": "2025-12-17T12:00:00Z"
  }]
}
```

### Status Flow (Vendor View)
```
Order Received
  ↓ Vendor Action: Start preparing items
Preparing for Pickup
  ↓ Admin Action: Schedule pickup
Pickup Scheduled ← Vendor sees pickup window here
  ↓ Courier picks up
Picked Up
  ↓ In transit to customer
In Transit
  ↓ Out for delivery
Out for Delivery
  ↓ Delivered to customer
Delivered ← Vendor gets notification
```

---

## Known Limitations

1. **Pickup scheduling**: Currently only supports ONE pickup window per order. Multi-vendor orders with different pickup times not yet supported.

2. **Real-time updates**: Vendor dashboard requires page refresh to see status changes. Consider implementing WebSocket for real-time updates in future.

3. **Email delivery**: Depends on Brevo API. If Brevo is down, notifications will fail silently (logged but not retried).

---

## Next Actions

**Immediate**: I'll implement these fixes now in order of priority:
1. ✅ Investigate: Review code (DONE)
2. 🔨 Implement: Fix vendor dashboard sync (NEXT)
3. 🔨 Implement: Add pickup scheduling modal
4. 🔍 Debug: Test email notifications with visible logs

**User Action Required**:
- Provide test email address for notification testing
- Confirm Brevo API key is valid in Brevo dashboard

---

**Ready to proceed with implementation?**
