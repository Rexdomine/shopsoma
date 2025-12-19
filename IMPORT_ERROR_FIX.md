# ImportError Fix: require_admin Dependency

## Problem Statement

**Error**: `ImportError: cannot import name 'require_admin' from 'app.api.dependencies'`

**Root Cause**: The new settings API endpoint (`app/api/v1/settings.py`) was importing `require_admin` from `app.api.dependencies`, but this function didn't exist. The codebase already had `get_current_admin` function that performs the exact same role.

## Solution

Added `require_admin` as an alias to the existing `get_current_admin` function in the dependencies module for naming consistency and clarity.

### Changes Made

**File**: `shopsoma-backend/app/api/dependencies.py`

**Line 136-137**: Added alias after `get_current_admin` function
```python
# Alias for consistency with naming conventions
require_admin = get_current_admin
```

This creates a reference to the existing `get_current_admin` function under the name `require_admin`, allowing both names to be used interchangeably.

## Why This Approach?

### Option 1: Create New Function (NOT CHOSEN)
```python
async def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require admin role"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user
```
**Pros**: Explicit, separate function
**Cons**: Code duplication, maintenance overhead

### Option 2: Use Alias (CHOSEN) ✅
```python
require_admin = get_current_admin
```
**Pros**:
- No code duplication
- Single source of truth
- Easy to maintain
- Pythonic approach
- Both naming conventions supported

**Cons**: None significant

### Option 3: Update Settings API to Use get_current_admin (NOT CHOSEN)
```python
# In settings.py
from app.api.dependencies import get_current_user, get_current_admin

# Then use get_current_admin instead of require_admin
```
**Pros**: Uses existing function directly
**Cons**: Inconsistent naming (some endpoints use `require_X`, others use `get_current_X`)

## How It Works

### Function Signature
```python
async def get_current_admin(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Require admin role"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user
```

### Usage in Settings API
```python
from app.api.dependencies import require_admin

@router.patch("/admin/exchange-rate")
async def update_exchange_rate(
    update_data: ExchangeRateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin)  # ← Using the alias
):
    # Only admins can reach this code
    ...
```

### Authentication Flow
1. Request hits endpoint with `Authorization: Bearer <token>`
2. FastAPI's dependency system calls `require_admin`
3. `require_admin` (aliased to `get_current_admin`) depends on `get_current_active_user`
4. `get_current_active_user` depends on `get_current_user`
5. `get_current_user` decodes JWT token and fetches user from database
6. `get_current_active_user` checks if user is active
7. `get_current_admin` checks if user role is ADMIN
8. If all checks pass, user object is injected into endpoint function
9. If any check fails, appropriate HTTP exception is raised

### Error Responses

**Unauthenticated (No Token)**:
```json
{
  "detail": "Not authenticated"
}
```
Status: `401 Unauthorized`

**Invalid Token**:
```json
{
  "detail": "Could not validate credentials"
}
```
Status: `401 Unauthorized`

**Inactive User**:
```json
{
  "detail": "Inactive user account"
}
```
Status: `403 Forbidden`

**Non-Admin User**:
```json
{
  "detail": "Admin access required"
}
```
Status: `403 Forbidden`

## Testing

### Manual Test

1. **Start the server**:
```bash
cd shopsoma-backend
source venv/bin/activate
uvicorn app.main:app --reload
```

2. **Verify server starts without errors**:
- No ImportError should appear
- Server should print "🚀 Shopsoma API starting..."
- API docs should be accessible at http://localhost:8000/api/docs

3. **Test admin endpoint (unauthenticated)**:
```bash
curl -X GET http://localhost:8000/api/v1/settings/admin
```
Expected: `401 Unauthorized` with "Not authenticated" message

4. **Test admin endpoint (with customer token)**:
```bash
# Login as customer first to get token
TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"customer@example.com","password":"password"}' \
  | jq -r '.access_token')

# Try to access admin endpoint
curl -X GET http://localhost:8000/api/v1/settings/admin \
  -H "Authorization: Bearer $TOKEN"
```
Expected: `403 Forbidden` with "Admin access required" message

5. **Test admin endpoint (with admin token)**:
```bash
# Login as admin
ADMIN_TOKEN=$(curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@shopsoma.com","password":"admin_password"}' \
  | jq -r '.access_token')

# Access admin endpoint
curl -X GET http://localhost:8000/api/v1/settings/admin \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```
Expected: `200 OK` with settings array

### Automated Test

Run the provided test script:
```bash
cd shopsoma-backend
source venv/bin/activate
python test_import_fix.py
```

Expected output:
```
============================================================
Testing Import Fix for require_admin Dependency
============================================================

Running: require_admin import
✓ Successfully imported require_admin from app.api.dependencies
✓ require_admin is correctly aliased to get_current_admin

Running: settings API import
✓ Successfully imported settings API module

Running: main app import
✓ Successfully imported main FastAPI app
✓ App title: Shopsoma API

============================================================
✓ All tests passed! Server should start successfully.
```

## Verification Checklist

- [x] `require_admin` can be imported from `app.api.dependencies`
- [x] `require_admin` is an alias of `get_current_admin`
- [x] Settings API module can be imported without errors
- [x] Main FastAPI app can be imported without errors
- [x] Server starts without ImportError
- [x] Unauthenticated requests to admin endpoints return 401
- [x] Non-admin authenticated requests return 403
- [x] Admin requests successfully access endpoints

## Related Files

- [app/api/dependencies.py](shopsoma-backend/app/api/dependencies.py:124-137) - Fixed file
- [app/api/v1/settings.py](shopsoma-backend/app/api/v1/settings.py:16) - Uses require_admin
- [test_import_fix.py](shopsoma-backend/test_import_fix.py) - Test script

## Alternative Solutions for Future

If we wanted to standardize on one naming convention across the codebase:

**Option A**: Use `require_*` naming everywhere
```python
require_admin = get_current_admin
require_vendor = get_current_vendor
require_customer = get_current_customer
```

**Option B**: Use `get_current_*` naming everywhere
- Update all imports in settings.py and other files to use `get_current_admin`
- Remove the alias

**Current Approach**: Support both naming conventions for maximum flexibility.

## Lessons Learned

1. **Check existing patterns**: Always review existing code for similar functionality before creating new functions
2. **Naming consistency**: The codebase had both `get_current_X` and `require_X` patterns; aliasing supports both
3. **Import testing**: Always test imports after adding new dependencies
4. **Documentation**: Clear error messages help quickly identify and fix issues

## Implementation Date
December 12, 2025
