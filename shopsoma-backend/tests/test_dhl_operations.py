"""Unit contract checks; PostgreSQL route integration remains in admin-order tests."""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from app.services.dhl.operations import operations_snapshot_query, project_operations


def snapshot():
    return {
        "read_at": datetime(2026, 9, 28, 10, tzinfo=UTC),
        "order_status": "order_received",
        "packages": [
            {
                "id": "p",
                "current_version": 3,
                "hub_id": "hub",
                "state": "ready",
                "ready_at": "2026-09-28T09:00:00+00:00",
            }
        ],
        "seals": [{"id": "s", "package_id": "p", "package_version": 3}],
        "intents": [
            {
                "id": "i",
                "package_id": "p",
                "package_version": 3,
                "seal_id": "s",
                "origin_hub_id": "hub",
            }
        ],
        "guards": [],
        "bookings": [],
        "handoffs": [],
        "quotes": [{"intent_id": "i"}],
        "versions": [{"package_id": "p", "version": 3}],
        "items": [{"package_id": "p", "package_version": 3}],
    }


def attempt(classification="success"):
    return {
        "id": "b",
        "intent_id": "i",
        "package_id": "p",
        "package_version": 3,
        "seal_id": "s",
        "origin_hub_id": "hub",
        "created_at": "2026-09-28T09:00:00+00:00",
        "classification": classification,
        "outbound_state": "booked",
        "tracking_number": "synthetic",
        "label_available": True,
        "handoff_recorded_at": None,
        "last_tracking_refresh_at": None,
        "claim_expires_at": "2026-09-28T11:00:00+00:00",
        "reconciliation_resolution": None,
        "reconciliation_recorded_at": None,
    }


def with_booking(classification):
    data = snapshot()
    data["bookings"] = [attempt(classification)]
    data["guards"] = [
        {
            "intent_id": "i",
            "active_booking_id": "b",
            "booking_blocked_reason": (
                "unknown_outcome" if classification == "unknown" else None
            ),
        }
    ]
    return data


def test_exact_persisted_binding_and_read_only_projection():
    data = snapshot()
    original = deepcopy(data)
    p = project_operations(data)["packages"][0]
    assert p["selection_eligible"]
    assert (p["intent_id"], p["seal_id"], p["package_version"], p["origin_hub_id"]) == (
        "i",
        "s",
        3,
        "hub",
    )
    assert data == original


@pytest.mark.parametrize(
    "field,blocker",
    [
        ("seals", "active_seal_missing"),
        ("intents", "active_intent_missing"),
        ("quotes", "selected_dhl_quote_missing"),
        ("versions", "inconsistent_persisted_state"),
        ("items", "inconsistent_persisted_state"),
    ],
)
def test_missing_prerequisite_fails_closed(field, blocker):
    data = snapshot()
    data[field] = []
    p = project_operations(data)["packages"][0]
    assert not p["selection_eligible"]
    assert blocker in p["selection_blockers"]


@pytest.mark.parametrize("field", ["seals", "intents", "quotes"])
def test_ambiguous_binding_fails_closed(field):
    data = snapshot()
    data[field] *= 2
    assert not project_operations(data)["packages"][0]["selection_eligible"]


def test_current_version_and_hub_must_match():
    data = snapshot()
    data["intents"][0]["origin_hub_id"] = "vendor"
    assert not project_operations(data)["packages"][0]["selection_eligible"]
    data = snapshot()
    data["seals"][0]["package_version"] = 2
    assert project_operations(data)["packages"][0]["seal_id"] is None


@pytest.mark.parametrize(
    "status,expected",
    [("success", "not_required"), ("pending", "in_progress"), ("unknown", "required")],
)
def test_booking_reconciliation_states_and_no_retry(status, expected):
    data = with_booking(status)
    result = project_operations(data)
    assert result["bookings"][0]["reconciliation_state"] == expected
    assert not result["packages"][0]["selection_eligible"]


def test_expired_pending_is_not_mutated_or_misrepresented_as_unknown():
    data = with_booking("pending")
    data["bookings"][0]["claim_expires_at"] = "2026-09-28T09:00:00+00:00"
    original = deepcopy(data)
    result = project_operations(data)
    assert (
        result["bookings"][0]["reconciliation_state"]
        == "expired_claim_requires_recovery"
    )
    assert result["bookings"][0]["classification"] == "pending"
    assert data == original


@pytest.mark.parametrize(
    "classification,resolution",
    [("success", "confirm_success"), ("failure", "confirm_failure")],
)
def test_resolved_history_remains_visible_without_ready_package(
    classification, resolution
):
    data = with_booking(classification)
    data["packages"] = []
    data["bookings"][0].update(
        reconciliation_resolution=resolution,
        reconciliation_recorded_at="2026-09-28T10:00:00+00:00",
    )
    if classification == "failure":
        data["guards"][0]["active_booking_id"] = None
    result = project_operations(data)
    assert result["packages"] == []
    assert result["bookings"][0]["reconciliation_state"] == "resolved"


@pytest.mark.parametrize(
    "guard",
    [
        [],
        [
            {
                "intent_id": "i",
                "active_booking_id": "missing",
                "booking_blocked_reason": None,
            }
        ],
        [{"intent_id": "i", "active_booking_id": None, "booking_blocked_reason": None}],
    ],
)
def test_unguarded_or_dangling_active_booking_is_inconsistent(guard):
    data = with_booking("success")
    data["guards"] = guard
    result = project_operations(data)
    assert result["bookings"][0]["reconciliation_state"] == "inconsistent"
    assert not result["packages"][0]["selection_eligible"]


def test_failure_with_clear_guard_can_select_again():
    data = with_booking("failure")
    data["guards"][0]["active_booking_id"] = None
    assert project_operations(data)["packages"][0]["selection_eligible"]


def test_cancellation_and_handoff_block_selection():
    data = snapshot()
    data["order_status"] = "cancelled"
    data["handoffs"] = [{"package_id": "p", "package_version": 3}]
    assert set(project_operations(data)["packages"][0]["selection_blockers"]) == {
        "order_cancelled",
        "custody_handed_off",
    }


def test_projection_privacy_and_history_order():
    data = with_booking("failure")
    data["guards"] = []
    data["bookings"][0].update(
        evidence_ref="private",
        label_content="secret",
        account_alias="secret",
        failure_code="private",
        idempotency_key="secret",
    )
    data["bookings"].append({**attempt("failure"), "id": "a"})
    result = project_operations(data)
    assert [b["booking_id"] for b in result["bookings"]] == ["a", "b"]
    for denied in [
        "evidence_ref",
        "label_content",
        "account_alias",
        "failure_code",
        "idempotency_key",
        "claim_expires_at",
    ]:
        assert denied not in str(result)


def test_query_is_one_explicit_order_scoped_statement_without_locks_or_blob_output():
    sql = str(operations_snapshot_query(uuid4()).compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" not in sql
    assert "statement_timestamp()" in sql
    assert "outbound_shipment_booking.order_id =" in sql
    assert "hub_packages.order_id =" in sql
    assert "outbound_shipment_intents.order_id =" in sql
    assert "label_content IS NOT NULL" in sql
    assert "octet_length(outbound_shipment_booking.label_content)" in sql
    for denied in [
        "destination_name",
        "evidence_ref",
        "account_alias",
        "idempotency_key",
        "provider_reference",
    ]:
        assert denied not in sql


def test_invalidated_intent_is_unselectable_but_history_remains():
    data = with_booking("success")
    data["intents"][0]["invalidated"] = True
    result = project_operations(data)
    assert result["packages"][0]["intent_id"] is None
    assert result["bookings"][0]["booking_id"] == "b"


def test_mismatched_booking_binding_and_contradictory_resolution_fail_closed():
    data = with_booking("success")
    data["bookings"][0]["seal_id"] = "wrong"
    assert (
        project_operations(data)["bookings"][0]["reconciliation_state"]
        == "inconsistent"
    )
    data = with_booking("success")
    data["bookings"][0]["reconciliation_resolution"] = "confirm_failure"
    assert (
        project_operations(data)["bookings"][0]["reconciliation_state"]
        == "inconsistent"
    )


def test_order_enum_cancellation():
    from app.models.order import FulfillmentStatus

    data = snapshot()
    data["order_status"] = FulfillmentStatus.CANCELLED
    assert (
        "order_cancelled"
        in project_operations(data)["packages"][0]["selection_blockers"]
    )
