# Shopsoma Database Schema

**Version:** 1.0
**Database:** PostgreSQL 14+
**ORM:** SQLAlchemy 2.0 (Async)
**Last Updated:** November 11, 2025

---

## Entity Relationship Diagram (ERD)

### Core Entities

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│    Users    │────────▶│   Vendors   │────────▶│  Products   │
└─────────────┘         └─────────────┘         └─────────────┘
       │                       │                       │
       │                       │                       │
       │                       │                       ▼
       │                       │              ┌─────────────────┐
       │                       │              │ Product Variants│
       │                       │              └─────────────────┘
       │                       │                       │
       │                       ▼                       ▼
       │              ┌─────────────┐         ┌─────────────┐
       │              │Vendor Orders│         │Product Images│
       │              └─────────────┘         └─────────────┘
       │                       │
       ▼                       ▼
┌─────────────┐         ┌─────────────┐
│   Orders    │◀────────│ Order Items │
└─────────────┘         └─────────────┘
       │
       │
       ▼
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│  Payments   │         │  Addresses  │         │  Reviews    │
└─────────────┘         └─────────────┘         └─────────────┘
       │
       ▼
┌─────────────┐
│   Payouts   │
└─────────────┘
```

---

## Table Definitions

### 1. Users Table
Stores all user accounts (customers, vendors, admins).

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255),  -- NULL for magic link only users
    full_name VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20),
    role VARCHAR(20) NOT NULL DEFAULT 'customer',  -- customer, vendor, admin
    email_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    profile_image_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
```

**Fields:**
- `id` - Unique identifier (UUID)
- `email` - User email (unique)
- `hashed_password` - Bcrypt hashed password (nullable for magic link)
- `full_name` - User's full name
- `phone_number` - Contact number
- `role` - User role (customer/vendor/admin)
- `email_verified` - Email verification status
- `is_active` - Account active status
- `profile_image_url` - S3 URL for profile picture
- `created_at` - Account creation timestamp
- `updated_at` - Last update timestamp
- `last_login_at` - Last login timestamp

---

### 2. Vendors Table
Vendor-specific information and KYC data.

```sql
CREATE TABLE vendors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    business_name VARCHAR(255) NOT NULL,
    business_description TEXT,
    business_address TEXT,
    business_phone VARCHAR(20),

    -- KYC Information
    kyc_status VARCHAR(20) DEFAULT 'pending',  -- pending, submitted, approved, rejected
    kyc_document_type VARCHAR(50),  -- passport, drivers_license, national_id
    kyc_document_url TEXT,
    kyc_submitted_at TIMESTAMP WITH TIME ZONE,
    kyc_reviewed_at TIMESTAMP WITH TIME ZONE,
    kyc_reviewer_id UUID REFERENCES users(id),
    kyc_rejection_reason TEXT,

    -- Business Information
    bank_name VARCHAR(100),
    bank_account_number VARCHAR(50),
    bank_account_name VARCHAR(255),

    -- Platform Settings
    commission_rate NUMERIC(5,2) DEFAULT 12.5,  -- Percentage
    approved BOOLEAN DEFAULT FALSE,
    approved_at TIMESTAMP WITH TIME ZONE,
    approved_by UUID REFERENCES users(id),

    -- Metrics
    total_products INT DEFAULT 0,
    total_orders INT DEFAULT 0,
    total_revenue NUMERIC(12,2) DEFAULT 0.00,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_vendors_user_id ON vendors(user_id);
CREATE INDEX idx_vendors_kyc_status ON vendors(kyc_status);
CREATE INDEX idx_vendors_approved ON vendors(approved);
```

---

### 3. Categories Table
Product categories (Phase 1: Clothes, Shoes, Accessories).

```sql
CREATE TABLE categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parent_id UUID REFERENCES categories(id) ON DELETE CASCADE,
    image_url TEXT,
    display_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_categories_slug ON categories(slug);
CREATE INDEX idx_categories_parent_id ON categories(parent_id);
```

---

### 4. Products Table
Core product information.

```sql
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    category_id UUID REFERENCES categories(id) ON DELETE SET NULL,

    -- Product Information
    title VARCHAR(255) NOT NULL,
    description TEXT,
    sku VARCHAR(100) UNIQUE,

    -- Pricing
    base_price NUMERIC(10,2) NOT NULL,
    compare_at_price NUMERIC(10,2),  -- Original price for showing discounts

    -- Inventory (for products without variants)
    total_stock INT DEFAULT 0,

    -- Status
    status VARCHAR(20) DEFAULT 'draft',  -- draft, active, inactive, archived
    is_featured BOOLEAN DEFAULT FALSE,

    -- SEO
    meta_title VARCHAR(255),
    meta_description TEXT,

    -- Metrics
    views_count INT DEFAULT 0,
    orders_count INT DEFAULT 0,

    -- Moderation
    moderation_status VARCHAR(20) DEFAULT 'pending',  -- pending, approved, rejected
    moderated_at TIMESTAMP WITH TIME ZONE,
    moderated_by UUID REFERENCES users(id),
    moderation_notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_products_vendor_id ON products(vendor_id);
CREATE INDEX idx_products_category_id ON products(category_id);
CREATE INDEX idx_products_status ON products(status);
CREATE INDEX idx_products_sku ON products(sku);
```

---

### 5. Product Variants Table
Size and color variations of products.

```sql
CREATE TABLE product_variants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,

    -- Variant Attributes
    size VARCHAR(50),  -- S, M, L, XL, 38, 40, etc.
    color VARCHAR(50),
    color_hex VARCHAR(7),  -- #FFFFFF for display

    -- Pricing & Stock
    price NUMERIC(10,2) NOT NULL,
    stock INT NOT NULL DEFAULT 0,
    sku VARCHAR(100) UNIQUE,

    -- Status
    is_available BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(product_id, size, color)
);

CREATE INDEX idx_variants_product_id ON product_variants(product_id);
CREATE INDEX idx_variants_sku ON product_variants(sku);
CREATE INDEX idx_variants_stock ON product_variants(stock);
```

---

### 6. Product Images Table
Product photos with ordering.

```sql
CREATE TABLE product_images (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    image_url TEXT NOT NULL,
    thumbnail_url TEXT,
    alt_text VARCHAR(255),
    display_order INT DEFAULT 0,
    is_primary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_images_product_id ON product_images(product_id);
CREATE INDEX idx_images_display_order ON product_images(product_id, display_order);
```

---

### 7. Addresses Table
Customer shipping and billing addresses.

```sql
CREATE TABLE addresses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Address Type
    address_type VARCHAR(20) DEFAULT 'shipping',  -- shipping, billing

    -- Address Details
    full_name VARCHAR(255) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255),
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20),
    country VARCHAR(100) DEFAULT 'Nigeria',

    -- Flags
    is_default BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_addresses_user_id ON addresses(user_id);
CREATE INDEX idx_addresses_default ON addresses(user_id, is_default);
```

---

### 8. Orders Table
Customer orders.

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_number VARCHAR(50) UNIQUE NOT NULL,
    customer_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

    -- Address Information
    shipping_address_id UUID REFERENCES addresses(id),
    billing_address_id UUID REFERENCES addresses(id),

    -- Pricing
    subtotal NUMERIC(10,2) NOT NULL,
    shipping_cost NUMERIC(10,2) DEFAULT 0.00,
    tax_amount NUMERIC(10,2) DEFAULT 0.00,
    discount_amount NUMERIC(10,2) DEFAULT 0.00,
    total_amount NUMERIC(10,2) NOT NULL,

    -- Status
    payment_status VARCHAR(20) DEFAULT 'pending',  -- pending, paid, failed, refunded
    fulfillment_status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, shipped, delivered, cancelled

    -- Delivery
    delivery_provider VARCHAR(50),  -- okada, dhl, internal
    tracking_number VARCHAR(100),
    estimated_delivery_date DATE,
    delivered_at TIMESTAMP WITH TIME ZONE,

    -- Notes
    customer_notes TEXT,
    admin_notes TEXT,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    confirmed_at TIMESTAMP WITH TIME ZONE,
    cancelled_at TIMESTAMP WITH TIME ZONE,
    cancellation_reason TEXT
);

CREATE INDEX idx_orders_order_number ON orders(order_number);
CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_payment_status ON orders(payment_status);
CREATE INDEX idx_orders_fulfillment_status ON orders(fulfillment_status);
CREATE INDEX idx_orders_created_at ON orders(created_at DESC);
```

---

### 9. Order Items Table
Individual items in an order.

```sql
CREATE TABLE order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    variant_id UUID REFERENCES product_variants(id) ON DELETE RESTRICT,
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,

    -- Product Snapshot (at time of order)
    product_title VARCHAR(255) NOT NULL,
    variant_details JSONB,  -- {size: "M", color: "Blue"}

    -- Pricing
    unit_price NUMERIC(10,2) NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    subtotal NUMERIC(10,2) NOT NULL,

    -- Vendor Commission
    commission_rate NUMERIC(5,2) NOT NULL,
    commission_amount NUMERIC(10,2) NOT NULL,
    vendor_payout NUMERIC(10,2) NOT NULL,

    -- Fulfillment
    fulfillment_status VARCHAR(20) DEFAULT 'pending',

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_order_items_order_id ON order_items(order_id);
CREATE INDEX idx_order_items_vendor_id ON order_items(vendor_id);
CREATE INDEX idx_order_items_product_id ON order_items(product_id);
```

---

### 10. Payments Table
Payment transactions.

```sql
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,

    -- Payment Details
    payment_gateway VARCHAR(20) NOT NULL,  -- stripe, paystack
    transaction_id VARCHAR(255) UNIQUE,
    payment_method VARCHAR(50),  -- card, bank_transfer

    -- Amount
    amount NUMERIC(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'NGN',

    -- Status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed, refunded

    -- Gateway Response
    gateway_response JSONB,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    failed_at TIMESTAMP WITH TIME ZONE,
    failure_reason TEXT
);

CREATE INDEX idx_payments_order_id ON payments(order_id);
CREATE INDEX idx_payments_transaction_id ON payments(transaction_id);
CREATE INDEX idx_payments_status ON payments(status);
```

---

### 11. Payouts Table
Vendor payouts.

```sql
CREATE TABLE payouts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE RESTRICT,

    -- Payout Details
    payout_period_start DATE NOT NULL,
    payout_period_end DATE NOT NULL,

    -- Amounts
    total_sales NUMERIC(12,2) NOT NULL,
    commission_amount NUMERIC(12,2) NOT NULL,
    payout_amount NUMERIC(12,2) NOT NULL,

    -- Status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, processing, completed, failed

    -- Processing
    processed_by UUID REFERENCES users(id),
    processed_at TIMESTAMP WITH TIME ZONE,
    payment_reference VARCHAR(100),

    -- Notes
    notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_payouts_vendor_id ON payouts(vendor_id);
CREATE INDEX idx_payouts_status ON payouts(status);
CREATE INDEX idx_payouts_period ON payouts(payout_period_start, payout_period_end);
```

---

### 12. Reviews Table
Product reviews and ratings.

```sql
CREATE TABLE reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id UUID REFERENCES orders(id) ON DELETE SET NULL,

    -- Review Content
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    title VARCHAR(255),
    comment TEXT,

    -- Images
    review_images JSONB,  -- Array of image URLs

    -- Status
    is_verified_purchase BOOLEAN DEFAULT FALSE,
    is_approved BOOLEAN DEFAULT FALSE,
    moderated_at TIMESTAMP WITH TIME ZONE,
    moderated_by UUID REFERENCES users(id),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(product_id, customer_id, order_id)
);

CREATE INDEX idx_reviews_product_id ON reviews(product_id);
CREATE INDEX idx_reviews_customer_id ON reviews(customer_id);
CREATE INDEX idx_reviews_approved ON reviews(is_approved);
```

---

### 13. Returns Table
Product returns and RMA.

```sql
CREATE TABLE returns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    return_number VARCHAR(50) UNIQUE NOT NULL,
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
    customer_id UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,

    -- Return Details
    reason VARCHAR(100) NOT NULL,
    description TEXT,
    return_images JSONB,

    -- Status
    status VARCHAR(20) DEFAULT 'requested',  -- requested, approved, rejected, received, refunded

    -- Refund
    refund_amount NUMERIC(10,2),
    refund_method VARCHAR(50),

    -- Processing
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_returns_order_id ON returns(order_id);
CREATE INDEX idx_returns_customer_id ON returns(customer_id);
CREATE INDEX idx_returns_status ON returns(status);
```

---

### 14. Audit Logs Table
System audit trail for critical actions.

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- Action Details
    action VARCHAR(100) NOT NULL,  -- vendor_approved, product_moderated, payout_processed
    entity_type VARCHAR(50),  -- vendor, product, order, payout
    entity_id UUID,

    -- Changes
    old_values JSONB,
    new_values JSONB,

    -- Metadata
    ip_address INET,
    user_agent TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs(created_at DESC);
```

---

## Relationships Summary

1. **Users → Vendors** (1:1) - One user can be one vendor
2. **Vendors → Products** (1:N) - Vendor has many products
3. **Products → Product Variants** (1:N) - Product has many variants
4. **Products → Product Images** (1:N) - Product has many images
5. **Products → Categories** (N:1) - Many products in one category
6. **Users → Orders** (1:N) - User has many orders
7. **Orders → Order Items** (1:N) - Order has many items
8. **Orders → Payments** (1:N) - Order can have multiple payment attempts
9. **Vendors → Payouts** (1:N) - Vendor has many payouts
10. **Products → Reviews** (1:N) - Product has many reviews
11. **Orders → Returns** (1:N) - Order can have multiple returns

---

## Indexes Strategy

### Primary Indexes
- All primary keys (UUID)
- Unique constraints (email, order_number, sku)

### Query Optimization Indexes
- Foreign key columns
- Status columns (frequently filtered)
- Timestamp columns (for date ranges)
- Composite indexes for common queries

---

## Data Integrity Rules

1. **Cascade Deletes:**
   - User deleted → Vendor deleted
   - Product deleted → Variants, Images deleted
   - Order deleted → Order Items deleted

2. **Restrict Deletes:**
   - Cannot delete User with Orders
   - Cannot delete Product with Orders
   - Cannot delete Order with Payments

3. **Soft Deletes:**
   - Users: `is_active = FALSE`
   - Products: `status = 'archived'`

---

## Performance Considerations

1. **Partitioning** (Future):
   - Orders table by created_at (monthly)
   - Audit logs by created_at (monthly)

2. **Materialized Views** (Future):
   - Vendor analytics dashboard
   - Product search with filters
   - Sales reports

3. **Caching Strategy**:
   - Product listings (Redis, 5 min TTL)
   - Category tree (Redis, 1 hour TTL)
   - Vendor stats (Redis, 15 min TTL)

---

**Next Steps:**
1. Create SQLAlchemy models
2. Set up Alembic migrations
3. Generate initial migration
4. Test locally with PostgreSQL

*Database schema designed for Shopsoma v1.0 Phase 1*
