"""DHL Express live map tracking, checkpoint projection, and sandbox step simulator."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import logging
from typing import Any, Dict, List, Optional
import uuid

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.address import Address
from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimate,
    CheckoutShippingEstimateOption,
    CheckoutShippingEstimateSelection,
)
from app.models.dhl_shipment import (
    OutboundShipmentBooking,
    OutboundShipmentTrackingSnapshot,
)
from app.models.fulfillment_hub import FulfillmentHub
from app.models.order import FulfillmentStatus, Order
from app.models.package_custody import OutboundShipmentIntent
from app.models.user import User, UserRole
from app.services.dhl.hub_preparation import ensure_custody_released_for_booking
from app.services.dhl.shipments import (
    HandoffCommand,
    TrackingRefreshCommand,
    record_collection_handoff,
    refresh_tracking,
)
from app.services.shipping.shipbubble_tracking import (
    DEFAULT_ORIGIN_HUB,
    _generate_route_waypoints,
    _interpolate_along_waypoints,
    _resolve_coordinates_for_address,
)

logger = logging.getLogger(__name__)


def _dhl_state_to_progress_and_label(
    outbound_state: Optional[str],
    current_status: str,
    courier_name: str,
    origin_city: str,
    dest_city: str,
    is_booked: bool,
) -> tuple[float, str]:
    state = (outbound_state or "").lower().strip()
    if state == "delivered" or current_status == "delivered":
        return 1.0, f"Delivered by {courier_name} in {dest_city}"
    if state == "out_for_delivery" or current_status == "out_for_delivery":
        return 0.88, f"Arrived in {dest_city} — Out for delivery with {courier_name} courier"
    if state == "in_transit" or current_status == "in_transit":
        return 0.62, f"In transit via {courier_name} domestic network towards {dest_city}"
    if state == "collected" or current_status == "picked_up":
        return 0.28, f"Collected by {courier_name} — Departed {origin_city} Hub"
    if state == "exception" or current_status == "delivery_failed":
        return 0.90, f"Delivery exception reported by {courier_name} in {dest_city}"
    if is_booked or state in {"booked", "label_ready", "awaiting_collection"}:
        return 0.10, f"DHL Express waybill & label ready at {origin_city} Hub — Awaiting courier collection"
    return 0.04, f"Preparing package at {origin_city} Hub for {courier_name} dispatch"


async def is_dhl_order(db: AsyncSession, *, order: Order) -> bool:
    if order.delivery_provider:
        prov = order.delivery_provider.lower().strip()
        if prov == "dhl":
            return True
        if prov == "manual" or prov == "shipbubble" or prov.startswith("shipbubble"):
            return False
    booking_id = await db.scalar(
        select(OutboundShipmentBooking.id)
        .where(OutboundShipmentBooking.order_id == order.id)
        .limit(1)
    )
    if booking_id is not None:
        return True
    if order.checkout_estimate_selection_id is not None:
        est_kind = await db.scalar(
            select(CheckoutShippingEstimate.source_kind)
            .join(
                CheckoutShippingEstimateSelection,
                CheckoutShippingEstimateSelection.estimate_id
                == CheckoutShippingEstimate.id,
            )
            .where(
                CheckoutShippingEstimateSelection.id
                == order.checkout_estimate_selection_id
            )
        )
        if est_kind == "sandbox_normalized":
            return True
    latest_est_kind = await db.scalar(
        select(CheckoutShippingEstimate.source_kind)
        .where(CheckoutShippingEstimate.order_id == order.id)
        .order_by(CheckoutShippingEstimate.created_at.desc())
        .limit(1)
    )
    return latest_est_kind == "sandbox_normalized"


async def build_dhl_live_tracking_payload(
    db: AsyncSession,
    *,
    order: Order,
    current_status: str,
) -> Optional[Dict[str, Any]]:
    """Build live DHL Express tracking & Leaflet map data for an order."""
    if not await is_dhl_order(db, order=order):
        return None

    booking = (
        await db.execute(
            select(OutboundShipmentBooking)
            .where(OutboundShipmentBooking.order_id == order.id)
            .order_by(OutboundShipmentBooking.claimed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    intent: Optional[OutboundShipmentIntent] = None
    if booking is not None:
        intent = await db.get(OutboundShipmentIntent, booking.intent_id)
    if intent is None:
        intent = (
            await db.execute(
                select(OutboundShipmentIntent)
                .where(OutboundShipmentIntent.order_id == order.id)
                .order_by(OutboundShipmentIntent.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    hub: Optional[FulfillmentHub] = None
    if booking is not None:
        hub = await db.get(FulfillmentHub, booking.origin_hub_id)
    elif intent is not None:
        hub = await db.get(FulfillmentHub, intent.origin_hub_id)
    if hub is None:
        hub = (
            await db.execute(
                select(FulfillmentHub)
                .where(FulfillmentHub.is_active.is_(True))
                .order_by(FulfillmentHub.id)
                .limit(1)
            )
        ).scalar_one_or_none()

    origin_city = hub.city if hub else DEFAULT_ORIGIN_HUB["city"]
    origin_state = hub.state if hub else DEFAULT_ORIGIN_HUB["state"]
    origin_name = hub.name if hub else "ShopSoma Lagos Hub"
    origin_address = (
        f"{hub.address_line1}, {hub.city}, {hub.state}, Nigeria"
        if hub
        else DEFAULT_ORIGIN_HUB["address"]
    )
    origin_lat, origin_lng = _resolve_coordinates_for_address(
        origin_city, origin_state, origin_address
    )

    dest_addr = (
        await db.get(Address, order.shipping_address_id)
        if order.shipping_address_id
        else None
    )
    dest_name = (
        (intent.destination_name if intent else None)
        or (getattr(dest_addr, "recipient_name", None) if dest_addr else None)
        or "Customer"
    )
    dest_city = (
        (intent.destination_city if intent else None)
        or (dest_addr.city if dest_addr else None)
        or "Lagos"
    )
    dest_state = (
        (intent.destination_state if intent else None)
        or (dest_addr.state if dest_addr else None)
        or "Lagos"
    )
    dest_line1 = (
        (intent.destination_address_line1 if intent else None)
        or (getattr(dest_addr, "street_address", None) if dest_addr else None)
        or "Customer Delivery Address"
    )
    dest_address_str = f"{dest_line1}, {dest_city}, {dest_state}, Nigeria"
    dest_lat, dest_lng = _resolve_coordinates_for_address(
        dest_city, dest_state, dest_address_str
    )
    if abs(dest_lat - origin_lat) < 0.005 and abs(dest_lng - origin_lng) < 0.005:
        # Add a realistic intra-city offset when origin and destination are in the same district
        dest_lat = round(origin_lat + 0.045, 6)
        dest_lng = round(origin_lng + 0.062, 6)

    selected_option: Optional[CheckoutShippingEstimateOption] = None
    if order.checkout_estimate_selection_id is not None:
        sel = await db.get(
            CheckoutShippingEstimateSelection, order.checkout_estimate_selection_id
        )
        if sel is not None:
            selected_option = await db.get(CheckoutShippingEstimateOption, sel.option_id)

    service_label = (
        (selected_option.service_label if selected_option else None)
        or "EXPRESS DOMESTIC"
    )
    service_code = (
        (booking.service_code if booking and booking.service_code else None)
        or (selected_option.service_code if selected_option else None)
        or "N"
    )
    delivery_eta = (
        f"Est. {order.estimated_delivery_date.isoformat()}"
        if order.estimated_delivery_date
        else (
            f"{selected_option.max_delivery_days} business days"
            if selected_option and selected_option.max_delivery_days
            else "1-3 business days"
        )
    )
    courier_name = f"DHL Express ({service_label})"

    is_booked = bool(
        booking is not None
        and booking.classification == "success"
        and booking.tracking_number
    )
    outbound_state = booking.outbound_state if booking is not None else None
    waypoints = _generate_route_waypoints((origin_lat, origin_lng), (dest_lat, dest_lng))
    progress, location_label = _dhl_state_to_progress_and_label(
        outbound_state,
        current_status,
        "DHL Express",
        origin_city,
        dest_city,
        is_booked,
    )
    curr_lat, curr_lng = _interpolate_along_waypoints(waypoints, progress)

    snapshots: List[OutboundShipmentTrackingSnapshot] = []
    if booking is not None:
        snapshots = list(
            (
                await db.execute(
                    select(OutboundShipmentTrackingSnapshot)
                    .where(OutboundShipmentTrackingSnapshot.booking_id == booking.id)
                    .order_by(OutboundShipmentTrackingSnapshot.observed_at.asc())
                )
            ).scalars().all()
        )

    events: List[Dict[str, Any]] = []
    if booking is not None and booking.result_recorded_at is not None and is_booked:
        events.append(
            {
                "status_code": "BOOKED",
                "outbound_state": "label_ready",
                "customer_status": "label_created",
                "description": f"DHL Express waybill #{booking.tracking_number} created and PDF label generated",
                "observed_at": booking.result_recorded_at.isoformat(),
                "location": f"{origin_city} Hub",
            }
        )
    for snap in snapshots:
        events.append(
            {
                "status_code": snap.provider_status_code,
                "outbound_state": snap.outbound_state,
                "customer_status": snap.customer_status,
                "description": snap.detail,
                "observed_at": snap.observed_at.isoformat(),
                "exception_code": snap.exception_code,
                "location": dest_city
                if snap.outbound_state in {"out_for_delivery", "delivered", "exception"}
                else origin_city,
            }
        )

    tracking_number = (
        (booking.tracking_number if booking and booking.tracking_number else None)
        or order.tracking_number
    )
    tracking_url = (
        f"https://www.dhl.com/ng-en/home/tracking/tracking-express.html?submit=1&tracking-id={tracking_number}"
        if tracking_number
        else None
    )
    waybill_url = (
        f"/api/v1/admin/orders/{order.id}/dhl/bookings/{booking.id}/label"
        if booking is not None and booking.label_sha256
        else None
    )
    updated_at_iso = (
        snapshots[-1].observed_at.isoformat()
        if snapshots
        else (
            booking.result_recorded_at.isoformat()
            if booking and booking.result_recorded_at
            else order.updated_at.isoformat()
        )
    )

    return {
        "provider": "dhl",
        "is_sandbox": settings.DHL_ENVIRONMENT == "sandbox",
        "is_booked": is_booked,
        "booking_id": str(booking.id) if booking else None,
        "shipbubble_order_id": booking.provider_reference if booking else None,
        "courier_name": courier_name,
        "courier_image": None,
        "service_code": service_code,
        "delivery_eta": delivery_eta,
        "shipment_status": outbound_state or current_status,
        "tracking_code": tracking_number,
        "tracking_url": tracking_url,
        "waybill_document_url": waybill_url,
        "handoff_recorded_at": (
            booking.handoff_recorded_at.isoformat()
            if booking and booking.handoff_recorded_at
            else None
        ),
        "origin": {
            "lat": origin_lat,
            "lng": origin_lng,
            "name": origin_name,
            "city": origin_city,
            "state": origin_state,
            "address": origin_address,
        },
        "destination": {
            "lat": dest_lat,
            "lng": dest_lng,
            "name": dest_name,
            "city": dest_city,
            "state": dest_state,
            "address": dest_address_str,
        },
        "current_location": {
            "lat": curr_lat,
            "lng": curr_lng,
            "progress": round(progress, 2),
            "status_label": location_label,
            "updated_at": updated_at_iso,
        },
        "route_waypoints": [[lat, lng] for lat, lng in waypoints],
        "events": events,
    }


async def sync_dhl_shipment_status(
    db: AsyncSession,
    *,
    order: Order,
) -> Optional[OutboundShipmentBooking]:
    """Query MyDHL Tracking API for the order's active booking and persist checkpoints."""
    booking = (
        await db.execute(
            select(OutboundShipmentBooking)
            .where(
                OutboundShipmentBooking.order_id == order.id,
                OutboundShipmentBooking.classification == "success",
            )
            .order_by(OutboundShipmentBooking.claimed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if booking is None or not booking.tracking_number:
        return booking

    try:
        idem_key = f"sync-dhl-{booking.id.hex[:16]}-{int(datetime.now(timezone.utc).timestamp())}"
        await refresh_tracking(
            db,
            order_id=order.id,
            settings=settings,
            command=TrackingRefreshCommand(
                order_id=order.id,
                booking_id=booking.id,
                idempotency_key=idem_key,
            ),
        )
        await db.commit()
        await db.refresh(order)
        await db.refresh(booking)
    except Exception as exc:
        logger.warning("[DHL] Live tracking poll note for %s: %s", booking.tracking_number, exc)
        await db.rollback()
    return booking


async def simulate_dhl_tracking_step(
    db: AsyncSession,
    *,
    order: Order,
    target_status: str,
    actor_id: Optional[uuid.UUID] = None,
) -> None:
    """Simulate a MyDHL checkpoint event and custody transition in Sandbox mode."""
    if settings.DHL_ENVIRONMENT != "sandbox":
        raise HTTPException(
            status_code=403,
            detail="DHL tracking simulation is only available in sandbox mode",
        )

    booking = (
        await db.execute(
            select(OutboundShipmentBooking)
            .where(
                OutboundShipmentBooking.order_id == order.id,
                OutboundShipmentBooking.classification == "success",
            )
            .order_by(OutboundShipmentBooking.claimed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if booking is None or not booking.tracking_number:
        raise HTTPException(
            status_code=400,
            detail="Create a DHL shipment booking before simulating tracking checkpoints",
        )

    step_definitions = {
        "order_placed": (
            "BOOKED",
            "label_ready",
            "label_created",
            "Shipment booked and waybill generated at Lagos Hub",
            None,
            FulfillmentStatus.PREPARING_FOR_PICKUP,
        ),
        "picked_up": (
            "PU",
            "collected",
            "picked_up",
            "Shipment collected by DHL Express courier at Lagos Hub",
            None,
            FulfillmentStatus.PICKED_UP,
        ),
        "in_transit": (
            "TRANSIT",
            "in_transit",
            "in_transit",
            "Shipment in transit through DHL Express Nigeria domestic sort facility",
            None,
            FulfillmentStatus.IN_TRANSIT,
        ),
        "out_for_delivery": (
            "OOD",
            "out_for_delivery",
            "out_for_delivery",
            "Shipment out for delivery with DHL Express courier",
            None,
            FulfillmentStatus.OUT_FOR_DELIVERY,
        ),
        "delivered": (
            "OK",
            "delivered",
            "delivered",
            "Shipment delivered and signed for by recipient",
            None,
            FulfillmentStatus.DELIVERED,
        ),
        "delivery_failed": (
            "FAILURE",
            "exception",
            "delivery_exception",
            "Delivery exception: recipient unavailable at destination address",
            "FAILURE",
            FulfillmentStatus.DELIVERY_FAILED,
        ),
    }
    if target_status not in step_definitions:
        raise HTTPException(status_code=422, detail="Invalid simulation status")

    (
        provider_code,
        outbound_state,
        customer_status,
        detail,
        exception_code,
        fulfillment_enum,
    ) = step_definitions[target_status]

    admin_user = (
        await db.execute(select(User).where(User.role == UserRole.ADMIN).limit(1))
    ).scalar_one_or_none()
    resolved_actor_id = actor_id or (admin_user.id if admin_user else order.customer_id)

    # Ensure custody stream is at 'released' before recording carrier acceptance/handoff
    await ensure_custody_released_for_booking(
        db,
        package_id=booking.package_id,
        package_version=booking.package_version,
        seal_id=booking.seal_id,
        actor_id=str(resolved_actor_id or "dhl-simulator"),
    )

    if target_status != "order_placed":
        # If jumping ahead of picked_up and handoff isn't recorded yet, ensure a
        # verified PU/collected acceptance snapshot exists first so handoff can
        # be recorded cleanly.
        if booking.handoff_recorded_at is None and outbound_state != "collected":
            existing_pu = (
                await db.execute(
                    select(OutboundShipmentTrackingSnapshot)
                    .where(
                        OutboundShipmentTrackingSnapshot.booking_id == booking.id,
                        OutboundShipmentTrackingSnapshot.outbound_state == "collected",
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing_pu is None:
                pu_time = await db.scalar(text("SELECT clock_timestamp()"))
                assert pu_time is not None
                pu_snap = OutboundShipmentTrackingSnapshot(
                    booking_id=booking.id,
                    order_id=order.id,
                    provider="dhl",
                    tracking_number=booking.tracking_number,
                    provider_status_code="PU",
                    outbound_state="collected",
                    customer_status="picked_up",
                    detail="Shipment collected by DHL Express courier at Lagos Hub",
                    observed_at=pu_time,
                    recorded_at=pu_time,
                    idempotency_key=f"sim-pu-{booking.id.hex[:16]}-{uuid.uuid4().hex[:8]}",
                    source_command="dhl_sandbox_simulator",
                )
                db.add(pu_snap)
                await db.flush()

        now = await db.scalar(text("SELECT clock_timestamp()"))
        assert now is not None
        snap = OutboundShipmentTrackingSnapshot(
            booking_id=booking.id,
            order_id=order.id,
            provider="dhl",
            tracking_number=booking.tracking_number,
            provider_status_code=provider_code,
            outbound_state=outbound_state,
            customer_status=customer_status,
            detail=detail,
            exception_code=exception_code,
            observed_at=now,
            recorded_at=now,
            idempotency_key=f"sim-{target_status}-{booking.id.hex[:12]}-{uuid.uuid4().hex[:8]}",
            source_command="dhl_sandbox_simulator",
        )
        db.add(snap)
        await db.flush()

        # Record Hub-to-DHL handoff if not yet recorded
        if booking.handoff_recorded_at is None and admin_user is not None:
            try:
                handoff_time = await db.scalar(text("SELECT clock_timestamp()"))
                assert handoff_time is not None
                evidence_ref = f"dhl-sandbox-handoff-{booking.tracking_number}"
                await record_collection_handoff(
                    db,
                    order_id=order.id,
                    admin=admin_user,
                    command=HandoffCommand(
                        order_id=order.id,
                        booking_id=booking.id,
                        counterparty="DHL Express Sandbox Courier",
                        evidence_ref=evidence_ref,
                        evidence_sha256=hashlib.sha256(
                            evidence_ref.encode("utf-8")
                        ).hexdigest(),
                        occurred_at=handoff_time,
                        idempotency_key=f"sim-handoff-{booking.id.hex}",
                    ),
                )
            except Exception as exc:
                logger.info("[DHL Simulator] Handoff auto-record note: %s", exc)

    booking.outbound_state = outbound_state
    booking.last_tracking_refresh_at = await db.scalar(text("SELECT clock_timestamp()"))
    order.fulfillment_status = fulfillment_enum
    if fulfillment_enum == FulfillmentStatus.DELIVERED and order.delivered_at is None:
        order.delivered_at = booking.last_tracking_refresh_at

    db.add(booking)
    db.add(order)
    await db.commit()
    await db.refresh(order)
