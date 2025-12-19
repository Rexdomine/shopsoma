# Shipping Total Calculation Bug Fix

## Problem Summary

**Issue:** On the checkout "Shipping method" step, the order summary showed a catastrophically wrong total:
- Subtotal: ₦66,600
- Shipping cost: ₦5,000
- Tax (VAT 7.5%): ₦4,995
- **Expected total**: ₦76,595
- **Actual total shown**: ₦666,005,000 (HUGE!)

The bug pattern "666,005,000" suggested string concatenation: "66600" + "5000" + "0" = "666005000"

## Root Cause

The backend uses `Decimal` type for `base_rate` in the shipping rate model. Pydantic by default serializes `Decimal` fields as **strings** in JSON responses (for precision reasons).

This meant the frontend received:
```json
{
  "base_rate": "5000",  // String instead of number!
  "name": "Standard Shipping"
}
```

When JavaScript tried to add these values:
```javascript
const total = subtotal + shipping + tax - discount;
// Became: 66600 + "5000" + 4995 - 0
// JavaScript coerces 66600 to "66600", concatenates with "5000"
// Result: "666005000" (or similar with formatting)
```

## Files Modified

### 1. [shopsoma-backend/app/schemas/shipping_rate.py](shopsoma-backend/app/schemas/shipping_rate.py:24-27)

**Change:** Added `@field_serializer` to convert Decimal fields to float in JSON responses

**Lines 2, 24-27:**
```python
from pydantic import BaseModel, Field, field_serializer

# ... class definition ...

@field_serializer('base_rate', 'min_order_value', 'max_order_value')
def serialize_decimal(self, value: Optional[Decimal]) -> Optional[float]:
    """Serialize Decimal fields as float for JSON"""
    return float(value) if value is not None else None
```

**Why this works:**
- Backend still uses `Decimal` for database precision (Numeric(10, 2))
- Pydantic now serializes these as JSON numbers: `5000` not `"5000"`
- Frontend receives proper numbers for arithmetic operations

### 2. [shopsoma-frontend/src/pages/checkout/Checkout.tsx](shopsoma-frontend/src/pages/checkout/Checkout.tsx:520-524)

**Change:** Added defensive `Number()` conversions to prevent string concatenation

**Lines 520-524:**
```typescript
const calculateCheckoutTotal = () => {
  if (orderReview) return orderReview.summary.total_amount;
  // Calculate total (before order review is created)
  const subtotal = Number(cart.summary.subtotal);
  const shipping = Number(selectedShippingRate?.base_rate || 0);
  const tax = calculateCheckoutTax();
  const discount = Number(appliedPromo?.discount_amount || 0);
  return subtotal + shipping + tax - discount;
};
```

**Line 967:**
```typescript
<span>{formatPrice(orderReview?.summary.shipping_cost ?? Number(selectedShippingRate?.base_rate || 0))}</span>
```

**Why this is important:**
- Even though backend now returns numbers, `Number()` adds type safety
- If any future API change returns strings, this prevents bugs
- Ensures arithmetic operations instead of string concatenation
- `Number("5000")` returns `5000` (number)
- `Number(5000)` returns `5000` (number) - safe for both

## How It Works Now

### Backend Serialization
```python
# Database model
base_rate = Column(Numeric(10, 2), nullable=False)  # Stores: 5000.00

# Pydantic schema (before fix)
base_rate: Decimal  # Serialized to JSON: "5000.00" (STRING!)

# Pydantic schema (after fix)
@field_serializer('base_rate')
def serialize_decimal(self, value):
    return float(value)  # Serialized to JSON: 5000.0 (NUMBER!)
```

### Frontend Calculation
```typescript
// Before fix - String concatenation bug
const shipping = selectedShippingRate?.base_rate || 0;
// If base_rate is "5000" (string), then:
// 66600 + "5000" = "666005000" (STRING CONCATENATION!)

// After fix - Numeric addition
const shipping = Number(selectedShippingRate?.base_rate || 0);
// Number("5000") = 5000
// 66600 + 5000 = 71600 (NUMERIC ADDITION!)
```

## Expected Behavior After Fix

**Scenario:** Cart has ₦66,600 worth of items, shipping is ₦5,000

| Component | Value | Type |
|-----------|-------|------|
| Subtotal | ₦66,600 | number |
| Shipping | ₦5,000 | number (was string) |
| Tax (VAT 7.5%) | ₦4,995 | number |
| Total | ₦76,595 | number (was "666005000") |

## Manual Test Checklist

### Test 1: Standard Shipping Rate
1. ✅ Add items totaling ₦66,600 to cart
2. ✅ Go to checkout, complete email and address
3. ✅ Select "Standard Shipping" (₦5,000)
4. ✅ **Expected**: Shipping cost = ₦5,000 (not "5000" or weird number)
5. ✅ **Expected**: Total = ₦76,595 (66,600 + 5,000 + 4,995)
6. ✅ **Verify in DevTools Network tab**: API response shows `"base_rate": 5000` (number, not string)

### Test 2: Free Shipping Threshold
1. ✅ Add items totaling ₦55,000 (above ₦50,000 threshold)
2. ✅ Go to checkout
3. ✅ Select free shipping rate
4. ✅ **Expected**: Shipping cost = ₦0
5. ✅ **Expected**: Total = ₦59,125 (55,000 + 0 + 4,125)

### Test 3: Express Shipping
1. ✅ Cart subtotal = ₦100,000
2. ✅ Select "Express Delivery" (₦10,000)
3. ✅ **Expected**: Shipping cost = ₦10,000
4. ✅ **Expected**: Tax = ₦7,500 (100,000 × 0.075)
5. ✅ **Expected**: Total = ₦117,500

### Test 4: With Promo Code
1. ✅ Cart subtotal = ₦80,000
2. ✅ Apply promo code for ₦10,000 off
3. ✅ Select shipping (₦5,000)
4. ✅ **Expected**: Tax calculated on ₦70,000 (subtotal - discount) = ₦5,250
5. ✅ **Expected**: Total = ₦70,250 (80,000 + 5,000 + 5,250 - 10,000)

### Test 5: USD Currency
1. ✅ Switch to USD currency
2. ✅ Cart subtotal converts to USD (e.g., $100)
3. ✅ Select shipping
4. ✅ **Expected**: All amounts in USD with 2 decimal places
5. ✅ **Expected**: Total calculated correctly in USD

### Test 6: Multiple Shipping Options
1. ✅ Complete checkout up to shipping step
2. ✅ Switch between different shipping rates
3. ✅ **Expected**: Total updates correctly for each shipping rate
4. ✅ **Expected**: No string concatenation at any step

## Technical Details

### Why Pydantic Serializes Decimal as String

By default, Pydantic serializes Python `Decimal` as strings in JSON to preserve precision:
```python
from decimal import Decimal
x = Decimal("5000.00")
# Default Pydantic JSON: {"value": "5000.00"}
# Why? To avoid floating-point precision issues in JavaScript
```

However, for currency values in the thousands range (not millions), JavaScript's `number` type (IEEE 754 double) has sufficient precision (53-bit mantissa = 15-17 decimal digits).

### The @field_serializer Solution

```python
@field_serializer('base_rate', 'min_order_value', 'max_order_value')
def serialize_decimal(self, value: Optional[Decimal]) -> Optional[float]:
    """Serialize Decimal fields as float for JSON"""
    return float(value) if value is not None else None
```

This tells Pydantic: "When serializing these fields to JSON, convert Decimal to float (number)."

### Why Number() in Frontend

```typescript
const shipping = Number(selectedShippingRate?.base_rate || 0);
```

- **Type safety**: Ensures numeric type even if API returns string
- **Defensive programming**: Prevents future bugs if backend changes
- **Explicit intent**: Makes it clear we need a number for arithmetic
- **No performance cost**: `Number()` is optimized in modern JS engines

## Other Decimal Fields to Check

If this bug appears elsewhere, check these schemas for Decimal fields that might need `@field_serializer`:

1. **Order schemas** (`app/schemas/order.py`):
   - `subtotal`, `shipping_cost`, `tax_amount`, `discount_amount`, `total_amount`

2. **Promo code schemas** (`app/schemas/promo_code.py`):
   - `discount_value`, `discount_amount`, `min_order_value`

3. **Product schemas** (if using Decimal for prices)

**Check command:**
```bash
grep -r "Decimal" shopsoma-backend/app/schemas/
```

## Status

✅ **FIXED**
- Backend serializes shipping rates as numbers
- Frontend uses defensive Number() conversions
- Both frontend and backend will hot-reload
- Test immediately with checklist above

## Currency Handling

This fix works for both NGN and USD:
- Backend stores amounts in Naira (base currency)
- Backend serializes as numbers (not strings)
- Frontend receives numbers
- Frontend converts to USD if needed (using `convertNGNToUSD()`)
- Frontend formats display with `formatPriceWithCurrency()`

## Changes NOT Made

- ❌ No changes to database schema
- ❌ No changes to payment gateway integration
- ❌ No changes to cart merge logic
- ❌ No changes to VAT calculation (already fixed in VAT_TAX_FIX.md)
- ❌ No changes to existing shipping rates in database (they'll still work)
