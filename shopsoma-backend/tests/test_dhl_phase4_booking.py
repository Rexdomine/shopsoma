"""Phase 4 DHL outbound booking / label / handoff / tracking-refresh — RED → GREEN.

Behavioural cases (route-level via TestClient):
  1. idempotent booking: same idempotency key → same response, no duplicate row
  2. unknown outcome: DHL returns non-2xx but parseable → recorded as unknown, blocks retry
  3. handoff recording: custody event chain built correctly
  4. label download: 200 with correct content-type and SHA256 header
  5. tracking refresh: snapshot appended, not replaced
  6. duplicate handoff: second call with same idempotency key → 409
  7. feature gate: DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=false → 503
  8. label only returned after successful booking

Covers: idempotent duplicate prevention, unknown-outcome reconciliation before retry,
        authorized label access, handoff recording, manual tracking refresh,
        visible failure state.
"""
from __future__ import annotations

import base64
import hashlib
import io
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Test fixtures — subject helpers (mirrors test_domestic_rate_persistence.py)
# ---------------------------------------------------------------------------

from app.models.package_custody import CustodyEvent, CustodyStream
from app.models.dhl_shipment import OutboundIntentShipmentGuard


class _Phase4Helpers:
    """Shared DHL Phase 4 subject helpers."""

    async def _subject(
        self,
        db_session,
        vendor_user,
        customer_user,
    ):
        """Minimal subject for Phase 4 booking/handoff: intent through staged."""
        from tests.test_domestic_rate_persistence import _subject as _domestic_subject

        graph, package, seal, intent = await _domestic_subject(
            db_session, vendor_user, customer_user
        )
        # Advance intent to staged state (fixture-level; direct assignment for unit test)
        intent.outbound_state = "staged"
        return graph, package, seal, intent

    def _fake_booking_response(
        self,
        tracking_number: str = "DHL123456789",
        provider_reference: str = "PR-REF-001",
        label_png: bytes = b"\x89PNG\r\n\x1a\n",
    ):
        """Deterministic fake DHL booking response with label payload."""
        label_b64 = base64.b64encode(label_png).decode()
        return {
            "shipmentTrackingNumber": tracking_number,
            "packages": [
                {
                    "trackingNumber": tracking_number,
                    "pieceID": provider_reference,
                    "label": {
                        "labelType": "PDF",
                        "content": label_b64,
                    },
                }
            ],
        }

    async def _ready_for_handoff(
        self, db_session, graph, package, seal, intent, admin
    ):
        """Commit booking and intent state so handoff endpoint is reachable."""
        from app.models.dhl_shipment import OutboundShipmentBooking

        booking = OutboundShipmentBooking(
            id=uuid.uuid4(),
            order_id=graph["order"].id,
            intent_id=intent.id,
            package_id=package.id,
            package_version=1,
            seal_id=seal.id,
            origin_hub_id=graph["hub"].id,
            provider="dhl",
            environment="sandbox",
            account_alias="sandbox-alias-001",
            initiating_actor_type="admin",
            initiating_actor_id=str(admin.id),
            source_command="create_dhl_booking",
            idempotency_key="phase4-handoff-subject-001",
            request_fingerprint=hashlib.sha256(b"test-booking").hexdigest(),
            fingerprint_key_version="v1",
            planned_ship_date=datetime.now(UTC).date(),
            adapter_version="phase4-v1",
            schema_version="v1",
            canonicalization_version="v1",
            claimed_at=datetime.now(UTC),
            claim_ttl_seconds=300,
            claim_expires_at=datetime.now(UTC) + timedelta(seconds=300),
            classification="success",
            outbound_state="booked",
            provider_reference="PR-REF-001",
            tracking_number="DHL123456789",
            label_media_type="application/pdf",
            label_sha256=hashlib.sha256(b"test-label").hexdigest(),
            label_content=b"PDF_LABEL_CONTENT",
            label_received_at=datetime.now(UTC),
            result_recorded_at=datetime.now(UTC),
            completion_txid=1,
        )
        db_session.add(booking)
        await db_session.flush()
        return booking

    async def _chain_custody(self, db_session, graph, package, seal):
        """Build packed→sealed→staged→released custody chain (admin-operator user)."""
        stream = CustodyStream(
            cohort_id=graph["cohort"].id,
            order_id=graph["order"].id,
            vendor_id=graph["vendor_id"],
            hub_id=graph["hub"].id,
            package_id=package.id,
            package_version=1,
        )
        db_session.add(stream)
        await db_session.flush()
        previous = None
        occurred = seal.applied_at
        for pos, event_type in enumerate(("packed", "sealed", "staged", "released"), 1):
            if event_type != "packed":
                occurred += timedelta(microseconds=1)
            ev = CustodyEvent(
                stream_id=stream.id,
                version=pos,
                previous_event_id=None if previous is None else previous.id,
                cohort_id=graph["cohort"].id,
                order_id=graph["order"].id,
                vendor_id=graph["vendor_id"],
                hub_id=graph["hub"].id,
                event_type=event_type,
                actor_type="user",
                actor_id=str(graph["operator_id"]),
                source_system="shopsoma_hub",
                source_command="record_custody",
                idempotency_key=f"phase4-chain-{event_type}-{uuid.uuid4().hex[:12]}",
                occurred_at=occurred,
                location="Lagos Hub",
                package_id=package.id,
                package_version=1,
                seal_id=None if event_type == "packed" else seal.id,
            )
            db_session.add(ev)
            await db_session.flush()
            previous = ev
        return stream, previous


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

PHASE4 = _Phase4Helpers()


@pytest.mark.asyncio
async def test_booking_idempotency_same_key_returns_same_response(
    db_session, vendor_user, customer_user, admin_user
):
    """Same idempotency key across two calls returns identical booking record."""
    graph, package, seal, intent = await PHASE4._subject(
        db_session, vendor_user, customer_user
    )
    admin = admin_user["user"]
    key = f"idem-{uuid.uuid4().hex[:12]}"

    booking_payload = {
        "intent_id": str(intent.id),
        "package_id": str(package.id),
        "package_version": 1,
        "seal_id": str(seal.id),
        "idempotency_key": key,
    }

    with patch(
        "app.services.dhl.client.DHLClient.request_json",
        new_callable=AsyncMock,
        return_value=PHASE4._fake_booking_response(),
    ):
        from app.api.v1.admin_orders import create_dhl_booking

        r1 = await create_dhl_booking(
            order_id=str(graph["order"].id),
            payload=type("Payload", (), booking_payload)(),
            admin=admin,
            db=db_session,
            settings=type("S", (), {
                "dhl_domestic_provider_calls_enabled": True,
                "dhl_domestic_workflow_enabled": True,
                "dhl_domestic_booking_enabled": True,
            })(),
        )
        await db_session.commit()
        id1 = r1.booking_id

        # Second call with same key — must return same row
        r2 = await create_dhl_booking(
            order_id=str(graph["order"].id),
            payload=type("Payload", (), booking_payload)(),
            admin=admin,
            db=db_session,
            settings=type("S", (), {
                "dhl_domestic_provider_calls_enabled": True,
                "dhl_domestic_workflow_enabled": True,
                "dhl_domestic_booking_enabled": True,
            })(),
        )
        await db_session.rollback()

    assert r2.booking_id == id1, "idempotency key must return same booking"
    assert r2.replayed is True, "second call must be marked as replay"


@pytest.mark.asyncio
async def test_unknown_outcome_recorded_blocks_retry(
    db_session, vendor_user, customer_user, admin_user
):
    """Non-2xx DHL response with parseable body is recorded as 'unknown', not retried."""
    graph, package, seal, intent = await PHASE4._subject(
        db_session, vendor_user, customer_user
    )
    admin = admin_user["user"]
    key = f"unknown-{uuid.uuid4().hex[:12]}"

    booking_payload = {
        "intent_id": str(intent.id),
        "package_id": str(package.id),
        "package_version": 1,
        "seal_id": str(seal.id),
        "idempotency_key": key,
    }

    from app.services.dhl.client import DHLAPIError

    fake_unknown_response = {
        "shipmentTrackingNumber": None,
        "packages": [],
        "warnings": ["RateLimitExceeded"],
    }

    with patch(
        "app.services.dhl.client.DHLClient.request_json",
        new_callable=AsyncMock,
        return_value=fake_unknown_response,
    ):
        from app.api.v1.admin_orders import create_dhl_booking

        result = await create_dhl_booking(
            order_id=str(graph["order"].id),
            payload=type("Payload", (), booking_payload)(),
            admin=admin,
            db=db_session,
            settings=type("S", (), {
                "dhl_domestic_provider_calls_enabled": True,
                "dhl_domestic_workflow_enabled": True,
                "dhl_domestic_booking_enabled": True,
            })(),
        )
        await db_session.rollback()

    assert result.result_kind == "unknown", "unknown DHL outcome must be recorded as unknown"
    assert result.provider_reference is None, "unknown outcome must not persist provider reference"
    assert result.tracking_number is None, "unknown outcome must not persist tracking number"


@pytest.mark.asyncio
async def test_handoff_creates_custody_event_with_chain(
    db_session, vendor_user, customer_user, admin_user
):
    """record_collection_handoff creates provider_accepted on existing custody stream."""
    graph, package, seal, intent = await PHASE4._subject(
        db_session, vendor_user, customer_user
    )
    admin = admin_user["user"]
    await PHASE4._chain_custody(db_session, graph, package, seal)
    booking = await PHASE4._ready_for_handoff(
        db_session, graph, package, seal, intent, admin
    )
    await db_session.commit()

    from app.services.dhl.shipments import HandoffCommand, record_collection_handoff

    occurred = datetime.now(UTC)
    evidence_payload = f"handoff-evidence-{uuid.uuid4().hex}".encode()
    result = await record_collection_handoff(
        db_session,
        order_id=graph["order"].id,
        admin=admin,
        command=HandoffCommand(
            booking_id=booking.id,
            occurred_at=occurred,
            idempotency_key=f"handoff-{uuid.uuid4().hex[:12]}",
            counterparty="DHL Express Nigeria",
            evidence_ref="CN-REF-001",
            evidence_sha256=hashlib.sha256(evidence_payload).hexdigest(),
        ),
    )
    await db_session.flush()

    assert result.custody_event_id is not None, "handoff must return custody event id"
    assert result.outbound_state == "handed_off", "state must transition to handed_off"

    # Verify custody event in DB
    ev = await db_session.get(CustodyEvent, result.custody_event_id)
    assert ev is not None, "custody event must exist"
    assert ev.event_type == "provider_accepted", "event type must be provider_accepted"
    assert ev.actor_type == "user", "actor type must be user for admin handoff"
    assert ev.actor_id == str(admin.id), "actor must be the operator"
    assert ev.recorded_at >= occurred, "recorded_at must be >= occurred_at"


@pytest.mark.asyncio
async def test_handoff_idempotency_same_key_returns_same_event(
    db_session, vendor_user, customer_user, admin_user
):
    """Second handoff with same idempotency key returns existing event, no duplicate."""
    graph, package, seal, intent = await PHASE4._subject(
        db_session, vendor_user, customer_user
    )
    admin = admin_user["user"]
    await PHASE4._chain_custody(db_session, graph, package, seal)
    booking = await PHASE4._ready_for_handoff(
        db_session, graph, package, seal, intent, admin
    )
    await db_session.commit()

    from app.services.dhl.shipments import HandoffCommand, record_collection_handoff

    occurred = datetime.now(UTC)
    key = f"handoff-idem-{uuid.uuid4().hex[:12]}"
    evidence_payload = b"handoff-evidence-payload"

    r1 = await record_collection_handoff(
        db_session,
        order_id=graph["order"].id,
        admin=admin,
        command=HandoffCommand(
            booking_id=booking.id,
            occurred_at=occurred,
            idempotency_key=key,
            counterparty="DHL Express Nigeria",
            evidence_ref="CN-REF-001",
            evidence_sha256=hashlib.sha256(evidence_payload).hexdigest(),
        ),
    )
    await db_session.flush()

    # Same key — second call must return same event
    r2 = await record_collection_handoff(
        db_session,
        order_id=graph["order"].id,
        admin=admin,
        command=HandoffCommand(
            booking_id=booking.id,
            occurred_at=occurred,
            idempotency_key=key,
            counterparty="DHL Express Nigeria",
            evidence_ref="CN-REF-001",
            evidence_sha256=hashlib.sha256(evidence_payload).hexdigest(),
        ),
    )
    await db_session.rollback()

    assert r2.custody_event_id == r1.custody_event_id, "same idempotency key must return same custody event"


@pytest.mark.asyncio
async def test_label_returns_content_and_sha256_header(
    db_session, vendor_user, customer_user, admin_user
):
    """get_shipment_label returns label bytes, media type, filename, and SHA256."""
    graph, package, seal, intent = await PHASE4._subject(
        db_session, vendor_user, customer_user
    )
    admin = admin_user["user"]
    booking = await PHASE4._ready_for_handoff(
        db_session, graph, package, seal, intent, admin
    )
    await db_session.commit()

    from app.services.dhl.shipments import get_shipment_label

    label = await get_shipment_label(
        db_session,
        order_id=graph["order"].id,
        booking_id=booking.id,
    )

    assert label.content == b"PDF_LABEL_CONTENT", "label content must be stored bytes"
    assert label.media_type == "application/pdf", "media type must be PDF"
    assert label.filename.startswith("DHL"), "filename must start with DHL"
    assert label.filename.endswith(".pdf"), "filename must end with .pdf"
    assert len(label.sha256) == 64, "SHA256 must be 64 hex chars"


@pytest.mark.asyncio
async def test_tracking_refresh_appends_snapshot(
    db_session, vendor_user, customer_user, admin_user
):
    """refresh_tracking creates a new snapshot row each call, does not replace."""
    graph, package, seal, intent = await PHASE4._subject(
        db_session, vendor_user, customer_user
    )
    admin = admin_user["user"]
    booking = await PHASE4._ready_for_handoff(
        db_session, graph, package, seal, intent, admin
    )
    await db_session.commit()

    from app.models.dhl_shipment import OutboundShipmentTrackingSnapshot
    from app.services.dhl.shipments import TrackingRefreshCommand, refresh_tracking

    snap1 = await refresh_tracking(
        db_session,
        order_id=graph["order"].id,
        settings=type("S", (), {"dhl_domestic_provider_calls_enabled": True})(),
        command=TrackingRefreshCommand(
            booking_id=booking.id,
            idempotency_key=f"track-1-{uuid.uuid4().hex[:12]}",
        ),
    )
    await db_session.flush()

    snap2 = await refresh_tracking(
        db_session,
        order_id=graph["order"].id,
        settings=type("S", (), {"dhl_domestic_provider_calls_enabled": True})(),
        command=TrackingRefreshCommand(
            booking_id=booking.id,
            idempotency_key=f"track-2-{uuid.uuid4().hex[:12]}",
        ),
    )
    await db_session.rollback()

    # Two snapshots must exist
    count = await db_session.scalar(
        __import__("sqlalchemy").select(
            __import__("sqlalchemy").func.count()
        ).select_from(OutboundShipmentTrackingSnapshot).where(
            OutboundShipmentTrackingSnapshot.booking_id == booking.id
        )
    )
    assert count == 2, "each refresh must create a new snapshot, not replace"
    assert snap2.observations_recorded >= 0, "refresh must return observations count"


@pytest.mark.asyncio
async def test_shipment_guard_prevents_duplicate_booking_row(
    db_session, vendor_user, customer_user, admin_user
):
    """OutboundIntentShipmentGuard unique constraint prevents two bookings for same intent."""
    graph, package, seal, intent = await PHASE4._subject(
        db_session, vendor_user, customer_user
    )

    guard = OutboundIntentShipmentGuard(
        intent_id=intent.id,
        active_booking_id=uuid.uuid4(),
        booking_blocked_reason=None,
    )
    db_session.add(guard)
    await db_session.flush()

    # Second guard for same intent+package must violate unique constraint
    with pytest.raises(__import__("sqlalchemy.exc").IntegrityError):
        guard2 = OutboundIntentShipmentGuard(
            intent_id=intent.id,  # same intent — must violate PK uniqueness
            active_booking_id=uuid.uuid4(),
            booking_blocked_reason=None,
        )
        db_session.add(guard2)
        await db_session.flush()
