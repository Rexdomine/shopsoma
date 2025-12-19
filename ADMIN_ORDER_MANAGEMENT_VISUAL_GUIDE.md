# Admin Order Management - Visual UI Guide

**Version**: 1.0.0 | **Date**: December 13, 2025

This guide shows you exactly what you'll see on screen and how to use each UI element.

---

## Page Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ SHOPSOMA ADMIN                                    👤 Admin Menu  │
├──────────────────────────────────────────────────────────────────┤
│ ┌─────────┐                                                      │
│ │ SIDEBAR │ ┌────────────────────────────────────────────────┐  │
│ │         │ │                                                │  │
│ │ 📊 Dash │ │         MAIN CONTENT AREA                      │  │
│ │ 📦 Orders│ │                                                │  │
│ │ 👥 Users │ │   [Statistics Cards]                          │  │
│ │ 🏪 Vendors│ │   [Filter Panel]                             │  │
│ │ 📦 Products│ │   [Order Table]                              │  │
│ └─────────┘ │   [Pagination]                                 │  │
│             │                                                │  │
│             └────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 1. Statistics Dashboard

Located at the top of the page:

```
┌───────────────────────────────────────────────────────────────────┐
│  📊 ORDER STATISTICS                                              │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐│
│  │ Total Orders│ │   Pending   │ │ Processing  │ │   Shipped   ││
│  │             │ │             │ │             │ │             ││
│  │    1,234    │ │     45      │ │     89      │ │     123     ││
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘│
│                                                                   │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │  Delivered  │ │  Cancelled  │ │Total Revenue│                │
│  │             │ │             │ │             │                │
│  │    977      │ │     12      │ │ ₦25,450,000 │                │
│  └─────────────┘ └─────────────┘ └─────────────┘                │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

**Visual Indicators**:
- Each card has an icon at the top
- Numbers are large and bold
- Different colors for each status
- Loading spinner shows while fetching data

---

## 2. Filter Panel

Below statistics, above the order table:

```
┌───────────────────────────────────────────────────────────────────┐
│  🔍 FILTERS & SEARCH                                              │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ 🔍 Search orders...                                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐   │
│  │ Payment Status ▼ │  │ Fulfillment   ▼  │  │  Vendor   ▼  │   │
│  │ All Statuses     │  │ All Statuses     │  │ All Vendors  │   │
│  └──────────────────┘  └──────────────────┘  └──────────────┘   │
│                                                                   │
│  ┌─────────────┐  ┌─────────────┐                                │
│  │ From: 📅    │  │ To: 📅      │                                │
│  │ Select date │  │ Select date │                                │
│  └─────────────┘  └─────────────┘                                │
│                                                                   │
│  [Apply Filters]  [Clear Filters]                                │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

**How It Looks**:
- Search box has magnifying glass icon
- Dropdowns show current selection + down arrow
- Date pickers show calendar icon
- Buttons are colored (blue for apply, gray for clear)

---

## 3. Order Table

Main list of orders:

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  📋 ORDERS                                           [Export All ▼] [Bulk Actions]  │
├────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                    │
│  ☑️  Order #    Customer           Amount     Items    Payment   Fulfillment  Actions│
│  ──────────────────────────────────────────────────────────────────────────────   │
│  ☐  ORD-12345  John Doe           ₦25,000   3 items   🟢 Paid   🔵 Processing  View→│
│                john@example.com              2 vendors                             │
│                                                                                    │
│  ☐  ORD-12346  Jane Smith         ₦15,500   2 items   🟡 Pending 🟡 Pending    View→│
│                jane@example.com              1 vendor                              │
│                                                                                    │
│  ☐  ORD-12347  Bob Johnson        ₦42,000   5 items   🟢 Paid   🟣 Shipped     View→│
│                bob@example.com               3 vendors                             │
│                                                                                    │
│  ☐  ORD-12348  Alice Brown        ₦18,750   4 items   🟢 Paid   🟢 Delivered   View→│
│                alice@example.com             2 vendors                             │
│                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────┘

                        ← Previous    Page 1 of 25    Next →
                              Showing 1-20 of 489 orders
```

**Visual Elements**:
- Checkboxes for bulk selection (☐ ☑️)
- Order number in bold monospace font
- Customer name + email (two lines)
- Amount in Naira with ₦ symbol
- Items count shows "X items, Y vendors"
- Status badges with colored circles (🟢🟡🔵🟣🔴)
- "View →" button on right
- Pagination controls centered at bottom

---

## 4. Order Detail Page

When you click "View →":

```
┌────────────────────────────────────────────────────────────────────┐
│  ← Back to Orders                                                  │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ORDER #ORD-12345                    🟢 Paid   🔵 Processing       │
│  Created: Dec 10, 2025 at 2:30 PM                                 │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ 📦 ORDER SUMMARY                                           │   │
│  ├────────────────────────────────────────────────────────────┤   │
│  │  Subtotal:              ₦22,000                            │   │
│  │  Shipping Cost:         ₦2,500                             │   │
│  │  Tax Amount:            ₦500                               │   │
│  │  Discount:              -₦0                                │   │
│  │  ─────────────────────────────                             │   │
│  │  Total Amount:          ₦25,000                            │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌──────────────────────┐  ┌──────────────────────┐              │
│  │ 👤 CUSTOMER          │  │ 📦 SHIPPING ADDRESS  │              │
│  ├──────────────────────┤  ├──────────────────────┤              │
│  │ Name: John Doe       │  │ John Doe             │              │
│  │ Email: john@ex.com   │  │ 123 Main Street      │              │
│  │ Phone: +234 123...   │  │ Apt 4B               │              │
│  └──────────────────────┘  │ Lagos, Lagos 100001  │              │
│                             │ Nigeria              │              │
│                             │ Phone: +234 123...   │              │
│                             └──────────────────────┘              │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ 📦 ORDER ITEMS                                             │   │
│  ├────────────────────────────────────────────────────────────┤   │
│  │                                                            │   │
│  │  ┌──────┐  Men's Cotton T-Shirt                           │   │
│  │  │ IMG  │  Size: L, Color: Blue                           │   │
│  │  └──────┘  Qty: 2 × ₦5,000 = ₦10,000                      │   │
│  │            Vendor: Fashion Hub (+234 999...)               │   │
│  │            Status: 🔵 Processing                           │   │
│  │                                                            │   │
│  │  ┌──────┐  Women's Denim Jeans                            │   │
│  │  │ IMG  │  Size: M, Color: Black                          │   │
│  │  └──────┘  Qty: 1 × ₦12,000 = ₦12,000                     │   │
│  │            Vendor: Style Store (+234 888...)               │   │
│  │            Status: 🔵 Processing                           │   │
│  │                                                            │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ 🚚 DELIVERY INFORMATION                                    │   │
│  ├────────────────────────────────────────────────────────────┤   │
│  │  Provider: DHL Express                                     │   │
│  │  Tracking #: DHL123456789                                  │   │
│  │  Estimated Delivery: Dec 15, 2025                          │   │
│  │  Status: In Transit                                        │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ 📝 NOTES                                                   │   │
│  ├────────────────────────────────────────────────────────────┤   │
│  │  Customer Notes:                                           │   │
│  │  "Please deliver after 5 PM. Gift wrap requested."        │   │
│  │                                                            │   │
│  │  Admin Notes:                                              │   │
│  │  "Confirmed with customer. Delivery scheduled for 6 PM."  │   │
│  └────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  [Update Status]  [Update Shipping]  [Cancel Order]  [Refund]    │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

**Visual Features**:
- Back button (←) at top left
- Order number and status badges at top
- Sections in bordered cards
- Icons for each section (👤📦🚚📝)
- Item images shown as thumbnails
- Vendor info under each item
- Action buttons at bottom (blue/gray/red colors)

---

## 5. Action Buttons & Modals

### Update Status Button

When clicked, shows modal:

```
┌──────────────────────────────────────────┐
│  Update Order Status            ✕       │
├──────────────────────────────────────────┤
│                                          │
│  Current Status: 🔵 Processing           │
│                                          │
│  New Status:                             │
│  ┌────────────────────────────────────┐  │
│  │ Select new status...           ▼  │  │
│  └────────────────────────────────────┘  │
│  Options:                                │
│  • Pending                               │
│  • Processing                            │
│  • Shipped                               │
│  • Delivered                             │
│  • Cancelled                             │
│                                          │
│  Notes (optional):                       │
│  ┌────────────────────────────────────┐  │
│  │                                    │  │
│  │                                    │  │
│  └────────────────────────────────────┘  │
│                                          │
│  [Cancel]           [Update Status]     │
│                                          │
└──────────────────────────────────────────┘
```

### Update Shipping Modal

```
┌──────────────────────────────────────────┐
│  Update Shipping Information    ✕       │
├──────────────────────────────────────────┤
│                                          │
│  Delivery Provider:                      │
│  ┌────────────────────────────────────┐  │
│  │ Select provider...             ▼  │  │
│  └────────────────────────────────────┘  │
│  Options: DHL, FedEx, NIPOST, Other      │
│                                          │
│  Tracking Number:                        │
│  ┌────────────────────────────────────┐  │
│  │ Enter tracking number              │  │
│  └────────────────────────────────────┘  │
│                                          │
│  Estimated Delivery Date:                │
│  ┌────────────────────────────────────┐  │
│  │ Select date               📅       │  │
│  └────────────────────────────────────┘  │
│                                          │
│  [Cancel]           [Save Changes]      │
│                                          │
└──────────────────────────────────────────┘
```

### Cancel Order Modal

```
┌──────────────────────────────────────────┐
│  Cancel Order                   ✕       │
├──────────────────────────────────────────┤
│                                          │
│  ⚠️ Warning: This action cannot be      │
│     undone. The customer will be        │
│     notified immediately.               │
│                                          │
│  Cancellation Reason:                    │
│  ┌────────────────────────────────────┐  │
│  │ Select reason...               ▼  │  │
│  └────────────────────────────────────┘  │
│  Options:                                │
│  • Customer requested                    │
│  • Payment failed                        │
│  • Out of stock                          │
│  • Fraudulent order                      │
│  • Other                                 │
│                                          │
│  Detailed Notes:                         │
│  ┌────────────────────────────────────┐  │
│  │ Explain the cancellation...        │  │
│  │                                    │  │
│  └────────────────────────────────────┘  │
│                                          │
│  [Go Back]        [Confirm Cancel]      │
│                                          │
└──────────────────────────────────────────┘
```

**Modal Features**:
- Centered on screen with overlay
- Close button (✕) in top right
- Warning messages in orange/red
- Required fields marked with *
- Cancel button (gray) on left
- Action button (blue/red) on right
- Pressing ESC closes modal

---

## 6. Bulk Actions

When orders are selected:

```
┌────────────────────────────────────────────────────────────────────┐
│  📋 ORDERS                      3 selected  [Bulk Actions ▼]       │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ☑️  Order #    Customer           Amount     Items    Payment ...│
│  ──────────────────────────────────────────────────────────────   │
│  ☑️  ORD-12345  John Doe           ₦25,000   3 items   🟢 Paid ...│
│  ☐  ORD-12346  Jane Smith         ₦15,500   2 items   🟡 Pending..│
│  ☑️  ORD-12347  Bob Johnson        ₦42,000   5 items   🟢 Paid ...│
│  ☑️  ORD-12348  Alice Brown        ₦18,750   4 items   🟢 Paid ...│
│                                                                    │
└────────────────────────────────────────────────────────────────────┘

Bulk Actions Dropdown:
┌──────────────────────────┐
│ Update Status            │
│ Export Selected          │
│ Cancel Selected          │
└──────────────────────────┘
```

**Visual Feedback**:
- Selected rows highlighted in light blue
- Selection count shown in header
- Bulk actions dropdown becomes active
- Checkmarks (☑️) show selected items

---

## 7. Export Functionality

Export button dropdown:

```
                                    ┌───────────────────┐
                                    │ Export All Orders │
                                    │ Export Filtered   │
                                    │ Export Selected   │
                                    └───────────────────┘
```

**What Happens**:
1. Click export option
2. Loading spinner appears
3. CSV file downloads automatically
4. Success notification shows
5. File saved to Downloads folder

**File Contents**:
```
Order Number,Customer,Email,Date,Payment,Fulfillment,Amount
ORD-12345,John Doe,john@example.com,2025-12-10,Paid,Processing,25000
ORD-12346,Jane Smith,jane@example.com,2025-12-10,Pending,Pending,15500
...
```

---

## 8. Loading States

### Initial Page Load

```
┌───────────────────────────────────┐
│                                   │
│          ⏳                        │
│     Loading orders...             │
│                                   │
└───────────────────────────────────┘
```

### Updating Order

```
┌───────────────────────────────────┐
│  Update Order Status       ✕      │
├───────────────────────────────────┤
│                                   │
│       ⏳ Updating...               │
│                                   │
│  [Cancel]       [Updating...]     │
│                                   │
└───────────────────────────────────┘
```

**Loading Indicators**:
- Spinner icon (⏳ or animated circle)
- Button disabled during action
- Text changes to "Processing..." or "Updating..."
- Prevents double-clicks

---

## 9. Success/Error Notifications

### Success Toast

```
┌─────────────────────────────────────┐
│  ✅ Success                          │
│  Order status updated successfully  │
└─────────────────────────────────────┘
```

### Error Toast

```
┌─────────────────────────────────────┐
│  ❌ Error                            │
│  Failed to update order. Try again. │
└─────────────────────────────────────┘
```

**Toast Features**:
- Appears top-right corner
- Auto-dismisses after 3-5 seconds
- Click to dismiss immediately
- Color coded (green=success, red=error, yellow=warning)

---

## 10. Empty States

### No Orders Found

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│                           📦                                        │
│                                                                    │
│                      No orders found                               │
│                                                                    │
│            Try adjusting your filters or search term               │
│                                                                    │
│                    [Clear All Filters]                             │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### No Items in Order

```
┌────────────────────────────────────────────────────────────────────┐
│  📦 ORDER ITEMS                                                    │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│                           📭                                        │
│                                                                    │
│                    No items in this order                          │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## 11. Responsive Design

### Desktop View (> 1024px)
- Full sidebar visible
- 4 statistics cards per row
- Wide table with all columns
- Modals centered at 600px width

### Tablet View (768px - 1024px)
- Collapsible sidebar
- 3 statistics cards per row
- Table shows most important columns
- Modals adapt to screen width

### Mobile View (< 768px)
- Hamburger menu for sidebar
- 1 statistics card per row (stacked)
- Table shows cards instead of table rows
- Full-width modals

---

## 12. Color Scheme

### Status Colors

| Status | Color | Hex Code |
|--------|-------|----------|
| Pending | Yellow | `#FFC107` |
| Processing | Blue | `#2196F3` |
| Shipped | Purple | `#9C27B0` |
| Delivered | Green | `#4CAF50` |
| Cancelled | Red | `#F44336` |
| Paid | Green | `#4CAF50` |
| Failed | Red | `#F44336` |
| Refunded | Gray | `#9E9E9E` |

### UI Colors

| Element | Color |
|---------|-------|
| Primary Button | Blue `#2563EB` |
| Success Button | Green `#10B981` |
| Danger Button | Red `#EF4444` |
| Background | Light Gray `#F9FAFB` |
| Text | Dark Gray `#111827` |
| Border | Light Gray `#E5E7EB` |

---

## Summary

The Admin Order Management UI is designed for **efficiency and clarity**:

✅ **Clear visual hierarchy** - Most important info prominent
✅ **Consistent color coding** - Same colors = same meaning
✅ **Intuitive navigation** - Everything where you expect it
✅ **Helpful feedback** - Loading states, success/error messages
✅ **Accessible** - Keyboard shortcuts, clear labels
✅ **Responsive** - Works on all screen sizes

**Use this guide to quickly understand what each UI element does and how to interact with it!**

---

**Related Guides**:
- [User Guide](ADMIN_ORDER_MANAGEMENT_USER_GUIDE.md) - Complete feature documentation
- [Quick Reference](ADMIN_ORDER_MANAGEMENT_QUICK_REFERENCE.md) - Fast lookup card

**Last Updated**: December 13, 2025
