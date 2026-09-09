"""Create the durable, server-owned shipment subject for checkout DHL rating."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select

from app.models.fulfillment_cohort import (
    CohortItemAllocation,
    FulfillmentCohort,
    FulfillmentReadinessType,
)
from app.models.fulfillment_hub import FulfillmentHub
from app.models.order import Order, OrderItem
from app.models.package_custody import (
    HubPackage,
    HubPackageItem,
    HubPackageSeal,
    HubPackageVersion,
    OutboundShipmentIntent,
)
from app.models.product import Product


async def ensure_checkout_shipment_subject(db, *, order: Order, actor_id):
    """Persist one ready quote subject for an enforced checkout order.

    This is deliberately limited to the pre-payment checkout quote boundary. It
    creates no payment, booking, label, or provider state. The DHL adapter still
    validates the complete subject before making the provider request.
    """
    existing = (
        await db.execute(
            select(HubPackage).where(
                HubPackage.order_id == order.id,
                HubPackage.source_command == "checkout_prepare_shipment_subject",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    if order.shipping_address is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="shipping address required for DHL rating")
    if not order.shipping_address.postal_code:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="postal code required for DHL rating")

    hubs = (
        await db.execute(
            select(FulfillmentHub).where(FulfillmentHub.is_active.is_(True)).order_by(FulfillmentHub.id)
        )
    ).scalars().all()
    if len(hubs) != 1:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="exactly one active DHL fulfillment hub required")
    hub = hubs[0]

    item_rows = (
        await db.execute(
            select(OrderItem, Product)
            .join(Product, Product.id == OrderItem.product_id)
            .where(OrderItem.order_id == order.id)
            .order_by(OrderItem.id)
        )
    ).all()
    if not item_rows:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="checkout has no shippable items")
    if any(None in (product.weight_kg, product.length_cm, product.width_cm, product.height_cm) for _, product in item_rows):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="vendor parcel dimensions required before DHL rating")

    now = datetime.now(timezone.utc)
    package_id = uuid4()
    package_key = f"checkout:{order.id}:shipment-subject:v1"
    package = HubPackage(
        id=package_id,
        order_id=order.id,
        hub_id=hub.id,
        state="ready",
        current_version=1,
        row_version=1,
        source_command="checkout_prepare_shipment_subject",
        idempotency_key=package_key,
        created_by_id=actor_id,
        sealed_at=now,
        ready_at=now,
    )
    db.add(package)

    total_weight = Decimal("0")
    max_length = Decimal("0")
    max_width = Decimal("0")
    max_height = Decimal("0")
    cohorts = {}
    for item, product in item_rows:
        readiness = (
            FulfillmentReadinessType.MADE_TO_ORDER
            if product.made_to_order
            else FulfillmentReadinessType.READY_TO_WEAR
        )
        cohort = cohorts.get((item.vendor_id, readiness))
        if cohort is None:
            cohort = FulfillmentCohort(
                id=uuid4(),
                order_id=order.id,
                vendor_id=item.vendor_id,
                readiness_type=readiness,
                ready_from=now,
                ready_through=now + timedelta(days=30),
            )
            db.add(cohort)
            cohorts[(item.vendor_id, readiness)] = cohort
        db.add(
            CohortItemAllocation(
                cohort_id=cohort.id,
                order_item_id=item.id,
                order_id=order.id,
                vendor_id=item.vendor_id,
                allocated_quantity=item.quantity,
            )
        )
        total_weight += Decimal(product.weight_kg) * item.quantity
        max_length = max(max_length, Decimal(product.length_cm))
        max_width = max(max_width, Decimal(product.width_cm))
        max_height = max(max_height, Decimal(product.height_cm))
        db.add(
            HubPackageItem(
                package_id=package_id,
                package_version=1,
                order_id=order.id,
                hub_id=hub.id,
                cohort_id=cohort.id,
                vendor_id=item.vendor_id,
                order_item_id=item.id,
                quantity=item.quantity,
            )
        )

    db.add(
        HubPackageVersion(
            package_id=package_id,
            version=1,
            order_id=order.id,
            hub_id=hub.id,
            previous_version=None,
            weight_kg=total_weight,
            length_cm=max_length,
            width_cm=max_width,
            height_cm=max_height,
            packed_by_id=actor_id,
            packed_at=now,
            reason=None,
        )
    )
    seal = HubPackageSeal(
        id=uuid4(),
        package_id=package_id,
        package_version=1,
        opaque_value=f"checkout-seal-{uuid4().hex}",
        applied_by_id=actor_id,
        applied_at=now,
    )
    db.add(seal)
    db.add(
        OutboundShipmentIntent(
            id=uuid4(),
            package_id=package_id,
            package_version=1,
            seal_id=seal.id,
            order_id=order.id,
            origin_hub_id=hub.id,
            destination_name=order.shipping_address.full_name,
            destination_phone=order.shipping_address.phone_number,
            destination_address_line1=order.shipping_address.address_line1,
            destination_address_line2=order.shipping_address.address_line2,
            destination_city=order.shipping_address.city,
            destination_state=order.shipping_address.state,
            destination_postal_code=order.shipping_address.postal_code,
            destination_country_code="NG",
            source_command="checkout_prepare_shipment_subject",
            idempotency_key=package_key,
            created_by_id=actor_id,
        )
    )
    await db.flush()
    return package
