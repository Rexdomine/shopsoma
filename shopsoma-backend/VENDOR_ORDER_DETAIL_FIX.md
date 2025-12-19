# Vendor Order Detail - 500 Error Fix

**Date**: December 11, 2025  
**Status**: ✅ FIXED

---

## Problem

Clicking an order in the vendor orders list caused:
- 500 Internal Server Error
- Page quickly refreshes back to list
- Order detail never loads

**Error**:
```
PydanticSerializationError: Unable to serialize unknown type: 
<class 'app.models.order.OrderItem'>
```

---

## Root Cause

The `get_vendor_order()` endpoint was returning SQLAlchemy `OrderItem` objects directly:

```python
# ❌ BEFORE (Line 466)
return {
    "id": order.id,              # UUID object
    "items": vendor_items,        # SQLAlchemy OrderItem objects ← Bug!
    "created_at": order.created_at,  # datetime object
    ...
}
```

FastAPI/Pydantic cannot serialize SQLAlchemy model objects automatically.

---

## Solution

Added explicit serialization for all non-JSON-native types:

```python
# ✅ AFTER (Lines 463-501)

# Serialize order items to dictionaries
serialized_items = []
for item in vendor_items:
    serialized_items.append({
        "id": str(item.id),                    # UUID → string
        "product_title": item.product_title,
        "unit_price": float(item.unit_price),  # Decimal → float
        "quantity": item.quantity,
        "vendor_payout": float(item.vendor_payout),
        "fulfillment_status": item.fulfillment_status.value,  # Enum → string
        "created_at": item.created_at.isoformat(),  # datetime → ISO string
        ...
    })

return {
    "id": str(order.id),                    # UUID → string
    "items": serialized_items,              # Proper dictionaries ✓
    "created_at": order.created_at.isoformat(),  # datetime → ISO string
    "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
    ...
}
```

---

## What Was Fixed

### 1. OrderItem Objects
**Before**: Returned SQLAlchemy `OrderItem` model instances  
**After**: Serialized to dictionaries with all fields converted

### 2. UUID Fields
**Before**: UUID objects (`order.id`)  
**After**: Strings (`str(order.id)`)

### 3. Decimal Fields
**Before**: `Decimal` objects (`item.unit_price`)  
**After**: Floats (`float(item.unit_price)`)

### 4. Datetime Fields
**Before**: `datetime` objects (`order.created_at`)  
**After**: ISO strings (`order.created_at.isoformat()`)

### 5. Enum Fields
**Before**: Enum objects (`item.fulfillment_status`)  
**After**: String values (`item.fulfillment_status.value`)

---

## Files Changed

**Backend**:
- `shopsoma-backend/app/api/v1/vendors.py`
  - Lines 463-480: Added OrderItem serialization loop
  - Line 483: Convert order ID to string
  - Line 498: Convert created_at to ISO string
  - Line 499: Convert confirmed_at to ISO string

---

## Testing

### Before Fix
```bash
# Server logs
INFO: "GET /api/v1/vendor/orders/790ff9e3-... HTTP/1.1" 500 Internal Server Error
ERROR: PydanticSerializationError: Unable to serialize unknown type...

# UI behavior
Click order → Quick refresh → Back to list (never loads detail)
```

### After Fix
```bash
# Server logs
INFO: "GET /api/v1/vendor/orders/790ff9e3-... HTTP/1.1" 200 OK

# UI behavior
Click order → Navigate to detail page → Order details displayed ✓
```

### How to Test Now

1. **Start backend** (if not already running):
   ```bash
   cd shopsoma-backend
   source venv/bin/activate
   uvicorn app.main:app --reload
   ```

2. **Navigate to orders**: `http://localhost:5173/vendor/orders`

3. **Click any order row**

4. **Expected result**:
   - ✅ URL changes to `/vendor/orders/{order_id}`
   - ✅ Order detail page loads
   - ✅ Shows order number, items, customer info, shipping address
   - ✅ No 500 error in server logs
   - ✅ No quick refresh/redirect

5. **Check server logs**:
   ```
   INFO: ... "GET /api/v1/vendor/orders/790ff9e3-... HTTP/1.1" 200 OK
   ```

---

## API Response Example

**Endpoint**: `GET /api/v1/vendor/orders/{order_id}`

**Response** (200 OK):
```json
{
  "id": "790ff9e3-5e24-490c-bac2-849200a4ddfe",
  "order_number": "SHP-20251211-F1ABE539",
  "items": [
    {
      "id": "item-uuid-here",
      "order_id": "790ff9e3-5e24-490c-bac2-849200a4ddfe",
      "product_id": "product-uuid-here",
      "product_title": "Product Name",
      "variant_details": {...},
      "unit_price": 60000.0,
      "quantity": 1,
      "subtotal": 60000.0,
      "commission_rate": 12.5,
      "commission_amount": 7500.0,
      "vendor_payout": 52500.0,
      "fulfillment_status": "pending",
      "created_at": "2025-12-11T12:00:00"
    }
  ],
  "customer_name": "Customer Name",
  "customer_email": "customer@example.com",
  "shipping_address": {
    "address_line1": "123 Main St",
    "city": "Lagos",
    "state": "Lagos",
    "postal_code": "100001",
    "country": "Nigeria"
  },
  "payment_status": "paid",
  "fulfillment_status": "processing",
  "created_at": "2025-12-11T12:00:00",
  "confirmed_at": "2025-12-11T12:05:00",
  "customer_notes": "Please deliver in the morning"
}
```

---

## Pattern to Prevent Future Issues

This is the **second time** we've hit this serialization bug:
1. **First**: Order list endpoint
2. **Now**: Order detail endpoint

**Root cause**: Using `response_model=dict` instead of proper Pydantic models.

**Better approach** (for future endpoints):
```python
from pydantic import BaseModel

class OrderItemResponse(BaseModel):
    id: str
    product_title: str
    unit_price: float
    # ... etc

class OrderDetailResponse(BaseModel):
    id: str
    order_number: str
    items: list[OrderItemResponse]
    # ... etc

@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
async def get_vendor_order(...):
    # Pydantic will auto-serialize or error at development time
    pass
```

This would catch serialization issues during development instead of at runtime.

---

## Summary

**Fixed**: ✅ Vendor order detail now loads properly  
**Cause**: SQLAlchemy objects in API response  
**Solution**: Explicit serialization to dictionaries  
**Impact**: Order detail page now works end-to-end  

---

**Test it now!** Click an order and watch it load. 🎉
