# Footer client documents — implementation record

## Authority and scope
- Rex approved the staging-first plan at `/opt/data/projects/shopsoma/.hermes/plans/2026-09-22_042500-shopsoma-footer-staging.md`.
- Isolated worktree: `/opt/data/projects/shopsoma-worktrees/footer-documents`, branch `feat/footer-client-documents`, base `origin/develop` at 5095d284.
- Client PDFs: `/opt/data/deliverables/shopsoma-footer-documents/`; complete layout extracts under `extracted/`.
- No backend/payment/auth implementation, production changes, merge, or direct develop push authorized.

## Boundary map / invariants
- Footer navigation -> public informational pages -> existing tracking-detail route; no new order lookup contract or identity handling.
- Existing newsletter request and partner registration route retained.
- Coming Soon and authenticated returns behavior retained.
- PDF prose authority: only explicit designer instruction omitted; questionable legal references flagged, not invented/reworded.
- Deployment: existing Render frontend staging only; build exact reviewed SHA. Read back target deploy and production baseline. Manual SHA deployment may disable staging autodeploy; disclose/preserve intentionally until Rex approval rather than enabling and accidentally reverting preview.

## Current phase
Implementation and verification in progress. Initial delegated worker timed out and left unverified partial files; parent rejected defective repeated PDF extraction before publication. Recovery split into disjoint source-content and renderer/regression owners.

## Gates remaining
- Source fidelity audit: 10 documents, precise sections, no entire-PDF duplication, valid keys.
- Focused tests, full frontend tests, build, lint baseline comparison.
- Independent NightWing review and remediation.
- Local responsive browser QA, with API mocks explicitly labeled where used.
- Focused PR against develop, exact-head hosted CI / Codex review.
- Exact-SHA staging deployment, readback and live route/browser verification.
- Client staging review before Rex merge/promote.

## Verified environment / blockers
- Staging frontend service `srv-d4atpfmr433s738inhgg`, URL https://shopsoma-staging.onrender.com, branch develop.
- Production frontend `srv-dan4bhegekts73fler10` must remain untouched.
- Rex explicitly chose: keep Coming Soon enabled; review using an admin login. Browser currently holds a vendor session, not admin; no admin credentials available in the checked credential environment.
- Staging API Coming Soon is enabled; anonymous visitors cannot review storefront/footer. Existing admin session/access required for unmocked staged page visual verification. Do not disable gate silently.
- `gh` CLI absent; authenticated GitHub API via git credential helper works; credentials not printed.
- Python browser QA environment `/opt/data/tmp/shopsoma-footer-qa-venv`; existing Chromium `/opt/data/.cache/ms-playwright/chromium-1187/chrome-linux/chrome` launches successfully.
