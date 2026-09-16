# Findings — Vendor Activation Email Delivery Reporting

## Root cause
- Staging Brevo `401 Unauthorized` failures occurred when `BREVO_API_KEY` and sender configuration were absent.
- `VendorOTPService.create_and_send_otp` persisted an OTP and suppressed both provider exceptions and `False` return values.
- The activation UI consequently showed success despite no provider acceptance, and the undelivered OTP could remain usable until expiry.

## Implemented contract
- `False` from Brevo or a send exception invalidates the newly created OTP and raises `OTPDeliveryError`.
- Vendor activation initiation and resend return HTTP `503` with: `Unable to send verification code. Please try again.`
- Admin activation resend returns HTTP `503` with a generic retry-safe message.
- Application approval remains durable. Its response has `activation_email_sent: false` when the handoff fails, and the Admin UI explicitly reports the delivery problem rather than claiming the email was sent.
- A follow-up retry creates a fresh OTP because failed OTPs are invalidated.

## Verification
- RED: initiate returned HTTP 200 on an email-provider `False`; resend returned HTTP 500.
- GREEN: `tests/test_vendor_activation_invite_flow.py` — 4 passed.
- Scoped Ruff — all checks passed.
- Modified backend modules compiled successfully.
- Frontend production build completed successfully.
