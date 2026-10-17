"""Server-owned checkout-estimate creation and snapshot validation."""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
import hashlib
import json
import logging
import re
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased, selectinload

from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimate,
    CheckoutShippingEstimateOption,
    CheckoutShippingEstimateSelection,
)
from app.models.address import Address
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.models.product_logistics_profile import ProductLogisticsProfile
from app.models.setting import Setting
from app.models.user import User
from app.services.shipbubble_service import get_shipbubble_service, ShipBubbleError
from app.services.shipping.provider_settings import shipping_provider_settings
from app.services.shipping.manual_rates import manual_rates_query
from app.models.fulfillment_cohort import CohortItemAllocation, FulfillmentCohort
from app.models.fulfillment_hub import FulfillmentHub
from app.models.package_custody import (
    CustodyEvent,
    HubPackage,
    HubPackageItem,
    HubPackageSeal,
    HubPackageVersion,
    OutboundShipmentIntent,
    OutboundShipmentIntentInvalidation,
)
from app.core.config import settings
from app.services.dhl.rating import (
    DHLResolvedHub,
    DHLRateAdapterError,
    create_sandbox_domestic_rate_adapter,
    derive_sandbox_cohort_ids,
)
from app.services.fulfillment.contracts import (
    DomesticAddress,
    FulfillmentCohortRef,
    HubRef,
    PackageItemRef,
    PackageRef,
    ParcelMeasurement,
    SealRef,
)
from app.services.shipping.contracts import DomesticRateRequest
from app.services.shipping.capabilities import domestic_shipping_capabilities
from app.services.checkout.capabilities import authorize_checkout_actor

_CENT = Decimal("0.01")
_MAX_CHECKOUT_OPTION_AMOUNT = Decimal("99999999.99")
_ESTIMATE_TTL_SECONDS = 1800
_LAGOS_TZ = ZoneInfo("Africa/Lagos")
logger = logging.getLogger(__name__)


def _planned_ship_date() -> date:
    """Return the next DHL tender date in the provider's local timezone."""
    now = datetime.now(_LAGOS_TZ)
    ship_date = now.date() if now.hour < 12 else now.date() + timedelta(days=1)
    if ship_date.weekday() == 5:
        ship_date += timedelta(days=2)
    elif ship_date.weekday() == 6:
        ship_date += timedelta(days=1)
    return ship_date


async def _rate_pre_payment_quote_subject(
    db, *, order: Order, planned_ship_date=None
):
    """Rate a non-custodial quote subject before payment/fulfillment handoff."""
    configured_cohorts = settings.dhl_domestic_sandbox_cohort_ids
    if not configured_cohorts:
        raise HTTPException(status_code=503, detail="configured DHL sandbox cohort required")
    address = order.shipping_address
    if address is None or not address.postal_code:
        raise HTTPException(status_code=422, detail="postal code required for DHL rating")
    hubs = (
        await db.execute(
            select(FulfillmentHub).where(FulfillmentHub.is_active.is_(True)).order_by(FulfillmentHub.id)
        )
    ).scalars().all()
    if len(hubs) != 1:
        raise HTTPException(status_code=503, detail="exactly one active DHL fulfillment hub required")
    hub = hubs[0]
    rows = (
        await db.execute(
            select(OrderItem, Product)
            .join(Product, Product.id == OrderItem.product_id)
            .where(OrderItem.order_id == order.id)
            .order_by(OrderItem.id)
        )
    ).all()
    if not rows:
        raise HTTPException(status_code=422, detail="checkout has no shippable items")
    item_measurements = [
        (item, product, values)
        for item, product, _profile, values in await _authoritative_parcel_measurements(
            db, order
        )
    ]
    if any(values is None or any(value is None for value in values) for _, _, values in item_measurements):
        raise HTTPException(status_code=422, detail="vendor parcel dimensions required before DHL rating")
    allocations = (
        await db.execute(
            select(CohortItemAllocation, FulfillmentCohort)
            .join(FulfillmentCohort, FulfillmentCohort.id == CohortItemAllocation.cohort_id)
            .where(CohortItemAllocation.order_id == order.id)
        )
    ).all()
    allocation_by_item = {}
    for allocation, cohort in allocations:
        allocation_by_item.setdefault(allocation.order_item_id, []).append((allocation, cohort))
    expected_quantities = {item.id: item.quantity for item, _ in rows}
    if any(
        sum(allocation.allocated_quantity for allocation, _ in item_allocations)
        != expected_quantities[item_id]
        for item_id, item_allocations in allocation_by_item.items()
    ):
        raise HTTPException(status_code=503, detail="cohort allocation does not cover the order item")
    if set(allocation_by_item) != set(expected_quantities):
        raise HTTPException(status_code=503, detail="order is not assigned to a fulfillment cohort")
    hub_ref = HubRef(id=hub.id)
    package_id = uuid5(NAMESPACE_URL, f"shopsoma:checkout:{order.id}:quote-package")
    seal_id = uuid5(NAMESPACE_URL, f"shopsoma:checkout:{order.id}:quote-seal")
    total_weight = Decimal("0")
    max_length = Decimal("0")
    max_width = Decimal("0")
    max_height = Decimal("0")
    total_volume = Decimal("0")
    composition = []
    for item, product, values in item_measurements:
        assert values is not None
        weight_kg, length_cm, width_cm, height_cm = values
        total_weight += Decimal(weight_kg) * item.quantity
        max_length = max(max_length, Decimal(length_cm))
        max_width = max(max_width, Decimal(width_cm))
        max_height = max(max_height, Decimal(height_cm))
        total_volume += (
            Decimal(length_cm)
            * Decimal(width_cm)
            * Decimal(height_cm)
            * item.quantity
        )
        for allocation, cohort in allocation_by_item[item.id]:
            composition.append(
                PackageItemRef(
                    cohort=FulfillmentCohortRef(id=cohort.id, hub=hub_ref),
                    order_item_id=item.id,
                    quantity=allocation.allocated_quantity,
                )
            )
    if max_length <= 0 or max_width <= 0:
        raise HTTPException(status_code=422, detail="vendor parcel dimensions must be positive")
    max_height = max(
        max_height,
        (total_volume / (max_length * max_width)).quantize(
            Decimal("0.001"), rounding=ROUND_CEILING
        ),
    )
    package = PackageRef(
        package_id=package_id,
        package_version=1,
        composition=tuple(composition),
        measurement=ParcelMeasurement(
            weight_kg=total_weight,
            length_cm=max_length,
            width_cm=max_width,
            height_cm=max_height,
        ),
        seal=SealRef(value=f"checkout-quote-{seal_id}"),
    )
    try:
        destination = DomesticAddress(
            contact_name=address.full_name,
            phone=address.phone_number,
            line1=address.address_line1,
            line2=address.address_line2.strip() or None if address.address_line2 else None,
            city=address.city,
            state=address.state,
            postal_code=address.postal_code.strip() or None if address.postal_code else None,
            country_code="NG",
        )
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="shipping address is invalid") from None
    resolved = DHLResolvedHub(
        hub=hub_ref,
        hub_version=hub.version,
        intent_id=uuid5(NAMESPACE_URL, f"shopsoma:checkout:{order.id}:quote-intent"),
        order_id=order.id,
        seal_id=seal_id,
        package_id=package_id,
        package_version=1,
        destination=destination,
        package=package,
        contact_name=hub.contact_name,
        phone=hub.contact_phone,
        line1=hub.address_line1,
        line2=hub.address_line2.strip() or None if hub.address_line2 else None,
        city=hub.city,
        state=hub.state,
        postal_code=hub.postal_code.strip() or None if hub.postal_code else None,
        country_code=hub.country_code,
        cohort_count=len({cohort.id for _, cohort in allocations}),
    )
    planned_ship_date = planned_ship_date or _planned_ship_date()
    request = DomesticRateRequest(
        origin=hub_ref,
        destination=destination,
        package=package,
        planned_ship_date=planned_ship_date,
    )
    if not settings.checkout_capability_configured:
        raise HTTPException(status_code=503, detail="checkout rate identity is not configured")
    identity_key = settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER.get_secret_value().encode()
    identity_version = f"checkout-capability-v{settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION}"
    try:
        adapter = create_sandbox_domestic_rate_adapter(
            config=settings,
            transport=None,
            identity_key=identity_key,
            identity_key_version=identity_version,
        )
        payload = adapter.prepare_rate_payload(resolved, request)
        result = await adapter.rate(resolved, request, prepared_payload=payload)
    except DHLRateAdapterError as exc:
        logger.error("DHL rate adapter error: %s", exc)
        raise HTTPException(status_code=503, detail="DHL sandbox rate request failed") from None
    if result.result_kind != "success":
        raise HTTPException(status_code=503, detail="DHL has no service for this shipment")
    return result.offers


async def _dhl_checkout_options(db, *, order: Order, planned_ship_date=None):
        """Rate the exact checkout shipment subject through DHL sandbox."""
        handed_off = select(CustodyEvent.id).where(
            CustodyEvent.package_id == HubPackage.id,
            CustodyEvent.package_version == HubPackage.current_version,
            CustodyEvent.event_type.in_(("released", "tendered", "provider_accepted")),
        ).exists()
        packages = (
            await db.execute(
                select(HubPackage)
                .where(HubPackage.order_id == order.id, HubPackage.state == "ready", ~handed_off)
                .order_by(HubPackage.ready_at.desc(), HubPackage.id.desc())
            )
        ).scalars().all()
        if not packages:
            return await _rate_pre_payment_quote_subject(
                db, order=order, planned_ship_date=planned_ship_date
            )
        if len(packages) != 1:
            raise HTTPException(status_code=503, detail="DHL shipment subject is not ready")
        package = packages[0]
        seal = (
            await db.execute(
                select(HubPackageSeal).where(
                    HubPackageSeal.package_id == package.id,
                    HubPackageSeal.package_version == package.current_version,
                    HubPackageSeal.retired_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        intent = (
            await db.execute(
                select(OutboundShipmentIntent).where(
                    OutboundShipmentIntent.order_id == order.id,
                    OutboundShipmentIntent.package_id == package.id,
                    OutboundShipmentIntent.package_version == package.current_version,
                    ~select(OutboundShipmentIntentInvalidation.id)
                    .where(OutboundShipmentIntentInvalidation.intent_id == OutboundShipmentIntent.id)
                    .exists(),
                )
            )
        ).scalar_one_or_none()
        hub = (
            await db.execute(
                select(FulfillmentHub).where(
                    FulfillmentHub.id == package.hub_id,
                    FulfillmentHub.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        version = (
            await db.execute(
                select(HubPackageVersion).where(
                    HubPackageVersion.package_id == package.id,
                    HubPackageVersion.version == package.current_version,
                )
            )
        ).scalar_one_or_none()
        items = (
            await db.execute(
                select(HubPackageItem).where(
                    HubPackageItem.package_id == package.id,
                    HubPackageItem.package_version == package.current_version,
                ).order_by(HubPackageItem.id)
            )
        ).scalars().all()
        if not all((seal, intent, hub, version, items)):
            raise HTTPException(status_code=503, detail="DHL shipment subject is incomplete")
        destination = DomesticAddress(
            contact_name=intent.destination_name,
            phone=intent.destination_phone,
            line1=intent.destination_address_line1,
            line2=intent.destination_address_line2.strip() or None if intent.destination_address_line2 else None,
            city=intent.destination_city,
            state=intent.destination_state,
            postal_code=intent.destination_postal_code,
            country_code=intent.destination_country_code,
        )
        hub_ref = HubRef(id=hub.id)
        package_ref = PackageRef(
            package_id=package.id,
            package_version=package.current_version,
            composition=tuple(
                PackageItemRef(
                    cohort=FulfillmentCohortRef(id=item.cohort_id, hub=hub_ref),
                    order_item_id=item.order_item_id,
                    quantity=item.quantity,
                )
                for item in items
            ),
            measurement=ParcelMeasurement(
                weight_kg=version.weight_kg,
                length_cm=version.length_cm,
                width_cm=version.width_cm,
                height_cm=version.height_cm,
            ),
            seal=SealRef(value=seal.opaque_value),
        )
        order_cohort_count = len(
            (
                await db.execute(
                    select(FulfillmentCohort.id).where(
                        FulfillmentCohort.order_id == order.id
                    )
                )
            ).scalars().all()
        )
        resolved = DHLResolvedHub(
            hub=hub_ref,
            hub_version=hub.version,
            intent_id=intent.id,
            order_id=order.id,
            seal_id=seal.id,
            package_id=package.id,
            package_version=package.current_version,
            destination=destination,
            package=package_ref,
            contact_name=hub.contact_name,
            phone=hub.contact_phone,
            line1=hub.address_line1,
            line2=hub.address_line2.strip() or None if hub.address_line2 else None,
            city=hub.city,
            state=hub.state,
            postal_code=hub.postal_code.strip() or None if hub.postal_code else None,
            country_code=hub.country_code,
            cohort_count=len(
                (
                    await db.execute(
                        select(FulfillmentCohort.id).where(
                            FulfillmentCohort.order_id == order.id
                        )
                    )
                ).scalars().all()
            ),
        )
        planned_ship_date = planned_ship_date or _planned_ship_date()
        request = DomesticRateRequest(
            origin=hub_ref,
            destination=destination,
            package=package_ref,
            planned_ship_date=planned_ship_date,
        )
        configured_cohorts = settings.dhl_domestic_sandbox_cohort_ids
        package_cohort_ids = {item.cohort_id for item in items}
        if not configured_cohorts or not package_cohort_ids <= (
            configured_cohorts
            | derive_sandbox_cohort_ids(
                configured_cohorts, order.id, order_cohort_count
            )
        ):
            raise HTTPException(status_code=503, detail="checkout cohort is outside the configured DHL sandbox allowlist")
        checkout_settings = settings
        if not settings.checkout_capability_configured:
            raise HTTPException(status_code=503, detail="checkout rate identity is not configured")
        identity_key = settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER.get_secret_value().encode()
        identity_version = f"checkout-capability-v{settings.CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION}"
        try:
            adapter = create_sandbox_domestic_rate_adapter(
                config=checkout_settings,
                transport=None,
                identity_key=identity_key,
                identity_key_version=identity_version,
            )
            payload = adapter.prepare_rate_payload(resolved, request)
            result = await adapter.rate(resolved, request, prepared_payload=payload)
        except DHLRateAdapterError as exc:
            logger.error("DHL rate adapter error: %s", exc)
            raise HTTPException(status_code=503, detail="DHL sandbox rate request failed") from None
        if result.result_kind != "success":
            raise HTTPException(status_code=503, detail="DHL has no service for this shipment")
        return result.offers


async def _shipbubble_checkout_options(db, *, order: Order):
    """Retrieve live rates from ShipBubble for domestic checkout."""
    hubs = (
        await db.execute(
            select(FulfillmentHub).where(FulfillmentHub.is_active.is_(True)).order_by(FulfillmentHub.id)
        )
    ).scalars().all()
    if not hubs:
        # Check if an existing hub can be activated or auto-seed
        any_hub = (await db.execute(select(FulfillmentHub).order_by(FulfillmentHub.id))).scalars().first()
        if any_hub:
            any_hub.is_active = True
            any_hub.activated_at = datetime.now(ZoneInfo("UTC"))
            db.add(any_hub)
            await db.flush()
            hubs = [any_hub]
        else:
            admin = (await db.execute(select(User).where(User.role == "admin"))).scalars().first()
            import uuid as _uuid
            import datetime as _dt
            new_hub = FulfillmentHub(
                id=_uuid.uuid4(),
                code="lagos-central-hub",
                name="Shopsoma Lagos Central Hub",
                contact_name="Shopsoma Logistics",
                contact_phone="+2348012345678",
                address_line1="1 Admiralty Way, Lekki Phase 1",
                city="Lekki",
                state="Lagos",
                postal_code="105102",
                country_code="NG",
                timezone="Africa/Lagos",
                cutoff_time=_dt.time(16, 0),
                is_active=True,
                activated_at=datetime.now(ZoneInfo("UTC")),
                activated_by_id=admin.id if admin else None,
                version=1,
            )
            db.add(new_hub)
            await db.flush()
            hubs = [new_hub]
    hub = hubs[0]

    service = get_shipbubble_service()
    sender_address_code = hub.shipbubble_address_code
    if not sender_address_code:
        hub_address_str = f"{hub.address_line1} {hub.address_line2 or ''}".strip()
        try:
            val_hub = await service.validate_address(
                name=hub.contact_name or "Shopsoma Fulfillment Hub",
                email=settings.SHIPBUBBLE_SENDER_EMAIL or "logistics@shopsoma.com",
                phone=hub.contact_phone or "+2348000000000",
                address=f"{hub_address_str}, {hub.city}, {hub.state}, Nigeria",
            )
            sender_address_code = int(val_hub["address_code"])
            hub.shipbubble_address_code = sender_address_code
            db.add(hub)
            await db.flush()
        except ShipBubbleError as exc:
            logger.error("[ShipBubble] Failed to validate hub origin address: %s", exc)
            raise HTTPException(status_code=503, detail="Failed to validate fulfillment hub shipping origin") from exc

    address = order.shipping_address
    if not address or not address.address_line1 or not address.city or not address.state:
        raise HTTPException(status_code=422, detail="Valid delivery address required for ShipBubble rates")

    customer = await db.get(User, order.customer_id)
    dest_name = address.full_name or (customer.full_name if customer else "Valued Customer")
    dest_email = (customer.email if customer else None) or "customer@shopsoma.com"
    dest_phone = address.phone_number or (customer.phone_number if customer else "+2348000000000")
    dest_address_str = f"{address.address_line1} {address.address_line2 or ''}".strip()
    dest_country = "Nigeria" if not address.country or address.country.lower() in ("ng", "nigeria") else address.country
    dest_full = f"{dest_address_str}, {address.city}, {address.state}, {dest_country}"

    try:
        val_dest = await service.validate_address(
            name=dest_name,
            email=dest_email,
            phone=dest_phone,
            address=dest_full,
        )
        receiver_address_code = int(val_dest["address_code"])
    except ShipBubbleError as exc:
        logger.warning("[ShipBubble] Failed to validate customer delivery address: %s", exc)
        raise HTTPException(status_code=422, detail=f"Delivery address validation failed: {exc.message}") from exc

    item_measurements = [
        (item, product, values)
        for item, product, _profile, values in await _authoritative_parcel_measurements(
            db, order
        )
    ]
    if not item_measurements:
        raise HTTPException(status_code=422, detail="checkout has no shippable items")

    total_weight = Decimal("0")
    max_length = Decimal("0")
    max_width = Decimal("0")
    max_height = Decimal("0")
    total_volume = Decimal("0")
    package_items = []

    for item, product, values in item_measurements:
        if values is None or any(v is None for v in values):
            w, l, wd, h = (Decimal("0.5"), Decimal("10.0"), Decimal("10.0"), Decimal("10.0"))
        else:
            w = max(Decimal(str(values[0] or 0.5)), Decimal("0.01"))
            l = max(Decimal(str(values[1] or 10.0)), Decimal("1.0"))
            wd = max(Decimal(str(values[2] or 10.0)), Decimal("1.0"))
            h = max(Decimal(str(values[3] or 10.0)), Decimal("1.0"))

        total_weight += w * item.quantity
        max_length = max(max_length, l)
        max_width = max(max_width, wd)
        max_height = max(max_height, h)
        total_volume += l * wd * h * item.quantity

        product_title = getattr(product, "title", None) or getattr(product, "name", None) or "Item"
        product_desc = getattr(product, "description", None) or product_title

        package_items.append({
            "name": str(product_title)[:50],
            "description": str(product_desc)[:100],
            "unit_weight": float(w),
            "unit_amount": float(item.unit_price),
            "quantity": int(item.quantity),
        })

    effective_height = max(
        max_height,
        (total_volume / (max_length * max_width)).quantize(
            Decimal("0.1"), rounding=ROUND_CEILING
        ),
    )
    package_dimension = {
        "length": float(max_length.quantize(Decimal("0.1"))),
        "width": float(max_width.quantize(Decimal("0.1"))),
        "height": float(effective_height.quantize(Decimal("0.1"))),
    }

    now_lagos = datetime.now(_LAGOS_TZ)
    pickup_date = (
        now_lagos.date() if now_lagos.hour < 18 else now_lagos.date() + timedelta(days=1)
    ).strftime("%Y-%m-%d")
    category_id = settings.SHIPBUBBLE_CATEGORY_ID or 74794423

    try:
        rates_result = await service.fetch_rates(
            sender_address_code=sender_address_code,
            receiver_address_code=receiver_address_code,
            pickup_date=pickup_date,
            category_id=category_id,
            package_items=package_items,
            package_dimension=package_dimension,
        )
    except ShipBubbleError as exc:
        if "category" in str(exc).lower():
            try:
                available_cats = await service.get_categories()
                fallback_cat = next(
                    (c["category_id"] for c in available_cats if "fashion" in str(c.get("category", "")).lower()),
                    None
                )
                if not fallback_cat and available_cats:
                    fallback_cat = available_cats[0].get("category_id")
                if fallback_cat:
                    rates_result = await service.fetch_rates(
                        sender_address_code=sender_address_code,
                        receiver_address_code=receiver_address_code,
                        pickup_date=pickup_date,
                        category_id=fallback_cat,
                        package_items=package_items,
                        package_dimension=package_dimension,
                    )
                else:
                    raise exc
            except Exception:
                logger.error("[ShipBubble] fetch_rates error: %s", exc)
                raise HTTPException(status_code=503, detail=f"Unable to retrieve courier rates from ShipBubble: {exc.message}") from exc
        else:
            logger.error("[ShipBubble] fetch_rates error: %s", exc)
            raise HTTPException(status_code=503, detail=f"Unable to retrieve courier rates from ShipBubble: {exc.message}") from exc

    if not rates_result.couriers:
        raise HTTPException(status_code=503, detail="No courier services available for this destination")

    return rates_result


def _estimate_expiry_delta(ttl_seconds: int) -> timedelta:
    return timedelta(seconds=ttl_seconds)


def _estimate_request_fingerprint(
    order_id,
    snapshot_hash: str,
    parcel_snapshot_hash: str | None = None,
    subject_snapshot_hash: str | None = None,
) -> str:
    value = {"order_id": str(order_id), "snapshot": snapshot_hash}
    if parcel_snapshot_hash is not None:
        value["parcel_snapshot"] = parcel_snapshot_hash
    if subject_snapshot_hash is not None:
        value["subject_snapshot"] = subject_snapshot_hash
    return _hash(value)


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def order_snapshot(order: Order) -> tuple[str, str]:
    destination = {
        "address_line1": order.shipping_address.address_line1,
        "address_line2": order.shipping_address.address_line2,
        "city": order.shipping_address.city,
        "country": order.shipping_address.country,
        "postal_code": order.shipping_address.postal_code,
        "state": order.shipping_address.state,
    }
    items = [
        {
            "currency": item.currency,
            "id": str(item.id),
            "inventory_policy": item.inventory_policy,
            "inventory_subject_id": (
                str(item.inventory_subject_id) if item.inventory_subject_id else None
            ),
            "inventory_subject_kind": item.inventory_subject_kind,
            "quantity": item.quantity,
            "subtotal": str(item.subtotal),
            "unit_price": str(item.unit_price),
        }
        for item in sorted(order.items, key=lambda row: str(row.id))
    ]
    return _hash(destination), _hash(
        {
            "currency": order.currency,
            "destination": destination,
            "discount_amount": str(order.discount_amount),
            "items": items,
            "policy": order.workflow_policy_version,
            "subtotal": str(order.subtotal),
        }
    )


async def _authoritative_parcel_measurements(
    db, order: Order, *, for_update: bool = False
):
    """Resolve parcel measurements through the same profile path used for rating."""
    statement = (
        select(OrderItem, Product)
        .join(Product, Product.id == OrderItem.product_id)
        .where(OrderItem.order_id == order.id)
        .order_by(OrderItem.id)
    )
    if for_update:
        statement = statement.with_for_update()
    rows = (await db.execute(statement)).all()
    profile_statement = select(ProductLogisticsProfile).where(
        ProductLogisticsProfile.product_id.in_({product.id for _, product in rows})
    )
    if for_update:
        profile_statement = profile_statement.with_for_update()
    profile_rows = (await db.execute(profile_statement)).scalars().all()
    profiles_by_item = {
        (profile.product_id, profile.variant_id): profile for profile in profile_rows
    }

    measurements = []
    for item, product in rows:
        profile = profiles_by_item.get((product.id, item.variant_id))
        values = None
        if profile is not None:
            values = (
                profile.weight_kg,
                profile.length_cm,
                profile.width_cm,
                profile.height_cm,
            )
        if profile is None or (values is not None and all(value is None for value in values)):
            profile = profiles_by_item.get((product.id, None))
            values = (
                (
                    profile.weight_kg,
                    profile.length_cm,
                    profile.width_cm,
                    profile.height_cm,
                )
                if profile is not None
                else None
            )
        if profile is None or values is None or all(value is None for value in values):
            profile = None
            values = (
                product.weight_kg,
                product.length_cm,
                product.width_cm,
                product.height_cm,
            )
        measurements.append((item, product, profile, values))
    return measurements


async def parcel_measurement_snapshot(db, order: Order, *, for_update: bool = False) -> str:
    """Hash the authoritative parcel facts used by the DHL rating request."""
    measurements = await _authoritative_parcel_measurements(
        db, order, for_update=for_update
    )
    return _hash([
        {
            "order_item_id": str(item.id),
            "product_id": str(product.id),
            "variant_id": str(item.variant_id) if item.variant_id else None,
            "measurement_source_id": str(profile.id) if profile else None,
            "weight_kg": str(values[0]),
            "length_cm": str(values[1]),
            "width_cm": str(values[2]),
            "height_cm": str(values[3]),
        }
        for item, product, profile, values in measurements
    ])


async def dhl_subject_snapshot(
    db, order: Order, *, planned_ship_date=None, for_update: bool = False
) -> str:
    """Hash the persisted DHL subject identity, not only mutable order facts."""
    planned_ship_date = planned_ship_date or _planned_ship_date()
    handed_off = select(CustodyEvent.id).where(
        CustodyEvent.package_id == HubPackage.id,
        CustodyEvent.package_version == HubPackage.current_version,
        CustodyEvent.event_type.in_(("released", "tendered", "provider_accepted")),
    ).exists()
    packages = (
        await db.execute(
            select(HubPackage.id, HubPackage.current_version, HubPackage.hub_id)
            .where(HubPackage.order_id == order.id, HubPackage.state == "ready", ~handed_off)
            .order_by(HubPackage.ready_at.desc(), HubPackage.id.desc())
        )
    ).all()
    if len(packages) == 1:
        package_id, package_version, hub_id = packages[0]
        intent = (
            await db.execute(
                select(OutboundShipmentIntent.id, OutboundShipmentIntent.destination_postal_code)
                .where(
                    OutboundShipmentIntent.order_id == order.id,
                    OutboundShipmentIntent.package_id == package_id,
                    OutboundShipmentIntent.package_version == package_version,
                    ~select(OutboundShipmentIntentInvalidation.id)
                    .where(OutboundShipmentIntentInvalidation.intent_id == OutboundShipmentIntent.id)
                    .exists(),
                )
            )
        ).all()
        items = (
            await db.execute(
                select(HubPackageItem.order_item_id, HubPackageItem.cohort_id, HubPackageItem.quantity)
                .where(
                    HubPackageItem.package_id == package_id,
                    HubPackageItem.package_version == package_version,
                )
                .order_by(HubPackageItem.id)
            )
        ).all()
        hub_statement = select(FulfillmentHub.id, FulfillmentHub.version).where(
            FulfillmentHub.id == hub_id
        )
        if for_update:
            hub_statement = hub_statement.with_for_update()
        hub = (await db.execute(hub_statement)).one_or_none()
        version = await db.scalar(
            select(HubPackageVersion.id).where(
                HubPackageVersion.package_id == package_id,
                HubPackageVersion.version == package_version,
            )
        )
        seal = await db.scalar(
            select(HubPackageSeal.id).where(
                HubPackageSeal.package_id == package_id,
                HubPackageSeal.package_version == package_version,
                HubPackageSeal.retired_at.is_(None),
            )
        )
        return _hash({"package": [str(package_id), package_version, str(hub_id)], "intent": intent, "items": items, "hub": hub, "version": version, "seal": seal, "planned_ship_date": planned_ship_date})
    hub_statement = (
        select(FulfillmentHub.id, FulfillmentHub.version)
        .where(FulfillmentHub.is_active.is_(True))
        .order_by(FulfillmentHub.id)
    )
    if for_update:
        hub_statement = hub_statement.with_for_update()
    hubs = (await db.execute(hub_statement)).all()
    allocations = (
        await db.execute(
            select(CohortItemAllocation.order_item_id, CohortItemAllocation.cohort_id, CohortItemAllocation.allocated_quantity)
            .where(CohortItemAllocation.order_id == order.id)
            .order_by(CohortItemAllocation.order_item_id, CohortItemAllocation.cohort_id)
        )
    ).all()
    return _hash(
        {
            "ready_package_count": len(packages),
            "hubs": hubs,
            "allocations": allocations,
            "planned_ship_date": planned_ship_date,
        }
    )


async def _unhanded_ready_package_ids(
    db, order: Order, *, for_update: bool = False
) -> list:
    """Return ready packages still eligible for rating, locking state when requested."""
    package_query = (
        select(HubPackage.id, HubPackage.current_version, HubPackage.state)
        .where(HubPackage.order_id == order.id)
        .order_by(HubPackage.id)
    )
    if for_update:
        # Lock every package, not only ready ones: sealed -> ready is a
        # supported transition that must serialize with final revalidation.
        package_query = package_query.with_for_update()
    package_rows = (await db.execute(package_query)).all()
    if not package_rows:
        return []

    package_ids = [row.id for row in package_rows]
    custody_query = select(
        CustodyEvent.package_id,
        CustodyEvent.package_version,
        CustodyEvent.event_type,
    ).where(
        CustodyEvent.order_id == order.id,
        CustodyEvent.package_id.in_(package_ids),
    )
    if for_update:
        # Keep package and custody state stable through the final eligibility
        # fingerprint. Fulfillment handoff paths lock the package before
        # appending a custody event at this same serialization boundary.
        custody_query = custody_query.with_for_update()
    custody_rows = (await db.execute(custody_query)).all()
    handed_off = {
        (row.package_id, row.package_version)
        for row in custody_rows
        if row.event_type in ("released", "tendered", "provider_accepted")
    }
    return [
        row.id
        for row in package_rows
        if row.state == "ready"
        and (row.id, row.current_version) not in handed_off
    ]




async def _prepayment_parcel_snapshot(
    db, order: Order, *, for_update: bool = False
) -> str | None:
    """Return mutable parcel evidence only when no ready package is rated."""
    if await _unhanded_ready_package_ids(db, order, for_update=for_update):
        return None
    return await parcel_measurement_snapshot(db, order, for_update=for_update)


async def load_checkout_order(
    db, order_id, *, for_update: bool = False
) -> Order | None:
    if for_update:
        # Canonical checkout lock order starts with the aggregate root, then its
        # destination, then every item in stable UUID order. Callers retain
        # these locks before owner/coordinator/inventory/estimate/option locks.
        order = (
            await db.execute(
                select(Order).where(Order.id == order_id).with_for_update()
            )
        ).scalar_one_or_none()
        if not order:
            return None
        if order.shipping_address_id:
            await db.execute(
                select(Address.id)
                .where(Address.id == order.shipping_address_id)
                .with_for_update()
            )
        await db.execute(
            select(OrderItem.id)
            .where(OrderItem.order_id == order.id)
            .order_by(OrderItem.id)
            .with_for_update()
        )
        return await reload_checkout_order(db, order)

    statement = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.shipping_address))
        .where(Order.id == order_id)
    )
    return (await db.execute(statement)).scalar_one_or_none()


async def reload_checkout_order(db, order: Order) -> Order:
    """Replace cached aggregate state with fresh PostgreSQL row values."""
    db.expire(order, ["shipping_address", "items"])
    return (
        await db.execute(
            select(Order)
            .options(selectinload(Order.items), selectinload(Order.shipping_address))
            .where(Order.id == order.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def create_estimate(
    db,
    *,
    order: Order,
    actor_type: str,
    actor_id: str,
    idempotency_key: str,
    current_user=None,
    capability=None,
):
    if order.workflow_cohort != "domestic_checkout_v1":
        raise HTTPException(status_code=404, detail="checkout not available")
    existing = (
        await db.execute(
            select(CheckoutShippingEstimate).where(
                CheckoutShippingEstimate.customer_id == order.customer_id,
                CheckoutShippingEstimate.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()
    destination_hash, snapshot_hash = order_snapshot(order)

    provider_config = await shipping_provider_settings(db)
    provider = provider_config.provider
    enabled_providers = provider_config.enabled_providers
    if not existing and not provider_config.readiness.get(provider, False):
        raise HTTPException(status_code=503, detail=f"{provider} is not available for secure checkout")
    # Explicit manual overrides the environment; absent selection preserves
    # existing gated DHL behavior. Recovery of issued estimates is unchanged.
    capabilities = domestic_shipping_capabilities(settings)
    has_dhl_postal = bool(order.shipping_address and order.shipping_address.postal_code)
    manual_provider_enabled = (
        existing.source_kind == "static_domestic_rate" if existing
        else ("manual" in enabled_providers and provider_config.readiness["manual"])
    )
    dhl_provider_enabled = (
        existing.source_kind == "sandbox_normalized" if existing
        else ("dhl" in enabled_providers and capabilities.checkout_enabled and (len(enabled_providers) == 1 or has_dhl_postal))
    )
    shipbubble_provider_enabled = (
        existing.source_kind == "shipbubble_live" if existing
        else ("shipbubble" in enabled_providers and provider_config.readiness["shipbubble"])
    )
    is_pure_manual = manual_provider_enabled and not dhl_provider_enabled and not shipbubble_provider_enabled
    planned_ship_date = _planned_ship_date() if dhl_provider_enabled else None

    if is_pure_manual:
        # Static refreshes must serialize on the checkout aggregate too. The
        # provider path reacquires this lock after its external await; the
        # static path has no await boundary, so acquire it before leaf lookup.
        order = await load_checkout_order(db, order.id, for_update=True)
        if order is None:
            raise HTTPException(status_code=404, detail="checkout order no longer exists")
        destination_hash, snapshot_hash = order_snapshot(order)

    successor_estimate = aliased(CheckoutShippingEstimate)
    selection = aliased(CheckoutShippingEstimateSelection)
    current_unselected_leaf = (
        await db.execute(
            select(CheckoutShippingEstimate)
            .where(
                CheckoutShippingEstimate.order_id == order.id,
                CheckoutShippingEstimate.customer_id == order.customer_id,
                ~select(successor_estimate.id)
                .where(
                    successor_estimate.supersedes_estimate_id
                    == CheckoutShippingEstimate.id
                )
                .exists(),
                ~select(selection.id)
                .where(selection.estimate_id == CheckoutShippingEstimate.id)
                .exists(),
            )
            .order_by(
                CheckoutShippingEstimate.created_at.desc(),
                CheckoutShippingEstimate.id.desc(),
            )
            .limit(1)
        )
    ).scalar_one_or_none()

    # Ready packages rate their immutable HubPackageVersion measurements;
    # mutable catalog dimensions only belong to the pre-payment quote subject.
    parcel_snapshot_hash = (
        await _prepayment_parcel_snapshot(db, order)
        if dhl_provider_enabled
        else None
    )
    subject_snapshot_hash = (
        await dhl_subject_snapshot(
            db, order, planned_ship_date=planned_ship_date
        )
        if dhl_provider_enabled
        else None
    )
    fingerprint = _estimate_request_fingerprint(
        order.id, snapshot_hash, parcel_snapshot_hash, subject_snapshot_hash
    )
    if existing:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail="idempotency conflict")
        return existing
    payment_status = getattr(order, "payment_status", None)
    fulfillment_status = getattr(order, "fulfillment_status", None)
    if (
        getattr(order, "checkout_prerequisites_completed_at", None) is not None
        or getattr(payment_status, "value", payment_status) == "paid"
        or getattr(fulfillment_status, "value", fulfillment_status) == "cancelled"
    ):
        raise HTTPException(status_code=409, detail="checkout estimate is no longer available")

    estimate = None
    usd_to_ngn_rate = None
    if order.currency == "USD":
        rate_setting = await db.scalar(
            select(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
        )
        try:
            usd_to_ngn_rate = Decimal(str(rate_setting.value))
        except (ArithmeticError, ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(
                status_code=503, detail="authoritative exchange rate unavailable"
            ) from exc
        if not usd_to_ngn_rate.is_finite() or usd_to_ngn_rate <= 0:
            raise HTTPException(
                status_code=503, detail="authoritative exchange rate unavailable"
            )

    if is_pure_manual:
        database_now = await db.scalar(select(text("statement_timestamp()")))
        estimate = CheckoutShippingEstimate(
            order_id=order.id,
            customer_id=order.customer_id,
            supersedes_estimate_id=(
                current_unselected_leaf.id if current_unselected_leaf is not None else None
            ),
            destination_snapshot_hash=destination_hash,
            order_snapshot_hash=snapshot_hash,
            currency=order.currency,
            ttl_seconds=_ESTIMATE_TTL_SECONDS,
            expires_at=database_now + _estimate_expiry_delta(_ESTIMATE_TTL_SECONDS),
            source_kind="static_domestic_rate",
            source_reference="shipping_rates:v1",
            source_command=(
                "refresh_checkout_estimate"
                if current_unselected_leaf is not None
                else "create_checkout_estimate"
            ),
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            schema_version="checkout_estimate_v1",
            created_by_actor_type=actor_type,
            created_by_actor_id=actor_id,
        )
        customer_id = order.customer_id
        db.add(estimate)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            replay = await db.scalar(
                select(CheckoutShippingEstimate).where(
                    CheckoutShippingEstimate.customer_id == customer_id,
                    CheckoutShippingEstimate.idempotency_key == idempotency_key,
                )
            )
            if replay is None:
                raise
            if replay.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return replay

    def ngn_in_order_currency(value) -> Decimal:
        amount = Decimal(value)
        if order.currency == "USD":
            assert usd_to_ngn_rate is not None
            amount /= usd_to_ngn_rate
        return amount.quantize(_CENT, rounding=ROUND_HALF_UP)

    rates = (
        (
            await db.execute(
                manual_rates_query(order.shipping_address.country, order.shipping_address.state)
            )
        )
        .scalars()
        .all()
    )
    eligible_manual_rates = [
        rate
        for rate in rates
        if (
            rate.min_order_value is None
            or ngn_in_order_currency(rate.min_order_value) <= order.subtotal
        )
        and (
            rate.max_order_value is None
            or ngn_in_order_currency(rate.max_order_value) >= order.subtotal
        )
    ]
    if not eligible_manual_rates and is_pure_manual:
        raise HTTPException(status_code=503, detail="no eligible estimate options")
    dhl_offers = None
    sb_rates_result = None
    combined_manual_rates = None

    active_providers_count = sum(1 for p in (manual_provider_enabled, dhl_provider_enabled, shipbubble_provider_enabled) if p)
    if provider == "combined" or active_providers_count > 1:
        comb_lock_key = f"comb:{order.customer_id}:{idempotency_key}"
        await db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(:lock_key, 0))"
            ),
            {"lock_key": comb_lock_key},
        )
        existing = await db.scalar(
            select(CheckoutShippingEstimate).where(
                CheckoutShippingEstimate.customer_id == order.customer_id,
                CheckoutShippingEstimate.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return existing

        if dhl_provider_enabled:
            try:
                raw_dhl = await _dhl_checkout_options(
                    db, order=order, planned_ship_date=planned_ship_date
                )
                dhl_offers = tuple(
                    offer for offer in raw_dhl if offer.provider_product_code == "N"
                )
            except HTTPException as exc:
                logger.warning("[Combined Shipping] DHL rate check skipped/failed: %s", exc.detail)
                dhl_offers = None
            except Exception as exc:
                logger.warning("[Combined Shipping] DHL rate check unexpected error: %s", exc)
                dhl_offers = None

        if shipbubble_provider_enabled:
            try:
                sb_rates_result = await _shipbubble_checkout_options(db, order=order)
            except HTTPException as exc:
                logger.warning("[Combined Shipping] ShipBubble rate check skipped/failed: %s", exc.detail)
                sb_rates_result = None
            except Exception as exc:
                logger.warning("[Combined Shipping] ShipBubble rate check unexpected error: %s", exc)
                sb_rates_result = None

        if manual_provider_enabled and eligible_manual_rates:
            combined_manual_rates = eligible_manual_rates

        if not dhl_offers and not sb_rates_result and not combined_manual_rates:
            raise HTTPException(
                status_code=503,
                detail="No eligible courier services available from enabled shipping providers",
            )

        fresh_order = await load_checkout_order(db, order.id, for_update=True)
        if fresh_order is None:
            raise HTTPException(status_code=404, detail="checkout order no longer exists")
        refreshed_actor_type, refreshed_actor_id = await authorize_checkout_actor(
            db,
            order=fresh_order,
            current_user=current_user,
            token=capability,
        )
        if (refreshed_actor_type, refreshed_actor_id) != (actor_type, actor_id):
            raise HTTPException(status_code=404, detail="checkout not available")
        fresh_payment_status = getattr(fresh_order, "payment_status", None)
        fresh_fulfillment_status = getattr(fresh_order, "fulfillment_status", None)
        if (
            getattr(fresh_order, "checkout_prerequisites_completed_at", None) is not None
            or getattr(fresh_payment_status, "value", fresh_payment_status) == "paid"
            or getattr(fresh_fulfillment_status, "value", fresh_fulfillment_status)
            == "cancelled"
        ):
            raise HTTPException(status_code=409, detail="checkout estimate is no longer available")
        _, fresh_snapshot_hash = order_snapshot(fresh_order)
        if fresh_snapshot_hash != snapshot_hash:
            raise HTTPException(status_code=409, detail="order changed during courier rating")
        if dhl_offers:
            fresh_parcel_snapshot_hash = await _prepayment_parcel_snapshot(
                db, fresh_order, for_update=True
            )
            if fresh_parcel_snapshot_hash != parcel_snapshot_hash:
                raise HTTPException(
                    status_code=409, detail="parcel measurements changed during DHL rating"
                )
            fresh_subject_snapshot_hash = await dhl_subject_snapshot(
                db,
                fresh_order,
                planned_ship_date=planned_ship_date,
                for_update=True,
            )
            if fresh_subject_snapshot_hash != subject_snapshot_hash:
                raise HTTPException(
                    status_code=409, detail="DHL shipment subject changed during rating"
                )
        order = fresh_order
        current_unselected_leaf = (
            await db.execute(
                select(CheckoutShippingEstimate)
                .where(
                    CheckoutShippingEstimate.order_id == order.id,
                    CheckoutShippingEstimate.customer_id == order.customer_id,
                    ~select(successor_estimate.id)
                    .where(
                        successor_estimate.supersedes_estimate_id
                        == CheckoutShippingEstimate.id
                    )
                    .exists(),
                    ~select(selection.id)
                    .where(selection.estimate_id == CheckoutShippingEstimate.id)
                    .exists(),
                )
                .order_by(
                    CheckoutShippingEstimate.created_at.desc(),
                    CheckoutShippingEstimate.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        existing = await db.scalar(
            select(CheckoutShippingEstimate).where(
                CheckoutShippingEstimate.customer_id == order.customer_id,
                CheckoutShippingEstimate.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return existing
        database_now = await db.scalar(select(text("statement_timestamp()")))
        customer_id = order.customer_id
        source_kind = "sandbox_normalized" if dhl_offers else ("shipbubble_live" if sb_rates_result else "static_domestic_rate")
        refs = []
        if dhl_offers:
            refs.append("dhl")
        if sb_rates_result:
            refs.append(f"sb:{sb_rates_result.request_token[:16]}")
        if combined_manual_rates:
            refs.append("manual")
        source_ref = (
            f"combined:{'+'.join(refs)}"
            if len(refs) > 1
            else ("dhl:mydhlapi:test" if dhl_offers else (f"shipbubble:{sb_rates_result.request_token[:16]}" if sb_rates_result else "shipping_rates:v1"))
        )
        estimate = CheckoutShippingEstimate(
            order_id=order.id,
            customer_id=customer_id,
            supersedes_estimate_id=(
                current_unselected_leaf.id if current_unselected_leaf is not None else None
            ),
            destination_snapshot_hash=destination_hash,
            order_snapshot_hash=snapshot_hash,
            currency=order.currency,
            ttl_seconds=_ESTIMATE_TTL_SECONDS,
            expires_at=database_now + _estimate_expiry_delta(_ESTIMATE_TTL_SECONDS),
            source_kind=source_kind,
            source_reference=source_ref,
            source_command=(
                "refresh_checkout_estimate"
                if current_unselected_leaf is not None
                else "create_checkout_estimate"
            ),
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            schema_version="checkout_estimate_v1",
            created_by_actor_type=actor_type,
            created_by_actor_id=actor_id,
        )
        db.add(estimate)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            replay = await db.scalar(
                select(CheckoutShippingEstimate).where(
                    CheckoutShippingEstimate.customer_id == customer_id,
                    CheckoutShippingEstimate.idempotency_key == idempotency_key,
                )
            )
            if replay is None:
                raise
            if replay.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return replay
    elif dhl_provider_enabled:
        # Serialize the provider boundary for one customer/idempotency key.  A
        # row-level estimate claim cannot be inserted until the provider result
        # is known, so use a transaction-scoped advisory lock to prevent two
        # concurrent requests from both consuming a DHL rating attempt.
        dhl_idempotency_lock_key = f"{order.customer_id}:{idempotency_key}"
        await db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(:lock_key, 0))"
            ),
            {"lock_key": dhl_idempotency_lock_key},
        )
        existing = await db.scalar(
            select(CheckoutShippingEstimate).where(
                CheckoutShippingEstimate.customer_id == order.customer_id,
                CheckoutShippingEstimate.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return existing
        dhl_offers = tuple(
            offer
            for offer in await _dhl_checkout_options(
                db, order=order, planned_ship_date=planned_ship_date
            )
            if offer.provider_product_code == "N"
        )
        if not dhl_offers:
            raise HTTPException(status_code=503, detail="DHL has no eligible checkout service")
        fresh_order = await load_checkout_order(db, order.id, for_update=True)
        if fresh_order is None:
            raise HTTPException(status_code=404, detail="checkout order no longer exists")
        refreshed_actor_type, refreshed_actor_id = await authorize_checkout_actor(
            db,
            order=fresh_order,
            current_user=current_user,
            token=capability,
        )
        if (refreshed_actor_type, refreshed_actor_id) != (actor_type, actor_id):
            raise HTTPException(status_code=404, detail="checkout not available")
        fresh_payment_status = getattr(fresh_order, "payment_status", None)
        fresh_fulfillment_status = getattr(fresh_order, "fulfillment_status", None)
        if (
            getattr(fresh_order, "checkout_prerequisites_completed_at", None) is not None
            or getattr(fresh_payment_status, "value", fresh_payment_status) == "paid"
            or getattr(fresh_fulfillment_status, "value", fresh_fulfillment_status)
            == "cancelled"
        ):
            raise HTTPException(status_code=409, detail="checkout estimate is no longer available")
        _, fresh_snapshot_hash = order_snapshot(fresh_order)
        if fresh_snapshot_hash != snapshot_hash:
            raise HTTPException(status_code=409, detail="order changed during DHL rating")
        fresh_parcel_snapshot_hash = await _prepayment_parcel_snapshot(
            db, fresh_order, for_update=True
        )
        if fresh_parcel_snapshot_hash != parcel_snapshot_hash:
            raise HTTPException(
                status_code=409, detail="parcel measurements changed during DHL rating"
            )
        fresh_subject_snapshot_hash = await dhl_subject_snapshot(
            db,
            fresh_order,
            planned_ship_date=planned_ship_date,
            for_update=True,
        )
        if fresh_subject_snapshot_hash != subject_snapshot_hash:
            raise HTTPException(
                status_code=409, detail="DHL shipment subject changed during rating"
            )
        order = fresh_order
        current_unselected_leaf = (
            await db.execute(
                select(CheckoutShippingEstimate)
                .where(
                    CheckoutShippingEstimate.order_id == order.id,
                    CheckoutShippingEstimate.customer_id == order.customer_id,
                    ~select(successor_estimate.id)
                    .where(
                        successor_estimate.supersedes_estimate_id
                        == CheckoutShippingEstimate.id
                    )
                    .exists(),
                    ~select(selection.id)
                    .where(selection.estimate_id == CheckoutShippingEstimate.id)
                    .exists(),
                )
                .order_by(
                    CheckoutShippingEstimate.created_at.desc(),
                    CheckoutShippingEstimate.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        existing = await db.scalar(
            select(CheckoutShippingEstimate).where(
                CheckoutShippingEstimate.customer_id == order.customer_id,
                CheckoutShippingEstimate.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return existing
        database_now = await db.scalar(select(text("statement_timestamp()")))
        customer_id = order.customer_id
        estimate = CheckoutShippingEstimate(
            order_id=order.id,
            customer_id=customer_id,
            supersedes_estimate_id=(
                current_unselected_leaf.id if current_unselected_leaf is not None else None
            ),
            destination_snapshot_hash=destination_hash,
            order_snapshot_hash=snapshot_hash,
            currency=order.currency,
            ttl_seconds=_ESTIMATE_TTL_SECONDS,
            expires_at=database_now + _estimate_expiry_delta(_ESTIMATE_TTL_SECONDS),
            source_kind="sandbox_normalized",
            source_reference="dhl:mydhlapi:test",
            source_command=(
                "refresh_checkout_estimate"
                if current_unselected_leaf is not None
                else "create_checkout_estimate"
            ),
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            schema_version="checkout_estimate_v1",
            created_by_actor_type=actor_type,
            created_by_actor_id=actor_id,
        )
        db.add(estimate)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            replay = await db.scalar(
                select(CheckoutShippingEstimate).where(
                    CheckoutShippingEstimate.customer_id == customer_id,
                    CheckoutShippingEstimate.idempotency_key == idempotency_key,
                )
            )
            if replay is None:
                raise
            if replay.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return replay

    elif shipbubble_provider_enabled:
        sb_idempotency_lock_key = f"sb:{order.customer_id}:{idempotency_key}"
        await db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(:lock_key, 0))"
            ),
            {"lock_key": sb_idempotency_lock_key},
        )
        existing = await db.scalar(
            select(CheckoutShippingEstimate).where(
                CheckoutShippingEstimate.customer_id == order.customer_id,
                CheckoutShippingEstimate.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return existing
        sb_rates_result = await _shipbubble_checkout_options(db, order=order)
        fresh_order = await load_checkout_order(db, order.id, for_update=True)
        if fresh_order is None:
            raise HTTPException(status_code=404, detail="checkout order no longer exists")
        refreshed_actor_type, refreshed_actor_id = await authorize_checkout_actor(
            db,
            order=fresh_order,
            current_user=current_user,
            token=capability,
        )
        if (refreshed_actor_type, refreshed_actor_id) != (actor_type, actor_id):
            raise HTTPException(status_code=404, detail="checkout not available")
        fresh_payment_status = getattr(fresh_order, "payment_status", None)
        fresh_fulfillment_status = getattr(fresh_order, "fulfillment_status", None)
        if (
            getattr(fresh_order, "checkout_prerequisites_completed_at", None) is not None
            or getattr(fresh_payment_status, "value", fresh_payment_status) == "paid"
            or getattr(fresh_fulfillment_status, "value", fresh_fulfillment_status)
            == "cancelled"
        ):
            raise HTTPException(status_code=409, detail="checkout estimate is no longer available")
        _, fresh_snapshot_hash = order_snapshot(fresh_order)
        if fresh_snapshot_hash != snapshot_hash:
            raise HTTPException(status_code=409, detail="order changed during ShipBubble rating")
        order = fresh_order
        current_unselected_leaf = (
            await db.execute(
                select(CheckoutShippingEstimate)
                .where(
                    CheckoutShippingEstimate.order_id == order.id,
                    CheckoutShippingEstimate.customer_id == order.customer_id,
                    ~select(successor_estimate.id)
                    .where(
                        successor_estimate.supersedes_estimate_id
                        == CheckoutShippingEstimate.id
                    )
                    .exists(),
                    ~select(selection.id)
                    .where(selection.estimate_id == CheckoutShippingEstimate.id)
                    .exists(),
                )
                .order_by(
                    CheckoutShippingEstimate.created_at.desc(),
                    CheckoutShippingEstimate.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        existing = await db.scalar(
            select(CheckoutShippingEstimate).where(
                CheckoutShippingEstimate.customer_id == order.customer_id,
                CheckoutShippingEstimate.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return existing
        database_now = await db.scalar(select(text("statement_timestamp()")))
        customer_id = order.customer_id
        estimate = CheckoutShippingEstimate(
            order_id=order.id,
            customer_id=customer_id,
            supersedes_estimate_id=(
                current_unselected_leaf.id if current_unselected_leaf is not None else None
            ),
            destination_snapshot_hash=destination_hash,
            order_snapshot_hash=snapshot_hash,
            currency=order.currency,
            ttl_seconds=_ESTIMATE_TTL_SECONDS,
            expires_at=database_now + _estimate_expiry_delta(_ESTIMATE_TTL_SECONDS),
            source_kind="shipbubble_live",
            source_reference=f"shipbubble:{sb_rates_result.request_token[:16]}",
            source_command=(
                "refresh_checkout_estimate"
                if current_unselected_leaf is not None
                else "create_checkout_estimate"
            ),
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            schema_version="checkout_estimate_v1",
            created_by_actor_type=actor_type,
            created_by_actor_id=actor_id,
        )
        db.add(estimate)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            replay = await db.scalar(
                select(CheckoutShippingEstimate).where(
                    CheckoutShippingEstimate.customer_id == customer_id,
                    CheckoutShippingEstimate.idempotency_key == idempotency_key,
                )
            )
            if replay is None:
                raise
            if replay.request_fingerprint != fingerprint:
                raise HTTPException(status_code=409, detail="idempotency conflict")
            return replay

    if estimate is None:
        raise HTTPException(status_code=500, detail="checkout estimate was not created")
    if dhl_offers is not None or sb_rates_result is not None or combined_manual_rates is not None:
        if dhl_offers is not None:
            for offer in dhl_offers:
                rate = offer.rate
                if rate.currency == order.currency:
                    amount = Decimal(rate.total_amount).quantize(_CENT, rounding=ROUND_HALF_UP)
                elif rate.currency == "NGN":
                    amount = ngn_in_order_currency(rate.total_amount)
                elif rate.currency == "USD" and order.currency == "NGN":
                    if usd_to_ngn_rate is None:
                        rate_setting = await db.scalar(
                            select(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
                        )
                        try:
                            usd_to_ngn_rate = Decimal(str(rate_setting.value))
                        except (ArithmeticError, ValueError, TypeError, AttributeError) as exc:
                            raise HTTPException(
                                status_code=503, detail="authoritative exchange rate unavailable"
                            ) from exc
                        if not usd_to_ngn_rate.is_finite() or usd_to_ngn_rate <= 0:
                            raise HTTPException(
                                status_code=503, detail="authoritative exchange rate unavailable"
                            )
                    amount = (Decimal(rate.total_amount) * usd_to_ngn_rate).quantize(_CENT, rounding=ROUND_HALF_UP)
                else:
                    raise HTTPException(status_code=503, detail="DHL returned an unsupported checkout currency")
                if amount > _MAX_CHECKOUT_OPTION_AMOUNT:
                    raise HTTPException(
                        status_code=503,
                        detail="DHL returned a checkout amount outside the supported range",
                    )
                transit_days = getattr(rate, "carrier_transit_days", None)
                eta_date = getattr(rate, "estimated_carrier_delivery_date", None)
                if transit_days is None and eta_date is not None and estimate.created_at is not None:
                    delta_days = (eta_date - estimate.created_at.date()).days
                    if delta_days >= 1:
                        transit_days = delta_days
                clamped_days = (
                    max(1, min(365, int(transit_days)))
                    if isinstance(transit_days, int) and not isinstance(transit_days, bool) and transit_days >= 1
                    else None
                )
                dhl_label = f"DHL Express ({offer.service_label})" if "dhl" not in offer.service_label.lower() else offer.service_label
                db.add(
                    CheckoutShippingEstimateOption(
                        estimate_id=estimate.id,
                        option_key=f"dhl:{offer.provider_product_code}:{offer.provider_service_code}",
                        service_code=offer.provider_service_code,
                        service_label=dhl_label,
                        amount=amount,
                        currency=order.currency,
                        min_delivery_days=clamped_days,
                        max_delivery_days=clamped_days,
                        source_rate_id=None,
                        provider_metadata={
                            "provider": "dhl",
                            "product_code": offer.provider_product_code,
                            "service_code": offer.provider_service_code,
                            "service_label": dhl_label,
                            "transit_days": clamped_days,
                            "estimated_delivery_date": (
                                eta_date.isoformat() if eta_date is not None else None
                            ),
                            "source_amount": str(rate.total_amount),
                            "source_currency": rate.currency,
                        },
                    )
                )
        if sb_rates_result is not None:
            for rank, courier in enumerate(sb_rates_result.couriers):
                if courier.currency == order.currency:
                    amount = courier.rate_card_amount.quantize(_CENT, rounding=ROUND_HALF_UP)
                elif courier.currency == "NGN" and order.currency == "USD":
                    amount = ngn_in_order_currency(courier.rate_card_amount)
                elif courier.currency == "USD" and order.currency == "NGN":
                    if usd_to_ngn_rate is None:
                        rate_setting = await db.scalar(
                            select(Setting).where(Setting.key == "exchange_rate_usd_to_ngn")
                        )
                        try:
                            usd_to_ngn_rate = Decimal(str(rate_setting.value))
                        except (ArithmeticError, ValueError, TypeError, AttributeError) as exc:
                            raise HTTPException(
                                status_code=503, detail="authoritative exchange rate unavailable"
                            ) from exc
                        if not usd_to_ngn_rate.is_finite() or usd_to_ngn_rate <= 0:
                            raise HTTPException(
                                status_code=503, detail="authoritative exchange rate unavailable"
                            )
                    amount = (courier.rate_card_amount * usd_to_ngn_rate).quantize(_CENT, rounding=ROUND_HALF_UP)
                else:
                    amount = ngn_in_order_currency(courier.rate_card_amount)

                if amount > _MAX_CHECKOUT_OPTION_AMOUNT:
                    raise HTTPException(
                        status_code=503,
                        detail="ShipBubble returned a checkout amount outside the supported range",
                    )

                cid_slug = re.sub(r"[^a-zA-Z0-9_\-]", "", str(courier.courier_id))
                sc_slug = re.sub(r"[^a-zA-Z0-9_\-]", "", str(courier.service_code))
                opt_key = f"sb:{rank:02d}:{cid_slug}:{sc_slug}"[:100]
                svc_code = f"sb-{cid_slug}-{sc_slug}"[:100]

                provider_metadata = {
                    "provider": "shipbubble",
                    "request_token": sb_rates_result.request_token,
                    "courier_id": str(courier.courier_id),
                    "courier_name": courier.courier_name,
                    "service_code": courier.service_code,
                    "service_type": courier.service_type,
                    "rate_card_amount": str(courier.rate_card_amount),
                    "total_wallet_amount": str(courier.total_wallet_amount),
                    "delivery_eta": courier.delivery_eta,
                    "courier_image": courier.courier_image,
                }

                label = courier.courier_name
                if courier.delivery_eta:
                    label = f"{courier.courier_name} ({courier.delivery_eta})"

                db.add(
                    CheckoutShippingEstimateOption(
                        estimate_id=estimate.id,
                        option_key=opt_key,
                        service_code=svc_code,
                        service_label=label,
                        amount=amount,
                        currency=order.currency,
                        min_delivery_days=courier.min_delivery_days,
                        max_delivery_days=courier.max_delivery_days,
                        source_rate_id=None,
                        provider_metadata=provider_metadata,
                    )
                )
        if combined_manual_rates is not None:
            for rank, rate in enumerate(combined_manual_rates):
                amount = ngn_in_order_currency(rate.base_rate)
                db.add(
                    CheckoutShippingEstimateOption(
                        estimate_id=estimate.id,
                        option_key=f"static:{rank:09d}:{rate.id}",
                        service_code=f"static-{rate.priority}",
                        service_label=rate.name,
                        amount=amount,
                        currency=order.currency,
                        min_delivery_days=rate.min_delivery_days,
                        max_delivery_days=rate.max_delivery_days,
                        source_rate_id=None,
                        provider_metadata={
                            "provider": "manual",
                            "rate_id": str(rate.id),
                            "priority": rate.priority,
                        },
                    )
                )
    else:
        for rank, rate in enumerate(eligible_manual_rates):
            amount = ngn_in_order_currency(rate.base_rate)
            db.add(
                CheckoutShippingEstimateOption(
                    estimate_id=estimate.id,
                    # The query order is the configured default/priority order.
                    # Persist that rank because estimate_payload() reloads rows
                    # later and must not sort by the random UUID suffix.
                    option_key=f"static:{rank:09d}:{rate.id}",
                    service_code=f"static-{rate.priority}",
                    service_label=rate.name,
                    amount=amount,
                    currency=order.currency,
                    min_delivery_days=rate.min_delivery_days,
                    max_delivery_days=rate.max_delivery_days,
                    source_rate_id=rate.id,
                    provider_metadata={
                        "provider": "manual",
                        "rate_id": str(rate.id),
                        "priority": rate.priority,
                    },
                )
            )
    await db.flush()
    return estimate


async def estimate_payload(
    db, *, order: Order, estimate: CheckoutShippingEstimate
) -> dict:
    options = (
        (
            await db.execute(
                select(CheckoutShippingEstimateOption)
                .where(CheckoutShippingEstimateOption.estimate_id == estimate.id)
                .order_by(CheckoutShippingEstimateOption.option_key)
            )
        )
        .scalars()
        .all()
    )
    selection = (
        await db.execute(
            select(CheckoutShippingEstimateSelection).where(
                CheckoutShippingEstimateSelection.estimate_id == estimate.id
            )
        )
    ).scalar_one_or_none()
    selected = next(
        (row for row in options if selection and row.id == selection.option_id), None
    )
    return {
        "id": estimate.id,
        "order_id": estimate.order_id,
        "currency": estimate.currency,
        "expires_at": estimate.expires_at,
        "options": options,
        "selected_option": selected,
        "server_tax_amount": order.tax_amount,
        "server_payable_total": order.total_amount,
    }
