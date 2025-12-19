# Address Model Attribute Fix

**Date**: December 12, 2025
**Status**: ✅ RESOLVED
**Issue**: AttributeError - Address object has no attribute 'phone'

---

## Problem

When clicking "View" on an order in the admin orders list, the API returned HTTP 500 error:

```
AttributeError: 'Address' object has no attribute 'phone'
```

**Error Location**: `/app/api/v1/admin_orders.py` line 76 in `build_address_info()` function

**Frontend Impact**: Order detail page showed "Order not found" message

---

## Root Cause

**Same issue as User model** - mismatch between Address model schema and expected fields.

The `build_address_info()` function was trying to access:
- `address.phone` ❌ (doesn't exist)
- `address.street_address` ❌ (doesn't exist)

But the **actual Address model** has:
- `address.phone_number` ✅
- `address.address_line1` and `address.address_line2` ✅ (two separate fields)

### Address Model Schema

```python
class Address(Base):
    __tablename__ = "addresses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Address Type
    address_type = Column(SQLEnum(AddressType), default=AddressType.SHIPPING)

    # Address Details
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=False)     # ← Not 'phone'
    address_line1 = Column(String(255), nullable=False)   # ← Not 'street_address'
    address_line2 = Column(String(255), nullable=True)    # ← Optional second line
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), default="Nigeria")

    is_default = Column(Boolean, default=False)
    # ... timestamps
```

---

## Solution

### Fixed Code

**File**: `shopsoma-backend/app/api/v1/admin_orders.py`

**Before** (Broken):
```python
def build_address_info(address: Address) -> AddressInfo:
    """Build address info"""
    return AddressInfo(
        id=address.id,
        full_name=address.full_name,
        phone=address.phone,                    # ❌ AttributeError
        street_address=address.street_address,  # ❌ AttributeError
        city=address.city,
        state=address.state,
        country=address.country,
        postal_code=address.postal_code,
    )
```

**After** (Fixed):
```python
def build_address_info(address: Address) -> AddressInfo:
    """Build address info"""
    # Combine address_line1 and address_line2 into street_address
    street_address = address.address_line1
    if address.address_line2:
        street_address = f"{address.address_line1}, {address.address_line2}"

    return AddressInfo(
        id=address.id,
        full_name=address.full_name,
        phone=address.phone_number,      # ✅ Correct field name
        street_address=street_address,   # ✅ Combined from address_line1 & address_line2
        city=address.city,
        state=address.state,
        country=address.country,
        postal_code=address.postal_code,
    )
```

### Key Changes

1. **Use correct phone field**:
   ```python
   phone=address.phone_number  # Not address.phone
   ```

2. **Combine address lines**:
   ```python
   street_address = address.address_line1
   if address.address_line2:
       street_address = f"{address.address_line1}, {address.address_line2}"
   ```

---

## Edge Cases Handled

### Address with Line 2
**Input**:
```python
address_line1 = "123 Main Street"
address_line2 = "Apt 4B"
```

**Output**:
```python
street_address = "123 Main Street, Apt 4B"
```

### Address without Line 2
**Input**:
```python
address_line1 = "456 Oak Avenue"
address_line2 = None
```

**Output**:
```python
street_address = "456 Oak Avenue"
```

### Empty Line 2
**Input**:
```python
address_line1 = "789 Pine Road"
address_line2 = ""
```

**Output**:
```python
street_address = "789 Pine Road"
# Empty string is falsy, so not included
```

---

## Example Data Flow

### Database
```sql
SELECT id, full_name, phone_number, address_line1, address_line2, city, state
FROM addresses
WHERE id = 'address-uuid';

-- Result:
-- id: 'addr-123'
-- full_name: 'John Doe'
-- phone_number: '+1234567890'
-- address_line1: '123 Main Street'
-- address_line2: 'Suite 100'
-- city: 'Lagos'
-- state: 'Lagos'
```

### API Response
```json
{
  "id": "order-uuid",
  "shipping_address": {
    "id": "addr-123",
    "full_name": "John Doe",
    "phone": "+1234567890",              // ← From phone_number
    "street_address": "123 Main Street, Suite 100",  // ← Combined
    "city": "Lagos",
    "state": "Lagos",
    "country": "Nigeria",
    "postal_code": "100001"
  }
}
```

### Frontend Display
```
Shipping Address:
John Doe
123 Main Street, Suite 100
Lagos, Lagos 100001
Nigeria
Phone: +1234567890
```

---

## Testing

### Manual Test

```bash
# 1. Make sure backend is running
curl http://localhost:8000/healthz
# Expected: {"status": "healthy"}

# 2. Test order detail endpoint (replace with actual order ID)
ORDER_ID="790ff9e3-5e24-490c-bac2-849200a4ddfe"
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
     http://localhost:8000/api/v1/admin/orders/$ORDER_ID

# Expected: HTTP 200 with complete order details (no 500 error)
```

### Frontend Test

```bash
# 1. Start frontend (in VS Code terminal)
cd /Users/rex/Documents/Shopsoma/shopsoma-frontend
npm run dev

# 2. Navigate to admin orders
open http://localhost:5173/admin/orders

# 3. Click "View →" on any order

# Expected:
# ✅ Order detail page loads
# ✅ Shipping address displays correctly
# ✅ Billing address displays correctly
# ✅ No "Order not found" error
# ✅ All address fields populated
```

---

## Related Files

### Modified
1. **`shopsoma-backend/app/api/v1/admin_orders.py`**
   - Fixed `build_address_info()` function (lines 71-87)
   - Added address line combination logic

### Checked (No Changes Needed)
1. **`shopsoma-backend/app/models/address.py`**
   - Confirmed Address model structure
   - Has `phone_number` (not `phone`)
   - Has `address_line1` and `address_line2` (not `street_address`)

2. **`shopsoma-backend/app/schemas/admin_order.py`**
   - AddressInfo schema already correct (expects combined street_address)

---

## Summary of Model Field Mismatches Fixed

### User Model
| Expected Field | Actual Field | Fix |
|---|---|---|
| `first_name` | `full_name` | Parse/split |
| `last_name` | `full_name` | Parse/split |
| `phone` | `phone_number` | Use correct name |

### Address Model
| Expected Field | Actual Field | Fix |
|---|---|---|
| `phone` | `phone_number` | Use correct name |
| `street_address` | `address_line1` + `address_line2` | Combine fields |

---

## Prevention

### Best Practices

1. **Always check model schemas first**:
   ```bash
   # Quick reference
   grep -A 30 "class Address" app/models/address.py
   grep -A 30 "class User" app/models/user.py
   ```

2. **Use type hints** for better IDE support:
   ```python
   def build_address_info(address: Address) -> AddressInfo:
       # IDE autocomplete shows actual fields
   ```

3. **Write integration tests** that query actual database:
   ```python
   async def test_get_order_detail():
       order = await create_test_order()  # Creates real address
       response = await client.get(f"/admin/orders/{order.id}")
       assert response.status_code == 200  # Would catch AttributeError
   ```

4. **Document model schemas** in API documentation

---

## Status

**Issue**: ✅ RESOLVED
**Backend**: ✅ Fixed and running
**Frontend**: Ready to test order details
**Testing**: Manual testing required

---

## Next Steps

1. ✅ Backend fix applied
2. ⏳ Test order detail page loads
3. ⏳ Verify addresses display correctly
4. ⏳ Test order updates
5. ⏳ Test all order management features

---

## Commands to Test

### View Order Detail (Browser)

1. Navigate to: `http://localhost:5173/admin/orders`
2. Click "View →" on any order
3. Expected: Order detail page loads with shipping/billing addresses

### Check Backend Logs

```bash
# In backend terminal, you should NOT see:
# AttributeError: 'Address' object has no attribute 'phone'

# You SHOULD see:
# INFO: 127.0.0.1 - "GET /api/v1/admin/orders/{id} HTTP/1.1" 200 OK
```

---

**Last Updated**: December 12, 2025
**Version**: 1.0.0
**Related Fix**: USER_MODEL_ATTRIBUTE_FIX.md
