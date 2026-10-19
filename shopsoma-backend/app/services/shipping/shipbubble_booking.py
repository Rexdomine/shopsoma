"""ShipBubble label booking when the Hub marks the order Ready for Pickup."""

from decimal import Decimal
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select

from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimate,
    CheckoutShippingEstimateOption,
    CheckoutShippingEstimateSelection,
)
from app.models.order import FulfillmentStatus, Order, PaymentStatus
from app.models.shipbubble_shipment import ShipbubbleShipment
from app.services.shipbubble_service import get_shipbubble_service, ShipBubbleError

logger = logging.getLogger(__name__)


async def record_shipbubble_selection_on_paid_order(session, *, order_id: UUID) -> Optional[Order]:
    """Record the customer's selected ShipBubble courier on the paid order without booking the label yet.

    Under Option B, the actual ShipBubble pickup label (POST /shipping/labels) is only created
    once the Shopsoma Hub marks the package/items as Ready for Pickup.
    """
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    if order is None or order.payment_status != PaymentStatus.PAID:
        return None

    selection = await session.scalar(
        select(CheckoutShippingEstimateSelection).where(
            CheckoutShippingEstimateSelection.order_id == order.id
        )
    )
    if not selection and getattr(order, "checkout_estimate_selection_id", None):
        selection = await session.scalar(
            select(CheckoutShippingEstimateSelection).where(
                CheckoutShippingEstimateSelection.id == order.checkout_estimate_selection_id
            )
        )
    if not selection:
        return None

    estimate = await session.scalar(
        select(CheckoutShippingEstimate).where(
            CheckoutShippingEstimate.id == selection.estimate_id
        )
    )
    option = await session.scalar(
        select(CheckoutShippingEstimateOption).where(
            CheckoutShippingEstimateOption.id == selection.option_id
        )
    )
    if not option or not option.provider_metadata:
        return None

    is_shipbubble = (
        (estimate and estimate.source_kind == "shipbubble_live")
        or (option.provider_metadata.get("provider") == "shipbubble")
        or bool(order.delivery_provider and "shipbubble" in order.delivery_provider.lower())
    )
    if not is_shipbubble:
        return None

    metadata = option.provider_metadata
    courier_name = metadata.get("courier_name") or "Shipbubble Courier"
    if not order.delivery_provider:
        order.delivery_provider = f"shipbubble:{courier_name}"
        session.add(order)
        await session.flush()
        await session.refresh(order)
        logger.info(
            "[ShipBubble] Recorded selected courier '%s' for paid order %s (awaiting Hub readiness to dispatch pickup)",
            order.delivery_provider,
            order.id,
        )
    return order


async def book_shipbubble_shipment_if_selected(session, *, order_id: UUID) -> Optional[ShipbubbleShipment]:
    """Book a Shipbubble shipment when the Hub marks the order/items Ready for Pickup.

    Idempotent: if a ShipbubbleShipment record already exists for this order, returns it.
    If the checkout request_token has expired while items were being prepared/sent to the Hub,
    automatically re-fetches a fresh request_token with today's pickup_date for the same courier.
    """
    order = await session.scalar(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    if order is None or order.payment_status != PaymentStatus.PAID:
        return None

    # Check if a shipment already exists for this order
    existing_shipment = await session.scalar(
        select(ShipbubbleShipment).where(ShipbubbleShipment.order_id == order.id)
    )
    if existing_shipment is not None:
        logger.info("[ShipBubble] Shipment already booked for order %s: %s", order.id, existing_shipment.shipbubble_order_id)
        return existing_shipment

    selection = await session.scalar(
        select(CheckoutShippingEstimateSelection).where(
            CheckoutShippingEstimateSelection.order_id == order.id
        )
    )
    if not selection and getattr(order, "checkout_estimate_selection_id", None):
        selection = await session.scalar(
            select(CheckoutShippingEstimateSelection).where(
                CheckoutShippingEstimateSelection.id == order.checkout_estimate_selection_id
            )
        )
    if not selection:
        return None

    estimate = await session.scalar(
        select(CheckoutShippingEstimate).where(
            CheckoutShippingEstimate.id == selection.estimate_id
        )
    )
    option = await session.scalar(
        select(CheckoutShippingEstimateOption).where(
            CheckoutShippingEstimateOption.id == selection.option_id
        )
    )
    if not option or not option.provider_metadata:
        logger.warning("[ShipBubble] Order %s has no option provider_metadata", order.id)
        return None

    is_shipbubble = (
        (estimate and estimate.source_kind == "shipbubble_live")
        or (option.provider_metadata.get("provider") == "shipbubble")
        or bool(order.delivery_provider and "shipbubble" in order.delivery_provider.lower())
    )
    if not is_shipbubble:
        return None

    metadata = option.provider_metadata
    request_token = metadata.get("request_token")
    service_code = metadata.get("service_code")
    courier_id = metadata.get("courier_id")
    courier_name = metadata.get("courier_name") or "Shipbubble Courier"

    if not request_token or not service_code or not courier_id:
        logger.error("[ShipBubble] Incomplete provider_metadata for order %s: %s", order.id, metadata)
        return None

    service = get_shipbubble_service()
    result = None
    try:
        result = await service.create_label(
            request_token=request_token,
            service_code=service_code,
            courier_id=str(courier_id),
        )
    except ShipBubbleError as exc:
        logger.warning(
            "[ShipBubble] Initial create_label for order %s returned status=%s msg=%s",
            order.id, exc.status_code, exc.message
        )
        # 1. If the token expired or pickup_date passed while items were travelling to the Hub,
        # re-fetch fresh rates with today's pickup_date and book with the fresh request_token.
        if exc.status_code in (400, 422):
            try:
                from app.services.checkout.estimates import _shipbubble_checkout_options
                from sqlalchemy.orm import selectinload
                order_full = await session.scalar(
                    select(Order)
                    .options(selectinload(Order.shipping_address), selectinload(Order.items))
                    .where(Order.id == order.id)
                )
                if order_full:
                    fresh_rates = await _shipbubble_checkout_options(session, order=order_full)
                    matched = next(
                        (
                            c for c in fresh_rates.couriers
                            if str(c.courier_id) == str(courier_id) and str(c.service_code) == str(service_code)
                        ),
                        None,
                    ) or next(
                        (c for c in fresh_rates.couriers if str(c.courier_id) == str(courier_id)),
                        None,
                    ) or (fresh_rates.couriers[0] if fresh_rates.couriers else None)
                    if matched and fresh_rates.request_token:
                        request_token = fresh_rates.request_token
                        service_code = matched.service_code
                        courier_id = matched.courier_id
                        result = await service.create_label(
                            request_token=request_token,
                            service_code=service_code,
                            courier_id=str(courier_id),
                        )
                        logger.info(
                            "[ShipBubble] Re-rated and booked label %s with fresh pickup_date for order %s",
                            result.order_id,
                            order.id,
                        )
            except Exception as rerate_exc:
                logger.warning("[ShipBubble] Re-rate attempt failed for order %s: %s", order.id, rerate_exc)

        # 2. If the request_token was already consumed on ShipBubble before our DB transaction committed,
        # attempt to recover the most recent unlinked label from ShipBubble GET /shipping/labels.
        if result is None and exc.status_code == 422 and "request token" in (exc.message or "").lower():
            try:
                labels_res = await service._make_request("GET", "/shipping/labels")
                results_list = (labels_res.get("data") or {}).get("results") or []
                for item in results_list:
                    sb_oid = item.get("order_id")
                    if not sb_oid:
                        continue
                    already_linked = await session.scalar(
                        select(ShipbubbleShipment).where(ShipbubbleShipment.shipbubble_order_id == sb_oid)
                    )
                    if already_linked is None:
                        courier_info = item.get("courier") or {}
                        payment_info = item.get("payment") or {}
                        fee_raw = payment_info.get("shipping_fee")
                        from app.services.shipbubble_service import ShipbubbleShipmentResult
                        result = ShipbubbleShipmentResult(
                            order_id=sb_oid,
                            status=str(item.get("status") or "pending").lower(),
                            courier_name=str(courier_info.get("name") or courier_name),
                            tracking_code=courier_info.get("tracking_code"),
                            tracking_url=item.get("tracking_url"),
                            waybill_document_url=item.get("waybill_document"),
                            shipping_fee=Decimal(str(fee_raw)) if fee_raw is not None else None,
                            currency=payment_info.get("currency", "NGN"),
                            raw_response={"status": "success", "data": item},
                        )
                        logger.info("[ShipBubble] Recovered existing label %s for order %s", sb_oid, order.id)
                        break
            except Exception as rec_exc:
                logger.warning("[ShipBubble] Recovery check failed for order %s: %s", order.id, rec_exc)

        if result is None:
            note_prefix = f"[ShipBubble booking failed: {exc.message}] "
            if not (order.admin_notes or "").startswith("[ShipBubble booking failed:"):
                order.admin_notes = note_prefix + (order.admin_notes or "")
                session.add(order)
                await session.flush()
                await session.refresh(order)
            if exc.status_code and 400 <= exc.status_code < 500:
                return None
            raise

    shipment = ShipbubbleShipment(
        order_id=order.id,
        estimate_option_id=option.id,
        request_token=str(request_token),
        shipbubble_order_id=result.order_id,
        courier_id=str(courier_id),
        courier_name=result.courier_name or courier_name,
        service_code=str(service_code),
        status=result.status or "pending",
        tracking_code=result.tracking_code,
        tracking_url=result.tracking_url,
        waybill_document_url=result.waybill_document_url,
        shipping_fee=result.shipping_fee,
        currency=result.currency or "NGN",
        raw_response=result.raw_response,
    )
    session.add(shipment)

    order.delivery_provider = f"shipbubble:{result.courier_name or courier_name}"
    if result.tracking_code:
        order.tracking_number = result.tracking_code
    elif result.order_id:
        order.tracking_number = result.order_id
    if order.fulfillment_status in (
        FulfillmentStatus.ORDER_RECEIVED,
        FulfillmentStatus.PREPARING_FOR_PICKUP,
    ):
        order.fulfillment_status = FulfillmentStatus.PICKUP_SCHEDULED
    session.add(order)
    await session.flush()
    await session.refresh(order)
    await session.refresh(shipment)

    logger.info("[ShipBubble] Successfully booked shipment %s for order %s", result.order_id, order.id)
    return shipment


