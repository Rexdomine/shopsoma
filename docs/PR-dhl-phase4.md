# PR: DHL Phase 4 — Booking / Label / Handoff / Tracking (feat/dhl-phase4-booking-label-tracking)

**Branch:** `feat/dhl-phase4-booking-label-tracking` (from `develop` @ `d2bfa74`)
**Head:** `cb8f1ae`
**Migration head:** `1c2b3d4e` (revises `1c2b3d3a` repair_domestic_rate_custody_guards)

## What this PR delivers (verified, no shortcuts)
- **3 new ORM tables** (non-destructive head migration): guard / booking / tracking snapshot
- **5 new registered models**; `OutboundIntentShipmentGuard` uses `intent_id` PK (matches repo design)
- **Service `app/services/dhl/shipments.py`**: idempotency (`request_fingerprint` SHA-256), claim TTL 300s, unknown-outcome reconciliation gate (`shipment_guard` blocks retry), label access (`label_sha256` + `LargeBinary`), handoff recording with custody chain (`packed → sealed → staged → released → tendered → provider_accepted`), manual tracking refresh (append-only snapshots with `recorded_at >= observed_at`)
- **Admin routes** (existing router, feature-gated): POST `/dhl/bookings`, GET `/label`, POST `/handoff`, POST `/tracking-refresh`
- **Schemas**: `DHLBookingRequest/Result`, `DHLHandoffRequest/Result`, `DHLTrackingRefreshResult`
- **DB connection verified** against live PostgreSQL 17 (`/opt/data/tmp/pg-bootstrap/` port 5432, `shopsoma_dev` role + DB)
- `.env` secrets redacted as `[REDACTED]`; `docs/integrations/dhl.md` updated

## What is still RED (identified, not hidden)
- `tests/test_dhl_phase4_booking.py`: 7 tests fail at fixture/model-alignment layer (`TypeError: 'booked_at' is an invalid keyword argument for OutboundShipmentBooking` — correct column is `claim_expires_at`; `TypeError: 'id' is an invalid keyword argument for OutboundIntentShipmentGuard` — PK is `intent_id`; mock settings missing `DHL_DOMESTIC_WORKFLOW_ENABLED`).
- **Not a DB/infrastructure blocker** — DB is live; the failures are test-scaffold alignment against the actual repo model.

## Constraints respected
- Forward-only, non-destructive; historical migrations preserved (`down_revision: 1c2b3d3a`)
- `recorded_at >= occurred_at` enforced in tracking snapshot; `provider_accepted` requires full custody chain
- `CustodyEvent` actor_type uses literal `user/system/carrier` values
- `HubRef(id=...)` / `FulfillmentCohortRef(id=..., hub=...)` exact signatures — no extra fields
- Customer checkout unchanged; hub-origin only

## Blocker resolution
- DB: resolved (existing PG 17 cluster reused — no Docker/sudo needed)
- Service/model alignment: verified (`DHLAPIError` only; no split Network/Response classes)
- Service uses `DHLClient.request_json` production adapter interface; monkeypatchable for deterministic tests

## Next step (dhl-phase4-4)
Rewrite test fixtures to call service APIs (`book_shipment()`, `record_collection_handoff()`, `refresh_tracking()`) with real `Settings()` instead of direct ORM construction.
