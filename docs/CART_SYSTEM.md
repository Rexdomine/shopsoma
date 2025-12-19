# Shopsoma Cart & Pricing System

## Overview

A complete cart and pricing service with LocalStorage persistence, server synchronization, and automatic price recalculation hooks.

## Architecture

### Frontend Components

#### 1. **Types** (`shopsoma-frontend/src/types/cart.ts`)
- `CartItem`: Individual cart item with product, variant, quantity, and price
- `CartSummary`: Calculated totals (subtotal, shipping, tax, discount, total)
- `Cart`: Complete cart state with items and summary
- `CartState`: Zustand store interface

#### 2. **Pricing Utilities** (`shopsoma-frontend/src/utils/pricing.ts`)
- **Configuration:**
  - VAT Rate: 7.5% (Nigeria standard)
  - Shipping: ₦2,000 flat rate
  - Free shipping threshold: ₦50,000

- **Functions:**
  - `calculateCartSummary()`: Calculate all cart totals
  - `calculateItemSubtotal()`: Item price × quantity
  - `getVariantPrice()`: Get variant price with fallback
  - `formatCurrency()`: Format in Nigerian Naira
  - `applyCoupon()`: Apply discount codes

#### 3. **Cart Service** (`shopsoma-frontend/src/services/cartService.ts`)
- LocalStorage management (key: `shopsoma_cart`)
- Cart CRUD operations
- Server sync placeholders
- Cart validation
- Cart merging (local + server)

#### 4. **Zustand Store** (`shopsoma-frontend/src/store/cartStore.ts`)
- **State Management:**
  - `cart`: Current cart data
  - `isLoading`: Loading state
  - `error`: Error messages

- **Actions:**
  - `addItem()`: Add/update cart items
  - `removeItem()`: Remove from cart
  - `updateQuantity()`: Change item quantity
  - `clearCart()`: Empty the cart
  - `applyCoupon()`: Apply discount codes
  - `syncWithServer()`: Sync with backend
  - `loadFromLocalStorage()`: Load persisted cart
  - `recalculatePrices()`: Refresh all calculations

### Backend Components

#### 1. **Models** (`shopsoma-backend/app/models/cart.py`)

**CartItem Model:**
```python
- id: String (primary key)
- user_id: UUID (foreign key to users)
- session_id: String (for guest users)
- product_id: UUID (foreign key to products)
- variant_id: String
- quantity: Integer
- price: Float (locked at add time)
- created_at, updated_at: DateTime
```

**Coupon Model:**
```python
- id: String (primary key)
- code: String (unique)
- discount_type: 'percentage' | 'fixed'
- discount_value: Float
- min_purchase: Float (optional)
- max_discount: Float (for percentage coupons)
- usage_limit, used_count: Integer
- valid_from, valid_until: DateTime
- is_active: Boolean
```

#### 2. **Schemas** (`shopsoma-backend/app/schemas/cart.py`)
- Request/Response models for all cart operations
- Validation rules (quantity >= 1, etc.)
- Pydantic models for type safety

#### 3. **API Endpoints** (`shopsoma-backend/app/api/v1/cart.py`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/cart` | GET | Get user's cart |
| `/api/v1/cart/items` | POST | Add item to cart |
| `/api/v1/cart/items/{id}` | PATCH | Update item quantity |
| `/api/v1/cart/items/{id}` | DELETE | Remove item |
| `/api/v1/cart` | DELETE | Clear cart |
| `/api/v1/cart/apply-coupon` | POST | Apply coupon code |

**Features:**
- Supports both authenticated users and guest sessions
- Session ID via `X-Session-ID` header for guests
- Automatic price locking when items are added
- Real-time cart summary calculations
- Coupon validation with expiry and limits

## Usage Examples

### Frontend - Adding to Cart

```typescript
import { useCartStore } from '@/store/cartStore';

function ProductPage() {
  const addItem = useCartStore((state) => state.addItem);

  const handleAddToCart = () => {
    addItem({
      product: productData,
      variant: selectedVariant,
      quantity: 1
    });
  };
}
```

### Frontend - Cart Summary

```typescript
import { useCartStore } from '@/store/cartStore';

function CartSummary() {
  const { summary } = useCartStore((state) => state.cart);

  return (
    <div>
      <p>Subtotal: ₦{summary.subtotal.toLocaleString()}</p>
      <p>Shipping: ₦{summary.shipping.toLocaleString()}</p>
      <p>Tax (7.5%): ₦{summary.tax.toLocaleString()}</p>
      {summary.discount > 0 && (
        <p>Discount: -₦{summary.discount.toLocaleString()}</p>
      )}
      <p><strong>Total: ₦{summary.total.toLocaleString()}</strong></p>
    </div>
  );
}
```

### Backend - Adding to Cart

```bash
# For authenticated users
POST /api/v1/cart/items
Authorization: Bearer {token}
Content-Type: application/json

{
  "product_id": "uuid-here",
  "variant_id": "size-m-color-blue",
  "quantity": 2
}

# For guest users
POST /api/v1/cart/items
X-Session-ID: session-uuid-here
Content-Type: application/json

{
  "product_id": "uuid-here",
  "variant_id": "size-m-color-blue",
  "quantity": 2
}
```

### Backend - Applying Coupon

```bash
POST /api/v1/cart/apply-coupon
Authorization: Bearer {token}
Content-Type: application/json

{
  "code": "WELCOME10"
}

# Response
{
  "is_valid": true,
  "discount_amount": 5000.0,
  "discount_type": "percentage",
  "message": "Coupon applied: 10% off",
  "cart": {
    "items": [...],
    "summary": {...}
  }
}
```

## Pricing Calculation Flow

1. **Subtotal** = Sum of (price × quantity) for all items
2. **Shipping** = ₦2,000 (or ₦0 if subtotal >= ₦50,000)
3. **Taxable Amount** = Subtotal - Discount
4. **Tax** = Taxable Amount × 0.075 (7.5%)
5. **Total** = Subtotal + Shipping + Tax - Discount

## LocalStorage Structure

```json
{
  "items": [
    {
      "id": "product-uuid_variant-id",
      "product_id": "product-uuid",
      "product": {...},
      "variant": {...},
      "quantity": 2,
      "price": 25000,
      "subtotal": 50000
    }
  ],
  "summary": {
    "subtotal": 50000,
    "shipping": 0,
    "tax": 3750,
    "discount": 0,
    "total": 53750,
    "itemCount": 2
  },
  "lastUpdated": "2025-11-15T12:00:00.000Z",
  "userId": "user-uuid-or-null"
}
```

## Database Schema

```sql
-- Cart Items Table
CREATE TABLE cart_items (
    id VARCHAR PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    session_id VARCHAR,
    product_id UUID REFERENCES products(id) NOT NULL,
    variant_id VARCHAR NOT NULL,
    quantity INTEGER NOT NULL,
    price FLOAT NOT NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX ix_cart_items_session_id ON cart_items(session_id);

-- Coupons Table
CREATE TABLE coupons (
    id VARCHAR PRIMARY KEY,
    code VARCHAR UNIQUE NOT NULL,
    discount_type VARCHAR NOT NULL,
    discount_value FLOAT NOT NULL,
    min_purchase FLOAT,
    max_discount FLOAT,
    usage_limit INTEGER,
    used_count INTEGER DEFAULT 0,
    valid_from TIMESTAMP NOT NULL,
    valid_until TIMESTAMP NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP
);

CREATE UNIQUE INDEX ix_coupons_code ON coupons(code);
```

## Features Implemented

✅ LocalStorage persistence
✅ Server-side cart storage
✅ Guest cart support (session-based)
✅ User cart support (authenticated)
✅ Automatic price recalculation
✅ Tax calculation (7.5% VAT)
✅ Shipping calculation with free shipping threshold
✅ Coupon/discount system
✅ Cart validation
✅ Quantity updates
✅ Item removal
✅ Cart clearing
✅ Price locking (prices stored when items added)

## Next Steps

### UI Components Needed:
1. **Cart Drawer/Modal** - Slide-out cart preview
2. **Cart Page** - Full cart view with item management
3. **Cart Icon with Badge** - Show item count in header
4. **Checkout Summary** - Final review before payment
5. **Coupon Input** - Apply discount codes

### Future Enhancements:
- Cart abandonment emails
- Save for later functionality
- Recently viewed products
- Recommended products in cart
- Bulk operations (remove all out-of-stock items)
- Cart sharing (share cart link)
- Wishlists integration

## Testing

Test the cart functionality:

```bash
# Run backend
cd shopsoma-backend
source venv/bin/activate
uvicorn app.main:app --reload

# Test endpoints
curl http://localhost:8000/api/v1/cart \
  -H "X-Session-ID: test-session-123"
```

## Deployment Checklist

- [ ] Apply database migration on production
- [ ] Update CORS settings for cart endpoints
- [ ] Set up monitoring for cart operations
- [ ] Configure Redis for session management (future)
- [ ] Set up cart abandonment tracking
- [ ] Test guest-to-user cart migration

---

**Built with:** React, TypeScript, Zustand, FastAPI, PostgreSQL, Alembic
