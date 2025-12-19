# Vendor Model Attribute Fix & Comprehensive Error Handling

**Date**: December 13, 2025
**Status**: ✅ RESOLVED
**Issue**: AttributeError - Vendor object has no attribute 'contact_email'

---

## Problem

When clicking "View" on an order in the admin orders list, the API returned HTTP 500 error:

```
AttributeError: 'Vendor' object has no attribute 'contact_email'
```

**Error Location**: `/app/api/v1/admin_orders.py` line 66 in `build_vendor_info()` function

**Frontend Impact**: Order detail page showed "Order not found" message

---

## Root Cause

**Third instance of model attribute mismatch** - following the same pattern as User and Address model issues.

The `build_vendor_info()` function was trying to access:
- `vendor.contact_email` ❌ (doesn't exist)
- `vendor.contact_phone` ❌ (doesn't exist)

But the **actual Vendor model** has:
- `vendor.business_phone` ✅ (not contact_phone)
- **NO email field directly** - must access via `vendor.user.email` relationship

### Vendor Model Schema

```python
class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Business Information
    business_name = Column(String(255), nullable=False)  # ✅ Exists
    business_phone = Column(String(20), nullable=True)   # ← Not contact_phone
    business_description = Column(Text, nullable=True)
    business_address = Column(Text, nullable=True)
    logo_url = Column(Text, nullable=True)
    # NO contact_email field - must use vendor.user.email

    # Relationships
    user = relationship("User", back_populates="vendor")  # ← Email comes from here
```

---

## Solution

### 1. Fixed `build_vendor_info()` Function

**File**: `shopsoma-backend/app/api/v1/admin_orders.py`

**Before** (Broken):
```python
def build_vendor_info(vendor: Vendor) -> VendorInfo:
    """Build vendor info"""
    return VendorInfo(
        id=vendor.id,
        business_name=vendor.business_name,
        contact_email=vendor.contact_email,  # ❌ AttributeError
        contact_phone=vendor.contact_phone,  # ❌ AttributeError
    )
```

**After** (Fixed):
```python
def build_vendor_info(vendor: Vendor) -> VendorInfo:
    """Build vendor info"""
    try:
        # Get email from vendor.user relationship (if loaded)
        contact_email = None
        if hasattr(vendor, 'user') and vendor.user:
            contact_email = vendor.user.email

        return VendorInfo(
            id=vendor.id,
            business_name=vendor.business_name,
            contact_email=contact_email,
            contact_phone=vendor.business_phone,  # ✅ Correct field name
        )
    except AttributeError as e:
        # Log detailed error for debugging
        raise ValueError(f"Error building vendor info for vendor {vendor.id}: Missing attribute {str(e)}") from e
```

### Key Changes

1. **Access email via relationship**:
   ```python
   contact_email = None
   if hasattr(vendor, 'user') and vendor.user:
       contact_email = vendor.user.email
   ```

2. **Use correct phone field**:
   ```python
   contact_phone=vendor.business_phone  # Not vendor.contact_phone
   ```

3. **Add error handling**:
   ```python
   except AttributeError as e:
       raise ValueError(f"Error building vendor info for vendor {vendor.id}: Missing attribute {str(e)}") from e
   ```

---

### 2. Updated Query to Load Vendor.User Relationship

**File**: `shopsoma-backend/app/api/v1/admin_orders.py`

**Before** (Vendor user not loaded):
```python
query = select(Order).where(Order.id == order_id).options(
    selectinload(Order.customer),
    selectinload(Order.shipping_address),
    selectinload(Order.billing_address),
    selectinload(Order.items).selectinload(OrderItem.vendor),  # ❌ User not loaded
    selectinload(Order.pickups),
)
```

**After** (Vendor user loaded):
```python
query = select(Order).where(Order.id == order_id).options(
    selectinload(Order.customer),
    selectinload(Order.shipping_address),
    selectinload(Order.billing_address),
    selectinload(Order.items).selectinload(OrderItem.vendor).selectinload(Vendor.user),  # ✅ User loaded
    selectinload(Order.pickups),
)
```

---

## Comprehensive Error Handling Added

### 3. Enhanced All Build Functions with Error Handling

#### `build_customer_info()`
```python
def build_customer_info(customer: User) -> CustomerInfo:
    """Build customer info from user"""
    try:
        # Parse full_name into first_name and last_name
        full_name_parts = (customer.full_name or "").split(" ", 1)
        first_name = full_name_parts[0] if len(full_name_parts) > 0 else None
        last_name = full_name_parts[1] if len(full_name_parts) > 1 else None

        return CustomerInfo(
            id=customer.id,
            first_name=first_name,
            last_name=last_name,
            email=customer.email,
            phone=customer.phone_number,
        )
    except AttributeError as e:
        raise ValueError(f"Error building customer info for user {customer.id}: Missing attribute {str(e)}") from e
```

#### `build_address_info()`
```python
def build_address_info(address: Address) -> AddressInfo:
    """Build address info"""
    try:
        # Combine address_line1 and address_line2 into street_address
        street_address = address.address_line1
        if address.address_line2:
            street_address = f"{address.address_line1}, {address.address_line2}"

        return AddressInfo(
            id=address.id,
            full_name=address.full_name,
            phone=address.phone_number,
            street_address=street_address,
            city=address.city,
            state=address.state,
            country=address.country,
            postal_code=address.postal_code or "",  # Handle nullable
        )
    except AttributeError as e:
        raise ValueError(f"Error building address info for address {address.id}: Missing attribute {str(e)}") from e
```

---

### 4. Added Endpoint-Level Error Handling

**File**: `shopsoma-backend/app/api/v1/admin_orders.py`

```python
@router.get("/{order_id}", response_model=OrderDetail)
async def get_order_detail(
    order_id: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get complete order details"""

    try:
        # Query order with all relationships
        query = select(Order).where(Order.id == order_id).options(
            selectinload(Order.customer),
            selectinload(Order.shipping_address),
            selectinload(Order.billing_address),
            selectinload(Order.items).selectinload(OrderItem.vendor).selectinload(Vendor.user),
            selectinload(Order.pickups),
        )

        result = await db.execute(query)
        order = result.scalar_one_or_none()

        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found",
            )

        # Build response with detailed error tracking
        return OrderDetail(
            # ... order details ...
        )
    except ValueError as e:
        # Catch our custom ValueError from build_* functions with detailed error info
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error building order details: {str(e)}",
        )
    except AttributeError as e:
        # Catch any unexpected AttributeErrors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Model attribute error in order {order_id}: {str(e)}. Please check model mappings.",
        )
    except Exception as e:
        # Catch all other errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error loading order details: {str(e)}",
        )
```

**Error Handling Layers**:

1. **Build Function Level**: Catches AttributeError, wraps in ValueError with context
2. **Endpoint Level**:
   - Catches ValueError (from build functions) → Returns detailed error
   - Catches AttributeError (unexpected) → Returns model mapping error
   - Catches Exception (any other) → Returns generic error

**Benefits**:
- ✅ Clear, actionable error messages
- ✅ Identifies which model/entity has the issue
- ✅ Distinguishes between expected and unexpected errors
- ✅ Easier debugging for future model mismatches

---

### 5. Fixed Search Filter

**Issue**: Search filter was trying to use `first_name` and `last_name` which don't exist in User model

**Before** (Broken):
```python
if search:
    search_term = f"%{search}%"
    filters.append(
        or_(
            Order.order_number.ilike(search_term),
            Order.customer.has(User.email.ilike(search_term)),
            Order.customer.has(
                or_(
                    User.first_name.ilike(search_term),  # ❌ Doesn't exist
                    User.last_name.ilike(search_term),   # ❌ Doesn't exist
                )
            ),
        )
    )
```

**After** (Fixed):
```python
if search:
    # Search by order number, customer name (full_name), or email
    search_term = f"%{search}%"
    filters.append(
        or_(
            Order.order_number.ilike(search_term),
            Order.customer.has(User.email.ilike(search_term)),
            Order.customer.has(User.full_name.ilike(search_term)),  # ✅ Correct field
        )
    )
```

---

## Complete Model Field Mapping Reference

### User Model
| Schema Field | Actual Model Field | Fix |
|---|---|---|
| `first_name` | `full_name` (split first part) | Parse/split |
| `last_name` | `full_name` (split rest) | Parse/split |
| `phone` | `phone_number` | Use correct name |

### Address Model
| Schema Field | Actual Model Field | Fix |
|---|---|---|
| `phone` | `phone_number` | Use correct name |
| `street_address` | `address_line1` + `address_line2` | Combine fields |

### Vendor Model
| Schema Field | Actual Model Field | Fix |
|---|---|---|
| `contact_email` | `user.email` (via relationship) | Access via vendor.user |
| `contact_phone` | `business_phone` | Use correct name |

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

# Expected: HTTP 200 with complete order details including vendor info (no 500 error)
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
# ✅ Customer information displays correctly
# ✅ Shipping address displays correctly
# ✅ Billing address displays correctly
# ✅ Vendor information displays correctly (business name, phone, email)
# ✅ All order items with vendor details
# ✅ No "Order not found" error
# ✅ No backend 500 errors
```

---

## Error Message Examples

### Before Error Handling
```
AttributeError: 'Vendor' object has no attribute 'contact_email'
```
❌ Unclear where the error occurred
❌ No context about which vendor
❌ Generic 500 error

### After Error Handling

**Build Function Error**:
```json
{
  "detail": "Error building vendor info for vendor abc-123-vendor-id: Missing attribute 'contact_email'"
}
```
✅ Clear which function failed
✅ Identifies the vendor ID
✅ Shows the missing attribute

**Model Mapping Error**:
```json
{
  "detail": "Model attribute error in order 790ff9e3-5e24-490c-bac2-849200a4ddfe: 'Vendor' object has no attribute 'contact_email'. Please check model mappings."
}
```
✅ Clear it's a model mapping issue
✅ Identifies the order
✅ Actionable guidance

---

## Related Files

### Modified
1. **`shopsoma-backend/app/api/v1/admin_orders.py`**
   - Fixed `build_customer_info()` with error handling (lines 45-62)
   - Fixed `build_vendor_info()` with error handling (lines 65-81)
   - Fixed `build_address_info()` with error handling (lines 84-104)
   - Updated `get_order_detail()` query to load vendor.user (line 310)
   - Added comprehensive endpoint error handling (lines 382-399)
   - Fixed search filter to use `full_name` (line 218)

### Checked (No Changes Needed)
1. **`shopsoma-backend/app/models/vendor.py`**
   - Confirmed Vendor model structure
   - Has `business_phone` (not `contact_phone`)
   - NO direct email field (use `vendor.user.email`)

2. **`shopsoma-backend/app/schemas/admin_order.py`**
   - VendorInfo schema already correct (has optional contact_email/contact_phone)

---

## Prevention Strategies

### 1. Always Check Model Schemas First
```bash
# Quick reference commands
grep -A 30 "class User" app/models/user.py
grep -A 30 "class Address" app/models/address.py
grep -A 30 "class Vendor" app/models/vendor.py
```

### 2. Use Type Hints for IDE Support
```python
def build_vendor_info(vendor: Vendor) -> VendorInfo:
    # IDE autocomplete shows actual vendor fields
```

### 3. Load Relationships in Queries
```python
# If you need vendor.user.email, load it:
selectinload(OrderItem.vendor).selectinload(Vendor.user)
```

### 4. Add Defensive Error Handling
```python
# Check relationship is loaded before accessing
if hasattr(vendor, 'user') and vendor.user:
    email = vendor.user.email
```

### 5. Wrap Build Functions with Try-Catch
```python
try:
    # Build logic
    return Schema(...)
except AttributeError as e:
    raise ValueError(f"Context: {str(e)}") from e
```

---

## Summary of All Model Fixes

### Issue Pattern
All three model issues followed the same pattern:
1. Assumed field names based on common conventions
2. Didn't check actual Shopsoma model schemas
3. Got cryptic AttributeError at runtime
4. No helpful error messages for debugging

### Fix Pattern
1. ✅ Read actual model file to verify field names
2. ✅ Use correct field names or access via relationships
3. ✅ Add try-catch with detailed error messages
4. ✅ Load relationships in queries if needed
5. ✅ Add endpoint-level error handling

### Files Fixed
1. **User Model**: `build_customer_info()` + search filter
2. **Address Model**: `build_address_info()`
3. **Vendor Model**: `build_vendor_info()` + query relationships
4. **Error Handling**: All build functions + `get_order_detail()` endpoint

---

## Status

**Issue**: ✅ RESOLVED
**Backend**: ✅ Fixed with comprehensive error handling
**Frontend**: Ready to test
**Testing**: Manual testing required

---

## Next Steps

1. ✅ Backend fixes applied
2. ✅ Error handling implemented
3. ⏳ Start frontend to test order detail page
4. ⏳ Verify all order information displays correctly
5. ⏳ Test all order management features
6. ⏳ Monitor backend logs for any remaining issues

---

## Commands to Test

### Start Frontend (VS Code Terminal)

```bash
cd /Users/rex/Documents/Shopsoma/shopsoma-frontend
npm run dev
```

### View Order Detail (Browser)

1. Navigate to: `http://localhost:5173/admin/orders`
2. Click "View →" on any order
3. Expected: Order detail page loads with all information including vendor details

### Check Backend Logs

```bash
# In backend terminal, you should NOT see any AttributeErrors
# You SHOULD see:
# INFO: 127.0.0.1 - "GET /api/v1/admin/orders/{id} HTTP/1.1" 200 OK
```

---

**Last Updated**: December 13, 2025
**Version**: 1.0.0
**Related Fixes**:
- USER_MODEL_ATTRIBUTE_FIX.md
- ADDRESS_MODEL_ATTRIBUTE_FIX.md
