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
                if status_lower in ("picked_up", "pickup_completed"):
                    order.fulfillment_status = FulfillmentStatus.PICKED_UP
                elif status_lower in ("in_transit", "in-transit"):
                    order.fulfillment_status = FulfillmentStatus.IN_TRANSIT
                elif status_lower in ("out_for_delivery", "out-for-delivery"):
                    order.fulfillment_status = FulfillmentStatus.OUT_FOR_DELIVERY
                elif status_lower in ("delivered", "completed"):
                    order.fulfillment_status = FulfillmentStatus.DELIVERED
                    if order.delivered_at is None:
                        order.delivered_at = datetime.now(timezone.utc)
                elif status_lower in ("delivery_failed", "failed"):
                    order.fulfillment_status = FulfillmentStatus.DELIVERY_FAILED
                elif status_lower in ("returned",):
                    order.fulfillment_status = FulfillmentStatus.RETURNED
                elif status_lower in ("cancelled", "canceled"):
                    order.fulfillment_status = FulfillmentStatus.CANCELLED

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
