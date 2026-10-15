"""ShipBubble live tracking & map coordinate resolution service."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.address import Address
from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimate,
    CheckoutShippingEstimateOption,
    CheckoutShippingEstimateSelection,
)
from app.models.fulfillment_hub import FulfillmentHub
from app.models.order import FulfillmentStatus, Order, PaymentStatus
from app.models.shipbubble_shipment import ShipbubbleShipment
from app.services.shipbubble_service import (
    _ADDRESS_VALIDATION_CACHE,
    ShipBubbleError,
    get_shipbubble_service,
)
from app.services.shipping.shipbubble_booking import book_shipbubble_shipment_if_selected

logger = logging.getLogger(__name__)

# Comprehensive coordinates for Nigerian states and major cities
NIGERIA_COORDINATES: Dict[str, Tuple[float, float]] = {
    "lagos": (6.5244, 3.3792),
    "lekki": (6.4377, 3.4571),
    "ikeja": (6.6018, 3.3515),
    "victoria island": (6.4281, 3.4219),
    "ikoyi": (6.4549, 3.4246),
    "abuja": (9.0765, 7.3986),
    "fct": (9.0765, 7.3986),
    "federal capital territory": (9.0765, 7.3986),
    "kogi": (7.8023, 6.7333),
    "lokoja": (7.8023, 6.7333),
    "ogun": (7.1475, 3.3619),
    "abeokuta": (7.1475, 3.3619),
    "oyo": (7.3775, 3.9470),
    "ibadan": (7.3775, 3.9470),
    "osun": (7.7827, 4.5418),
    "osogbo": (7.7827, 4.5418),
    "ondo": (7.2571, 5.2058),
    "akure": (7.2571, 5.2058),
    "ekiti": (7.6211, 5.2215),
    "ado ekiti": (7.6211, 5.2215),
    "kwara": (8.4799, 4.5418),
    "ilorin": (8.4799, 4.5418),
    "edo": (6.3350, 5.6037),
    "benin": (6.3350, 5.6037),
    "benin city": (6.3350, 5.6037),
    "delta": (6.2059, 6.6959),
    "asaba": (6.2059, 6.6959),
    "warri": (5.5544, 5.7932),
    "rivers": (4.8156, 7.0498),
    "port harcourt": (4.8156, 7.0498),
    "anambra": (6.2209, 7.0722),
    "awka": (6.2209, 7.0722),
    "onitsha": (6.1413, 6.7857),
    "enugu": (6.4584, 7.5464),
    "imo": (5.4836, 7.0333),
    "owerri": (5.4836, 7.0333),
    "abia": (5.5249, 7.4922),
    "umuahia": (5.5249, 7.4922),
    "aba": (5.1066, 7.3667),
    "ebonyi": (6.3249, 8.1137),
    "abakaliki": (6.3249, 8.1137),
    "cross river": (4.9757, 8.3417),
    "calabar": (4.9757, 8.3417),
    "akwa ibom": (5.0377, 7.9128),
    "uyo": (5.0377, 7.9128),
    "bayelsa": (4.9267, 6.2676),
    "yenagoa": (4.9267, 6.2676),
    "kaduna": (10.5105, 7.4165),
    "kano": (12.0022, 8.5920),
    "katsina": (12.9816, 7.6223),
    "plateau": (9.8965, 8.8583),
    "jos": (9.8965, 8.8583),
    "benue": (7.7322, 8.5391),
    "makurdi": (7.7322, 8.5391),
    "nasarawa": (8.4998, 8.5153),
    "lafia": (8.4998, 8.5153),
    "niger": (9.6139, 6.5569),
    "minna": (9.6139, 6.5569),
    "bauchi": (10.3158, 9.8442),
    "gombe": (10.2897, 11.1673),
    "adamawa": (9.2035, 12.4954),
    "yola": (9.2035, 12.4954),
    "taraba": (8.8937, 11.3596),
    "jalingo": (8.8937, 11.3596),
    "borno": (11.8311, 13.1510),
    "maiduguri": (11.8311, 13.1510),
    "yobe": (11.7470, 11.9608),
    "damaturu": (11.7470, 11.9608),
    "jigawa": (11.7562, 9.3389),
    "dutse": (11.7562, 9.3389),
    "kebbi": (12.4539, 4.1975),
    "birnin kebbi": (12.4539, 4.1975),
    "sokoto": (13.0059, 5.2476),
    "zamfara": (12.1628, 6.6614),
    "gusau": (12.1628, 6.6614),
}

DEFAULT_ORIGIN_HUB = {
    "lat": 6.4377067,
    "lng": 3.4570923,
    "name": "Shopsoma Lagos Central Hub",
    "address": "1 Admiralty Way, Lekki Phase 1, Lekki, Lagos, Nigeria",
    "city": "Lekki",
    "state": "Lagos",
}


def _resolve_coordinates_for_address(
    city: Optional[str],
    state: Optional[str],
    raw_address: Optional[str] = None,
) -> Tuple[float, float]:
    """Resolve (latitude, longitude) from cache or Nigerian city/state lookup."""
    if raw_address:
        addr_lower = raw_address.strip().lower()
        for (_n, _e, _p, cached_addr), val_data in _ADDRESS_VALIDATION_CACHE.items():
            if addr_lower in cached_addr or cached_addr in addr_lower:
                lat = val_data.get("latitude")
                lng = val_data.get("longitude")
                if lat is not None and lng is not None:
                    try:
                        return float(lat), float(lng)
                    except (ValueError, TypeError):
                        pass

    for candidate in (city, state):
        if candidate:
            clean = candidate.strip().lower().replace(" state", "").strip()
            if clean in NIGERIA_COORDINATES:
                return NIGERIA_COORDINATES[clean]
            for key, coords in NIGERIA_COORDINATES.items():
                if key in clean or clean in key:
                    return coords

    return (6.5244, 3.3792)


def _generate_route_waypoints(
    origin: Tuple[float, float],
    destination: Tuple[float, float],
    num_points: int = 24,
) -> List[Tuple[float, float]]:
    """Generate a smooth curved logistics route between origin and destination."""
    lat1, lng1 = origin
    lat2, lng2 = destination
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    dist = (dlat ** 2 + dlng ** 2) ** 0.5

    # Slight highway arc offset perpendicular to straight line
    arc_scale = min(0.28, dist * 0.12)
    waypoints: List[Tuple[float, float]] = []
    for i in range(num_points + 1):
        t = i / num_points
        # Parabolic arc peaking at t=0.5 (4 * t * (1 - t))
        arc = 4.0 * t * (1.0 - t) * arc_scale
        lat = lat1 + dlat * t + arc * 0.65
        lng = lng1 + dlng * t - arc * 0.35
        waypoints.append((round(lat, 6), round(lng, 6)))
    return waypoints


def _status_to_progress_and_label(
    tracking_status: str,
    courier_name: str,
    origin_city: str,
    dest_city: str,
) -> Tuple[float, str]:
    """Map tracking status to route progress (0.0 -> 1.0) and human-readable location label."""
    status_map = {
        "order_placed": (0.06, f"Shipment registered with {courier_name} at {origin_city} Hub"),
        "pending_confirmation": (0.06, f"Awaiting pickup confirmation at {origin_city} Hub"),
        "picked_up": (0.28, f"Collected by {courier_name} — Departed {origin_city} Hub"),
        "in_transit": (0.62, f"In transit with {courier_name} towards {dest_city}"),
        "out_for_delivery": (0.88, f"Arrived in {dest_city} — Out for delivery with {courier_name} rider"),
        "delivered": (1.0, f"Delivered to destination in {dest_city}"),
        "delivery_failed": (0.90, f"Delivery attempt unsuccessful in {dest_city}"),
        "returned": (0.0, f"Returned to {origin_city} Hub"),
        "cancelled": (0.0, "Shipment cancelled"),
    }
    return status_map.get(tracking_status, (0.08, f"Processing with {courier_name}"))


def _interpolate_along_waypoints(
    waypoints: List[Tuple[float, float]],
    progress: float,
) -> Tuple[float, float]:
    if not waypoints:
        return DEFAULT_ORIGIN_HUB["lat"], DEFAULT_ORIGIN_HUB["lng"]
    if progress <= 0.0:
        return waypoints[0]
    if progress >= 1.0:
        return waypoints[-1]
    exact_idx = progress * (len(waypoints) - 1)
    idx = int(exact_idx)
    frac = exact_idx - idx
    if idx >= len(waypoints) - 1:
        return waypoints[-1]
    lat1, lng1 = waypoints[idx]
    lat2, lng2 = waypoints[idx + 1]
    return (
        round(lat1 + (lat2 - lat1) * frac, 6),
        round(lng1 + (lng2 - lng1) * frac, 6),
    )


async def build_shipbubble_tracking_payload(
    db: AsyncSession,
    *,
    order: Order,
    current_status: str,
) -> Optional[Dict[str, Any]]:
    """Build live ShipBubble tracking & Leaflet map data for an order."""
    # 1. Look up selection for this order
    selection = await db.scalar(
        select(CheckoutShippingEstimateSelection).where(
            CheckoutShippingEstimateSelection.order_id == order.id
        )
    )

    # 2. If order is PAID and has a ShipBubble selection, ensure selected courier is recorded on order
    if order.payment_status == PaymentStatus.PAID and selection is not None and not order.delivery_provider:
        try:
            from app.services.shipping.shipbubble_booking import record_shipbubble_selection_on_paid_order
            await record_shipbubble_selection_on_paid_order(db, order_id=order.id)
        except Exception as exc:
            logger.warning("[ShipBubble] Selection recording during tracking read failed: %s", exc)

    shipment = await db.scalar(
        select(ShipbubbleShipment).where(ShipbubbleShipment.order_id == order.id)
    )

    selected_option: Optional[CheckoutShippingEstimateOption] = None
    selected_estimate: Optional[CheckoutShippingEstimate] = None
    if selection:
        selected_estimate = await db.scalar(
            select(CheckoutShippingEstimate).where(
                CheckoutShippingEstimate.id == selection.estimate_id
            )
        )
        selected_option = await db.scalar(
            select(CheckoutShippingEstimateOption).where(
                CheckoutShippingEstimateOption.id == selection.option_id
            )
        )
    else:
        selected_estimate = (
            await db.execute(
                select(CheckoutShippingEstimate)
                .where(CheckoutShippingEstimate.order_id == order.id)
                .order_by(CheckoutShippingEstimate.created_at.desc())
            )
        ).scalars().first()
        if selected_estimate and selected_estimate.source_kind == "shipbubble_live":
            selected_option = (
                await db.execute(
                    select(CheckoutShippingEstimateOption)
                    .where(CheckoutShippingEstimateOption.estimate_id == selected_estimate.id)
                    .order_by(CheckoutShippingEstimateOption.id.asc())
                )
            ).scalars().first()

    is_shipbubble_order = (
        shipment is not None
        or (selected_estimate is not None and selected_estimate.source_kind == "shipbubble_live")
        or bool(order.delivery_provider and order.delivery_provider.lower().startswith("shipbubble"))
    )
    if not is_shipbubble_order:
        return None

    # Resolve Origin Hub
    hub = (
        await db.execute(
            select(FulfillmentHub).where(FulfillmentHub.is_active.is_(True)).order_by(FulfillmentHub.id)
        )
    ).scalars().first()

    origin_lat = DEFAULT_ORIGIN_HUB["lat"]
    origin_lng = DEFAULT_ORIGIN_HUB["lng"]
    origin_name = hub.name if hub else DEFAULT_ORIGIN_HUB["name"]
    origin_city = hub.city if hub else DEFAULT_ORIGIN_HUB["city"]
    origin_state = hub.state if hub else DEFAULT_ORIGIN_HUB["state"]
    origin_address = (
        f"{hub.address_line1}, {hub.city}, {hub.state}, Nigeria"
        if hub
        else DEFAULT_ORIGIN_HUB["address"]
    )

    # Resolve Destination Address
    dest_addr = await db.get(Address, order.shipping_address_id) if order.shipping_address_id else None
    dest_name = dest_addr.full_name if dest_addr else "Customer"
    dest_city = dest_addr.city if dest_addr else "Lagos"
    dest_state = dest_addr.state if dest_addr else "Lagos"
    dest_address_str = (
        f"{dest_addr.address_line1}, {dest_addr.city}, {dest_addr.state}, {dest_addr.country or 'Nigeria'}"
        if dest_addr
        else "Customer Delivery Address, Nigeria"
    )

    dest_lat, dest_lng = _resolve_coordinates_for_address(
        dest_city, dest_state, dest_address_str
    )

    # Check if raw_response from ShipBubble has exact coordinates
    if shipment and isinstance(shipment.raw_response, dict):
        sb_data = shipment.raw_response.get("data")
        if isinstance(sb_data, dict):
            addr_from = sb_data.get("address_from")
            if isinstance(addr_from, dict):
                if addr_from.get("latitude") and addr_from.get("longitude"):
                    try:
                        origin_lat = float(addr_from["latitude"])
                        origin_lng = float(addr_from["longitude"])
                    except (ValueError, TypeError):
                        pass
            addr_to = sb_data.get("address_to")
            if isinstance(addr_to, dict):
                if addr_to.get("latitude") and addr_to.get("longitude"):
                    try:
                        dest_lat = float(addr_to["latitude"])
                        dest_lng = float(addr_to["longitude"])
                    except (ValueError, TypeError):
                        pass

    metadata = (selected_option.provider_metadata or {}) if selected_option else {}
    courier_name = (
        (shipment.courier_name if shipment else None)
        or metadata.get("courier_name")
        or (order.delivery_provider.split(":", 1)[-1] if order.delivery_provider and ":" in order.delivery_provider else None)
        or "ShipBubble Courier"
    )
    courier_image = metadata.get("courier_image")
    delivery_eta = metadata.get("delivery_eta") or "Standard Delivery"
    service_code = (shipment.service_code if shipment else None) or metadata.get("service_code") or ""

    waypoints = _generate_route_waypoints((origin_lat, origin_lng), (dest_lat, dest_lng))
    progress, location_label = _status_to_progress_and_label(
        current_status,
        courier_name,
        origin_city,
        dest_city,
    )
    if shipment is None and current_status == "order_placed":
        progress = 0.04
        location_label = f"Preparing package at {origin_city} Hub — {courier_name} pickup will be dispatched once ready"
    curr_lat, curr_lng = _interpolate_along_waypoints(waypoints, progress)

    is_sandbox = bool(
        settings.SHIPBUBBLE_API_KEY
        and settings.SHIPBUBBLE_API_KEY.strip().startswith("sb_sandbox_")
    )

    return {
        "provider": "shipbubble",
        "is_sandbox": is_sandbox,
        "is_booked": shipment is not None,
        "shipbubble_order_id": shipment.shipbubble_order_id if shipment else None,
        "courier_name": courier_name,
        "courier_image": courier_image,
        "service_code": service_code,
        "delivery_eta": delivery_eta,
        "shipment_status": shipment.status if shipment else current_status,
        "tracking_code": (
            (shipment.tracking_code or shipment.shipbubble_order_id)
            if shipment
            else order.tracking_number
        ),
        "tracking_url": shipment.tracking_url if shipment else None,
        "waybill_document_url": shipment.waybill_document_url if shipment else None,
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
            "updated_at": (
                shipment.updated_at.isoformat()
                if shipment and shipment.updated_at
                else order.updated_at.isoformat()
            ),
        },
        "route_waypoints": [[lat, lng] for lat, lng in waypoints],
    }


async def sync_shipbubble_shipment_status(
    db: AsyncSession,
    *,
    order: Order,
) -> Optional[ShipbubbleShipment]:
    """Query ShipBubble GET /shipping/labels/list/:order_id and sync order fulfillment status."""
    shipment = await db.scalar(
        select(ShipbubbleShipment).where(ShipbubbleShipment.order_id == order.id)
    )
    if not shipment or not shipment.shipbubble_order_id:
        return shipment

    service = get_shipbubble_service()
    try:
        results = await service.track_shipments([shipment.shipbubble_order_id])
        if results and isinstance(results[0], dict):
            latest = results[0]
            sb_status = str(latest.get("status") or shipment.status).lower().strip()
            shipment.status = sb_status
            shipment.updated_at = datetime.now(timezone.utc)
            if latest.get("tracking_url"):
                shipment.tracking_url = latest.get("tracking_url")

            status_mapping = {
                "pending": FulfillmentStatus.PREPARING_FOR_PICKUP,
                "confirmed": FulfillmentStatus.PICKUP_SCHEDULED,
                "picked_up": FulfillmentStatus.PICKED_UP,
                "in_transit": FulfillmentStatus.IN_TRANSIT,
                "out_for_delivery": FulfillmentStatus.OUT_FOR_DELIVERY,
                "completed": FulfillmentStatus.DELIVERED,
                "delivered": FulfillmentStatus.DELIVERED,
                "cancelled": FulfillmentStatus.CANCELLED,
            }
            if sb_status in status_mapping:
                order.fulfillment_status = status_mapping[sb_status]
                if order.fulfillment_status == FulfillmentStatus.DELIVERED and not order.delivered_at:
                    order.delivered_at = datetime.now(timezone.utc)

            db.add(shipment)
            db.add(order)
            await db.commit()
            await db.refresh(order)
            await db.refresh(shipment)
    except ShipBubbleError as exc:
        logger.warning("[ShipBubble] Live tracking poll failed for %s: %s", shipment.shipbubble_order_id, exc)

    return shipment

