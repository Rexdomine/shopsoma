# ShipBubble Address Attribute Fix

## Problem
ShipBubble integration was failing with error:
```
[Shipping] ShipBubble error: 'Address' object has no attribute 'street_address', falling back to local rates
```

## Root Cause
The code in `app/api/v1/shipping_rates.py` was trying to access `address.street_address`, but the Address model actually uses:
- `address_line1` (required)
- `address_line2` (optional)

## Solution
Fixed the `_get_shipbubble_rates()` function in `app/api/v1/shipping_rates.py` to use correct Address model attributes.

## Changes Made

### File: `app/api/v1/shipping_rates.py`

**Lines 265-299**: Updated address field mapping

**Before**:
```python
address=vendor_address.street_address if vendor_address else "123 Store St"
address=address.street_address if address else "456 Customer Ave"
```

**After**:
```python
# Properly combine address_line1 and address_line2
sender_address_str = (
    f"{vendor_address.address_line1}, {vendor_address.address_line2 or ''}"
    if vendor_address
    else "123 Store St"
).strip().rstrip(',')

receiver_address_str = (
    f"{address.address_line1}, {address.address_line2 or ''}"
    if address
    else "456 Customer Ave"
).strip().rstrip(',')
```

**Additional improvements**:
- Uses `address.full_name` for receiver name (instead of hardcoded "Customer")
- Uses `address.phone_number` for receiver phone (instead of default)
- Properly handles optional `address_line2` field
- Strips trailing commas when address_line2 is empty

## Address Model Schema

```python
class Address(Base):
    __tablename__ = "addresses"

    # Address fields
    full_name = Column(String(255), nullable=False)
    phone_number = Column(String(20), nullable=False)
    address_line1 = Column(String(255), nullable=False)  # ← Primary address
    address_line2 = Column(String(255), nullable=True)   # ← Optional (apt, suite, etc)
    city = Column(String(100), nullable=False)
    state = Column(String(100), nullable=False)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), default="Nigeria", nullable=False)
```

## Testing

### 1. Module Import Test
```bash
cd shopsoma-backend
source venv/bin/activate
python3 -c "from app.api.v1.shipping_rates import _get_shipbubble_rates; print('✓ OK')"
```
**Result**: ✅ Imports successfully

### 2. API Key Test
```bash
./test_shipbubble_api_key.sh
```

This script tests:
- ✅ API key exists in .env
- ✅ Can create address in ShipBubble
- ✅ ShipBubble API is reachable

### 3. End-to-End Test
1. Enable ShipBubble in Admin Settings
2. Go to checkout as customer
3. Add address with both address_line1 and address_line2
4. Verify shipping rates appear without errors

## Expected Behavior

**Before fix**:
- ❌ AttributeError: 'Address' object has no attribute 'street_address'
- Falls back to local rates
- Error logged in backend

**After fix**:
- ✅ Address fields correctly mapped
- ShipBubble API called with proper address format
- Real courier rates returned (if API key is active)
- Fallback to local rates only if API fails (not attribute error)

## Address Format Examples

### Example 1: Full address with both lines
```python
address_line1 = "123 Main Street"
address_line2 = "Apt 4B"
# Result: "123 Main Street, Apt 4B"
```

### Example 2: Address with only line1
```python
address_line1 = "456 Market Road"
address_line2 = None
# Result: "456 Market Road"  (no trailing comma)
```

### Example 3: No address (fallback)
```python
address = None
# Result: "456 Customer Ave"  (default fallback)
```

## Related Files

- ✅ `app/models/address.py` - Address model definition
- ✅ `app/api/v1/shipping_rates.py` - ShipBubble integration (FIXED)
- ✅ `app/services/shipbubble_service.py` - ShipBubble API client
- ✅ `test_shipbubble_api_key.sh` - API key test script (NEW)

## Status: ✅ FIXED

The address attribute error has been resolved. ShipBubble integration now properly uses the correct Address model fields.

## Next Steps

1. **Test API Key**: Run `./test_shipbubble_api_key.sh` to verify your API key works
2. **Activate API Key** (if test fails):
   - Login to https://shipbubble.com
   - Go to Settings → API Keys
   - Enable API access
   - Update `.env` with new key
3. **Enable in Admin**: Toggle ShipBubble in Admin Settings
4. **Test Checkout**: Verify real shipping rates appear

---

**Fixed Date**: December 17, 2025
**Issue**: AttributeError on address.street_address
**Solution**: Use address_line1 and address_line2 correctly
**Files Changed**: 1 file (app/api/v1/shipping_rates.py)
**Lines Modified**: ~35 lines
