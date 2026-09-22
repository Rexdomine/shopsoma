# Footer document validation

## Scope
Ten client-supplied informational destinations, shared desktop/mobile footer navigation, and a simple entry to the existing protected/capability-backed tracking flow. No backend, checkout, auth, payment, or production configuration changes.

## Executed local checks
- Source fidelity: all ten bodies match the corresponding complete PDF sections after whitespace normalization. Explicit design annotation removed; source legal/editorial references preserved and noted in `shopsoma-frontend/src/content/REVIEW-NOTES.md`.
- Node 20 focused Vitest: 24 tests passed (2 files: 18 in `PublicDocument.test.tsx`, 6 in `footerDocuments.test.ts`). Includes complete rendered article text, headings, mailto, tracking navigation/validation, partner CTA, accordion state and mocked newsletter contract.
- `npm run build`: passed (TypeScript + Vite).
- `npm run lint`: passed, 0 errors / 279 warnings; untouched base has 0 errors / 277 warnings. Two additional react-refresh export warnings are nonblocking.
- Chromium: 10 pages at 390, 768, 1366 and 1440px; all 40 rendered without horizontal overflow or page exceptions. All ten footer links clicked successfully; mobile accordions exercised. Mobile Contact page screenshot visually reviewed.
- Browser evidence was local, not authenticated staging evidence. Local backend was unavailable; no live newsletter or order mutation was attempted.

## Full-suite limitation
- Default host Node 26 triggers unrelated jsdom/localStorage failures; CI-aligned Node 20 used for meaningful tests.
- Final Node 20 full candidate run: 182 passed, 10 failed, all failures in existing `Checkout.test.tsx`; 22 test files passed, 1 failed.
- Untouched base 5095d284 Node 20 run: 156 passed, 16 failed, all in the same checkout suite. Failure sets vary across runs; this is not claimed as a green full suite or exact one-to-one inherited-failure equivalence. Checkout mocks Layout and was not edited.
- Checkout instability is not repaired in this content-only change.

## Staging / acceptance
- Rex explicitly requested Coming Soon remain enabled and review use an admin login.
- Staging deployment and hosted verification are recorded in the PR after publishing the exact commit. Production must remain unchanged. No merge/promotion without Rex.
- Client should approve legal/editorial references and cookie-consent capability statements before production publication.
