# 🛍️ Shopsoma Technical Development Guide

**Project:** Shopsoma Marketplace  
**Focus:** African Fashion (Clothes, Shoes, Accessories)  
**Launch Target:** December 12, 2025 (Code Freeze)  
**Technology Stack:** Python (FastAPI), React (Vite + TypeScript), PostgreSQL, Redis, Node.js, Docker, Render  
**Project Manager:** Rex  
**Design Lead:** Chisom  
**Vendor Operations Lead:** Maryam Sulaiman  

---

## 🧭 1. Project Overview

**Shopsoma** is a multi-vendor marketplace that connects African fashion designers with global buyers.  
Phase 1 focuses on:
- Core shopping experience (browse → cart → checkout)
- Vendor dashboard (inventory upload, simple analytics)
- Admin system (vendor approval, payout preparation)
- Secure payments via **Stripe** and **Paystack**
- Internal logistics setup for **Nigeria-only** operations initially.

Post-launch, **Phase 2** will extend into **Beauty & Makeup vertical**, introducing product filters, shades, and attributes.

---

## 🏗️ 2. System Architecture Overview

### 2.1 Layered Architecture

| Layer | Technologies | Description |
|-------|---------------|-------------|
| **Frontend** | React + TypeScript + Vite | Customer UI, Vendor Dashboard, Admin Interface |
| **Backend API** | FastAPI (Python) | REST APIs, business logic, authentication, payments |
| **Database** | PostgreSQL | Core data store for users, vendors, products, orders |
| **Cache/Queues** | Redis | Notifications, rate limiting, job queues |
| **Worker Services** | Node.js + Celery | Async tasks: emails, image compression, payouts |
| **Storage** | S3-compatible Object Storage | Product images, CSV uploads, reports |
| **Infra** | Docker + Render | Containerized deployment and CI/CD |
| **Payments** | Stripe + Paystack | Multi-gateway payment processing |
| **Search** | PostgreSQL Full-text (MVP) | Search and filtering |
| **Monitoring** | Prometheus + Grafana | Performance tracking and error logs |

---

## 🧩 3. Core Modules

### 3.1 Authentication & Roles
- **Email + Password** or **Magic Link Login**
- Roles: `customer`, `vendor`, `admin`
- JWT-based session tokens
- Middleware for role enforcement and route protection

### 3.2 Vendor Management
- Vendor registration with KYC
- Manual approval by Admin
- Vendor Dashboard (P1):
  - Upload CSV (SKU, Price, Quantity, Images)
  - Add, Edit/Delete products
  - View orders and 7/30-day sales summary

### 3.3 Product & Catalog
- Categories: Clothes, Shoes, Accessories
- Image upload (white background)
- Product Variants (Size, Color)
- PostgreSQL tables:
  ```sql
  products(id, vendor_id, title, description, category, price, status)
  variants(product_id, size, color, stock)
  images(product_id, url)
  ```

### 3.4 Orders & Checkout
- Add to Cart → Checkout → Payment
- Address Management (local delivery within Nigeria)
- Stripe / Paystack Integration
- Webhooks for payment success/failure
- Inventory rollback on payment failure
- Email notifications for order confirmations

### 3.5 Admin & Operations
- Vendor approval & moderation
- Returns (RMA) workflow:
  - 7 days (local) / 14 days (international)
- Monthly payout export (CSV)
- Packing slips (PDF) with QR/barcode
- Audit logs for critical actions

### 3.6 Logistics & Delivery
- Internal delivery system:
  - Pickups from Abuja, Lagos
  - Partner couriers (Okada, DHL)
- Rate table configuration in Admin
- Orders tagged with logistics provider and tracking

### 3.7 Notifications
- Email via SendGrid/Mailgun
- In-app alerts via Redis pub/sub
- Event-driven triggers:
  - Order created
  - Payment success
  - Vendor product approval

---

## 🗃️ 4. Database Schema Overview

```sql
-- Vendors Table
CREATE TABLE vendors (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100),
  email VARCHAR(255) UNIQUE,
  kyc_status VARCHAR(20),
  commission_rate NUMERIC DEFAULT 12.5,
  approved BOOLEAN DEFAULT false
);

-- Products Table
CREATE TABLE products (
  id SERIAL PRIMARY KEY,
  vendor_id INT REFERENCES vendors(id),
  title VARCHAR(255),
  description TEXT,
  category VARCHAR(50),
  price NUMERIC,
  stock INT,
  status VARCHAR(20) DEFAULT 'active',
  created_at TIMESTAMP DEFAULT now()
);

-- Orders Table
CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  customer_id INT,
  vendor_id INT,
  total NUMERIC,
  payment_status VARCHAR(20),
  fulfillment_status VARCHAR(20),
  created_at TIMESTAMP DEFAULT now()
);
```

---

## ⚙️ 5. API Endpoints

| Method | Endpoint | Description |
|--------|-----------|-------------|
| **POST** | `/auth/signup` | Register customer or vendor |
| **POST** | `/auth/login` | Email/password login |
| **POST** | `/auth/magic-link` | Send login link |
| **GET** | `/products` | Get product listings |
| **GET** | `/products/{id}` | Product details |
| **POST** | `/vendor/products/upload` | Upload product CSV |
| **GET** | `/orders` | List customer/vendor orders |
| **POST** | `/checkout` | Create order & initiate payment |
| **POST** | `/webhooks/stripe` | Stripe webhook handler |
| **POST** | `/webhooks/paystack` | Paystack webhook handler |
| **GET** | `/admin/vendors` | Admin view of vendors |
| **POST** | `/admin/approve/{vendor_id}` | Approve vendor |
| **GET** | `/admin/payouts/export` | Generate payout CSV |

---

## 🧠 7. Deployment to Render

### Deployment Steps
1. **Push to GitHub** → Render auto-builds from the connected repo.  
2. Create three **Render Web Services**:
   - `shopsoma-frontend`
   - `shopsoma-backend`
   - `shopsoma-worker` (Celery)
3. Add **PostgreSQL** and **Redis** add-ons.  
4. Configure environment variables (Render dashboard).  
5. Enable **Auto Deploy** on merge to `main`.  
6. Define a `/healthz` endpoint for Render’s uptime checks.  
7. Monitor build logs for deployment status.  

---

**Author:** RexTexh Engineering  
**Version:** v1.0 Launch (Phase 1)  
**Last Updated:** November 8, 2025
