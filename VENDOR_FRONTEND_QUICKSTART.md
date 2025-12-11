# VENDOR DASHBOARD - FRONTEND QUICK START GUIDE

## 🚀 For Frontend Developers

This guide helps you quickly integrate with the vendor dashboard backend API.

---

## 📡 API BASE URL

```
Development: http://localhost:8000/api/v1
Production: https://api.shopsoma.com/api/v1
```

---

## 🔐 AUTHENTICATION

All vendor endpoints require authentication. Include the JWT token in headers:

```javascript
const headers = {
  'Authorization': `Bearer ${accessToken}`,
  'Content-Type': 'application/json'
}
```

---

## 📋 VENDOR DASHBOARD PAGES

### 1. **Vendor Onboarding** (`/vendor/register`)

**API Endpoint:** `POST /vendor/onboard`

```javascript
const registerVendor = async (data) => {
  const response = await fetch(`${API_BASE}/vendor/onboard`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      business_name: "Ankara Threads",
      business_description: "Premium African fashion",
      business_address: "123 Lagos St, Lagos, Nigeria",
      business_phone: "+234 800 123 4567",
      bank_name: "GTBank",
      bank_account_number: "0123456789",
      bank_account_name: "Ankara Threads Ltd"
    })
  });
  return response.json();
};
```

---

### 2. **Dashboard Home** (`/vendor/dashboard`)

**API Endpoint:** `GET /vendor/dashboard/metrics`

```javascript
const getDashboardMetrics = async () => {
  const response = await fetch(`${API_BASE}/vendor/dashboard/metrics`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};

// Response:
{
  "total_products": 45,
  "active_products": 38,
  "pending_approval_products": 7,
  "total_orders": 1234,
  "pending_orders": 5,
  "in_progress_orders": 12,
  "completed_orders": 1217,
  "total_revenue": "45678900.00",
  "current_month_revenue": "3456789.00",
  "pending_payout": "1234567.00",
  "scheduled_pickups": 3,
  "pending_pickups": 3,
  "unread_notifications": 8
}
```

**Sample Dashboard Component:**

```jsx
import React, { useEffect, useState } from 'react';

const VendorDashboard = () => {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchMetrics();
  }, []);

  const fetchMetrics = async () => {
    try {
      const data = await getDashboardMetrics();
      setMetrics(data);
    } catch (error) {
      console.error('Failed to load metrics:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <div>Loading...</div>;

  return (
    <div className="dashboard">
      <h1>Vendor Dashboard</h1>

      {/* Metrics Cards */}
      <div className="metrics-grid">
        <MetricCard
          title="Total Products"
          value={metrics.total_products}
          subtitle={`${metrics.active_products} active`}
        />
        <MetricCard
          title="Total Orders"
          value={metrics.total_orders}
          subtitle={`${metrics.pending_orders} pending`}
        />
        <MetricCard
          title="Total Revenue"
          value={`₦${Number(metrics.total_revenue).toLocaleString()}`}
          subtitle={`₦${Number(metrics.current_month_revenue).toLocaleString()} this month`}
        />
        <MetricCard
          title="Pending Payout"
          value={`₦${Number(metrics.pending_payout).toLocaleString()}`}
          subtitle="Next payout in 10 days"
        />
      </div>

      {/* Quick Actions */}
      <div className="quick-actions">
        <button onClick={() => navigate('/vendor/products/new')}>
          Add New Product
        </button>
        <button onClick={() => navigate('/vendor/orders')}>
          View Orders ({metrics.pending_orders})
        </button>
        <button onClick={() => navigate('/vendor/pickups')}>
          Scheduled Pickups ({metrics.scheduled_pickups})
        </button>
      </div>
    </div>
  );
};
```

---

### 3. **Orders Page** (`/vendor/orders`)

**API Endpoint:** `GET /vendor/orders?page=1&page_size=20`

```javascript
const getOrders = async (page = 1, status = null) => {
  const params = new URLSearchParams({
    page: page,
    page_size: 20
  });

  if (status) {
    params.append('status', status);
  }

  const response = await fetch(`${API_BASE}/vendor/orders?${params}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};

// Response:
{
  "orders": [
    {
      "id": "uuid",
      "order_number": "SHP-20251202-ABC123",
      "items": [
        {
          "id": "uuid",
          "product_title": "Ankara Dress",
          "quantity": 1,
          "unit_price": "25000.00",
          "subtotal": "25000.00",
          "vendor_payout": "21875.00"
        }
      ],
      "customer_name": "John Doe",
      "customer_email": "john@example.com",
      "payment_status": "PAID",
      "fulfillment_status": "PENDING",
      "created_at": "2025-12-02T10:30:00Z"
    }
  ],
  "total": 1234,
  "page": 1,
  "page_size": 20,
  "total_pages": 62
}
```

**Sample Orders Component:**

```jsx
const OrdersPage = () => {
  const [orders, setOrders] = useState([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);

  useEffect(() => {
    fetchOrders();
  }, [page]);

  const fetchOrders = async () => {
    const data = await getOrders(page);
    setOrders(data.orders);
    setTotalPages(data.total_pages);
  };

  return (
    <div className="orders-page">
      <h1>Orders</h1>

      <table>
        <thead>
          <tr>
            <th>Order #</th>
            <th>Date</th>
            <th>Customer</th>
            <th>Items</th>
            <th>Payout</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {orders.map(order => (
            <tr key={order.id}>
              <td>{order.order_number}</td>
              <td>{new Date(order.created_at).toLocaleDateString()}</td>
              <td>{order.customer_name}</td>
              <td>{order.items.length}</td>
              <td>
                ₦{order.items.reduce((sum, item) =>
                  sum + Number(item.vendor_payout), 0
                ).toLocaleString()}
              </td>
              <td>
                <StatusBadge status={order.fulfillment_status} />
              </td>
              <td>
                <button onClick={() => viewOrder(order.id)}>
                  View Details
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <Pagination
        currentPage={page}
        totalPages={totalPages}
        onPageChange={setPage}
      />
    </div>
  );
};
```

---

### 4. **Pickups Page** (`/vendor/pickups`)

**API Endpoint:** `GET /vendor/pickups?page=1&status=SCHEDULED`

```javascript
const getPickups = async (page = 1, status = 'SCHEDULED') => {
  const params = new URLSearchParams({
    page: page,
    page_size: 20
  });

  if (status) {
    params.append('status', status);
  }

  const response = await fetch(`${API_BASE}/vendor/pickups?${params}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};

// Response:
{
  "pickups": [
    {
      "id": "uuid",
      "order_id": "uuid",
      "order_item_id": "uuid",
      "order_type": "RTW",
      "scheduled_pickup_date": "2025-12-04T14:00:00Z",
      "pickup_address": "123 Lagos St, Lagos",
      "pickup_contact_name": "John Vendor",
      "pickup_contact_phone": "+234 800 123 4567",
      "status": "SCHEDULED",
      "vendor_notes": "Ready for pickup",
      "created_at": "2025-12-02T10:30:00Z"
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20,
  "total_pages": 1
}
```

---

### 5. **Notifications** (`/vendor/notifications`)

**API Endpoint:** `GET /vendor/notifications?unread_only=true`

```javascript
const getNotifications = async (unreadOnly = false) => {
  const params = new URLSearchParams({
    page: 1,
    page_size: 20
  });

  if (unreadOnly) {
    params.append('unread_only', 'true');
  }

  const response = await fetch(`${API_BASE}/vendor/notifications?${params}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};

const markAsRead = async (notificationIds) => {
  const response = await fetch(`${API_BASE}/vendor/notifications/mark-read`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      notification_ids: notificationIds
    })
  });
  return response.status === 204;
};

// Get unread count
const getUnreadCount = async () => {
  const response = await fetch(`${API_BASE}/vendor/notifications/unread-count`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json(); // { "unread_count": 8 }
};
```

**Sample Notification Component:**

```jsx
const NotificationBell = () => {
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    fetchUnreadCount();

    // Poll every 30 seconds
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchUnreadCount = async () => {
    const data = await getUnreadCount();
    setUnreadCount(data.unread_count);
  };

  return (
    <div className="notification-bell">
      <BellIcon />
      {unreadCount > 0 && (
        <span className="badge">{unreadCount}</span>
      )}
    </div>
  );
};
```

---

### 6. **Financials Page** (`/vendor/payouts`)

**API Endpoint:** `GET /vendor/payouts/summary`

```javascript
const getPayoutSummary = async () => {
  const response = await fetch(`${API_BASE}/vendor/payouts/summary`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};

// Response:
{
  "pending_amount": "1234567.00",
  "last_payout_amount": "987654.00",
  "last_payout_date": "2025-11-10",
  "total_earnings": "45678900.00",
  "current_month_sales": "3456789.00"
}

// List all payouts
const getPayouts = async (page = 1) => {
  const response = await fetch(`${API_BASE}/vendor/payouts?page=${page}&page_size=20`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};
```

---

### 7. **Profile Settings** (`/vendor/profile`)

**API Endpoint:** `PUT /vendor/profile`

```javascript
const updateProfile = async (data) => {
  const response = await fetch(`${API_BASE}/vendor/profile`, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      business_name: data.businessName,
      business_description: data.description,
      business_address: data.address,
      business_phone: data.phone,
      bank_name: data.bankName,
      bank_account_number: data.accountNumber,
      bank_account_name: data.accountName
    })
  });
  return response.json();
};
```

---

### 8. **Upload Assets** (Logo/Banner)

**API Endpoint:** `POST /vendor/assets`

```javascript
const uploadAsset = async (file, assetType) => {
  // Step 1: Upload file to S3/storage (your existing upload service)
  const fileUrl = await uploadToStorage(file);

  // Step 2: Register asset with backend
  const response = await fetch(`${API_BASE}/vendor/assets`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      asset_type: assetType, // 'logo', 'banner', or 'size_chart'
      file_url: fileUrl,
      file_name: file.name,
      file_size: file.size,
      mime_type: file.type
    })
  });
  return response.json();
};

// Get all assets
const getAssets = async (assetType = null) => {
  const params = assetType ? `?asset_type=${assetType}` : '';
  const response = await fetch(`${API_BASE}/vendor/assets${params}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  return response.json();
};
```

---

## 🎨 UI COMPONENTS NEEDED

### Dashboard Components:
1. **MetricCard** - Display key metrics
2. **OrdersTable** - List orders with pagination
3. **PickupCalendar** - Show scheduled pickups
4. **NotificationList** - Display notifications
5. **PayoutSummary** - Financial overview
6. **ProductList** - Vendor's products

### Forms:
1. **VendorRegistrationForm** - Onboarding
2. **KYCUploadForm** - Document submission
3. **ProfileEditForm** - Update business details
4. **AssetUploadForm** - Upload logos/banners

### Status Components:
1. **OrderStatusBadge** - Visual order status
2. **PickupStatusBadge** - Pickup status indicator
3. **PaymentStatusBadge** - Payment status

---

## 📱 RESPONSIVE DESIGN

### Breakpoints:
```css
/* Mobile */
@media (max-width: 640px) { }

/* Tablet */
@media (min-width: 641px) and (max-width: 1024px) { }

/* Desktop */
@media (min-width: 1025px) { }
```

### Key Pages Layout:
- **Dashboard**: 2x2 grid on desktop, single column on mobile
- **Orders**: Table on desktop, card list on mobile
- **Pickups**: Calendar on desktop, list on mobile
- **Notifications**: Sidebar on desktop, full page on mobile

---

## 🎯 USER FLOWS

### 1. **New Vendor Registration:**
```
Landing → Register Form → Submit → Profile Created
  → Upload Logo → Submit KYC → Wait for Approval
  → Approved → Dashboard Access
```

### 2. **Daily Vendor Workflow:**
```
Login → Dashboard → Check Notifications
  → View New Orders → Prepare Products
  → Check Pickup Schedule → Ready for Pickup
  → Track Fulfillment → Check Earnings
```

### 3. **Order Fulfillment:**
```
Order Received (Email + In-App Notification)
  → View Order Details → Prepare Product
  → Pickup Scheduled (48hrs for RTW)
  → Product Picked Up → QC Review
  → Shipped to Customer → Order Completed
  → Earnings Added to Pending Payout
```

---

## 🚦 STATUS COLORS

```css
/* Order Statuses */
.status-pending { background: #fef3c7; color: #92400e; }
.status-processing { background: #dbeafe; color: #1e40af; }
.status-shipped { background: #d1fae5; color: #065f46; }
.status-delivered { background: #dcfce7; color: #166534; }
.status-cancelled { background: #fee2e2; color: #991b1b; }

/* Payment Statuses */
.payment-pending { background: #fef3c7; color: #92400e; }
.payment-paid { background: #dcfce7; color: #166534; }
.payment-failed { background: #fee2e2; color: #991b1b; }

/* Pickup Statuses */
.pickup-scheduled { background: #dbeafe; color: #1e40af; }
.pickup-in-transit { background: #fef3c7; color: #92400e; }
.pickup-completed { background: #dcfce7; color: #166534; }
```

---

## 🔔 REAL-TIME UPDATES

### Polling Strategy:
```javascript
// Poll for new notifications every 30 seconds
useEffect(() => {
  const interval = setInterval(async () => {
    const count = await getUnreadCount();
    setUnreadCount(count.unread_count);
  }, 30000);

  return () => clearInterval(interval);
}, []);
```

### WebSocket (Future Enhancement):
```javascript
// Connect to WebSocket for real-time updates
const ws = new WebSocket('wss://api.shopsoma.com/vendor/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch (data.type) {
    case 'new_order':
      showNotification('New Order Received!');
      refreshOrders();
      break;
    case 'pickup_scheduled':
      refreshPickups();
      break;
    case 'payout_processed':
      refreshFinancials();
      break;
  }
};
```

---

## 🧪 TESTING APIS

### Use Postman/Insomnia:

1. **Import Collection:**
   - Base URL: `http://localhost:8000/api/v1`
   - Add Authorization header: `Bearer YOUR_TOKEN`

2. **Test Endpoints:**
   ```
   GET /vendor/profile
   GET /vendor/dashboard/metrics
   GET /vendor/orders
   GET /vendor/pickups
   GET /vendor/notifications
   GET /vendor/payouts/summary
   ```

---

## 📚 SAMPLE .ENV FILE

```env
VITE_API_BASE_URL=http://localhost:8000/api/v1
VITE_VENDOR_DASHBOARD_URL=http://localhost:5173/vendor
```

---

## ✅ QUICK CHECKLIST

- [ ] Set up API client with authentication
- [ ] Implement vendor registration form
- [ ] Build dashboard with metrics cards
- [ ] Create orders listing page
- [ ] Create pickups listing page
- [ ] Implement notification center
- [ ] Build financials/payouts page
- [ ] Add profile settings page
- [ ] Implement asset upload (logo/banner)
- [ ] Add loading states
- [ ] Add error handling
- [ ] Make responsive for mobile
- [ ] Test all API endpoints
- [ ] Add pagination
- [ ] Implement search/filters

---

## 🆘 TROUBLESHOOTING

### API Returns 401 Unauthorized:
- Check if JWT token is valid
- Verify Authorization header format: `Bearer TOKEN`
- Check if token has expired

### API Returns 403 Forbidden:
- User may not have vendor role
- Vendor account may not be approved
- KYC may not be submitted

### API Returns 404 Not Found:
- Check endpoint URL
- Verify vendor profile exists
- Check if resource belongs to vendor

---

## 📞 SUPPORT

**Questions?** Contact the backend team or check:
- API Documentation: `http://localhost:8000/api/docs`
- Technical Docs: `/VENDOR_DASHBOARD_BACKEND_SETUP.md`
- Complete Guide: `/VENDOR_DASHBOARD_COMPLETE.md`

---

**Happy Coding! 🚀**
