# Admin Order Management - Quick Reference Card

**Version**: 1.0.0 | **Date**: December 13, 2025

---

## Access

**URL**: `http://localhost:5173/admin/orders`
**Login**: Admin credentials required

---

## Dashboard Overview

| Metric | Description |
|--------|-------------|
| Total Orders | All orders in system |
| Pending | Awaiting fulfillment |
| Processing | Being prepared |
| Shipped | In transit |
| Delivered | Completed |
| Cancelled | Cancelled orders |
| Total Revenue | Sum of all orders (₦) |

---

## Order Statuses

### Payment Status
- 🟡 **Pending** - Not paid
- 🟢 **Paid** - Payment received
- 🔴 **Failed** - Payment failed
- ⚪ **Refunded** - Money returned

### Fulfillment Status
- 🟡 **Pending** - Not started
- 🔵 **Processing** - Being prepared
- 🟣 **Shipped** - In transit
- 🟢 **Delivered** - Completed
- 🔴 **Cancelled** - Order cancelled

---

## Quick Actions

### View Order
1. Find order in list
2. Click **"View →"**

### Update Status
1. Open order details
2. Click **"Update Status"**
3. Select new status
4. Save

### Add Tracking
1. Open order details
2. Click **"Update Shipping"**
3. Enter courier + tracking number
4. Save

### Cancel Order
1. Open order details
2. Click **"Cancel Order"**
3. Select reason
4. Confirm

### Process Refund
1. Open order details
2. Click **"Process Refund"**
3. Enter amount
4. Confirm

---

## Filters & Search

### Search Box
- Order number: `ORD-12345`
- Customer name: `John Doe`
- Customer email: `john@example.com`

### Filter Dropdowns
- **Payment Status**: All/Pending/Paid/Failed/Refunded
- **Fulfillment**: All/Pending/Processing/Shipped/Delivered/Cancelled
- **Vendor**: Filter by specific vendor
- **Date Range**: From/To dates

### Apply Filters
Click **"Apply Filters"** button

### Clear All
Click **"Clear Filters"** button

---

## Common Workflows

### Process New Order
```
1. Check Pending orders
2. Verify payment = Paid
3. Review items & address
4. Update to Processing
5. Monitor progress
```

### Ship Order
```
1. Open Processing order
2. Click "Update Shipping"
3. Enter courier & tracking
4. Update to Shipped
5. Customer gets email
```

### Handle Cancellation
```
1. Open order
2. Click "Cancel Order"
3. Select reason
4. Confirm
5. Process refund if paid
```

### Generate Report
```
1. Set date filter
2. Apply filter
3. Review stats
4. Export to CSV
5. Share with team
```

---

## Bulk Operations

### Select Orders
- ☑️ Check boxes next to orders
- ☑️ Check header to select all

### Bulk Actions
- **Update Status**: Change multiple at once
- **Export Selected**: Download CSV of selected

---

## Export Data

| Export Type | Button | Result |
|-------------|--------|--------|
| All Orders | "Export All" | Full CSV |
| Filtered | "Export Filtered" | Filtered CSV |
| Selected | "Export Selected" | Selected CSV |

**File Format**: `orders-export-YYYY-MM-DD.csv`

---

## Order Information

### Customer Details
- Name, Email, Phone
- Shipping address
- Billing address

### Order Summary
- Subtotal
- Shipping cost
- Tax amount
- Discount (if any)
- **Total amount**

### Items List
- Product name
- Variant (size, color)
- Quantity × Price
- Subtotal
- Vendor info
- Fulfillment status

### Delivery Info
- Provider (DHL, FedEx, etc.)
- Tracking number
- Estimated delivery
- Actual delivery

### Pickups (QC)
- Pickup status
- QC center arrival
- QC approval/rejection
- Notes

---

## Troubleshooting

| Issue | Quick Fix |
|-------|-----------|
| Order not found | Clear filters |
| Can't update | Check admin login |
| Export fails | Disable popup blocker |
| No notifications | Check spam folder |
| Wrong tracking | Update shipping info |

---

## Status Flow

```
┌─────────┐
│ PENDING │
└────┬────┘
     ↓
┌────────────┐
│ PROCESSING │
└─────┬──────┘
      ↓
┌─────────┐
│ SHIPPED │
└────┬────┘
     ↓
┌───────────┐
│ DELIVERED │
└───────────┘

CANCELLED (from any stage)
```

---

## Best Practices

✅ Check dashboard daily
✅ Update status immediately
✅ Add tracking ASAP when shipped
✅ Process refunds within 24h
✅ Add detailed notes
✅ Verify addresses before shipping
✅ Export data regularly

---

## Support

**Technical Issues**: Check logs → Contact dev team
**Business Issues**: Consult policies → Escalate

**Full Guide**: [ADMIN_ORDER_MANAGEMENT_USER_GUIDE.md](ADMIN_ORDER_MANAGEMENT_USER_GUIDE.md)

---

**Print this card and keep it at your desk for quick reference!**
