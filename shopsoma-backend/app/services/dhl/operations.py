"""Read-only, order-scoped DHL operations projection (one PostgreSQL snapshot).

Only explicit safe columns are selected. Never invoke shipment commands from GET.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order
from app.models.package_custody import (
    CustodyEvent,
    HubPackage,
    HubPackageItem,
    HubPackageVersion,
    HubPackageSeal,
    OutboundShipmentIntent,
    OutboundShipmentIntentInvalidation,
)
from app.models.dhl_shipment import OutboundIntentShipmentGuard, OutboundShipmentBooking
from app.models.customer_shipping_quote import (
    CustomerShippingQuote,
    CustomerShippingQuoteOption,
    CustomerShippingQuoteSelection,
)
from app.models.domestic_rate_quote import DomesticRateAttempt, DomesticRateResponse


def _rows(statement):
    rows = statement.subquery()
    return select(
        func.json_agg(func.row_to_json(rows.table_valued()))
    ).scalar_subquery()


def operations_snapshot_query(order_id: UUID):
    """Scalar aggregates share a single statement snapshot, without write locks."""
    p, s, i = HubPackage, HubPackageSeal, OutboundShipmentIntent
    b, g = OutboundShipmentBooking, OutboundIntentShipmentGuard
    package_ids = select(p.id).where(p.order_id == order_id)
    intent_ids = select(i.id).where(i.order_id == order_id)
    selected_quotes = (
        select(CustomerShippingQuoteSelection.intent_id)
        .join(
            CustomerShippingQuoteOption,
            and_(
                CustomerShippingQuoteSelection.option_id
                == CustomerShippingQuoteOption.id,
                CustomerShippingQuoteSelection.quote_id
                == CustomerShippingQuoteOption.quote_id,
            ),
        )
        .join(
            CustomerShippingQuote,
            CustomerShippingQuote.id == CustomerShippingQuoteSelection.quote_id,
        )
        .join(
            DomesticRateResponse,
            DomesticRateResponse.id == CustomerShippingQuote.source_rate_response_id,
        )
        .join(
            DomesticRateAttempt,
            DomesticRateAttempt.id == DomesticRateResponse.attempt_id,
        )
        .where(
            CustomerShippingQuoteSelection.intent_id.in_(intent_ids),
            CustomerShippingQuoteOption.provider == "dhl",
        )
    )
    return select(
        func.statement_timestamp().label("read_at"),
        select(Order.fulfillment_status)
        .where(Order.id == order_id)
        .scalar_subquery()
        .label("order_status"),
        _rows(
            select(p.id, p.current_version, p.hub_id, p.state, p.ready_at).where(
                p.order_id == order_id
            )
        ).label("packages"),
        _rows(
            select(s.id, s.package_id, s.package_version).where(
                s.package_id.in_(package_ids), s.retired_at.is_(None)
            )
        ).label("seals"),
        _rows(
            select(
                i.id,
                i.package_id,
                i.package_version,
                i.seal_id,
                i.origin_hub_id,
                select(OutboundShipmentIntentInvalidation.id)
                .where(OutboundShipmentIntentInvalidation.intent_id == i.id)
                .exists()
                .label("invalidated"),
            ).where(i.order_id == order_id)
        ).label("intents"),
        _rows(
            select(g.intent_id, g.active_booking_id, g.booking_blocked_reason).where(
                g.intent_id.in_(intent_ids)
            )
        ).label("guards"),
        _rows(
            select(
                b.id,
                b.intent_id,
                b.package_id,
                b.package_version,
                b.seal_id,
                b.origin_hub_id,
                b.created_at,
                b.classification,
                b.outbound_state,
                b.tracking_number,
                and_(
                    b.label_content.is_not(None),
                    func.octet_length(b.label_content) > 0,
                    b.label_media_type.is_not(None),
                    b.label_sha256.is_not(None),
                ).label("label_available"),
                b.handoff_recorded_at,
                b.last_tracking_refresh_at,
                b.claim_expires_at,
                b.reconciliation_resolution,
                b.reconciliation_recorded_at,
            ).where(b.order_id == order_id, b.provider == "dhl")
        ).label("bookings"),
        _rows(
            select(CustodyEvent.package_id, CustodyEvent.package_version).where(
                CustodyEvent.package_id.in_(package_ids),
                CustodyEvent.event_type.in_(
                    ("released", "tendered", "provider_accepted")
                ),
            )
        ).label("handoffs"),
        _rows(selected_quotes).label("quotes"),
        _rows(
            select(HubPackageVersion.package_id, HubPackageVersion.version).where(
                HubPackageVersion.package_id.in_(package_ids)
            )
        ).label("versions"),
        _rows(
            select(HubPackageItem.package_id, HubPackageItem.package_version).where(
                HubPackageItem.package_id.in_(package_ids)
            )
        ).label("items"),
    )


def _date(value):
    return datetime.fromisoformat(value) if isinstance(value, str) else value


def project_operations(snapshot):
    """Fail closed on ambiguous bindings or contradictions; never change rows."""
    rows = {
        key: snapshot.get(key) or []
        for key in (
            "packages",
            "seals",
            "intents",
            "guards",
            "bookings",
            "handoffs",
            "quotes",
            "versions",
            "items",
        )
    }
    bookings = {b["id"]: b for b in rows["bookings"]}
    guards = {g["intent_id"]: g for g in rows["guards"]}
    inconsistent = set()
    intent_records = {i["id"]: i for i in rows["intents"]}
    for b in bookings.values():
        intent = intent_records.get(b["intent_id"])
        if (
            not intent
            or any(
                b[k] != intent[k]
                for k in ("package_id", "package_version", "seal_id", "origin_hub_id")
            )
            or bool(b["reconciliation_resolution"])
            != bool(b["reconciliation_recorded_at"])
            or (
                b["reconciliation_resolution"] == "confirm_success"
                and b["classification"] != "success"
            )
            or (
                b["reconciliation_resolution"] == "confirm_failure"
                and b["classification"] != "failure"
            )
        ):
            inconsistent.add(b["intent_id"])
    for intent_id in {b["intent_id"] for b in bookings.values()} | set(guards):
        guard = guards.get(intent_id)
        active = [
            b
            for b in bookings.values()
            if b["intent_id"] == intent_id and b["classification"] != "failure"
        ]
        guarded = bookings.get(guard["active_booking_id"]) if guard else None
        if (
            len(active) > 1
            or (active and (not guard or guard["active_booking_id"] != active[0]["id"]))
            or (
                guard
                and guard["active_booking_id"]
                and (
                    not guarded
                    or guarded["intent_id"] != intent_id
                    or guarded["classification"] == "failure"
                )
            )
            or (
                guard
                and guard["booking_blocked_reason"]
                and (
                    guard["booking_blocked_reason"] != "unknown_outcome"
                    or not guarded
                    or guarded["classification"] != "unknown"
                )
            )
        ):
            inconsistent.add(intent_id)
    result_bookings = []
    states = {}
    for b in sorted(bookings.values(), key=lambda b: (b["created_at"], b["id"])):
        guard = guards.get(b["intent_id"])
        if b["intent_id"] in inconsistent:
            state = "inconsistent"
        elif b["reconciliation_resolution"] and b["reconciliation_recorded_at"]:
            state = "resolved"
        elif b["classification"] == "unknown" or (
            guard and guard["booking_blocked_reason"] == "unknown_outcome"
        ):
            state = "required"
        elif b["classification"] == "pending":
            state = (
                "expired_claim_requires_recovery"
                if _date(b["claim_expires_at"]) <= _date(snapshot["read_at"])
                else "in_progress"
            )
        else:
            state = "not_required"
        states[b["id"]] = state
        result_bookings.append(
            {
                **{
                    key: b[key]
                    for key in (
                        "intent_id",
                        "package_id",
                        "package_version",
                        "seal_id",
                        "origin_hub_id",
                        "created_at",
                        "classification",
                        "outbound_state",
                        "tracking_number",
                        "label_available",
                        "handoff_recorded_at",
                        "last_tracking_refresh_at",
                        "reconciliation_resolution",
                        "reconciliation_recorded_at",
                    )
                },
                "booking_id": b["id"],
                "reconciliation_state": state,
            }
        )
    packages = []
    for p in sorted(rows["packages"], key=lambda p: p["id"]):
        blockers = []
        pid, version = p["id"], p["current_version"]
        same = lambda r: r["package_id"] == pid and r["package_version"] == version
        seals = [s for s in rows["seals"] if same(s)]
        seal = seals[0] if len(seals) == 1 else None
        intents = [
            i
            for i in rows["intents"]
            if same(i)
            and not i.get("invalidated")
            and seal
            and i["seal_id"] == seal["id"]
            and i["origin_hub_id"] == p["hub_id"]
        ]
        intent = intents[0] if len(intents) == 1 else None
        guard = guards.get(intent["id"]) if intent else None
        active_id = guard["active_booking_id"] if guard else None
        if (
            getattr(snapshot["order_status"], "value", snapshot["order_status"])
            == "cancelled"
        ):
            blockers.append("order_cancelled")
        if p["state"] != "ready" or not p["ready_at"]:
            blockers.append("package_not_ready")
        if any(same(r) for r in rows["handoffs"]):
            blockers.append("custody_handed_off")
        if not seal:
            blockers.append("active_seal_missing")
        if not intent:
            blockers.append("active_intent_missing")
        quotes = [
            q for q in rows["quotes"] if intent and q["intent_id"] == intent["id"]
        ]
        if not quotes:
            blockers.append("selected_dhl_quote_missing")
        if active_id:
            blockers.append("active_booking_exists")
        subject_bookings = [
            b
            for b in bookings.values()
            if b["package_id"] == pid and b["package_version"] == version
        ]
        if any(states[b["id"]] == "required" for b in subject_bookings):
            blockers.append("reconciliation_required")
        if any(
            states[b["id"]] == "expired_claim_requires_recovery"
            for b in subject_bookings
        ):
            blockers.append("expired_claim_requires_recovery")
        if (
            len(seals) > 1
            or len(intents) > 1
            or len(quotes) > 1
            or (intent and intent["id"] in inconsistent)
            or any(
                b["intent_id"] in inconsistent
                or (
                    b["classification"] != "failure"
                    and (not intent or b["intent_id"] != intent["id"])
                )
                for b in subject_bookings
            )
            or not any(
                r["package_id"] == pid and r["version"] == version
                for r in rows["versions"]
            )
            or not any(same(r) for r in rows["items"])
        ):
            blockers.append("inconsistent_persisted_state")
        packages.append(
            {
                "package_id": pid,
                "package_version": version,
                "origin_hub_id": p["hub_id"],
                "package_state": p["state"],
                "ready_at": p["ready_at"],
                "seal_id": seal["id"] if seal else None,
                "intent_id": intent["id"] if intent else None,
                "active_booking_id": active_id,
                "selection_eligible": not blockers,
                "selection_blockers": blockers,
            }
        )
    return {
        "read_at": snapshot["read_at"],
        "packages": packages,
        "bookings": result_bookings,
    }


async def load_dhl_operations(db: AsyncSession, *, order_id: UUID):
    snapshot = (await db.execute(operations_snapshot_query(order_id))).mappings().one()
    return project_operations(snapshot)
