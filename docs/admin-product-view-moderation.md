# Product-detail moderation shortcuts

## Scope

Frontend-only Approve/Deny controls on the admin product detail page. Reuses `adminService.approveProduct` / `rejectProduct` and the existing server moderation workflow. Product list, backend, authorization, notifications, pricing, inventory and schema remain unchanged.

## Behavior

- Both actions are shown only for pending products, matching list eligibility.
- Approval supports optional notes; denial requires a reason of at least 10 trimmed characters and supports optional notes.
- Confirmation, disabled in-flight controls and a submission guard prevent accidental duplicates.
- Success refreshes the displayed product without navigating away. Structured errors retain entered values for retry.
- Failed post-success refresh displays a warning and offers GET-only refresh, not a second moderation request.
- Modal focus, Escape cancellation and responsive header wrapping are supported.

## Executed verification

- Full frontend suite: **230 tests passed across 26 files**.
- TypeScript (`tsc --noEmit`): passed.
- ESLint: zero errors; 280 warnings remain.
- Production build: passed.
- Real browser with isolated local API fixtures: approval and denial each sent exactly one existing moderation PUT followed by a product GET; the dialog closed, status updated, and the detail page stayed open.
- Regression coverage includes notes/reason payloads, cancellation, Escape/focus, duplicate submission prevention, structured errors, and GET-only retry after a successful mutation with a failed refresh.

No live product changes or vendor notification emails were performed during QA. Owner review and merge; no automatic merge or deployment.
