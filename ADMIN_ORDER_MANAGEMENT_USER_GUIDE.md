# Admin Order Management System - User Guide

**Date**: December 13, 2025
**Version**: 1.0.0
**For**: Shopsoma Administrators

---

## Table of Contents

1. [Overview](#overview)
2. [Accessing the Order Management System](#accessing-the-order-management-system)
3. [Dashboard & Statistics](#dashboard--statistics)
4. [Order List View](#order-list-view)
5. [Filtering & Search](#filtering--search)
6. [Order Details View](#order-details-view)
7. [Order Management Actions](#order-management-actions)
8. [Bulk Operations](#bulk-operations)
9. [Exporting Orders](#exporting-orders)
10. [Order Workflow](#order-workflow)
11. [Common Tasks](#common-tasks)
12. [Troubleshooting](#troubleshooting)

---

## Overview

The Admin Order Management System provides comprehensive tools for managing all orders in the Shopsoma marketplace. As an admin, you can:

- View and monitor all orders across all vendors
- Track order statistics and metrics
- Filter orders by status, date, vendor, and more
- Update order fulfillment and shipping status
- Manage pickups and quality control
- Handle cancellations and refunds
- Export order data for reporting
- Perform bulk operations on multiple orders

---

## Accessing the Order Management System

### Navigation

1. **Login** as admin at: `http://localhost:5173/admin/login`
   - Use your admin credentials
   - Email: `admin@shopsoma.com`
   - Password: Your admin password

2. **Navigate to Orders**:
   - From the admin dashboard, click on **"Orders"** in the left sidebar
   - Direct URL: `http://localhost:5173/admin/orders`

### Required Permissions

- You must have **admin role** to access order management
- Regular vendors can only see their own orders
- Customers can only see orders they placed

---

## Dashboard & Statistics

When you first open the order management page, you'll see a **statistics dashboard** at the top:

### Order Statistics Cards

#### 1. Total Orders
- Shows the total number of orders in the system
- Updates in real-time

#### 2. Pending Orders
- Orders awaiting fulfillment
- Status: `PENDING`
- Requires immediate attention

#### 3. Processing Orders
- Orders currently being processed
- Status: `PROCESSING`
- Items being prepared by vendors

#### 4. Shipped Orders
- Orders that have been shipped
- Status: `SHIPPED`
- In transit to customers

#### 5. Delivered Orders
- Successfully delivered orders
- Status: `DELIVERED`
- Completed orders

#### 6. Cancelled Orders
- Orders that were cancelled
- Status: `CANCELLED`
- May require refund processing

#### 7. Total Revenue
- Sum of all confirmed order amounts
- Shown in Naira (₦)
- Includes completed and in-progress orders

### Statistics Loading

- Statistics load automatically when you open the page
- Shows a loading spinner while fetching data
- Updates when you apply filters

---

## Order List View

The main order list displays all orders in a **table format**:

### Table Columns

| Column | Description |
|--------|-------------|
| **Order Number** | Unique identifier (e.g., `ORD-12345`) |
| **Customer** | Customer name and email |
| **Amount** | Total order amount in ₦ |
| **Items** | Number of items and vendors |
| **Payment** | Payment status badge |
| **Fulfillment** | Fulfillment status badge |
| **Date** | Order creation date |
| **Actions** | View button |

### Status Badges

#### Payment Status
- 🟡 **Pending** - Payment not yet received
- 🟢 **Paid** - Payment confirmed
- 🔴 **Failed** - Payment failed
- ⚪ **Refunded** - Payment refunded

#### Fulfillment Status
- 🟡 **Pending** - Not yet started
- 🔵 **Processing** - Being prepared
- 🟣 **Shipped** - In transit
- 🟢 **Delivered** - Completed
- 🔴 **Cancelled** - Order cancelled

### Pagination

- **Default**: 20 orders per page
- **Navigation**: Use "Previous" and "Next" buttons
- **Page Info**: Shows current page and total pages
- **Total Count**: Displays total number of orders

---

## Filtering & Search

Use the filter panel to narrow down orders:

### Search Box

```
🔍 Search orders...
```

**Search by**:
- Order number (e.g., `ORD-12345`)
- Customer name
- Customer email

**How to search**:
1. Type in the search box
2. Results update automatically as you type
3. Search is case-insensitive

### Filter Options

#### 1. Payment Status Filter

```
Payment Status: [All Statuses ▼]
```

**Options**:
- All Statuses (default)
- Pending
- Paid
- Failed
- Refunded

#### 2. Fulfillment Status Filter

```
Fulfillment Status: [All Statuses ▼]
```

**Options**:
- All Statuses (default)
- Pending
- Processing
- Shipped
- Delivered
- Cancelled

#### 3. Vendor Filter

```
Vendor: [All Vendors ▼]
```

**Purpose**: Filter orders containing items from specific vendor
- Shows dropdown of all vendors
- Useful for tracking vendor performance

#### 4. Date Range Filter

```
From: [Date Picker]
To: [Date Picker]
```

**Purpose**: Filter orders by creation date
- Click date field to open calendar picker
- Select start date and end date
- Shows orders created within range

### Applying Filters

1. Select your filter criteria
2. Click **"Apply Filters"** button
3. Order list and statistics update automatically
4. Current filters are shown above the table

### Clearing Filters

- Click **"Clear Filters"** button
- Resets all filters to default
- Shows all orders again

---

## Order Details View

Click **"View →"** on any order to see complete details:

### Order Information Section

**Header**:
- **Order Number**: `ORD-12345`
- **Status Badges**: Payment and Fulfillment status
- **Creation Date**: When order was placed

**Order Summary**:
- **Subtotal**: Sum of all items
- **Shipping Cost**: Delivery fee
- **Tax Amount**: Applicable taxes
- **Discount**: Promo code discount (if any)
- **Total Amount**: Final amount paid

### Customer Information

```
👤 Customer Details
Name: John Doe
Email: john@example.com
Phone: +234 123 456 7890
```

### Shipping Address

```
📦 Shipping Address
John Doe
123 Main Street, Apt 4B
Lagos, Lagos 100001
Nigeria
Phone: +234 123 456 7890
```

### Billing Address

```
💳 Billing Address
[Same as shipping or different address]
```

### Order Items

**For each item**:
- Product name and image
- Variant details (size, color, etc.)
- Quantity ordered
- Unit price
- Subtotal
- Fulfillment status
- **Vendor Information**:
  - Business name
  - Contact phone
  - Contact email

**Item Breakdown**:
- Shows commission rate and amount
- Shows vendor payout amount
- Individual fulfillment status per item

### Delivery Information

```
🚚 Delivery Details
Provider: DHL Express
Tracking Number: DHL123456789
Estimated Delivery: Dec 20, 2025
Status: Shipped
```

### Pickup Information

**For each pickup** (quality control process):
- Pickup ID
- Status
- Scheduled pickup date
- Actual pickup date (if picked up)
- Logistics partner
- Tracking number
- QC center arrival date
- QC approval/rejection status
- Notes (vendor, admin, QC)

### Notes Section

**Customer Notes**:
- Special delivery instructions
- Gift messages
- Other customer requests

**Admin Notes**:
- Internal notes for order processing
- Issue tracking
- Communication logs

---

## Order Management Actions

### Update Fulfillment Status

**Available Statuses**:
1. **Pending** → Order received, not started
2. **Processing** → Items being prepared
3. **Shipped** → In transit to customer
4. **Delivered** → Successfully delivered
5. **Cancelled** → Order cancelled

**How to Update**:
1. Open order details
2. Click **"Update Status"** button
3. Select new status from dropdown
4. Add optional notes
5. Click **"Save"**

**Status Flow**:
```
Pending → Processing → Shipped → Delivered
         ↓
    Cancelled (at any stage)
```

### Update Shipping Information

**Fields**:
- **Delivery Provider**: DHL, FedEx, NIPOST, etc.
- **Tracking Number**: Courier tracking ID
- **Estimated Delivery Date**: Expected delivery date
- **Actual Delivery Date**: When delivered (for completed orders)

**How to Update**:
1. Open order details
2. Click **"Update Shipping"** button
3. Fill in shipping details
4. Click **"Save"**

**Notifications**:
- Customer receives email with tracking info
- SMS notification with tracking link

### Update Pickup Status

**For Quality Control Process**:
- Update when items are picked up from vendor
- Update when items arrive at QC center
- Update QC approval/rejection status
- Add QC notes

**How to Update**:
1. Open order details
2. Find pickup in **Pickups** section
3. Click **"Update Pickup"** button
4. Update relevant fields
5. Click **"Save"**

### Cancel Order

**When to Cancel**:
- Customer requests cancellation
- Payment failed
- Item out of stock
- Fraudulent order

**How to Cancel**:
1. Open order details
2. Click **"Cancel Order"** button
3. Select cancellation reason:
   - Customer requested
   - Payment failed
   - Out of stock
   - Fraudulent
   - Other
4. Add detailed notes
5. Click **"Confirm Cancellation"**

**What Happens**:
- Order status changes to `CANCELLED`
- Customer notified via email
- Vendor notified
- Refund process initiated (if paid)

### Process Refund

**When to Refund**:
- Order cancelled after payment
- Item defective/damaged
- Customer returns item
- Service issue

**How to Refund**:
1. Open order details
2. Click **"Process Refund"** button
3. Enter refund amount (full or partial)
4. Select refund reason
5. Add notes explaining refund
6. Click **"Process Refund"**

**What Happens**:
- Refund initiated with payment gateway
- Customer notified
- Order status may change to `REFUNDED`
- Accounting records updated

---

## Bulk Operations

Perform actions on **multiple orders at once**:

### Select Orders

**Methods**:
1. **Select All**: Check box in table header
2. **Individual**: Check box next to each order
3. **Select Range**: Check multiple boxes

### Available Bulk Actions

#### 1. Update Fulfillment Status

**Use Case**: Move multiple orders to same status
- Select orders
- Click **"Bulk Update Status"** button
- Choose new status
- Confirm action

**Example**: Mark all shipped orders as delivered

#### 2. Bulk Export

**Use Case**: Export selected orders to CSV
- Select orders
- Click **"Export Selected"** button
- CSV file downloads

---

## Exporting Orders

### Export to CSV

**What Gets Exported**:
- Order number
- Customer name and email
- Order date
- Payment status
- Fulfillment status
- Total amount
- Items count
- Vendor information

**How to Export**:

#### Export All Orders
1. Click **"Export All"** button (top right)
2. CSV file downloads automatically
3. Filename: `orders-export-YYYY-MM-DD.csv`

#### Export Filtered Orders
1. Apply filters to narrow down orders
2. Click **"Export Filtered"** button
3. Only filtered orders are exported

#### Export Selected Orders
1. Select specific orders using checkboxes
2. Click **"Export Selected"** button
3. Only selected orders are exported

### Using Exported Data

**Open with**:
- Microsoft Excel
- Google Sheets
- LibreOffice Calc

**Use Cases**:
- Generate reports
- Analyze sales data
- Share with accounting team
- Create invoices
- Track vendor performance

---

## Order Workflow

### Complete Order Lifecycle

```
1. Customer Places Order
   ↓
2. Order Created (PENDING)
   ↓
3. Payment Confirmed (PAID)
   ↓
4. Admin/Vendor Starts Processing (PROCESSING)
   ↓
5. Vendor Prepares Items
   ↓
6. Pickup Scheduled
   ↓
7. Items Picked Up from Vendor
   ↓
8. QC Center Arrival
   ↓
9. QC Approval
   ↓
10. Order Shipped (SHIPPED)
    ↓
11. In Transit (tracking updated)
    ↓
12. Order Delivered (DELIVERED)
    ↓
13. Order Complete ✅
```

### Alternative Flows

#### Cancellation Flow
```
Any Stage → Cancel Order → Refund (if paid) → CANCELLED
```

#### Return Flow
```
Delivered → Customer Requests Return → Return Approved →
Pickup from Customer → QC Check → Refund → Return Complete
```

---

## Common Tasks

### Task 1: Process a New Order

1. **Check order list** for new `PENDING` orders
2. **Open order details** by clicking "View"
3. **Verify payment status** - ensure marked as `PAID`
4. **Review customer information** and shipping address
5. **Check items** - verify availability
6. **Update status to PROCESSING**
7. **Notify vendors** (automatic email sent)
8. **Monitor progress** in dashboard

### Task 2: Ship an Order

1. **Open order** in `PROCESSING` status
2. **Verify all items** ready to ship
3. **Click "Update Shipping"**
4. **Enter**:
   - Delivery provider
   - Tracking number
   - Estimated delivery date
5. **Update status to SHIPPED**
6. **Save changes**
7. **Verify** customer received tracking email

### Task 3: Handle a Cancellation Request

1. **Receive cancellation request** from customer
2. **Open order details**
3. **Check current status**:
   - If `PENDING`: Easy to cancel
   - If `PROCESSING`: Check if items prepared
   - If `SHIPPED`: Contact courier to intercept
4. **Click "Cancel Order"**
5. **Select reason**: "Customer requested"
6. **Add notes**: Customer's reason
7. **Confirm cancellation**
8. **Process refund** if payment was made
9. **Verify** customer received cancellation email

### Task 4: Process a Refund

1. **Open order details**
2. **Click "Process Refund"**
3. **Enter refund amount**:
   - Full refund: Enter total amount
   - Partial: Enter specific amount
4. **Select reason**: Defective, Return, etc.
5. **Add detailed notes**
6. **Process refund**
7. **Monitor** payment gateway for confirmation
8. **Update order notes** with refund status

### Task 5: Track Multiple Vendor Orders

1. **Use vendor filter**
2. **Select vendor from dropdown**
3. **Apply filter**
4. **Review all orders** from that vendor
5. **Check fulfillment rates**
6. **Export data** for vendor report
7. **Clear filter** when done

### Task 6: Generate Daily Report

1. **Set date filter** to today
2. **Apply filter**
3. **Review statistics**:
   - Total orders today
   - Revenue today
   - Status breakdown
4. **Export filtered orders** to CSV
5. **Open in Excel**
6. **Create summary report**
7. **Share with team**

---

## Troubleshooting

### Issue: Order Not Appearing

**Possible Causes**:
- Active filters hiding the order
- Wrong date range selected
- Search term too specific

**Solution**:
1. Click **"Clear Filters"**
2. Try searching by order number only
3. Check if order exists in database

### Issue: Cannot Update Order Status

**Possible Causes**:
- Order already in final status (DELIVERED/CANCELLED)
- Permission issue
- Network error

**Solution**:
1. Verify order current status
2. Check you're logged in as admin
3. Refresh page and try again
4. Check browser console for errors

### Issue: Export Not Working

**Possible Causes**:
- No orders to export
- Browser blocking download
- Network error

**Solution**:
1. Verify orders exist in list
2. Check browser download permissions
3. Disable popup blocker
4. Try different browser

### Issue: Customer Not Receiving Notifications

**Possible Causes**:
- Email in spam folder
- Wrong email address
- Email service issue

**Solution**:
1. Verify customer email in order details
2. Check backend email logs
3. Ask customer to check spam folder
4. Manually send email if needed

### Issue: Tracking Number Not Working

**Possible Causes**:
- Typo in tracking number
- Courier system delay
- Wrong courier selected

**Solution**:
1. Verify tracking number is correct
2. Check with correct courier
3. Update shipping information if wrong
4. Contact courier for tracking issues

---

## Best Practices

### 1. Regular Monitoring
- Check order dashboard **daily**
- Review pending orders **every few hours**
- Monitor shipping updates regularly

### 2. Timely Updates
- Update order status **as soon as it changes**
- Add tracking info **immediately when shipped**
- Process refunds **within 24 hours**

### 3. Clear Communication
- Add **detailed notes** to orders
- Use **admin notes** for internal tracking
- Keep **customer notes** for special requests

### 4. Quality Control
- **Verify addresses** before shipping
- **Double-check tracking numbers**
- **Confirm amounts** before refunding

### 5. Data Management
- **Export data** regularly for backups
- **Review statistics** for trends
- **Monitor vendor performance**

### 6. Customer Service
- **Respond quickly** to cancellation requests
- **Provide tracking info** proactively
- **Keep customers informed** of delays

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl + F` | Focus search box |
| `Esc` | Close modal/dialog |
| `Ctrl + E` | Export orders |
| `Enter` | Submit form |

---

## Support & Help

### Getting Help

**For Technical Issues**:
- Check backend logs for errors
- Review browser console
- Contact development team

**For Business Issues**:
- Consult order management policies
- Contact customer service team
- Escalate to management if needed

### Documentation

- **Technical Guide**: [docs/shopsoma_technical_guide.md](docs/shopsoma_technical_guide.md)
- **API Documentation**: Backend API endpoints
- **Frontend Code**: `shopsoma-frontend/src/pages/admin/`

---

## Summary

The Admin Order Management System provides complete control over all orders in the Shopsoma marketplace. Key features:

✅ **Dashboard** with real-time statistics
✅ **Comprehensive filtering** and search
✅ **Detailed order views** with all information
✅ **Status management** for orders, shipping, and pickups
✅ **Bulk operations** for efficiency
✅ **CSV export** for reporting
✅ **Complete order lifecycle** tracking

Use this system to efficiently manage orders, ensure timely fulfillment, maintain quality control, and provide excellent customer service.

---

**Questions?** Contact your development team or refer to the technical documentation.

**Last Updated**: December 13, 2025
**Version**: 1.0.0
