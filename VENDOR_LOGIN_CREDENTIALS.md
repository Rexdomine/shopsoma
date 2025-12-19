# Vendor Login Credentials

## Test Account: Shopsoma Fashion Store

### Login Details
- **URL**: http://localhost:5173/vendor/login
- **Email**: `vendor@shopsoma.com`
- **Password**: `vendor123`

### Account Information
- **Business Name**: Shopsoma Fashion Store
- **Full Name**: Shopsoma Fashion Store
- **Phone**: +2348012345678
- **Role**: vendor
- **KYC Status**: approved
- **Account Status**: approved & active
- **Commission Rate**: 12.5%

### After Login Redirect
When you login with the vendor account, you will be automatically redirected to:
- **Dashboard**: `/vendor/dashboard` ✅ (Route is now configured and working!)

The dashboard displays:
- Business information (name, description, KYC status)
- Account status and approval state
- Key metrics: Total products, orders, and revenue
- Placeholder for upcoming features

### API Endpoints Available
After logging in as a vendor, you have access to:

#### Profile & KYC
- `GET /api/v1/vendor/profile` - Get vendor profile
- `PUT /api/v1/vendor/profile` - Update vendor profile
- `POST /api/v1/vendor/kyc/submit` - Submit KYC documents

#### Assets Management
- `POST /api/v1/vendor/assets` - Upload assets (logo, banner, size charts)
- `GET /api/v1/vendor/assets` - List assets
- `GET /api/v1/vendor/assets/{id}` - Get specific asset
- `PUT /api/v1/vendor/assets/{id}` - Update asset
- `DELETE /api/v1/vendor/assets/{id}` - Delete asset

#### Orders Management
- `GET /api/v1/vendor/orders` - List vendor orders
- `GET /api/v1/vendor/orders/{id}` - Get specific order details

#### Pickups Management
- `GET /api/v1/vendor/pickups` - List vendor pickups
- `GET /api/v1/vendor/pickups/{id}` - Get specific pickup
- `PUT /api/v1/vendor/pickups/{id}` - Update pickup information

#### Notifications
- `GET /api/v1/vendor/notifications` - List notifications
- `GET /api/v1/vendor/notifications/unread-count` - Get unread count
- `POST /api/v1/vendor/notifications/mark-read` - Mark as read

#### Financials
- `GET /api/v1/vendor/payouts` - List payouts
- `GET /api/v1/vendor/payouts/summary` - Get payout summary

#### Dashboard
- `GET /api/v1/vendor/dashboard/metrics` - Get dashboard metrics

### Testing the Login

1. **Via Browser**:
   - Navigate to http://localhost:5173/vendor/login
   - Enter email: `vendor@shopsoma.com`
   - Enter password: `vendor123`
   - Click "Log in"

2. **Via API (curl)**:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "vendor@shopsoma.com",
       "password": "vendor123"
     }'
   ```

3. **Automated Test Script**:
   ```bash
   ./test_vendor_login.sh
   ```

### What's Been Set Up

✅ **Frontend**:
- Vendor login page at `/vendor/login`
- Vendor dashboard page at `/vendor/dashboard` (with ProtectedRoute for vendor-only access)
- Automatic redirect after login based on user role
- Beautiful UI matching the Shopsoma design system

✅ **Backend**:
- All vendor API endpoints are active and working
- Authentication uses the standard `/api/v1/auth/login` endpoint
- JWT tokens include the user's role for authorization
- Vendor-specific endpoints require authenticated vendor role

✅ **Database**:
- Test vendor account created and verified
- Password reset to `vendor123` for easy testing

### Notes
- The vendor login uses the same authentication endpoint as regular users (`/api/v1/auth/login`)
- The JWT token contains the user's role (`vendor`) which is used for authorization
- All vendor-specific API endpoints require the user to be authenticated and have the `vendor` role
- The dashboard is a placeholder - full product management, orders, and analytics features will be added in future updates
