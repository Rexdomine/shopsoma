"""Shipbubble Webhook Receiver with HMAC-SHA512 verification and deduplication."""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select

from app.core.config import settings
from app.core.database import get_db
from app.models.order import FulfillmentStatus, Order
from app.models.shipbubble_shipment import ShipbubbleShipment, ShipbubbleWebhookEvent
from app.services.orders.fulfillment_sync import (
    can_apply_carrier_status_transition,
    sync_vendor_items_and_pickups_for_order_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shipping/webhooks", tags=["Shipping Webhooks"])


@router.post("/shipbubble", status_code=status.HTTP_200_OK)
async def shipbubble_webhook(
    request: Request,
    x_ship_signature: str = Header(None, alias="x-ship-signature"),
    db=Depends(get_db),
) -> Dict[str, Any]:
    """Receive and process ShipBubble webhook notifications.

    Verifies HMAC-SHA512 signature using settings.SHIPBUBBLE_API_KEY.
    Deduplicates events by raw payload SHA-256 hash.
    Updates ShipbubbleShipment and Order fulfillment lifecycle.
    """
    raw_body = await request.body()

    # Signature verification
    api_key = settings.SHIPBUBBLE_API_KEY
    if not api_key:
        logger.error("[ShipBubble Webhook] API key not configured; cannot verify signature")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ShipBubble webhook processing unconfigured",
        )

    if not x_ship_signature:
        logger.warning("[ShipBubble Webhook] Missing x-ship-signature header")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing webhook signature",
        )

    expected_sig = hmac.new(
        api_key.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()

    if not hmac.compare_digest(expected_sig.lower(), x_ship_signature.lower()):
        logger.warning("[ShipBubble Webhook] Signature mismatch")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        logger.warning("[ShipBubble Webhook] Invalid JSON payload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    payload_sha256 = hashlib.sha256(raw_body).hexdigest()

    # Deduplication check
    existing_event = await db.scalar(
        select(ShipbubbleWebhookEvent).where(
            ShipbubbleWebhookEvent.payload_sha256 == payload_sha256
        )
    )
    if existing_event:
        logger.info("[ShipBubble Webhook] Duplicate event %s ignored", payload_sha256)
        return {"status": "ok", "message": "duplicate event ignored"}

    nested_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    event_type = payload.get("event") or nested_data.get("event") or "unknown"
    sb_order_id = payload.get("order_id") or nested_data.get("order_id")

    webhook_record = ShipbubbleWebhookEvent(
        event_id=str(sb_order_id) if sb_order_id else None,
        event_type=str(event_type),
        payload_sha256=payload_sha256,
        payload=payload,
        status="received",
    )
    db.add(webhook_record)
    await db.flush()

    if sb_order_id:
        shipment = await db.scalar(
            select(ShipbubbleShipment).where(
                ShipbubbleShipment.shipbubble_order_id == sb_order_id
            )
        )
        if shipment:
            status_val = payload.get("status") or nested_data.get("status")
            courier_info = payload.get("courier") or nested_data.get("courier") or {}
            tracking_code = (
                courier_info.get("tracking_code")
                if isinstance(courier_info, dict)
                else None
            ) or payload.get("tracking_code") or nested_data.get("tracking_code")
            tracking_url = payload.get("tracking_url") or nested_data.get("tracking_url")
            waybill_document = payload.get("waybill_document") or nested_data.get("waybill_document")

            if status_val:
                shipment.status = status_val
            if tracking_code:
                shipment.tracking_code = tracking_code
            if tracking_url:
                shipment.tracking_url = tracking_url
            if waybill_document:
                shipment.waybill_document_url = waybill_document

            order = await db.scalar(
                select(Order).where(Order.id == shipment.order_id).with_for_update()
            )
            old_status = order.fulfillment_status if order else None
            if order:
                if tracking_code and not order.tracking_number:
                    order.tracking_number = tracking_code
                elif sb_order_id and not order.tracking_number:
                    order.tracking_number = sb_order_id

                status_lower = (status_val or "").lower().strip()
                webhook_status_map = {
                    "picked_up": FulfillmentStatus.PICKED_UP,
                    "pickup_completed": FulfillmentStatus.PICKED_UP,
                    "in_transit": FulfillmentStatus.IN_TRANSIT,
                    "in-transit": FulfillmentStatus.IN_TRANSIT,
                    "out_for_delivery": FulfillmentStatus.OUT_FOR_DELIVERY,
                    "out-for-delivery": FulfillmentStatus.OUT_FOR_DELIVERY,
                    "delivered": FulfillmentStatus.DELIVERED,
                    "completed": FulfillmentStatus.DELIVERED,
                    "delivery_failed": FulfillmentStatus.DELIVERY_FAILED,
                    "failed": FulfillmentStatus.DELIVERY_FAILED,
                    "returned": FulfillmentStatus.RETURNED,
                    "cancelled": FulfillmentStatus.CANCELLED,
                    "canceled": FulfillmentStatus.CANCELLED,
                }
                target_status = webhook_status_map.get(status_lower)
                if target_status is not None:
                    if can_apply_carrier_status_transition(
                        old_status,
                        target_status,
                        is_webhook=True,
                    ):
                        now_utc = datetime.now(timezone.utc)
                        order.fulfillment_status = target_status
                        if target_status == FulfillmentStatus.DELIVERED and order.delivered_at is None:
                            order.delivered_at = now_utc
                        elif target_status == FulfillmentStatus.CANCELLED and order.cancelled_at is None:
                            order.cancelled_at = now_utc
                        await sync_vendor_items_and_pickups_for_order_status(
                            db,
                            order=order,
                            new_status=target_status,
                            now_utc=now_utc,
                        )
                    elif target_status != old_status:
                        logger.info(
                            "[ShipBubble Webhook] Ignoring non-forward status '%s' (%s) for order %s currently at '%s'",
                            status_lower,
                            target_status.value,
                            order.order_number,
                            old_status.value if hasattr(old_status, "value") else old_status,
                        )

                db.add(order)

            webhook_record.status = "processed"
            webhook_record.processed_at = datetime.now(timezone.utc)
            await db.flush()

            await db.commit()
            if order and old_status != order.fulfillment_status:
                try:
                    from app.api.v1.admin_orders import (
                        _broadcast_order_update,
                        _notify_order_status_change,
                    )

                    await _notify_order_status_change(db, order=order, old_status=old_status)
                    await _broadcast_order_update(order)
                except Exception as notify_exc:
                    logger.warning("[ShipBubble Webhook] Notification/broadcast note: %s", notify_exc)
            return {"status": "ok", "message": "webhook processed"}

    await db.commit()
    return {"status": "ok", "message": "webhook processed"}
