# Admin Exchange Rate Settings Implementation

## Overview
Implemented a complete system for administrators to manage currency exchange rates dynamically through an admin settings page. This allows admins to adjust the USD to NGN conversion rate as market prices fluctuate, without requiring code changes or deployments.

## Features Implemented

### Backend
1. **Settings Database Model** - Flexible key-value storage for application settings
2. **Settings API Endpoints** - RESTful API for reading and updating settings
3. **Admin-Only Access Control** - Exchange rate updates restricted to admin users
4. **Input Validation** - Ensures exchange rates are within reasonable bounds (100-10,000 NGN per USD)

### Frontend
1. **Admin Settings Page** - Beautiful UI for managing exchange rates
2. **Real-time Updates** - Changes take effect immediately across the platform
3. **Currency Store Integration** - Fetches rate from API on app initialization
4. **Form Validation** - Client-side validation before submission
5. **Toast Notifications** - Success/error feedback for admin actions

## Architecture

### Database Schema

**Table**: `settings`
```sql
CREATE TABLE settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(255) NOT NULL UNIQUE,
    value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Initial seed data
INSERT INTO settings (key, value, description)
VALUES ('exchange_rate_usd_to_ngn', '833', 'Exchange rate from USD to NGN (1 USD = X NGN)');
```

### API Endpoints

#### 1. Get Exchange Rate (Public)
```
GET /api/v1/settings/public/exchange-rate
```
**Response:**
```json
{
  "rate": 833.0,
  "updated_at": "2025-12-12T14:30:00Z"
}
```
**Notes:**
- No authentication required
- Used by frontend on app initialization
- Cached in Zustand store

#### 2. Get All Settings (Admin Only)
```
GET /api/v1/settings/admin
Authorization: Bearer <admin_token>
```
**Response:**
```json
[
  {
    "id": "uuid",
    "key": "exchange_rate_usd_to_ngn",
    "value": "833",
    "description": "Exchange rate from USD to NGN (1 USD = X NGN)",
    "created_at": "2025-12-12T14:30:00Z",
    "updated_at": "2025-12-12T14:30:00Z"
  }
]
```

#### 3. Update Exchange Rate (Admin Only)
```
PATCH /api/v1/settings/admin/exchange-rate
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "rate": 850.5
}
```
**Response:**
```json
{
  "rate": 850.5,
  "updated_at": "2025-12-12T15:00:00Z"
}
```
**Validation:**
- `rate` must be > 0
- `rate` must be between 100 and 10,000
- Only admins can update

#### 4. Update Any Setting (Admin Only)
```
PATCH /api/v1/settings/admin/{key}
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "value": "new_value"
}
```

## Files Created

### Backend
1. `shopsoma-backend/app/models/setting.py` - Settings database model
2. `shopsoma-backend/app/schemas/setting.py` - Pydantic schemas for validation
3. `shopsoma-backend/app/api/v1/settings.py` - API endpoints
4. `shopsoma-backend/alembic/versions/h4i5j6k7l8m9_create_settings_table.py` - Migration

### Frontend
1. `shopsoma-frontend/src/pages/admin/AdminSettings.tsx` - Admin settings UI
2. `shopsoma-frontend/src/services/settingsService.ts` - Settings API service

## Files Modified

### Backend
1. `shopsoma-backend/app/models/__init__.py` - Added Setting model export
2. `shopsoma-backend/app/main.py` - Registered settings router

### Frontend
1. `shopsoma-frontend/src/store/currencyStore.ts` - Added `fetchExchangeRate()` function
2. `shopsoma-frontend/src/hooks/useCurrency.ts` - Exposed fetch function and loading state
3. `shopsoma-frontend/src/router/index.tsx` - Added admin settings route
4. `shopsoma-frontend/src/components/admin/AdminSidebar.tsx` - Updated to support `activePrimary` prop
5. `shopsoma-frontend/src/App.tsx` - Fetch exchange rate on app initialization

## User Flow

### Admin Updates Exchange Rate

1. Admin navigates to Settings from admin sidebar
2. Current exchange rate is displayed in a read-only card
3. Admin enters new rate in the input field (e.g., 850)
4. Client-side validation ensures rate is valid
5. Admin clicks "Save Changes"
6. Backend validates and updates the rate
7. Success toast notification appears
8. Current rate card updates immediately
9. Currency store refreshes with new rate
10. All price displays across the platform use the new rate

### Frontend Initialization

1. User opens the Shopsoma app
2. `App.tsx` calls `fetchExchangeRate()` on mount
3. Public API endpoint returns current rate
4. Currency store updates with fresh rate
5. All components using `useCurrency()` hook automatically use the updated rate

## How to Run & Test

### 1. Apply Database Migration
```bash
cd shopsoma-backend
alembic upgrade head
```

### 2. Verify Migration
```bash
# Check that settings table exists and has initial data
psql -U shopsoma -d shopsoma_db -c "SELECT * FROM settings;"
```

### 3. Start Backend
```bash
cd shopsoma-backend
uvicorn app.main:app --reload
```

### 4. Start Frontend
```bash
cd shopsoma-frontend
npm run dev
```

### 5. Test Exchange Rate Fetch (No Auth)
```bash
curl http://localhost:8000/api/v1/settings/public/exchange-rate
```

### 6. Test Admin Settings Page
1. Log in as admin user
2. Navigate to `/admin/settings`
3. View current exchange rate
4. Update rate to a new value (e.g., 850)
5. Save changes
6. Verify success notification
7. Check that displayed rate updated

### 7. Verify Frontend Uses New Rate
1. Navigate to any product page
2. Toggle currency switcher between NGN and USD
3. Verify prices convert correctly using new rate
4. Check vendor order detail page
5. Verify all prices update with new rate

## Validation Rules

### Exchange Rate Constraints
- **Minimum**: 100 NGN per USD
- **Maximum**: 10,000 NGN per USD
- **Type**: Positive decimal number
- **Backend Validation**: Pydantic field validator
- **Frontend Validation**: HTML5 input constraints + custom validation

### Error Handling
- Invalid rate (≤ 0): "Please enter a valid exchange rate greater than 0"
- Out of range: "Exchange rate must be between 100 and 10,000 NGN per USD"
- Network error: "Failed to update exchange rate"
- Empty input: "Value cannot be empty or only whitespace"

## Security Considerations

1. **Admin-Only Access**: Only users with `role='admin'` can update settings
2. **Input Validation**: Both client and server-side validation
3. **Rate Limiting**: Protected by existing middleware
4. **Audit Trail**: `updated_at` timestamp tracks all changes
5. **SQL Injection Protection**: Using SQLAlchemy ORM with parameterized queries

## Future Enhancements

1. **Audit Log**: Track who changed the rate and when
2. **Rate History**: Store historical rates for reporting
3. **Automatic Updates**: Fetch rates from external API (e.g., Central Bank of Nigeria)
4. **Multi-Currency Support**: Add EUR, GBP, etc.
5. **Rate Alerts**: Notify admins when rate changes significantly
6. **Scheduled Updates**: Auto-update rates on a schedule
7. **Rate Override**: Allow vendors to set custom rates for their products

## Testing Checklist

- [x] Database migration creates settings table
- [x] Seed data inserts default exchange rate
- [x] Public endpoint returns exchange rate without auth
- [x] Admin endpoints require authentication
- [x] Non-admin users cannot update exchange rate
- [x] Validation rejects rates < 100
- [x] Validation rejects rates > 10,000
- [x] Validation rejects negative rates
- [x] Validation rejects non-numeric values
- [x] Frontend fetches rate on app initialization
- [x] Currency store caches rate correctly
- [x] Admin settings page displays correctly
- [x] Save button is disabled when no changes
- [x] Reset button restores original value
- [x] Success toast appears on successful update
- [x] Error toast appears on failed update
- [x] Currency conversions use updated rate
- [x] Vendor order detail page uses updated rate
- [x] Settings link in admin sidebar highlights correctly

## Implementation Date
December 12, 2025

## Related Documentation
- [Currency Switcher Implementation](./CURRENCY_SWITCHER_IMPLEMENTATION.md)
- [Vendor Dashboard Backend Setup](./shopsoma-backend/VENDOR_DASHBOARD_BACKEND_SETUP.md)
