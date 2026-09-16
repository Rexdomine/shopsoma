# Fix Vendor Activation Email Delivery Reporting

## Goal
Make vendor activation and OTP resend report Brevo handoff failure truthfully, preserve approval durability, and prevent an undelivered OTP from remaining usable.

## State and invariants
- Approval is independent of email delivery: `pending_review → approved` is never rolled back merely because Brevo rejects a message.
- OTP lifecycle: `active → verified | expired | locked | delivery_failed`; `delivery_failed` is represented by `is_used=True` until a dedicated state exists.
- An OTP can be verified only after Brevo accepted its send handoff.
- Failure responses must not reveal Brevo internals, tokens, or credentials.

## Completed
- [x] Mapped activation initiation, vendor resend, admin resend, and approval callers.
- [x] Wrote RED regressions for false provider return and resend failure.
- [x] Invalidate failed-send OTPs, producing a fresh code on retry.
- [x] Return generic HTTP `503` failure for vendor activation and resend.
- [x] Return truthful `503` failure for admin resend.
- [x] Preserve approval and expose `activation_email_sent` to the Admin UI.
- [x] Update both Admin approval views to stop falsely claiming delivery.
- [x] Focused backend test suite, Ruff, compilation, and frontend production build.

## Next
- [ ] Commit, push focused PR to `develop`, and request review.
- [ ] Deploy only after merge authorization; perform staging retry/UAT only after deployment readback.
