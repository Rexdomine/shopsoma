# Admin vendor activation resend

## Staging verification after merge

1. Configure the staging backend `FRONTEND_BASE_URL` to the staging frontend origin and allow that same origin in CORS. This PR does not change either environment.
2. Approve a dedicated staging vendor application whose email you control. Leave account activation incomplete.
3. Sign in as admin and open **Admin → Vendors**. The eligible row shows **Resend activation**. Cancel once: no email request should occur.
4. Confirm resend. The button shows **Sending…** and prevents repeated clicks; success says the provider accepted the email, not that mailbox delivery is proven.
5. Retry immediately: the backend returns a ten-minute cooldown. This cooldown also applies to the existing vendor-application resend action and to failed/uncertain provider attempts.
6. In the controlled mailbox, check the invitation host is the staging frontend and an email containing `+` remains intact in the link query.
7. Follow the invitation and complete the existing OTP → password → sign-in journey. After activation, the admin resend action is no longer eligible. Use normal password recovery for an established account.
8. Check a deliberately deactivated vendor, paused/deleted store, pending approval, and onboarding-completed vendor cannot be resent. The API independently enforces eligibility.
9. In local automated tests only, simulate a provider timeout/rejection: no false success; the attempt remains durably audited and rate-limited.

## Behavior and recovery

- Resend sends a new **invitation link**, not an OTP-bearing replacement. It never changes account/store status, passwords, approval, or OTP rows.
- Following the invitation uses the existing activation entrypoint. A valid existing OTP is reused; an expired/used/locked/missing OTP causes that flow to issue another. If the vendor cannot find a still-valid prior code, the OTP screen's existing resend-code control is available.
- Email links derive from `FRONTEND_BASE_URL`; email query values are encoded, including `+` as `%2B`.
- Backend eligibility is shared by vendor list/detail responses and both admin resend endpoints. Existing audited user deactivation is a conservative deny signal. Direct database edits without lifecycle audit cannot be reconstructed reliably and are not a supported account-status workflow.
- A vendor/user row lock serializes attempts. The attempt is committed before contacting the email provider, then a separate correlated result records acceptance or uncertainty.
- If the process dies after the attempt commit, the ten-minute cooldown remains, even if no email was sent. If provider acceptance occurs before result persistence/HTTP response fails, delivery may have occurred; do not assume non-delivery or promise exactly-once email. Retry after cooldown can intentionally duplicate an invitation.
- No schema migration or new production dependency is required. No production deployment, configuration edit, or real-mail test is performed by this PR.
