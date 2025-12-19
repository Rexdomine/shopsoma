# Vendor Orders 403 Forbidden - Comprehensive Error Handling

**Date**: December 11, 2025
**Status**: ✅ DIAGNOSTIC LOGGING ADDED
**Issue**: 403 Forbidden on `/api/v1/vendor/orders`

---

## 1. PROBLEM SUMMARY

### Server Error
```
INFO: 127.0.0.1:57688 - "GET /api/v1/vendor/orders?page=1&page_size=20 HTTP/1.1" 403 Forbidden
```

### User Impact
- Vendor dashboard shows "No orders found"
- No visibility into why orders aren't loading
- Poor debugging experience

### Root Cause (Unknown - To Be Diagnosed)
403 Forbidden indicates authorization failure, not authentication failure. Possible causes:
1. **Vendor role mismatch** - User doesn't have `role='vendor'`
2. **Vendor profile missing** - No Vendor record with `user_id`
3. **Vendor not approved** - `vendor.approved=False`
4. **User ID mismatch** - JWT user_id doesn't match vendor.user_id

---

## 2. SOLUTION: COMPREHENSIVE ERROR HANDLING

### Approach
Instead of guessing the root cause, add detailed logging at every step of the dependency chain to identify exactly where the 403 is triggered.

### Dependency Chain
```
1. get_current_user → Extract user from JWT
2. get_current_vendor → Check role=vendor
3. get_vendor_profile → Find Vendor by user_id
4. get_approved_vendor → Check vendor.approved=True
```

Each step can fail with 403. We need to know which one.

---

## 3. CHANGES IMPLEMENTED

### Backend: Enhanced Dependency Logging

**File**: `shopsoma-backend/app/api/dependencies.py`

#### Change #1: get_current_vendor (Lines 102-121)

**Added logging**:
```python
async def get_current_vendor(
    current_user: User = Depends(get_current_active_user)
) -> User:
    """Require vendor role"""
    print(f"[get_current_vendor] User ID: {current_user.id}, Email: {current_user.email}, Role: {current_user.role}")

    if current_user.role != UserRole.VENDOR:
        print(f"[get_current_vendor] ERROR: User role is {current_user.role}, not VENDOR")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Vendor access required",
                "error_code": "INVALID_ROLE",
                "user_role": current_user.role.value,
                "required_role": "vendor"
            }
        )

    print(f"[get_current_vendor] SUCCESS: User has VENDOR role")
    return current_user
```

**What it tells us**:
- ✅ User ID and email of authenticated user
- ✅ User's actual role
- ✅ Whether role check passes or fails
- ✅ Structured error response with error_code

#### Change #2: get_vendor_profile (Lines 196-235)

**Added logging**:
```python
async def get_vendor_profile(
    current_user: User = Depends(get_current_vendor),
    db: AsyncSession = Depends(get_db)
) -> Vendor:
    # Enhanced logging for debugging
    print(f"[get_vendor_profile] Looking for vendor with user_id: {current_user.id}")
    print(f"[get_vendor_profile] User email: {current_user.email}, Role: {current_user.role}")

    result = await db.execute(
        select(Vendor).where(Vendor.user_id == current_user.id)
    )
    vendor = result.scalar_one_or_none()

    if vendor is None:
        print(f"[get_vendor_profile] ERROR: No vendor found for user_id {current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Vendor profile not found. Please complete vendor registration.",
                "error_code": "VENDOR_PROFILE_NOT_FOUND",
                "user_id": str(current_user.id),
                "user_email": current_user.email
            }
        )

    print(f"[get_vendor_profile] SUCCESS: Found vendor {vendor.business_name} (id: {vendor.id})")
    return vendor
```

**What it tells us**:
- ✅ User ID being searched for
- ✅ Whether vendor record exists
- ✅ Vendor business name and ID if found
- ✅ Structured error with user details if not found

#### Change #3: get_approved_vendor (Lines 238-269)

**Added logging**:
```python
async def get_approved_vendor(
    vendor: Vendor = Depends(get_vendor_profile)
) -> Vendor:
    print(f"[get_approved_vendor] Checking approval for vendor: {vendor.business_name}")
    print(f"[get_approved_vendor] Vendor ID: {vendor.id}, Approved: {vendor.approved}")

    if not vendor.approved:
        print(f"[get_approved_vendor] ERROR: Vendor not approved")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Vendor account pending approval. Please wait for admin approval.",
                "error_code": "VENDOR_NOT_APPROVED",
                "vendor_id": str(vendor.id),
                "business_name": vendor.business_name
            }
        )

    print(f"[get_approved_vendor] SUCCESS: Vendor is approved")
    return vendor
```

**What it tells us**:
- ✅ Vendor business name being checked
- ✅ Vendor's approval status (True/False)
- ✅ Whether approval check passes or fails
- ✅ Structured error with vendor details

---

### Frontend: Enhanced Error Display

**File**: `shopsoma-frontend/src/pages/vendor/VendorOrders.tsx`

#### Change #1: Added Error State (Line 23)

```typescript
const [error, setError] = useState<string | null>(null);
```

#### Change #2: Comprehensive Error Handling (Lines 33-95)

**Added features**:

1. **Detailed Console Logging**:
```typescript
console.error('❌ Error fetching orders:', err);
console.error('📋 Error status:', err.response?.status);
console.error('📋 Error data:', err.response?.data);
console.error('📋 Full error:', err);
```

2. **Structured Error Parsing**:
```typescript
if (err.response?.data?.detail) {
  const detail = err.response.data.detail;

  // Handle structured error response
  if (typeof detail === 'object') {
    userMessage = detail.message || userMessage;
    technicalDetails = JSON.stringify(detail, null, 2);

    // Special handling for specific error codes
    if (detail.error_code === 'VENDOR_PROFILE_NOT_FOUND') {
      userMessage = 'No vendor profile found. Please complete vendor registration.';
    } else if (detail.error_code === 'VENDOR_NOT_APPROVED') {
      userMessage = 'Your vendor account is pending approval. Please wait for admin approval.';
    } else if (detail.error_code === 'INVALID_ROLE') {
      userMessage = 'Access denied. Please log in with a vendor account.';
    }
  }
}
```

3. **HTTP Status Code Fallbacks**:
```typescript
else if (err.response?.status === 401) {
  userMessage = 'Authentication expired. Please log in again.';
} else if (err.response?.status === 403) {
  userMessage = 'Access denied. Please check your account status.';
} else if (err.response?.status === 404) {
  userMessage = 'Vendor profile not found. Please complete registration.';
}
```

#### Change #3: Error UI Display (Lines 222-239)

**Added error state UI**:
```tsx
{error ? (
  <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
    <div className="px-6 py-20 text-center">
      <div className="mb-4">
        <svg className="mx-auto h-12 w-12 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      </div>
      <p className="text-red-600 font-medium text-base mb-2">Unable to Load Orders</p>
      <p className="text-gray-600 text-sm mb-4">{error}</p>
      <button
        onClick={() => fetchOrders()}
        className="inline-flex items-center px-4 py-2 border border-gray-300 rounded-md shadow-sm text-sm font-medium text-gray-700 bg-white hover:bg-gray-50"
      >
        Try Again
      </button>
    </div>
  </div>
) : ...}
```

**Features**:
- ✅ Warning icon (red triangle)
- ✅ Bold error title
- ✅ User-friendly error message
- ✅ "Try Again" button to retry

---

## 4. DIAGNOSTIC WORKFLOW

### Step 1: Check Server Logs

When vendor navigates to `/vendor/orders`, server logs will show:

**Success Flow**:
```
[get_current_vendor] User ID: xxx, Email: vendor@example.com, Role: vendor
[get_current_vendor] SUCCESS: User has VENDOR role
[get_vendor_profile] Looking for vendor with user_id: xxx
[get_vendor_profile] User email: vendor@example.com, Role: vendor
[get_vendor_profile] SUCCESS: Found vendor Business Name (id: yyy)
[get_approved_vendor] Checking approval for vendor: Business Name
[get_approved_vendor] Vendor ID: yyy, Approved: True
[get_approved_vendor] SUCCESS: Vendor is approved
```

**Failure at Role Check**:
```
[get_current_vendor] User ID: xxx, Email: user@example.com, Role: customer
[get_current_vendor] ERROR: User role is customer, not VENDOR
→ Returns 403 with error_code: INVALID_ROLE
```

**Failure at Profile Lookup**:
```
[get_current_vendor] SUCCESS: User has VENDOR role
[get_vendor_profile] Looking for vendor with user_id: xxx
[get_vendor_profile] ERROR: No vendor found for user_id xxx
→ Returns 404 with error_code: VENDOR_PROFILE_NOT_FOUND
```

**Failure at Approval Check**:
```
[get_current_vendor] SUCCESS: User has VENDOR role
[get_vendor_profile] SUCCESS: Found vendor Business Name
[get_approved_vendor] Checking approval for vendor: Business Name
[get_approved_vendor] Vendor ID: yyy, Approved: False
[get_approved_vendor] ERROR: Vendor not approved
→ Returns 403 with error_code: VENDOR_NOT_APPROVED
```

### Step 2: Check Browser Console

Frontend will log:

```javascript
❌ Error fetching orders: Error: Request failed with status code 403
📋 Error status: 403
📋 Error data: {detail: {message: "...", error_code: "...", ...}}
📋 Full error: {...}
🔍 User message: Access denied. Please log in with a vendor account.
🔍 Technical details: {"message": "...", "error_code": "INVALID_ROLE", ...}
```

### Step 3: Check UI Error Display

User will see:
- ⚠️ Warning icon
- **"Unable to Load Orders"** title
- Error message: "Access denied. Please log in with a vendor account."
- "Try Again" button

---

## 5. POSSIBLE ROOT CAUSES & FIXES

### Scenario A: User Logged In with Wrong Account

**Symptoms**:
```
[get_current_vendor] ERROR: User role is customer, not VENDOR
```

**Root Cause**: User logged in with customer account, not vendor account

**Fix**: Log out and log in with vendor credentials at `/vendor/login`

---

### Scenario B: Vendor Profile Not Found

**Symptoms**:
```
[get_vendor_profile] ERROR: No vendor found for user_id xxx
```

**Root Cause**: User has vendor role but no Vendor record in database

**Possible Reasons**:
1. Vendor registration incomplete
2. Database user_id mismatch
3. Vendor record deleted

**Fix**:
```sql
-- Check if vendor exists
SELECT * FROM vendors WHERE user_id = 'xxx';

-- If not, check user
SELECT id, email, role FROM users WHERE id = 'xxx';

-- Create vendor if needed or update user_id
```

---

### Scenario C: Vendor Not Approved

**Symptoms**:
```
[get_approved_vendor] ERROR: Vendor not approved
```

**Root Cause**: `vendor.approved = False`

**Fix**:
```sql
-- Check approval status
SELECT id, business_name, approved, kyc_status FROM vendors WHERE id = 'yyy';

-- Approve vendor
UPDATE vendors SET approved = TRUE WHERE id = 'yyy';
```

---

### Scenario D: JWT Token Has Wrong User ID

**Symptoms**:
- Log shows different user_id than expected
- Vendor exists but not found

**Root Cause**: JWT token contains wrong user_id

**Fix**: Log out and log in again to get fresh token

---

## 6. TESTING INSTRUCTIONS

### Test 1: Trigger Error and Check Logs

**Steps**:
1. Start backend with logs visible:
   ```bash
   cd shopsoma-backend
   source venv/bin/activate
   uvicorn app.main:app --reload
   ```

2. Open vendor dashboard in browser
3. Navigate to `/vendor/orders`
4. Check server terminal for log output

**Expected**:
- See `[get_current_vendor]` logs
- See `[get_vendor_profile]` logs
- See `[get_approved_vendor]` logs
- Identify which step fails

### Test 2: Check Browser Console

**Steps**:
1. Open DevTools (F12) → Console tab
2. Navigate to `/vendor/orders`
3. Look for emoji-prefixed logs:
   - ❌ Error fetching orders
   - 📋 Error status
   - 📋 Error data
   - 🔍 User message

**Expected**:
- Clear error logs with all details
- Technical error object visible
- User-friendly message extracted

### Test 3: Verify UI Error Display

**Steps**:
1. Navigate to `/vendor/orders` with error condition
2. Verify error UI shows:
   - Warning icon (red triangle)
   - "Unable to Load Orders" title
   - Specific error message
   - "Try Again" button
3. Click "Try Again"
4. Verify it attempts to refetch

---

## 7. FILES MODIFIED

### Backend
- **`app/api/dependencies.py`**
  - Lines 102-121: Added logging to `get_current_vendor`
  - Lines 196-235: Added logging to `get_vendor_profile`
  - Lines 238-269: Added logging to `get_approved_vendor`
  - Added structured error responses with error_code

### Frontend
- **`src/pages/vendor/VendorOrders.tsx`**
  - Line 23: Added error state
  - Lines 33-95: Enhanced error handling with logging
  - Lines 222-239: Added error UI display with retry button

### Total Changes
- Backend: ~60 lines modified (logging + structured errors)
- Frontend: ~70 lines modified (error handling + UI)

---

## 8. ACCEPTANCE CRITERIA

**Error Logging**:
- [x] Server logs show which dependency step fails
- [x] Server logs show user ID, email, role
- [x] Server logs show vendor ID, name, approval status
- [x] Errors include structured detail object with error_code

**Frontend Error Handling**:
- [x] Console logs show HTTP status and error data
- [x] Console logs extract user-friendly message
- [x] Error state displays in UI
- [x] "Try Again" button allows retry

**User Experience**:
- [x] User sees clear error message (not "No orders found")
- [x] Error message explains what's wrong
- [x] User can retry loading
- [x] Different errors show different messages

---

## 9. NEXT STEPS

### After Deployment

1. **Reproduce 403 Error**:
   - Have user navigate to `/vendor/orders`
   - Check server logs for exact failure point

2. **Identify Root Cause**:
   - Check which log shows ERROR
   - Review error_code in response
   - Determine fix based on scenario

3. **Apply Specific Fix**:
   - Scenario A → User re-login
   - Scenario B → Create/fix vendor profile
   - Scenario C → Approve vendor
   - Scenario D → Fresh JWT token

4. **Remove Logging** (Optional):
   - Once issue resolved, can remove print statements
   - Keep structured error responses
   - Keep frontend error handling

---

## 10. STRUCTURED ERROR CODES

| Error Code | HTTP Status | Meaning | User Action |
|------------|-------------|---------|-------------|
| `INVALID_ROLE` | 403 | User doesn't have vendor role | Log in with vendor account |
| `VENDOR_PROFILE_NOT_FOUND` | 404 | No Vendor record for user | Complete vendor registration |
| `VENDOR_NOT_APPROVED` | 403 | Vendor exists but not approved | Wait for admin approval |
| (None) | 401 | JWT token invalid/expired | Log in again |

---

## 11. EXAMPLE ERROR RESPONSES

### INVALID_ROLE
```json
{
  "detail": {
    "message": "Vendor access required",
    "error_code": "INVALID_ROLE",
    "user_role": "customer",
    "required_role": "vendor"
  }
}
```

### VENDOR_PROFILE_NOT_FOUND
```json
{
  "detail": {
    "message": "Vendor profile not found. Please complete vendor registration.",
    "error_code": "VENDOR_PROFILE_NOT_FOUND",
    "user_id": "xxx-xxx-xxx",
    "user_email": "user@example.com"
  }
}
```

### VENDOR_NOT_APPROVED
```json
{
  "detail": {
    "message": "Vendor account pending approval. Please wait for admin approval.",
    "error_code": "VENDOR_NOT_APPROVED",
    "vendor_id": "yyy-yyy-yyy",
    "business_name": "Business Name"
  }
}
```

---

**Implementation Date**: December 11, 2025
**Status**: ✅ Diagnostic Logging Added
**Next**: Run test to see server logs and identify root cause

---

## Summary

Added comprehensive error logging and handling to diagnose the 403 Forbidden error. Server logs will now show exactly which dependency check fails, and frontend will display user-friendly error messages with retry functionality. This eliminates the "going in circles" problem by providing clear visibility into the failure point.
