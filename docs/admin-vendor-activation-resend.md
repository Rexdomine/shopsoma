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
- Backend eligibility is shared by vendor list/detail responses, both admin resend endpoints, and public initiate, resend-OTP, verify-OTP and set-password boundaries. Each public capability binds its subject and email to current database identity. Paused/deleted/deactivated/completed recipients cannot use old invitations or previously issued tokens; active accounts retain password-reset guidance. OTP verification never restores approval. Helper commits are followed by a fresh locked check before capabilities or account updates; password persistence holds both identity locks through commit. Existing audited user deactivation is a conservative deny signal. Direct database edits without lifecycle audit cannot be reconstructed reliably and are not a supported account-status workflow.
- Vendor/User row locks serialize attempts. The attempt is committed and independently visible before contacting the provider. Both rows are then locked again, eligibility is freshly checked, and current recipient identity is captured. The locks remain held through provider handoff and correlated result commit. If eligibility changed in the commit gap, the endpoint records `skipped_ineligible` with the attempt ID, returns 409, and skips provider contact. The single and bulk user-status writers also lock when recording an audit-only deactivation; bulk deactivation records deny intent even when the inactive boolean is unchanged, without changing response counts. Provider latency therefore delays competing account/store writes; no exactly-once delivery guarantee is implied.
- If the process dies after the attempt commit, the ten-minute cooldown remains, even if no email was sent. If provider acceptance occurs before result persistence/HTTP response fails, delivery may have occurred; do not assume non-delivery or promise exactly-once email. Retry after cooldown can intentionally duplicate an invitation.
- No schema migration or new production dependency is required. No production deployment, configuration edit, or real-mail test is performed by this PR.

## Remediation QA

1. **Local setup/run:** from `shopsoma-backend`, use the isolated PostgreSQL test environment and run `python -m pytest tests/test_vendor_activation_invite_flow.py -q`. Provider seams are faked; no mailbox is contacted.
2. **Local test steps:** cover late lifecycle changes at all four public boundaries, stale subject/email and invalid UUIDs, helper-commit races, admin attempt-to-dispatch races, independent-session attempt visibility, and competing User/Vendor writes during provider await.
3. **Expected local result:** ineligible recipients receive 409, identity mismatches receive 401, password/state remain unchanged, skipped sends have correlated audit results, and competing writers wait. Valid approval → OTP → password → login and reset guidance pass.
4. **Staging test steps:** with dedicated controlled accounts, issue an invitation and tokens, then separately deactivate, pause, delete, or complete onboarding before the next public step. Repeat with an email change. Complete one unchanged account normally; replay its password token. Inspect resend audit correlation and cooldown.
5. **Expected staging result:** old links/capabilities cannot restore eligibility or alter passwords; changed identities are rejected; normal activation succeeds once; completed-account replay fails. Staging verification remains required after merge.
6. **Regression checks:** vendor list/detail eligibility agrees with both resend routes; customer/vendor/anonymous access remains denied; provider rejection/timeout preserves cooldown and truthful errors; active-account password recovery remains available.
