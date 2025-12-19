# Vendor Onboarding Implementation

## Overview

Complete implementation of the vendor onboarding flow with backend state management and frontend routing guards. Vendors must complete Brand Info and Payout Information sections before accessing other dashboard features.

## Backend Implementation

### 1. Database Schema Updates

**New Fields Added to `vendors` table:**
```sql
-- Onboarding State
is_onboarding BOOLEAN DEFAULT TRUE NOT NULL
brand_info_completed BOOLEAN DEFAULT FALSE NOT NULL
payout_info_completed BOOLEAN DEFAULT FALSE NOT NULL
onboarding_completed_at TIMESTAMP WITH TIME ZONE NULL
```

**Migration File:** `07fd66bddac5_add_vendor_onboarding_fields.py`

### 2. Updated Models

**File:** `app/models/vendor.py`

Added onboarding state fields to Vendor model:
- `is_onboarding`: Boolean flag indicating if vendor is in onboarding mode
- `brand_info_completed`: Tracks completion of brand information section
- `payout_info_completed`: Tracks completion of payout information section
- `onboarding_completed_at`: Timestamp when onboarding was completed

### 3. API Endpoints

#### a) Get Vendor Profile
```
GET /api/v1/vendor/profile
```
Returns vendor profile including onboarding state fields.

#### b) Save Brand Info
```
PUT /api/v1/vendor/onboarding/brand-info
```

**Request Body:**
```json
{
  "business_phone": "string",
  "email": "string (optional)",
  "business_description": "string (optional)",
  "shipping_country": "string (optional)",
  "shipping_address": "string",
  "returning_country": "string (optional)",
  "returning_address": "string (optional)",
  "open_days": ["MON", "TUE", ...],
  "open_hour": "09:00",
  "close_hour": "17:00"
}
```

**Behavior:**
- Saves brand information to vendor profile
- Sets `brand_info_completed = true`
- If both brand and payout info are complete, sets `is_onboarding = false` and records completion timestamp

#### c) Save Payout Info
```
PUT /api/v1/vendor/onboarding/payout-info
```

**Request Body:**
```json
{
  "tin": "string (optional)",
  "account_type": "Checking",
  "bank_name": "string",
  "account_number": "string",
  "account_holder": "string"
}
```

**Behavior:**
- Saves payout information to vendor profile
- Sets `payout_info_completed = true`
- If both brand and payout info are complete, sets `is_onboarding = false` and records completion timestamp

### 4. OTP Verification Updates

**File:** `app/api/v1/vendor_activation.py`

When a vendor verifies their OTP and activates their account:
- Sets initial onboarding state: `is_onboarding = true`
- Ensures completion flags are false: `brand_info_completed = false`, `payout_info_completed = false`
- Redirects to `/vendor/settings/brand-info` (handled by frontend)

## Frontend Implementation

### 1. Service Layer

**File:** `src/services/vendorService.ts`

New service methods:
- `getProfile()`: Fetch vendor profile with onboarding state
- `saveBrandInfo(data)`: Save brand information
- `savePayoutInfo(data)`: Save payout information

### 2. Context Provider

**File:** `src/context/VendorContext.tsx`

Provides vendor profile state across the application:
```typescript
interface VendorContextType {
  vendorProfile: VendorProfile | null;
  isOnboarding: boolean;
  brandInfoCompleted: boolean;
  payoutInfoCompleted: boolean;
  refreshProfile: () => Promise<void>;
  updateProfile: (profile: VendorProfile) => void;
  isLoading: boolean;
}
```

### 3. Onboarding Guard

**File:** `src/components/vendor/VendorOnboardingGuard.tsx`

Enforces onboarding flow:
- Fetches vendor profile on component mount
- If `is_onboarding = true`:
  - Blocks access to all vendor routes except settings pages
  - Redirects unauthorized routes to appropriate settings page
  - If neither section complete: redirects to brand-info
  - If brand info complete but not payout: redirects to payout-info
- Handles `/vendor/settings` route by redirecting to `/vendor/settings/brand-info`

### 4. Route Configuration

**Updated Routes:**
```typescript
VENDOR_SETTINGS: '/vendor/settings'
VENDOR_BRAND_INFO: '/vendor/settings/brand-info'
VENDOR_PAYOUT_INFO: '/vendor/settings/payout-information'
VENDOR_SECURITY: '/vendor/settings/security'
```

### 5. Integration with BrandInfoSettings

**File:** `src/pages/vendor/BrandInfoSettings.tsx`

The existing BrandInfoSettings component should:
1. Wrap in `VendorProvider` (in parent layout)
2. Use `useVendor()` hook to access onboarding state
3. Call `vendorService.saveBrandInfo()` when form is submitted
4. Update local and context state after successful save
5. Navigate to payout info page if brand info is newly completed

Example integration:
```typescript
const { vendorProfile, updateProfile } = useVendor();

const handleSave = async (formData) => {
  const updated = await vendorService.saveBrandInfo(formData);
  updateProfile(updated);

  if (updated.brand_info_completed && !updated.payout_info_completed) {
    navigate(ROUTES.VENDOR_PAYOUT_INFO);
  }
};
```

## Usage in Vendor Sidebar

**File:** `src/components/vendor/VendorSidebar.tsx`

The sidebar should:
1. Import and use `useVendor()` hook
2. Disable/grey out menu items based on `isOnboarding` state:

```typescript
const { isOnboarding } = useVendor();

const mainMenuItems = [
  { label: 'Orders', disabled: isOnboarding },
  { label: 'Products', disabled: isOnboarding },
  { label: 'Collections', disabled: isOnboarding },
  // ... etc
];
```

Apply styling for disabled items:
```typescript
className={`menu-item ${item.disabled ? 'opacity-50 cursor-not-allowed pointer-events-none' : ''}`}
```

## Complete Flow

### 1. New Vendor Activation
```
1. Admin approves vendor
2. Vendor clicks activation link
3. Lands on OTP page
4. Enters OTP code
5. Account activated with:
   - is_onboarding = true
   - brand_info_completed = false
   - payout_info_completed = false
6. Redirected to /vendor/settings/brand-info
```

### 2. Onboarding Process
```
1. Vendor fills Brand Info form
2. Clicks Save
3. Backend sets brand_info_completed = true
4. Frontend navigates to /vendor/settings/payout-information
5. Vendor fills Payout Info form
6. Clicks Save
7. Backend sets:
   - payout_info_completed = true
   - is_onboarding = false
   - onboarding_completed_at = now()
8. All sidebar menu items become enabled
9. Vendor can access full dashboard
```

### 3. Route Protection During Onboarding
```
- Vendor tries to access /vendor/orders
- OnboardingGuard detects is_onboarding = true
- Checks completion status
- Redirects to appropriate settings page:
  - If neither complete → /vendor/settings/brand-info
  - If brand complete, payout incomplete → /vendor/settings/payout-information
```

### 4. Base Settings Route Handling
```
- Any access to /vendor/settings (with or without onboarding)
- Automatically redirects to /vendor/settings/brand-info
- No 404 or blank page
```

## Testing Guide

### Manual Testing Checklist

**Prerequisites:**
- Backend running on http://localhost:8000
- Frontend running on http://localhost:5174
- Vendor account: vendor@shopsoma.com / vendor123

**Test Scenario 1: Initial Onboarding State**
1. Login at http://localhost:5174/vendor/login
2. ✅ Should redirect to /vendor/settings/brand-info
3. ✅ Sidebar menu items (Orders, Products, etc.) should be greyed out
4. ✅ Only Settings should be accessible

**Test Scenario 2: Complete Brand Info**
1. Fill out all required fields in Brand Info form:
   - Phone number
   - Shipping address
   - At least one open day
   - Open and close hours
2. Click "Save Changes"
3. ✅ Should show success message
4. ✅ Should auto-navigate to Payout Information page

**Test Scenario 3: Complete Payout Info**
1. Fill out payout information:
   - Account type
   - Bank name
   - Account number
   - Account holder name
2. Click "Save Payout Info"
3. ✅ Should show success message
4. ✅ Sidebar menu items should become enabled
5. ✅ Can now access Orders, Products, etc.

**Test Scenario 4: Route Protection**
1. During onboarding, try to access /vendor/orders directly
2. ✅ Should redirect back to brand-info or payout-info
3. After onboarding complete, try accessing /vendor/orders
4. ✅ Should allow access

### API Tests
```bash
# Test brand info save
curl -X PUT http://localhost:8000/api/v1/vendor/onboarding/brand-info \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "business_phone": "+234...",
    "shipping_address": "123 Main St",
    "open_days": ["MON", "TUE", "WED"],
    "open_hour": "09:00",
    "close_hour": "17:00"
  }'

# Test payout info save
curl -X PUT http://localhost:8000/api/v1/vendor/onboarding/payout-info \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "account_type": "Checking",
    "bank_name": "First Bank",
    "account_number": "1234567890",
    "account_holder": "John Doe"
  }'

# Verify profile
curl -X GET http://localhost:8000/api/v1/vendor/profile \
  -H "Authorization: Bearer <token>"
```

### Reset Onboarding State for Testing

To reset a vendor back to onboarding state:

```bash
# Via Docker
docker exec shopsoma-db psql -U shopsoma -d shopsoma_db -c \
  "UPDATE vendors SET is_onboarding = true, brand_info_completed = false,
   payout_info_completed = false, onboarding_completed_at = NULL
   WHERE business_name = 'Shopsoma Fashion Store';"
```

### Verification Commands

```bash
# Check current onboarding status
curl -X GET http://localhost:8000/api/v1/vendor/profile \
  -H "Authorization: Bearer <token>"

# Look for these fields in response:
# - is_onboarding: true/false
# - brand_info_completed: true/false
# - payout_info_completed: true/false
# - onboarding_completed_at: timestamp or null
```

## Files Created/Modified

### Backend
- `app/models/vendor.py` - Added onboarding fields
- `app/schemas/vendor.py` - Added VendorBrandInfoUpdate and VendorPayoutInfoUpdate schemas
- `app/api/v1/vendors.py` - Added brand-info and payout-info endpoints
- `app/api/v1/vendor_activation.py` - Updated OTP verification to set onboarding state
- `alembic/versions/07fd66bddac5_add_vendor_onboarding_fields.py` - Migration

### Frontend
- `src/services/vendorService.ts` - Vendor service methods (Created)
- `src/context/VendorContext.tsx` - Vendor context provider (Created)
- `src/components/vendor/VendorOnboardingGuard.tsx` - Route guard component (Created, Updated to use context)
- `src/components/vendor/VendorLayout.tsx` - Layout wrapper for vendor routes (Created)
- `src/config/constants.ts` - Added settings route constants (Modified)
- `src/pages/vendor/BrandInfoSettings.tsx` - Integrated with vendor service (Modified)
- `src/components/vendor/VendorSidebar.tsx` - Integrated with useVendor hook (Modified)
- `src/router/index.tsx` - Wrapped vendor routes with VendorLayout (Modified)

## Implementation Status

### ✅ COMPLETED

All implementation tasks have been completed successfully:

1. **✅ BrandInfoSettings Integration**
   - Integrated with vendorService for form submission
   - Calls `vendorService.saveBrandInfo()` on form submit
   - Calls `vendorService.savePayoutInfo()` for payout form
   - Navigates to payout info after brand info save
   - Shows completion message when onboarding finishes

2. **✅ VendorSidebar Updates**
   - Added `useVendor()` hook integration
   - Disables all main menu items during onboarding
   - Applied styling: `opacity-60 pointer-events-none` for disabled state
   - Settings menu remains accessible during onboarding

3. **✅ VendorProvider Integration**
   - Created `VendorLayout.tsx` wrapper component
   - Wraps all vendor routes with VendorProvider
   - VendorOnboardingGuard applied to enforce flow
   - Updated to use VendorContext instead of duplicate fetching

4. **✅ Backend API Testing**
   - Tested brand info save endpoint: ✅ Working
   - Tested payout info save endpoint: ✅ Working
   - Verified onboarding state transitions: ✅ Correct
   - Confirmed automatic completion when both sections done: ✅ Working

5. **✅ Frontend Build**
   - No TypeScript errors
   - Development server running successfully
   - All components compile correctly

## Security Considerations

- Onboarding state is server-side (cannot be bypassed)
- All endpoints require authentication
- Profile updates are validated on backend
- Route guards are client-side convenience (real protection is API-level)

## Backwards Compatibility

- Existing vendors without onboarding fields will have default values:
  - `is_onboarding = true` (migration default)
  - `brand_info_completed = false`
  - `payout_info_completed = false`
- They will need to complete onboarding or admin can manually set flags
- No breaking changes to existing endpoints
