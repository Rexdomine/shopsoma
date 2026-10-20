"""Authenticated MyDHL Express Webhook Receiver with idempotent checkpoint folding.

Supports HMAC-SHA256 (`X-DHL-Signature`) and HTTP Basic Auth verification,
duplicate event deduplication via `uq_outbound_shipment_tracking_snapshots_observation`,
and monotonic out-of-order state folding.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.models.dhl_shipment import (
    OutboundShipmentBooking,
    OutboundShipmentTrackingSnapshot,
)
from app.models.order import FulfillmentStatus, Order
from app.services.dhl.shipments import (
    MAX_TRACKING_DETAIL_LENGTH,
    MAX_TRACKING_EXCEPTION_CODE_LENGTH,
    MAX_TRACKING_STATUS_CODE_LENGTH,
    PROVIDER,
    TERMINAL_TRACKING_EXCEPTION_CODES,
    TrackingObservation,
    _aggregate_order_delivered_at,
    _aggregate_order_outbound_state,
    _bounded_tracking_code,
    _bounded_tracking_detail,
    _derived_handoff_idempotency_key,
    _highest_effective_tracking_snapshot_for_handoff,
    _is_unique_constraint_violation,
    _map_tracking_status,
    _state_rank,
    _tracking_exception_code,
    _tracking_observed_at,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipping/webhooks", tags=["Shipping Webhooks"])


def _verify_dhl_webhook_auth(
    *,
    raw_body: bytes,
    x_dhl_signature: Optional[str],
    authorization: Optional[str],
) -> None:
    """Verify either HMAC-SHA256 signature or Basic Auth credentials."""
    secret = settings.DHL_API_PASSWORD.get_secret_value() or settings.SECRET_KEY
    username = settings.DHL_API_USERNAME.get_secret_value()
    password = settings.DHL_API_PASSWORD.get_secret_value()

    if x_dhl_signature and secret:
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        candidate = x_dhl_signature.strip()
        if candidate.lower().startswith("sha256="):
            candidate = candidate.split("=", 1)[1].strip()
        if hmac.compare_digest(expected_sig.lower(), candidate.lower()):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid DHL webhook signature",
        )

    if authorization and authorization.strip().lower().startswith("basic ") and username and password:
        encoded = authorization.strip()[6:].strip()
        expected_basic = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        if hmac.compare_digest(encoded, expected_basic):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid DHL webhook credentials",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing DHL webhook authentication",
    )


def _extract_shipment_events(payload: Dict[str, Any]) -> List[tuple[str, List[Dict[str, Any]], Optional[str]]]:
    """Extract (tracking_number, events, shipment_timestamp) tuples from a DHL webhook payload."""
    results: List[tuple[str, List[Dict[str, Any]], Optional[str]]] = []
    shipments = payload.get("shipments")
    if isinstance(shipments, list):
        for item in shipments:
            if not isinstance(item, dict):
                continue
            tracking = str(
                item.get("shipmentTrackingNumber")
                or item.get("trackingNumber")
                or ""
            ).strip()
            events = item.get("events") or item.get("checkpoints") or []
            if tracking and isinstance(events, list):
                results.append((tracking, events, item.get("timestamp")))
    else:
        tracking = str(
            payload.get("shipmentTrackingNumber")
            or payload.get("trackingNumber")
            or ""
        ).strip()
        events = payload.get("events") or payload.get("checkpoints")
        if events is None and (payload.get("typeCode") or payload.get("statusCode")):
            events = [payload]
        if tracking and isinstance(events, list):
            results.append((tracking, events, payload.get("timestamp")))
    return results


@router.post("/dhl", status_code=status.HTTP_200_OK)
async def dhl_webhook(
    request: Request,
    x_dhl_signature: Optional[str] = Header(None, alias="X-DHL-Signature"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Receive and process authenticated MyDHL Express tracking webhook events."""
    raw_body = await request.body()
    _verify_dhl_webhook_auth(
        raw_body=raw_body,
        x_dhl_signature=x_dhl_signature,
        authorization=authorization,
    )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload structure",
        )

    shipment_entries = _extract_shipment_events(payload)
    if not shipment_entries:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Webhook payload missing trackingNumber or events",
        )

    payload_hash = hashlib.sha256(raw_body).hexdigest()
    total_inserted = 0
    total_replayed = 0
    processed_bookings: List[str] = []

    for tracking_number, raw_events, shipment_ts in shipment_entries:
        booking = (
            await db.execute(
                select(OutboundShipmentBooking)
                .where(
                    OutboundShipmentBooking.provider == PROVIDER,
                    OutboundShipmentBooking.tracking_number == tracking_number,
                    OutboundShipmentBooking.classification == "success",
                )
                .order_by(OutboundShipmentBooking.claimed_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if booking is None:
            continue

        order = (
            await db.execute(
                select(Order)
                .options(selectinload(Order.customer), selectinload(Order.items))
                .where(Order.id == booking.order_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if order is None or order.fulfillment_status == FulfillmentStatus.CANCELLED:
            continue

        booking = (
            await db.execute(
                select(OutboundShipmentBooking)
                .where(OutboundShipmentBooking.id == booking.id)
                .with_for_update()
            )
        ).scalar_one()

        old_status = order.fulfillment_status
        observations: List[TrackingObservation] = []
        for idx, cp in enumerate(raw_events):
            if not isinstance(cp, dict):
                continue
            codes = [
                str(raw).strip().upper()
                for raw in (
                    cp.get("typeCode"),
                    cp.get("statusCode"),
                    cp.get("code"),
                    cp.get("eventCode"),
                )
                if raw is not None and str(raw).strip()
            ]
            code = _bounded_tracking_code(
                codes[0] if codes else "UNKNOWN",
                field="provider_status_code",
                max_length=MAX_TRACKING_STATUS_CODE_LENGTH,
            )
            outbound_state, customer_status = _map_tracking_status(*codes)
            detail = _bounded_tracking_detail(
                cp.get("description")
                or cp.get("detail")
                or cp.get("remark")
                or code
            )
            observed_at = _tracking_observed_at(
                checkpoint=cp,
                shipment={"timestamp": shipment_ts},
                response=payload,
            ) or (datetime.now(UTC) + timedelta(microseconds=idx))
            observations.append(
                TrackingObservation(
                    provider_status_code=code,
                    outbound_state=outbound_state,
                    customer_status=customer_status,
                    detail=detail,
                    observed_at=observed_at,
                    exception_code=_tracking_exception_code(
                        codes,
                        outbound_state=outbound_state,
                    ),
                )
            )

        for pos, obs in enumerate(observations):
            idem_key = _derived_handoff_idempotency_key(
                f"dhl-wh:{payload_hash[:32]}",
                f":{tracking_number}:{pos}",
            )
            existing_by_key = await db.scalar(
                select(OutboundShipmentTrackingSnapshot.id).where(
                    OutboundShipmentTrackingSnapshot.booking_id == booking.id,
                    OutboundShipmentTrackingSnapshot.idempotency_key == idem_key,
                )
            )
            if existing_by_key is not None:
                total_replayed += 1
                continue

            recorded_at = await db.scalar(text("SELECT clock_timestamp()"))
            assert recorded_at is not None
            effective_observed = min(obs.observed_at, recorded_at)
            snapshot = OutboundShipmentTrackingSnapshot(
                booking_id=booking.id,
                order_id=booking.order_id,
                provider=PROVIDER,
                tracking_number=tracking_number,
                provider_status_code=obs.provider_status_code,
                outbound_state=obs.outbound_state,
                customer_status=obs.customer_status,
                detail=obs.detail,
                exception_code=obs.exception_code,
                observed_at=effective_observed,
                recorded_at=recorded_at,
                idempotency_key=idem_key,
                source_command="dhl_webhook",
            )
            try:
                async with db.begin_nested():
                    db.add(snapshot)
                    await db.flush()
                total_inserted += 1
            except IntegrityError as exc:
                if _is_unique_constraint_violation(
                    exc,
                    constraint_name="uq_outbound_shipment_tracking_snapshots_observation",
                ) or _is_unique_constraint_violation(
                    exc,
                    constraint_name="uq_outbound_shipment_tracking_snapshots_replay",
                ):
                    total_replayed += 1
                else:
                    raise

        # Fold all snapshots monotonically so out-of-order events never regress state
        all_snapshots = list(
            (
                await db.execute(
                    select(OutboundShipmentTrackingSnapshot)
                    .where(OutboundShipmentTrackingSnapshot.booking_id == booking.id)
                    .order_by(OutboundShipmentTrackingSnapshot.observed_at.asc())
                )
            ).scalars().all()
        )
        effective = _highest_effective_tracking_snapshot_for_handoff(all_snapshots)
        if effective is not None:
            chosen = effective.snapshot
            now_clock = await db.scalar(text("SELECT clock_timestamp()"))
            booking.last_tracking_refresh_at = now_clock
            if (
                booking.handoff_recorded_at is None
                and chosen.outbound_state in {"collected", "in_transit", "out_for_delivery", "delivered"}
            ):
                from app.services.dhl.hub_preparation import ensure_hub_prep_ready_for_handoff
                from app.services.dhl.shipments import HandoffCommand, record_collection_handoff

                effective_occurred_at = await ensure_hub_prep_ready_for_handoff(
                    db,
                    order_id=order.id,
                    booking_id=booking.id,
                    actor_id=booking.initiating_actor_id,
                    occurred_at=chosen.observed_at,
                )
                actor = None
                try:
                    import uuid as _uuid
                    from app.models.user import User, UserRole

                    actor = await db.get(User, _uuid.UUID(str(booking.initiating_actor_id)))
                except Exception:
                    actor = None
                if actor is None:
                    try:
                        from app.models.user import User, UserRole

                        actor = (
                            await db.execute(select(User).where(User.role == UserRole.ADMIN).limit(1))
                        ).scalar_one_or_none()
                    except Exception:
                        actor = None
                if actor is not None:
                    try:
                        async with db.begin_nested():
                            await record_collection_handoff(
                                db,
                                order_id=order.id,
                                admin=actor,
                                command=HandoffCommand(
                                    booking_id=booking.id,
                                    occurred_at=effective_occurred_at or chosen.observed_at,
                                    idempotency_key=f"dhl-wh-handoff-{booking.id.hex[:20]}",
                                    counterparty="DHL Express",
                                    evidence_ref=f"evidence/dhl/webhook-{booking.id.hex[:16]}",
                                    evidence_sha256=hashlib.sha256(f"dhl-wh-{booking.id.hex}".encode("utf-8")).hexdigest(),
                                ),
                            )
                    except Exception as handoff_exc:
                        logger.info("[DHL Webhook] Auto-handoff note: %s", handoff_exc)
            if chosen.outbound_state == "exception":
                if booking.handoff_recorded_at is not None:
                    booking.outbound_state = "exception"
                    booking.latest_exception_code = chosen.exception_code
            elif booking.handoff_recorded_at is not None:
                if (
                    booking.outbound_state == "exception"
                    and (booking.latest_exception_code or "").upper() not in TERMINAL_TRACKING_EXCEPTION_CODES
                    and chosen.outbound_state == "delivered"
                ):
                    booking.outbound_state = "delivered"
                elif (
                    booking.outbound_state != "exception"
                    and _state_rank(chosen.outbound_state) > _state_rank(booking.outbound_state)
                ):
                    booking.outbound_state = chosen.outbound_state

            aggregate_state = await _aggregate_order_outbound_state(
                db,
                order_id=order.id,
                fallback=booking.outbound_state,
            )
            if booking.handoff_recorded_at is not None:
                if aggregate_state == "collected":
                    order.fulfillment_status = FulfillmentStatus.PICKED_UP
                elif aggregate_state == "in_transit":
                    order.fulfillment_status = FulfillmentStatus.IN_TRANSIT
                elif aggregate_state == "out_for_delivery":
                    order.fulfillment_status = FulfillmentStatus.OUT_FOR_DELIVERY
                elif aggregate_state == "delivered":
                    order.fulfillment_status = FulfillmentStatus.DELIVERED
                    if order.delivered_at is None:
                        order.delivered_at = await _aggregate_order_delivered_at(
                            db,
                            order_id=order.id,
                            fallback=effective.resolved_observed_at,
                        )
                elif aggregate_state == "exception":
                    order.fulfillment_status = FulfillmentStatus.DELIVERY_FAILED

        await db.commit()
        processed_bookings.append(str(booking.id))

        try:
            from app.api.v1.admin_orders import (
                _broadcast_order_update,
                _notify_order_status_change,
            )

            await _notify_order_status_change(db, order=order, old_status=old_status)
            await _broadcast_order_update(order)
        except Exception as exc:
            logger.warning("[DHL Webhook] Notification/broadcast note: %s", exc)

    return {
        "status": "ok",
        "inserted_observations": total_inserted,
        "replayed_observations": total_replayed,
        "processed_bookings": processed_bookings,
    }
