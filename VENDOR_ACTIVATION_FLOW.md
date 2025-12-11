# Vendor OTP Activation Flow

## Overview

The vendor activation flow uses a secure OTP (One-Time Password) system to verify and activate vendor accounts after admin approval.

## Complete Flow

### 1. Vendor Signup & Approval (Existing)
1. Vendor registers at `/register` with role="vendor"
2. Admin reviews and approves the vendor account
3. Upon approval, vendor receives an activation email

### 2. Activation Email (To Be Implemented in Admin Panel)
When admin approves a vendor, send an email with an activation link:
```
Subject: Activate Your Shopsoma Vendor Account

Hi [Vendor Name],

Great news! Your vendor application has been approved.

Click the link below to activate your account and start selling:
https://shopsoma.com/vendor/otp?email=vendor@example.com

This link will send a verification code to your email.

Welcome to Shopsoma!
```

### 3. Activation Link Click
**URL Format**: `/vendor/otp?email=vendor@example.com`

**What happens**:
1. Frontend detects `email` parameter in URL
2. Automatically calls `POST /api/v1/vendor/activation/initiate` with the email
3. Backend:
   - Validates vendor exists and is approved
   - Generates 6-digit OTP code
   - Stores hashed code in `vendor_otps` table (expires in 15 minutes)
   - Sends OTP code via email
   - Returns activation token + masked email
4. Frontend displays OTP input form

### 4. OTP Verification
**User Action**: Enter 6-digit code received via email

**What happens**:
1. Frontend calls `POST /api/v1/vendor/activation/verify-otp`
2. Backend:
   - Verifies OTP code against stored hash
   - Checks expiration (15 minutes)
   - Tracks failed attempts (max 5)
   - On success:
     - Marks user as `is_active=true`
     - Marks vendor as `approved=true`
     - Marks OTP as `is_used=true`
     - Returns auth tokens (access + refresh)
3. Frontend:
   - Stores auth tokens
   - Redirects to `/vendor/dashboard`

### 5. Resend OTP
**User Action**: Click "Resend" link

**What happens**:
1. Frontend calls `POST /api/v1/vendor/activation/resend-otp`
2. Backend:
   - Invalidates previous OTP
   - Generates new OTP code
   - Sends new code via email
3. User receives new code and can try again

## API Endpoints

### POST /api/v1/vendor/activation/initiate
**Purpose**: Start activation process, send OTP

**Request**:
```json
{
  "email": "vendor@example.com"
}
```

**Response**:
```json
{
  "message": "Verification code sent successfully",
  "masked_email": "v***@example.com",
  "token": "eyJhbGc..."
}
```

### POST /api/v1/vendor/activation/verify-otp
**Purpose**: Verify OTP and activate account

**Request**:
```json
{
  "token": "eyJhbGc...",
  "otp_code": "123456"
}
```

**Response**:
```json
{
  "message": "Account activated successfully! Welcome to Shopsoma.",
  "access_token": "eyJhbGc...",
  "refresh_token": "eyJhbGc...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### POST /api/v1/vendor/activation/resend-otp
**Purpose**: Resend OTP code

**Request**:
```json
{
  "token": "eyJhbGc..."
}
```

**Response**:
```json
{
  "message": "New verification code sent successfully",
  "masked_email": "v***@example.com"
}
```

## Database Schema

### vendor_otps Table
```sql
CREATE TABLE vendor_otps (
    id UUID PRIMARY KEY,
    vendor_id UUID NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    code_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    is_used BOOLEAN NOT NULL DEFAULT FALSE,
    verified_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_vendor_otps_vendor_id ON vendor_otps(vendor_id);
CREATE INDEX ix_vendor_otps_email ON vendor_otps(email);
```

## Security Features

1. **OTP Code Hashing**: Codes are hashed with bcrypt before storage
2. **Short Expiration**: OTP expires after 15 minutes
3. **Attempt Limiting**: Max 5 attempts before requiring new code
4. **Single Use**: OTP is marked as used after successful verification
5. **Token-Based Flow**: Activation token prevents direct API access
6. **Email Masking**: Email is masked in responses for privacy

## Testing the Flow

### Manual Test
1. Create or use existing vendor account (email: `vendor@shopsoma.com`)
2. Ensure vendor is approved (`approved=true` in database)
3. Navigate to: `http://localhost:5173/vendor/otp?email=vendor@shopsoma.com`
4. Check email for OTP code
5. Enter code in the form
6. Should redirect to `/vendor/dashboard`

### API Test
```bash
# 1. Initiate activation
curl -X POST "http://localhost:8000/api/v1/vendor/activation/initiate" \
  -H "Content-Type: application/json" \
  -d '{"email": "vendor@shopsoma.com"}'

# Response will include token and masked_email

# 2. Check email for OTP code (or get from database for testing)

# 3. Verify OTP
curl -X POST "http://localhost:8000/api/v1/vendor/activation/verify-otp" \
  -H "Content-Type: application/json" \
  -d '{
    "token": "<token_from_step_1>",
    "otp_code": "123456"
  }'
```

### Get OTP Code from Database (Testing Only)
```sql
SELECT
    vo.email,
    vo.code_hash,
    vo.expires_at,
    vo.attempts,
    vo.is_used
FROM vendor_otps vo
WHERE vo.email = 'vendor@shopsoma.com'
AND vo.is_used = FALSE
ORDER BY vo.created_at DESC
LIMIT 1;
```

Note: You'll need to verify the code by entering it in the UI, as the hash cannot be reversed.

## Frontend Routes

- `/vendor/otp` - OTP verification page
- `/vendor/otp?email=vendor@example.com` - Activation link format
- `/vendor/dashboard` - Post-activation redirect destination
- `/vendor/login` - Fallback for invalid links

## Error Handling

### Frontend Errors
- **No activation token**: Shows "Invalid Activation Link" message
- **Invalid OTP**: Shows error with remaining attempts
- **Expired OTP**: Prompts to resend
- **Too many attempts**: Prompts to resend new code

### Backend Errors
- **400**: Invalid request data or code verification failed
- **401**: Invalid or expired activation token
- **403**: Vendor not approved yet
- **404**: Vendor account not found
- **500**: Server error (email sending failed, etc.)

## Next Steps

1. **Admin Panel Integration**: Add "Send Activation Email" button to vendor approval workflow
2. **Email Templates**: Create branded activation email template
3. **Rate Limiting**: Add rate limiting to prevent OTP spam
4. **SMS Option** (Optional): Add SMS as alternative OTP delivery method
5. **Monitoring**: Add logging and monitoring for activation flow

## Files Created/Modified

### Backend
- `/app/models/vendor_otp.py` - VendorOTP model
- `/app/services/vendor_otp_service.py` - OTP generation and verification logic
- `/app/services/email_service.py` - Added `send_vendor_otp_email()` method
- `/app/api/v1/vendor_activation.py` - Activation API endpoints
- `/app/main.py` - Registered vendor_activation router
- `/alembic/versions/abbae5384d63_create_vendor_otps_table.py` - Database migration

### Frontend
- `/src/services/vendorActivationService.ts` - API client for activation
- `/src/pages/auth/VendorOtp.tsx` - Updated OTP page with activation logic

### Documentation
- `/VENDOR_ACTIVATION_FLOW.md` - This file
