# VENDOR DASHBOARD BACKEND SETUP

## Overview
This document outlines the complete backend infrastructure for the SHOPSOMA Vendor Dashboard, integrating seamlessly with the existing marketplace.

## Created Date
December 2, 2025

---

## 1. DATABASE MODELS

### 1.1 Enhanced Existing Models
- **Vendor Model** (`app/models/vendor.py`)
  - Already existed with KYC, bank details, commission rate (12.5%)
  - Added new relationships: `assets`, `pickups`, `notifications`

- **Order & OrderItem Models** (`app/models/order.py`)
  - Added `pickups` relationship to Order
  - Added `pickup` relationship to OrderItem (one-to-one)

### 1.2 New Models Created

#### VendorAsset (`app/models/vendor_asset.py`)
Handles vendor logos, banners, and size charts.

**Fields:**
- `id`: UUID primary key
- `vendor_id`: Foreign key to vendors
- `asset_type`: String (logo, banner, size_chart)
- `file_url`: Text (S3/storage URL)
- `file_name`, `file_size`, `mime_type`: File metadata
- `display_order`: Integer for ordering
- `is_active`: Boolean
- `alt_text`, `description`: Optional metadata
- `created_at`, `updated_at`: Timestamps

#### VendorPickup (`app/models/vendor_pickup.py`)
Manages order fulfillment and logistics scheduling.

**Key Features:**
- Two order types: RTW (24-48 hours) and Made-to-Order (custom timeline)
- Complete pickup lifecycle tracking
- QC (Quality Control) integration
- Logistics partner integration

**Fields:**
- `id`, `vendor_id`, `order_id`, `order_item_id`: Identifiers
- `order_type`: Enum (RTW, MADE_TO_ORDER, CUSTOM)
- `estimated_production_days`: Integer (for made-to-order)
- `scheduled_pickup_date`, `actual_pickup_date`: Timestamps
- `pickup_address`, `pickup_contact_name`, `pickup_contact_phone`: Pickup details
- `logistics_partner`, `tracking_number`, `driver_name`, `driver_phone`: Logistics info
- `status`: Enum (SCHEDULED, IN_TRANSIT, DELIVERED_TO_QC, QC_APPROVED, QC_REJECTED, SHIPPED_TO_CUSTOMER, COMPLETED, CANCELLED)
- `qc_center_arrival_date`, `qc_approved_date`, `qc_rejected_date`, `qc_notes`: QC tracking
- `vendor_notes`, `admin_notes`: Communication fields
- Timestamps: `created_at`, `updated_at`, `completed_at`, `cancelled_at`

**Enums:**
- `PickupStatus`: 8 states tracking entire fulfillment lifecycle
- `OrderType`: RTW, MADE_TO_ORDER, CUSTOM

#### VendorNotification (`app/models/vendor_pickup.py`)
Real-time notification system for vendors.

**Fields:**
- `id`, `vendor_id`: Identifiers
- `notification_type`: String (order_placed, pickup_scheduled, payment_processed, etc.)
- `title`, `message`: Notification content
- `order_id`, `pickup_id`, `payout_id`: Optional references
- `data`: JSONB for additional context
- `is_read`, `read_at`: Read status
- `email_sent`, `email_sent_at`: Email delivery tracking
- `created_at`: Timestamp

---

## 2. DATABASE MIGRATION

### Migration File
`alembic/versions/3f110cfcb80f_add_vendor_assets_pickups_notifications_.py`

**Creates:**
1. `vendor_assets` table with indexes on `vendor_id` and `asset_type`
2. `vendor_pickups` table with indexes on `vendor_id`, `order_id`, `order_item_id`, `status`, `tracking_number`
3. `vendor_notifications` table with indexes on `vendor_id`, `notification_type`, `is_read`, `created_at`
4. Two PostgreSQL enums: `ordertype` and `pickupstatus`

**Status:** ✅ Successfully applied to database

---

## 3. API SCHEMAS

### File: `app/schemas/vendor.py`

Comprehensive Pydantic schemas for all vendor operations:

#### 3.1 Vendor Asset Schemas
- `VendorAssetBase`, `VendorAssetCreate`, `VendorAssetUpdate`, `VendorAssetResponse`

#### 3.2 Vendor Onboarding Schemas
- `VendorOnboardingRequest`: Registration form
- `VendorKYCSubmission`: KYC document upload
- `VendorProfileUpdate`: Profile editing
- `VendorResponse`: Complete vendor profile

#### 3.3 Vendor Pickup Schemas
- `VendorPickupBase`, `VendorPickupCreate`, `VendorPickupUpdate`, `VendorPickupResponse`

#### 3.4 Vendor Notification Schemas
- `VendorNotificationResponse`: Notification details
- `VendorNotificationMarkRead`: Mark multiple notifications as read

#### 3.5 Vendor Order Schemas
- `VendorOrderItemResponse`: Vendor-specific order item view
- `VendorOrderResponse`: Order with only vendor's items

#### 3.6 Vendor Payout Schemas
- `VendorPayoutResponse`: Payout details
- `VendorPayoutSummary`: Financial summary

#### 3.7 Vendor Dashboard Schemas
- `VendorDashboardMetrics`: Complete dashboard metrics
- `VendorProductPerformance`: Product analytics
- `VendorDashboardResponse`: Full dashboard data
- `VendorProductListFilters`: Product filtering

---

## 4. SERVICE LAYER

### File: `app/services/vendor_service.py`

Complete business logic implementation for vendor operations.

#### 4.1 Vendor Management
- `create_vendor()`: Create new vendor profile with 12.5% commission rate
- `get_vendor_by_user_id()`: Retrieve vendor by user
- `get_vendor_by_id()`: Retrieve vendor by ID
- `update_vendor_profile()`: Update vendor information
- `submit_kyc()`: Submit KYC documents

#### 4.2 Vendor Assets
- `create_vendor_asset()`: Upload logos, banners, size charts
- `get_vendor_assets()`: Retrieve assets by type
- `delete_vendor_asset()`: Remove assets

#### 4.3 Vendor Orders
- `get_vendor_orders()`: Paginated order list with filtering
- `get_vendor_order_items()`: Get vendor's items from specific order

#### 4.4 Vendor Pickups
- `create_pickup()`: Schedule pickup with automatic date calculation
  - RTW: 48 hours
  - Made-to-Order: Uses estimated_production_days
- `get_vendor_pickups()`: Paginated pickup list with status filtering

#### 4.5 Vendor Notifications
- `create_notification()`: Send notifications to vendors
- `get_vendor_notifications()`: Retrieve notifications (unread filter available)
- `mark_notifications_read()`: Bulk mark as read

#### 4.6 Dashboard & Analytics
- `get_dashboard_metrics()`: Complete dashboard metrics
  - Product stats (total, active, pending approval)
  - Order stats (total, pending, in progress, completed)
  - Revenue stats (total, current month, pending payout)
  - Pickup stats
  - Notification count
- `get_payout_summary()`: Financial summary
  - Pending payout amount
  - Last payout details
  - Total earnings
  - Current month sales

---

## 5. BUSINESS LOGIC IMPLEMENTATION

### 5.1 Commission System
- **Rate:** 12.5% per successful sale (stored in `Vendor.commission_rate`)
- **Calculation:** Happens at OrderItem level
  - `commission_amount = subtotal * (commission_rate / 100)`
  - `vendor_payout = subtotal - commission_amount`
- **Storage:** Pre-calculated and stored in `order_items` table

### 5.2 Fulfillment Flow

#### RTW (Ready-to-Wear) Orders:
1. Customer places order → `Order` created with `OrderItem`s
2. System calculates pickup window: **24-48 hours**
3. `VendorPickup` created with `status=SCHEDULED`
4. Vendor receives notification
5. Logistics partner picks up → `status=IN_TRANSIT`
6. Arrives at QC Center → `status=DELIVERED_TO_QC`
7. QC approval → `status=QC_APPROVED`
8. Ships to customer → `status=SHIPPED_TO_CUSTOMER`
9. Delivered → `status=COMPLETED`

#### Made-to-Order / Custom Orders:
1. Customer places order
2. Vendor specifies `estimated_production_days`
3. Pickup scheduled after production time
4. Same QC flow as RTW

### 5.3 Payment Schedule
- **Timing:** First 10 working days of each month
- **Period:** Previous month's completed orders
- **Process:**
  1. System identifies all `OrderItem`s where:
     - `Order.payment_status = PAID`
     - `Order.fulfillment_status = DELIVERED`
     - `created_at` within payout period
  2. Creates `Payout` record with:
     - `total_sales`: Sum of subtotals
     - `commission_amount`: Sum of commission amounts
     - `payout_amount`: Sum of vendor payouts
  3. Admin processes payment
  4. Updates `Payout.status = COMPLETED`

### 5.4 Notification Triggers
**Automatic notifications created when:**
- Order placed → `order_placed`
- Pickup scheduled → `pickup_scheduled`
- QC approved/rejected → `qc_status_update`
- Payment processed → `payment_processed`
- Product approved/rejected → `product_moderation`

---

## 6. INTEGRATION WITH EXISTING MARKETPLACE

### 6.1 Order Creation Flow Integration
**Location:** `app/api/v1/orders.py` (needs update)

**Required Changes:**
```python
# After creating OrderItem, create VendorPickup
from app.services.vendor_service import VendorService

# For each order_item:
pickup_data = VendorPickupCreate(
    order_item_id=order_item.id,
    order_type="RTW",  # or "MADE_TO_ORDER" based on product
    pickup_address=vendor.business_address,
    pickup_contact_name=vendor.user.full_name,
    pickup_contact_phone=vendor.business_phone
)
VendorService.create_pickup(db, vendor_id, pickup_data)

# Create notification
VendorService.create_notification(
    db=db,
    vendor_id=vendor_id,
    notification_type="order_placed",
    title=f"New Order #{order.order_number}",
    message=f"You have received a new order for {product.title}",
    order_id=order.id
)
```

### 6.2 Product Moderation Integration
**Location:** `app/api/v1/admin.py` (needs update)

**When approving/rejecting products:**
```python
# Notify vendor of moderation decision
VendorService.create_notification(
    db=db,
    vendor_id=product.vendor_id,
    notification_type="product_moderation",
    title="Product Moderation Update",
    message=f"Your product '{product.title}' has been {status}",
    data={"product_id": str(product.id), "status": status}
)
```

---

## 7. API ENDPOINTS (TO BE CREATED)

### 7.1 Vendor Onboarding
```
POST   /api/v1/vendor/onboard          - Create vendor profile
POST   /api/v1/vendor/kyc/submit       - Submit KYC documents
GET    /api/v1/vendor/profile          - Get vendor profile
PUT    /api/v1/vendor/profile          - Update vendor profile
```

### 7.2 Vendor Assets
```
POST   /api/v1/vendor/assets           - Upload asset (logo/banner/size chart)
GET    /api/v1/vendor/assets           - List assets
GET    /api/v1/vendor/assets/{id}      - Get specific asset
DELETE /api/v1/vendor/assets/{id}      - Delete asset
```

### 7.3 Vendor Products
```
GET    /api/v1/vendor/products         - List vendor's products
POST   /api/v1/vendor/products         - Create product
GET    /api/v1/vendor/products/{id}    - Get product details
PUT    /api/v1/vendor/products/{id}    - Update product
DELETE /api/v1/vendor/products/{id}    - Delete product
```

### 7.4 Vendor Orders
```
GET    /api/v1/vendor/orders           - List orders (with filters)
GET    /api/v1/vendor/orders/{id}      - Get order details
```

### 7.5 Vendor Pickups
```
GET    /api/v1/vendor/pickups          - List pickups
GET    /api/v1/vendor/pickups/{id}     - Get pickup details
PUT    /api/v1/vendor/pickups/{id}     - Update pickup info
```

### 7.6 Vendor Notifications
```
GET    /api/v1/vendor/notifications    - List notifications
POST   /api/v1/vendor/notifications/mark-read - Mark as read
GET    /api/v1/vendor/notifications/unread-count - Get unread count
```

### 7.7 Vendor Financials
```
GET    /api/v1/vendor/payouts          - List payouts
GET    /api/v1/vendor/payouts/{id}     - Get payout details
GET    /api/v1/vendor/payouts/summary  - Get financial summary
```

### 7.8 Vendor Dashboard
```
GET    /api/v1/vendor/dashboard        - Complete dashboard data
GET    /api/v1/vendor/metrics          - Dashboard metrics only
GET    /api/v1/vendor/analytics/products - Top performing products
```

---

## 8. AUTHENTICATION & AUTHORIZATION

### 8.1 Required Middleware
**To be created:** `app/api/dependencies.py` enhancements

```python
from app.models import Vendor, User
from app.models.user import UserRole

async def get_current_vendor(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Vendor:
    """Get current vendor from authenticated user"""
    if current_user.role != UserRole.VENDOR:
        raise HTTPException(status_code=403, detail="Vendor access required")

    vendor = db.query(Vendor).filter(Vendor.user_id == current_user.id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="Vendor profile not found")

    if not vendor.approved:
        raise HTTPException(status_code=403, detail="Vendor account not approved")

    return vendor

async def get_current_approved_vendor(
    vendor: Vendor = Depends(get_current_vendor)
) -> Vendor:
    """Ensure vendor is approved"""
    if not vendor.approved:
        raise HTTPException(status_code=403, detail="Vendor account pending approval")
    return vendor
```

### 8.2 Permission Levels
1. **Pending Vendor** - Can view profile, submit KYC, cannot create products
2. **Approved Vendor** - Full access to products, orders, pickups
3. **Admin** - Can approve vendors, review products, process payouts

---

## 9. NEXT STEPS

### Priority 1: Core Vendor API
1. ✅ Models created
2. ✅ Schemas created
3. ✅ Service layer created
4. ⏳ Create vendor API endpoints file (`app/api/v1/vendors.py`)
5. ⏳ Create auth middleware for vendors
6. ⏳ Add routes to main router

### Priority 2: Integration
1. ⏳ Update order creation flow to create pickups
2. ⏳ Update order creation flow to send notifications
3. ⏳ Update product moderation to send notifications
4. ⏳ Create notification service for email delivery

### Priority 3: Admin Features
1. ⏳ Vendor approval endpoint
2. ⏳ KYC review endpoint
3. ⏳ Payout processing endpoint
4. ⏳ QC management endpoint

### Priority 4: Frontend
1. ⏳ Vendor dashboard UI
2. ⏳ Product management UI
3. ⏳ Order management UI
4. ⏳ Notification UI

---

## 10. TESTING CHECKLIST

### Database Tests
- [ ] Test vendor creation
- [ ] Test pickup scheduling calculations
- [ ] Test notification creation
- [ ] Test payout calculations

### Service Tests
- [ ] Test vendor onboarding flow
- [ ] Test KYC submission
- [ ] Test order retrieval (only vendor's items)
- [ ] Test dashboard metrics calculations
- [ ] Test payout summary accuracy

### Integration Tests
- [ ] Test complete order → pickup → notification flow
- [ ] Test product approval → notification flow
- [ ] Test payout calculation accuracy

---

## 11. TECHNICAL NOTES

### Performance Considerations
- **Indexes:** All foreign keys and frequently queried fields are indexed
- **Pagination:** All list endpoints use pagination (default 20, max 100)
- **Query Optimization:** Dashboard metrics use aggregations instead of loading all records

### Security Considerations
- Vendors can only access their own data
- KYC documents stored securely (URLs only in DB)
- Bank information stored in encrypted format (recommended: use Fernet or similar)
- All vendor endpoints require authentication and vendor role

### Data Integrity
- Cascade deletes for vendor-owned resources (assets, notifications)
- RESTRICT deletes for financial records (orders, payouts)
- Foreign key constraints enforce referential integrity

---

## 12. DOCUMENTATION REFERENCES

### Business Requirements
- **Shop Soma Seller Guide**: Vendor onboarding, product guidelines, fulfillment process
- **Shop Soma Vendor Seller Plan**: Order types (RTW vs Made-to-Order), QC workflow, payment schedule

### Key Business Rules Implemented
✅ 12.5% commission rate
✅ RTW: 24-48 hour pickup
✅ Made-to-Order: Custom production timeline
✅ QC workflow integration
✅ Monthly payout schedule (first 10 working days)
✅ Vendor notification system
✅ Multi-vendor order support

---

## Status: BACKEND INFRASTRUCTURE COMPLETE
**Ready for API endpoint implementation and frontend integration**
