# Findings — admin activation resend
## Context
Production email URL/CORS mismatch was diagnosed; Rex says configuration fixed. Old emails retain old host. User requests permanent admin resend feature and fresh PR into develop for staging testing after merge.
## Preflight boundary map
Admin browser -> authenticated admin API (actor authenticated server-side); API -> PostgreSQL (authoritative vendor/user state, audit, cooldown); API -> existing email service/Brevo (acceptance is not mailbox delivery); vendor email link -> public activation -> OTP verification -> password setup. No production provider calls are authorized during development.
## State and invariants
Approved but never setup is eligible. Fully setup uses password recovery, not activation. Inactive does NOT alone imply never setup: admin-deactivated users must not be reactivated via this operation. Resend never approves, activates, changes password, or changes store flags. Map actual fields and lifecycle audit before implementation.
## Identity, retry, crash windows
Vendor UUID and linked user/email from DB, authenticated admin actor; browser must not supply destination. Duplicate sends/cooldown must be server-enforced. Reuse existing safe service where possible, document email accepted/DB commit/response loss uncertainty; no exactly-once delivery claims. Before email failure, no false success; provider timeout is ambiguous and UI must not claim definite non-delivery. Prefer sending invitation link without unnecessarily rotating OTP if existing invite architecture permits; implementation must document chosen contract.
## Time and parity
Use authoritative UTC clock and lock-safe cooldown. Existing OTP expiry and session expiry remain unchanged. Audit migration vs ORM parity if adding schema. Audit admin resend vs approval/public initiate/resend for eligibility and code invalidation. Email query values must be URL encoded and base URL deployment-configured, not hardcoded to production.
## Resume verification
- Exact requirements installed in isolated Python3.12 venv; baseline activation6/6 and critical flake8 pass.
- Frontend lifecycle tests7/7 pass; build and strict error-level lint pass. Built-UI mocked-API browser QA passed desktop/mobile action journeys.
- Full Node20 Vitest is not green at either base or candidate: base187pass11fail/198, candidate190pass13fail/203; failures confined to Checkout. Checkout implementation and tests have identical SHA256 across base/candidate. These are inherited timing-sensitive tests; not fixed in this scoped PR, and not a green-suite claim. Hosted frontend gate runs build (not Vitest).
- Resend uses invitation-only semantics: preserves OTP state, link uses canonical configured origin, existing public initiate handles expired/used/missing OTPs. Password existence and email_verified cannot identify setup completion. Audited user_deactivated plus current account/vendor/store state is the conservative guard.
## Regressions
Non-admin forbidden; eligible send; pending/active/suspended/deleted blocked; double-click/concurrent retry/cooldown; provider rejection/ambiguous failure; audit actor/target; encoded + email; UI success/failure/retry and reachable action; vendor follows invite through OTP/password in isolated tests.
