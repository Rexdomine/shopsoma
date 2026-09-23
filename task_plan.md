# Build admin vendor activation email resend
## Goal
Fresh focused PR into develop; no merge, deploy, production email or production data changes.
## Current Phase
in_progress — exact-candidate verification and independent review
## Next Step
Publish the focused tested candidate as a draft PR to develop, then reconcile exact-head independent review and hosted gates.
## Phases
1. complete — boundary/eligibility audit, baseline gates, backend and admin UI with focused regressions.
2. in_progress — parent verification and independent NightWing review; bounded repairs.
3. pending — fresh PR into develop, exact-head Codex and hosted gates, staging test instructions.
## Acceptance
Admin can resend from vendor dashboard with confirmation, pending/duplicate protection and truthful feedback. Backend owns eligibility: approved incomplete activation only; never bypass suspended/deactivated/deleted/fully-set-up account safeguards. Canonical encoded email links. Existing OTP and password setup remain valid and safe. Rate limiting and actor audit evidence; provider failures are not reported as success. No real email sends during local testing.
## Constraints
Base d6ea44cf1aca4214998256a8f8b2e02841f3b854; branch feat/admin-resend-vendor-activation. Other worktrees are off-limits. Implementation by Drax, review by independent NightWing. Inspect canonical CI commands and baseline before edits where practical. Max two repair cycles for a root failure.
