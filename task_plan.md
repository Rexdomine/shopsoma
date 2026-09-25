# Fix all homepage Shop by Category curated routes

## Goal
Open a fresh focused PR to `develop` that guarantees every homepage **Shop by Category** card—Casual, Evening, Party, and Workwear—shows products assigned through Shop Edits while preserving normal product classifications. No merge, deployment, or production-data changes.

## Classification
HEAVY regression repair: prior repair validated only an Evening example and did not prove the complete admin-association → public API → homepage-route matrix.

## Milestones
1. **Root-cause evidence** — complete: trace all four cards, category lookup, public association query, normal client filter, current PR/release state, and test coverage gap.
2. **Drax implementation** — running: create RED coverage for all four canonical leaves and repair the smallest shared boundary/seed-parity defect proven by that coverage.
3. **NightWing QA** — pending: independently review the complete four-category matrix, not a single leaf example.
4. **Fresh PR delivery** — pending: publish one focused PR to `develop`, request one exact-head Codex review, and reconcile CI/reviews. Rex alone merges.

## Acceptance criteria
- Each of Casual, Evening, Party, Workwear has a homepage card → canonical slug → server category association query path.
- A product whose ordinary category differs from its Shop Edit appears for each associated Shop Edit leaf.
- A shopper’s subsequent ordinary category refinement still filters the server-curated result.
- Seed/migration/runtime canonical category definitions cannot drift silently.
- Regression proof covers all four leaves, not Evening alone.
- Fresh PR targets `develop`; workspace is clean; no duplicate comments; no unresolved addressed review threads.

## Constraints
- PR #202 is already merged into `develop`; do not mutate it.
- No production writes, secrets, payment access, merge, auto-merge, or deployment.
- Drax implements; NightWing independently verifies; Groot coordinates.
