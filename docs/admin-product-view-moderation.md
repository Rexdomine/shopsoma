# Product-detail moderation shortcuts

## Scope

Approve/Deny controls on the admin product detail page and product list, backed by an atomic server-side pending-to-terminal moderation transition. Reuses `adminService.approveProduct` / `rejectProduct` and the existing authorization and notification workflow. Pricing, inventory, and schema/migrations remain unchanged.

## Behavior

- Both actions are shown only for pending products, matching list eligibility.
- Approval supports optional notes; denial requires a reason of at least 10 trimmed characters and supports optional notes.
- Confirmation, disabled in-flight controls and a submission guard prevent accidental duplicates.
- The backend conditionally transitions only pending products; a concurrent or repeated terminal request receives `409` and does not dispatch another notification.
- Success refreshes the displayed product without navigating away. A `409` conflict closes the stale detail/list modal and reloads authoritative product/list state; structured errors retain entered values for retry.
- Failed post-success refresh displays a warning and offers GET-only refresh, not a second moderation request.
- Modal focus, Escape cancellation and responsive header wrapping are supported.

## Executed verification

- Full frontend suite: **249 tests passed across 26 files**.
- Backend atomic moderation regression: **5 tests passed**, including approve/approve, deny/deny, approve/deny concurrency, terminal retry, and notification-failure commit preservation.
- Related backend product/admin-edit regressions: **88 tests passed**.
- TypeScript (`tsc --noEmit`): passed.
- ESLint: zero errors; 283 warnings remain.
- Production build: passed.
- Real browser with isolated local API fixtures: approval and denial each sent exactly one existing moderation PUT followed by a product GET; the dialog closed, status updated, and the detail page stayed open. Server-side concurrency is covered with separate PostgreSQL sessions.
- Regression coverage includes notes/reason payloads, cancellation, Escape/focus, duplicate submission prevention, structured errors, `409` conflict refresh/closure in detail and list consumers, and GET-only retry after a successful mutation with a failed refresh.

No live product changes or vendor notification emails were performed during QA. Owner review and merge; no automatic merge or deployment.
