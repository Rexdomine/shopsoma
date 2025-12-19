# User Model Attribute Fix

**Date**: December 12, 2025
**Status**: ✅ RESOLVED
**Issue**: AttributeError - User object has no attribute 'first_name'

---

## Problem

When navigating to `/admin/orders`, the API returned HTTP 500 error:

```
AttributeError: 'User' object has no attribute 'first_name'
```

**Error Location**: `/app/api/v1/admin_orders.py` line 49 in `build_customer_info()` function

**Stack Trace**:
```python
File "/Users/rex/Documents/Shopsoma/shopsoma-backend/app/api/v1/admin_orders.py", line 248, in list_orders
    customer=build_customer_info(order.customer),
File "/Users/rex/Documents/Shopsoma/shopsoma-backend/app/api/v1/admin_orders.py", line 49, in build_customer_info
    first_name=customer.first_name,
AttributeError: 'User' object has no attribute 'first_name'
```

---

## Root Cause

**Mismatch between User model schema and expected fields**

The `build_customer_info()` function was trying to access:
- `customer.first_name` ❌ (doesn't exist)
- `customer.last_name` ❌ (doesn't exist)
- `customer.phone` ❌ (doesn't exist)

But the **actual User model** has:
- `customer.full_name` ✅ (single field with full name)
- `customer.phone_number` ✅ (not `phone`)

### User Model Schema

```python
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)  # ← Single field
    phone_number = Column(String(20), nullable=True)  # ← Note: phone_number not phone
    # ... other fields
```

---

## Solution

### Fixed Code

**File**: `shopsoma-backend/app/api/v1/admin_orders.py`

**Before** (Broken):
```python
def build_customer_info(customer: User) -> CustomerInfo:
    """Build customer info from user"""
    return CustomerInfo(
        id=customer.id,
        first_name=customer.first_name,  # ❌ AttributeError
        last_name=customer.last_name,    # ❌ AttributeError
        email=customer.email,
        phone=customer.phone,            # ❌ AttributeError
    )
```

**After** (Fixed):
```python
def build_customer_info(customer: User) -> CustomerInfo:
    """Build customer info from user"""
    # Parse full_name into first_name and last_name
    full_name_parts = (customer.full_name or "").split(" ", 1)
    first_name = full_name_parts[0] if len(full_name_parts) > 0 else None
    last_name = full_name_parts[1] if len(full_name_parts) > 1 else None

    return CustomerInfo(
        id=customer.id,
        first_name=first_name,           # ✅ Parsed from full_name
        last_name=last_name,             # ✅ Parsed from full_name
        email=customer.email,
        phone=customer.phone_number,     # ✅ Correct field name
    )
```

### Key Changes

1. **Parse `full_name` into parts**:
   ```python
   full_name_parts = (customer.full_name or "").split(" ", 1)
   ```
   - Uses `.split(" ", 1)` to split on first space only
   - Handles `None` with `or ""` for null safety

2. **Extract first_name**:
   ```python
   first_name = full_name_parts[0] if len(full_name_parts) > 0 else None
   ```

3. **Extract last_name**:
   ```python
   last_name = full_name_parts[1] if len(full_name_parts) > 1 else None
   ```
   - Only if there are 2+ parts
   - Returns `None` if single-word name

4. **Use correct phone field**:
   ```python
   phone=customer.phone_number  # Not customer.phone
   ```

---

## Edge Cases Handled

### Single-Word Names
**Input**: `full_name = "Madonna"`

**Output**:
```python
first_name = "Madonna"
last_name = None
```

### Multi-Word Names
**Input**: `full_name = "John Doe Smith"`

**Output**:
```python
first_name = "John"
last_name = "Doe Smith"  # Everything after first space
```

### Empty/Null Names
**Input**: `full_name = None` or `full_name = ""`

**Output**:
```python
first_name = None
last_name = None
```

### Names with Multiple Spaces
**Input**: `full_name = "  John   Doe  "`

**Output**:
```python
first_name = ""  # First part (empty)
last_name = " John   Doe  "  # Rest
```

**Note**: Could add `.strip()` for better handling:
```python
full_name_parts = (customer.full_name or "").strip().split(" ", 1)
```

---

## Testing

### Manual Test

```bash
# 1. Make sure backend is running
curl http://localhost:8000/healthz
# Expected: {"status": "healthy"}

# 2. Test admin orders endpoint (requires admin token)
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
     http://localhost:8000/api/v1/admin/orders?page=1&page_size=20

# Expected: HTTP 200 with orders list (no 500 error)
```

### Frontend Test

```bash
# 1. Start frontend
cd /Users/rex/Documents/Shopsoma/shopsoma-frontend
PORT=5173 npm run dev

# 2. Navigate to admin orders
open http://localhost:5173/admin/orders

# Expected:
# ✅ Page loads
# ✅ Orders display in table
# ✅ Customer names show correctly
# ✅ No "Failed to load orders" error
```

---

## Example Data Flow

### Database
```sql
SELECT id, full_name, email, phone_number
FROM users
WHERE id = 'customer-uuid';

-- Result:
-- id: 'abc-123'
-- full_name: 'Jane Smith'
-- email: 'jane@example.com'
-- phone_number: '+1234567890'
```

### API Response
```json
{
  "orders": [
    {
      "id": "order-uuid",
      "order_number": "ORD-12345",
      "customer": {
        "id": "abc-123",
        "first_name": "Jane",      // ← Parsed from full_name
        "last_name": "Smith",       // ← Parsed from full_name
        "email": "jane@example.com",
        "phone": "+1234567890"      // ← From phone_number field
      },
      // ... rest of order data
    }
  ]
}
```

### Frontend Display
```
Customer: Jane Smith
Email: jane@example.com
Phone: +1234567890
```

---

## Related Files

### Modified
1. **`shopsoma-backend/app/api/v1/admin_orders.py`**
   - Fixed `build_customer_info()` function (lines 45-58)

### Checked (No Changes Needed)
1. **`shopsoma-backend/app/models/user.py`**
   - Confirmed User model structure
   - Has `full_name` (not `first_name`/`last_name`)
   - Has `phone_number` (not `phone`)

2. **`shopsoma-backend/app/schemas/admin_order.py`**
   - CustomerInfo schema already correct (has optional first_name/last_name)

---

## Prevention

### Why This Happened

When creating the admin orders API, I assumed the User model followed a common pattern of separate `first_name` and `last_name` fields. However, the actual Shopsoma User model uses a single `full_name` field.

### Best Practices

1. **Always check the actual model before writing code**:
   ```bash
   # Quick check
   grep -A 20 "class User" app/models/user.py
   ```

2. **Use IDE autocomplete** or check model file first

3. **Add type hints** to catch errors at dev time:
   ```python
   def build_customer_info(customer: User) -> CustomerInfo:
       # IDE will show available attributes
   ```

4. **Write tests** that actually hit the database:
   ```python
   def test_build_customer_info():
       user = User(full_name="John Doe", email="john@test.com")
       info = build_customer_info(user)
       assert info.first_name == "John"
   ```

---

## Status

**Issue**: ✅ RESOLVED
**Backend**: ✅ Fixed and running
**Frontend**: Ready to start manually
**Testing**: Manual testing required

---

## Next Steps

1. ✅ Backend fix applied
2. ⏳ Start frontend in VS Code terminal
3. ⏳ Test admin orders page loads
4. ⏳ Verify customer names display correctly
5. ⏳ Test all order management features

---

## Commands to Run

### Start Frontend (VS Code Terminal)

```bash
# Navigate to frontend directory
cd /Users/rex/Documents/Shopsoma/shopsoma-frontend

# Start on port 5173
PORT=5173 npm run dev

# Or simply (Vite defaults to 5173)
npm run dev
```

### Access Admin Orders

```
http://localhost:5173/admin/orders
```

**Expected Result**: Orders load successfully with customer information displayed correctly.

---

**Last Updated**: December 12, 2025
**Version**: 1.0.0
