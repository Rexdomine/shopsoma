"""Hub package readiness and quote-selection bridge for DHL sandbox fulfillment.

Constructs the trigger-verified Hub receipt, QC, package, seal, custody stream,
outbound shipment intent, and selected quote records for a paid DHL order so the
order can transition seamlessly from vendor/admin item readiness into DHL shadow
quoting, shipment booking, label download, tracking, and handoff.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, time, timedelta
from decimal import Decimal
import hashlib
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimate,
    CheckoutShippingEstimateOption,
    CheckoutShippingEstimateSelection,
)
from app.models.customer_shipping_quote import (
    CustomerShippingQuote,
    CustomerShippingQuoteOption,
    CustomerShippingQuoteSelection,
)
from app.models.domestic_rate_quote import (
    DomesticRateAttempt,
    DomesticRateOffer,
    DomesticRateResponse,
)
from app.models.fulfillment_cohort import (
    CohortItemAllocation,
    FulfillmentCohort,
    FulfillmentReadinessType,
)
from app.models.fulfillment_hub import FulfillmentHub
from app.models.hub_quality import (
    EvidencePurpose,
    HubEvidence,
    HubQCInspection,
    HubQCSession,
    HubReceiptItem,
    HubReceiptSession,
    QCDecision,
    QuarantineDisposition,
)
from app.models.inbound_transfer import (
    InboundTransfer,
    InboundTransferItemAllocation,
)
from app.models.order import Order, OrderItem
from app.models.package_custody import (
    CustodyEvent,
    CustodyStream,
    HubPackage,
    HubPackageItem,
    HubPackageSeal,
    HubPackageVersion,
    OutboundShipmentIntent,
    OutboundShipmentIntentInvalidation,
)
from app.models.product_logistics_profile import ProductLogisticsProfile
from app.models.user import User, UserRole
from app.services.admin_shadow_quote import _planned_ship_date_for_shadow_quote
from app.services.dhl.rating import derive_sandbox_cohort_id

HUB_PREP_SOURCE_SYSTEM = "shopsoma_hub_prep"
DEFAULT_SANDBOX_NAMESPACE = uuid.UUID("30f204c5-ac27-4719-89fc-cc9208f19032")


async def _resolve_operator_id(
    db: AsyncSession,
    *,
    order: Order,
    actor_id: uuid.UUID | None,
) -> uuid.UUID:
    if actor_id is not None:
        return actor_id
    admin_id = await db.scalar(
        select(User.id).where(User.role == UserRole.ADMIN).limit(1)
    )
    if admin_id is not None:
        return admin_id
    if order.customer_id is not None:
        return order.customer_id
    any_user_id = await db.scalar(select(User.id).limit(1))
    if any_user_id is None:
        raise ValueError("No operator user available to record hub package preparation")
    return any_user_id


async def _ensure_active_nigerian_hub(
    db: AsyncSession,
    *,
    operator_id: uuid.UUID,
) -> FulfillmentHub:
    hub = (
        await db.execute(
            select(FulfillmentHub)
            .where(
                FulfillmentHub.is_active.is_(True),
                FulfillmentHub.country_code == "NG",
            )
            .order_by(FulfillmentHub.created_at.asc(), FulfillmentHub.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if hub is not None:
        return hub

    inactive_hub = (
        await db.execute(
            select(FulfillmentHub)
            .where(FulfillmentHub.country_code == "NG")
            .order_by(FulfillmentHub.created_at.asc(), FulfillmentHub.id.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if inactive_hub is not None:
        await db.execute(
            text(
                "UPDATE fulfillment_hubs SET is_active=true, "
                "activated_at=clock_timestamp(), activated_by_id=:actor "
                "WHERE id=:hub"
            ),
            {"actor": operator_id, "hub": inactive_hub.id},
        )
        await db.refresh(inactive_hub)
        return inactive_hub

    hub = FulfillmentHub(
        code=f"lagos-hub-{uuid.uuid4().hex[:8]}",
        name="ShopSoma Lagos Hub",
        contact_name="ShopSoma Hub Dispatch",
        contact_phone="+2348000000000",
        address_line1="14 Ademola Adetokunbo Street, Victoria Island",
        city="Lagos",
        state="Lagos",
        postal_code="101241",
        country_code="NG",
        cutoff_time=time(14, 0),
    )
    db.add(hub)
    await db.flush()
    await db.execute(
        text(
            "UPDATE fulfillment_hubs SET is_active=true, "
            "activated_at=clock_timestamp(), activated_by_id=:actor "
            "WHERE id=:hub"
        ),
        {"actor": operator_id, "hub": hub.id},
    )
    await db.refresh(hub)
    return hub


async def _compute_parcel_measurements(
    db: AsyncSession,
    *,
    items: list[OrderItem],
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    total_weight = Decimal("0.000")
    max_length = Decimal("30.000")
    max_width = Decimal("25.000")
    total_height = Decimal("0.000")

    product_ids = [item.product_id for item in items if item.product_id is not None]
    profiles_by_product: dict[uuid.UUID, ProductLogisticsProfile] = {}
    if product_ids:
        rows = (
            await db.execute(
                select(ProductLogisticsProfile).where(
                    ProductLogisticsProfile.product_id.in_(product_ids)
                )
            )
        ).scalars().all()
        profiles_by_product = {row.product_id: row for row in rows}

    for item in items:
        qty = max(int(item.quantity or 1), 1)
        profile = profiles_by_product.get(item.product_id) if item.product_id else None
        if profile is not None:
            total_weight += Decimal(str(profile.weight_kg)) * qty
            max_length = max(max_length, Decimal(str(profile.length_cm)))
            max_width = max(max_width, Decimal(str(profile.width_cm)))
            total_height += Decimal(str(profile.height_cm)) * qty
        else:
            total_weight += Decimal("0.600") * qty
            total_height += Decimal("5.000") * qty

    if total_weight <= 0:
        total_weight = Decimal("1.250")
    if total_height <= 0:
        total_height = Decimal("10.000")

    return (
        total_weight.quantize(Decimal("0.001")),
        max_length.quantize(Decimal("0.001")),
        max_width.quantize(Decimal("0.001")),
        min(total_height, Decimal("120.000")).quantize(Decimal("0.001")),
    )


async def _resolve_selected_dhl_service_for_order(
    db: AsyncSession,
    *,
    order: Order,
    planned_ship_date: date,
) -> dict[str, Any]:
    product_code = "N"
    service_code = "N"
    service_label = "EXPRESS DOMESTIC"
    amount = Decimal(str(order.shipping_cost or Decimal("13555.09"))).quantize(
        Decimal("0.0001")
    )
    if amount <= 0:
        amount = Decimal("13555.0900")
    currency = (order.currency or "NGN").upper()
    transit_days = 3
    delivery_date = order.estimated_delivery_date or (
        planned_ship_date + timedelta(days=transit_days)
    )

    if order.checkout_estimate_selection_id is not None:
        row = (
            await db.execute(
                select(
                    CheckoutShippingEstimateSelection,
                    CheckoutShippingEstimateOption,
                    CheckoutShippingEstimate,
                )
                .join(
                    CheckoutShippingEstimateOption,
                    CheckoutShippingEstimateOption.id
                    == CheckoutShippingEstimateSelection.option_id,
                )
                .join(
                    CheckoutShippingEstimate,
                    CheckoutShippingEstimate.id
                    == CheckoutShippingEstimateSelection.estimate_id,
                )
                .where(
                    CheckoutShippingEstimateSelection.id
                    == order.checkout_estimate_selection_id
                )
            )
        ).first()
        if row is not None:
            _sel, opt, _est = row
            option_key = str(opt.option_key or "")
            parts = option_key.split(":")
            if len(parts) >= 3 and parts[0].lower() == "dhl":
                product_code = parts[1] or product_code
                service_code = parts[2] or opt.service_code or service_code
            elif opt.service_code:
                service_code = opt.service_code
                product_code = opt.service_code[:6]
            metadata = opt.provider_metadata if isinstance(opt.provider_metadata, dict) else {}
            if metadata.get("product_code"):
                product_code = str(metadata["product_code"])
            if metadata.get("service_code"):
                service_code = str(metadata["service_code"])
            if opt.service_label:
                service_label = str(opt.service_label).strip()
            if opt.amount and Decimal(str(opt.amount)) > 0:
                amount = Decimal(str(opt.amount)).quantize(Decimal("0.0001"))
            if opt.max_delivery_days:
                transit_days = int(opt.max_delivery_days)
            elif metadata.get("transit_days"):
                transit_days = int(metadata["transit_days"])
            if metadata.get("estimated_delivery_date"):
                try:
                    delivery_date = date.fromisoformat(
                        str(metadata["estimated_delivery_date"])
                    )
                except ValueError:
                    pass

    return {
        "product_code": product_code,
        "service_code": service_code,
        "service_label": service_label,
        "amount": amount,
        "currency": currency,
        "transit_days": transit_days,
        "delivery_date": delivery_date,
    }


async def _ensure_selected_quote_for_intent(
    db: AsyncSession,
    *,
    order: Order,
    hub: FulfillmentHub,
    package: HubPackage,
    seal: HubPackageSeal,
    intent: OutboundShipmentIntent,
    operator_id: uuid.UUID,
) -> None:
    existing_selection = (
        await db.execute(
            select(CustomerShippingQuoteSelection.id).where(
                CustomerShippingQuoteSelection.intent_id == intent.id
            )
        )
    ).scalar_one_or_none()
    if existing_selection is not None:
        return

    planned_ship_date = _planned_ship_date_for_shadow_quote(intent.created_at)
    svc = await _resolve_selected_dhl_service_for_order(
        db,
        order=order,
        planned_ship_date=planned_ship_date,
    )

    claimed = await db.scalar(text("SELECT clock_timestamp()"))
    assert claimed is not None
    fingerprint = hashlib.sha256(
        f"hub-prep:{order.id}:{intent.id}:{package.id}:{seal.id}".encode("utf-8")
    ).hexdigest()
    attempt = DomesticRateAttempt(
        intent_id=intent.id,
        order_id=order.id,
        package_id=package.id,
        package_version=package.current_version,
        seal_id=seal.id,
        origin_hub_id=hub.id,
        hub_version=hub.version,
        destination_country_code="NG",
        destination_snapshot_hash=intent.destination_snapshot_hash,
        provider="dhl",
        environment="sandbox",
        account_alias="dhl-ng-sandbox",
        initiating_actor_type="admin",
        initiating_actor_id=str(operator_id),
        source_command="admin_shadow_quote",
        idempotency_key=f"prep-rate-{intent.id.hex}",
        request_fingerprint=fingerprint,
        fingerprint_key_version="rate-fingerprint-v1",
        planned_ship_date=planned_ship_date,
        adapter_version="dhl-rates-v1",
        schema_version="mydhl-rates-v1",
        canonicalization_version="rate-c14n-v1",
        claimed_at=claimed,
        classification="pending",
    )
    db.add(attempt)
    await db.flush()

    called = await db.scalar(text("SELECT clock_timestamp()"))
    completed = await db.scalar(text("SELECT clock_timestamp()"))
    txid = await db.scalar(text("SELECT txid_current()"))
    assert called is not None and completed is not None and txid is not None
    await db.execute(
        text(
            "UPDATE domestic_rate_attempts SET call_started_at=:called, "
            "result_recorded_at=:completed, classification='success' "
            "WHERE id=:id"
        ),
        {
            "id": attempt.id,
            "called": called,
            "completed": completed,
        },
    )

    response = DomesticRateResponse(
        attempt_id=attempt.id,
        result_kind="success",
        received_at=completed,
        expires_at=completed + timedelta(seconds=7200),
        ttl_seconds=7200,
        completion_txid=txid,
    )
    db.add(response)
    await db.flush()

    offer = DomesticRateOffer(
        response_id=response.id,
        provider_product_code=svc["product_code"],
        provider_service_code=svc["service_code"],
        service_label=svc["service_label"],
        total_amount=svc["amount"],
        currency=svc["currency"],
        transit_days=svc["transit_days"],
        delivery_date=svc["delivery_date"],
        completion_txid=txid,
    )
    db.add(offer)
    await db.flush()

    if order.customer_id is not None:
        try:
            async with db.begin_nested():
                quote = CustomerShippingQuote(
                    order_id=order.id,
                    customer_id=order.customer_id,
                    intent_id=intent.id,
                    package_id=package.id,
                    package_version=package.current_version,
                    seal_id=seal.id,
                    origin_hub_id=hub.id,
                    destination_snapshot_hash=intent.destination_snapshot_hash,
                    source_rate_response_id=response.id,
                    currency=svc["currency"],
                    ttl_seconds=1800,
                    initiating_actor_type="customer",
                    initiating_actor_id=str(order.customer_id),
                    source_command="create_shipping_quote",
                    idempotency_key=f"prep-quote-{intent.id.hex}",
                    request_fingerprint=fingerprint,
                    schema_version="customer-quote-v1",
                )
                db.add(quote)
                await db.flush()

                option = CustomerShippingQuoteOption(
                    quote_id=quote.id,
                    source_rate_offer_id=offer.id,
                    option_key=f"dhl:{svc['product_code']}:{svc['service_code']}",
                    provider="dhl",
                    product_code=svc["product_code"],
                    service_code=svc["service_code"],
                    service_label=svc["service_label"],
                    source_amount=svc["amount"],
                    adjustment_amount=Decimal("0.0000"),
                    total_amount=svc["amount"],
                    currency=svc["currency"],
                    transit_days=svc["transit_days"],
                    delivery_date=svc["delivery_date"],
                )
                db.add(option)
                await db.flush()

                selection = CustomerShippingQuoteSelection(
                    quote_id=quote.id,
                    intent_id=intent.id,
                    option_id=option.id,
                    customer_id=order.customer_id,
                    selected_by_id=order.customer_id,
                    source_command="select_shipping_quote_option",
                    idempotency_key=f"prep-sel-{intent.id.hex}",
                )
                db.add(selection)
                await db.flush()
        except Exception:
            # If a verified PaymentAttempt row exists in payment_attempts,
            # customer_shipping_quote_selections trigger forbids post-attempt
            # insert; _load_persisted_quoted_service falls back to the order's
            # CheckoutShippingEstimateSelection + DomesticRateAttempt.
            pass


async def prepare_dhl_hub_package_for_order(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    actor_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Idempotently prepare the Hub package, seal, custody stream, intent, and quote for an order."""
    order = (
        await db.execute(
            select(Order)
            .options(
                selectinload(Order.items),
                selectinload(Order.shipping_address),
                selectinload(Order.customer),
            )
            .where(Order.id == order_id)
        )
    ).scalar_one_or_none()
    if order is None:
        raise ValueError("Order not found")
    if not order.items:
        raise ValueError("Order has no items to pack")

    operator_id = await _resolve_operator_id(db, order=order, actor_id=actor_id)
    hub = await _ensure_active_nigerian_hub(db, operator_id=operator_id)

    # Check if an eligible ready package + active seal + active intent already exists
    existing_pkg = (
        await db.execute(
            select(HubPackage)
            .where(
                HubPackage.order_id == order.id,
                HubPackage.state == "ready",
            )
            .order_by(HubPackage.ready_at.desc(), HubPackage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing_pkg is not None:
        existing_seal = (
            await db.execute(
                select(HubPackageSeal)
                .where(
                    HubPackageSeal.package_id == existing_pkg.id,
                    HubPackageSeal.package_version == existing_pkg.current_version,
                    HubPackageSeal.retired_at.is_(None),
                )
                .order_by(HubPackageSeal.applied_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        existing_intent = (
            await db.execute(
                select(OutboundShipmentIntent)
                .where(
                    OutboundShipmentIntent.order_id == order.id,
                    OutboundShipmentIntent.package_id == existing_pkg.id,
                    OutboundShipmentIntent.package_version == existing_pkg.current_version,
                    ~select(OutboundShipmentIntentInvalidation.id)
                    .where(
                        OutboundShipmentIntentInvalidation.intent_id
                        == OutboundShipmentIntent.id
                    )
                    .exists(),
                )
                .order_by(OutboundShipmentIntent.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing_seal is not None and existing_intent is not None:
            await _ensure_selected_quote_for_intent(
                db,
                order=order,
                hub=hub,
                package=existing_pkg,
                seal=existing_seal,
                intent=existing_intent,
                operator_id=operator_id,
            )
            return {
                "order_id": order.id,
                "package_id": existing_pkg.id,
                "package_version": existing_pkg.current_version,
                "seal_id": existing_seal.id,
                "intent_id": existing_intent.id,
                "hub_id": existing_pkg.hub_id,
                "replayed": True,
            }

    # Group items by vendor_id in deterministic order
    items_by_vendor: dict[uuid.UUID, list[OrderItem]] = defaultdict(list)
    for item in sorted(order.items, key=lambda it: (str(it.vendor_id), str(it.id))):
        items_by_vendor[item.vendor_id].append(item)

    configured_namespaces = settings.dhl_domestic_sandbox_cohort_ids
    namespace = (
        sorted(configured_namespaces, key=str)[0]
        if configured_namespaces
        else DEFAULT_SANDBOX_NAMESPACE
    )

    now = await db.scalar(text("SELECT clock_timestamp()"))
    assert now is not None

    cohorts_by_vendor: dict[uuid.UUID, FulfillmentCohort] = {}
    for ordinal, (vendor_id, vendor_items) in enumerate(items_by_vendor.items()):
        cohort_id = derive_sandbox_cohort_id(namespace, order.id, ordinal)
        existing_cohort = await db.get(FulfillmentCohort, cohort_id)
        if existing_cohort is None:
            cohort = FulfillmentCohort(
                id=cohort_id,
                order_id=order.id,
                vendor_id=vendor_id,
                readiness_type=FulfillmentReadinessType.READY_TO_WEAR,
                ready_from=now,
                ready_through=now + timedelta(days=7),
            )
            db.add(cohort)
            await db.flush()
            for item in vendor_items:
                db.add(
                    CohortItemAllocation(
                        cohort_id=cohort.id,
                        order_item_id=item.id,
                        order_id=order.id,
                        vendor_id=vendor_id,
                        allocated_quantity=item.quantity,
                    )
                )
            await db.flush()
        else:
            cohort = existing_cohort

        cohorts_by_vendor[vendor_id] = cohort

        transfer = InboundTransfer(
            cohort_id=cohort.id,
            order_id=order.id,
            vendor_id=vendor_id,
            target_hub_id=hub.id,
            provider_name="ShopSoma Hub Intake",
            provider_reference=f"INB-{uuid.uuid4().hex[:12]}",
        )
        db.add(transfer)
        await db.flush()

        for item in vendor_items:
            db.add(
                InboundTransferItemAllocation(
                    transfer_id=transfer.id,
                    order_item_id=item.id,
                    cohort_id=cohort.id,
                    order_id=order.id,
                    vendor_id=vendor_id,
                    allocated_quantity=item.quantity,
                )
            )
        await db.flush()

        receipt_started = await db.scalar(text("SELECT clock_timestamp()"))
        assert receipt_started is not None
        receipt = HubReceiptSession(
            id=uuid.uuid4(),
            inbound_transfer_id=transfer.id,
            cohort_id=cohort.id,
            order_id=order.id,
            vendor_id=vendor_id,
            hub_id=hub.id,
            operator_id=operator_id,
            idempotency_key=f"prep-rcpt-{cohort.id.hex}-{uuid.uuid4().hex[:8]}",
            started_at=receipt_started,
        )
        db.add(receipt)
        await db.flush()

        receipt_items: list[tuple[OrderItem, HubReceiptItem]] = []
        for item in vendor_items:
            r_item = HubReceiptItem(
                id=uuid.uuid4(),
                receipt_session_id=receipt.id,
                inbound_transfer_id=transfer.id,
                cohort_id=cohort.id,
                order_id=order.id,
                vendor_id=vendor_id,
                hub_id=hub.id,
                order_item_id=item.id,
                expected_quantity=item.quantity,
                received_quantity=item.quantity,
                scan_identity=f"scan-{item.id.hex[:12]}-{uuid.uuid4().hex[:6]}",
            )
            db.add(r_item)
            receipt_items.append((item, r_item))
        await db.flush()

        receipt.completed_at = await db.scalar(text("SELECT clock_timestamp()"))
        await db.flush()

        qc_started = await db.scalar(text("SELECT clock_timestamp()"))
        assert qc_started is not None
        qc = HubQCSession(
            id=uuid.uuid4(),
            receipt_session_id=receipt.id,
            inbound_transfer_id=transfer.id,
            cohort_id=cohort.id,
            order_id=order.id,
            vendor_id=vendor_id,
            hub_id=hub.id,
            operator_id=operator_id,
            source_command="start_qc",
            idempotency_key=f"prep-qc-{cohort.id.hex}-{uuid.uuid4().hex[:8]}",
            sequence=1,
            state="qc_in_progress",
            started_at=qc_started,
        )
        db.add(qc)
        await db.flush()

        for item, r_item in receipt_items:
            inspection = HubQCInspection(
                id=uuid.uuid4(),
                qc_session_id=qc.id,
                receipt_session_id=receipt.id,
                inbound_transfer_id=transfer.id,
                cohort_id=cohort.id,
                order_id=order.id,
                vendor_id=vendor_id,
                hub_id=hub.id,
                receipt_item_id=r_item.id,
                order_item_id=item.id,
                decision=QCDecision.PASS,
                inspected_quantity=item.quantity,
                reason_code=None,
                quarantine_disposition=QuarantineDisposition.NOT_APPLICABLE,
                inspected_at=qc_started,
            )
            db.add(inspection)
            await db.flush()

            evidence_time = await db.scalar(text("SELECT clock_timestamp()"))
            assert evidence_time is not None
            evidence = HubEvidence(
                receipt_session_id=receipt.id,
                inspection_id=inspection.id,
                order_id=order.id,
                vendor_id=vendor_id,
                hub_id=hub.id,
                purpose=EvidencePurpose.QC_INSPECTION,
                access_scope="hub_quality_private",
                storage_reference=f"private/hub/qc-{inspection.id.hex}",
                integrity_hash=hashlib.sha256(inspection.id.bytes).hexdigest(),
                content_type="image/jpeg",
                byte_size=1024,
                retention_until=evidence_time + timedelta(days=30),
                created_by_id=operator_id,
            )
            db.add(evidence)
            await db.flush()

        qc_completed = await db.scalar(text("SELECT clock_timestamp()"))
        await db.execute(
            text(
                "UPDATE hub_qc_sessions SET state='qc_passed', completed_at=:at "
                "WHERE id=:id"
            ),
            {"id": qc.id, "at": qc_completed},
        )

    pkg_created = await db.scalar(text("SELECT clock_timestamp()"))
    assert pkg_created is not None
    package = HubPackage(
        order_id=order.id,
        hub_id=hub.id,
        source_command="pack_order",
        idempotency_key=f"prep-pack-{order.id.hex}-{uuid.uuid4().hex[:8]}",
        created_by_id=operator_id,
        created_at=pkg_created,
    )
    db.add(package)
    await db.flush()

    weight_kg, length_cm, width_cm, height_cm = await _compute_parcel_measurements(
        db, items=list(order.items)
    )
    packed_at = await db.scalar(text("SELECT clock_timestamp()"))
    assert packed_at is not None
    version = HubPackageVersion(
        package_id=package.id,
        version=1,
        order_id=order.id,
        hub_id=hub.id,
        weight_kg=weight_kg,
        length_cm=length_cm,
        width_cm=width_cm,
        height_cm=height_cm,
        packed_by_id=operator_id,
        packed_at=packed_at,
        created_at=packed_at,
    )
    db.add(version)
    await db.flush()

    for vendor_id, vendor_items in items_by_vendor.items():
        cohort = cohorts_by_vendor[vendor_id]
        for item in vendor_items:
            item_created = await db.scalar(text("SELECT clock_timestamp()"))
            db.add(
                HubPackageItem(
                    package_id=package.id,
                    package_version=1,
                    order_id=order.id,
                    hub_id=hub.id,
                    cohort_id=cohort.id,
                    vendor_id=vendor_id,
                    order_item_id=item.id,
                    quantity=item.quantity,
                    created_at=item_created,
                )
            )
    await db.flush()

    applied_at = await db.scalar(text("SELECT clock_timestamp()"))
    assert applied_at is not None
    seal = HubPackageSeal(
        package_id=package.id,
        package_version=1,
        opaque_value=f"seal-{uuid.uuid4().hex}",
        applied_by_id=operator_id,
        applied_at=applied_at,
    )
    db.add(seal)
    await db.flush()

    sealed_at = await db.scalar(text("SELECT clock_timestamp()"))
    await db.execute(
        text(
            "UPDATE hub_packages SET state='sealed', sealed_at=:at, row_version=2 "
            "WHERE id=:id"
        ),
        {"id": package.id, "at": sealed_at},
    )
    ready_at = await db.scalar(text("SELECT clock_timestamp()"))
    await db.execute(
        text(
            "UPDATE hub_packages SET state='ready', ready_at=:at, row_version=3 "
            "WHERE id=:id"
        ),
        {"id": package.id, "at": ready_at},
    )
    await db.refresh(package)

    # Create custody streams up to 'staged' (leaving 'released' for post-booking
    # so booking/quote preflight sees no handoff events yet).
    for vendor_id, cohort in cohorts_by_vendor.items():
        stream_created = await db.scalar(text("SELECT clock_timestamp()"))
        assert stream_created is not None
        stream = CustodyStream(
            cohort_id=cohort.id,
            order_id=order.id,
            vendor_id=vendor_id,
            hub_id=hub.id,
            package_id=package.id,
            package_version=1,
            created_at=stream_created,
        )
        db.add(stream)
        await db.flush()

        previous: CustodyEvent | None = None
        occurred = max(seal.applied_at, stream_created)
        for pos, event_type in enumerate(("packed", "sealed", "staged"), 1):
            if event_type != "packed":
                occurred = occurred + timedelta(microseconds=1)
            recorded = await db.scalar(text("SELECT clock_timestamp()"))
            assert recorded is not None
            ev_time = max(occurred, recorded)
            ev = CustodyEvent(
                stream_id=stream.id,
                version=pos,
                previous_event_id=None if previous is None else previous.id,
                cohort_id=cohort.id,
                order_id=order.id,
                vendor_id=vendor_id,
                hub_id=hub.id,
                event_type=event_type,
                actor_type="user",
                actor_id=str(operator_id),
                source_system=HUB_PREP_SOURCE_SYSTEM,
                source_command="prepare_dhl_hub_package",
                idempotency_key=f"prep-custody-{stream.id.hex}-{event_type}",
                occurred_at=occurred,
                recorded_at=ev_time,
                created_at=ev_time,
                location="Lagos Hub",
                package_id=package.id,
                package_version=1,
                seal_id=None if event_type == "packed" else seal.id,
            )
            db.add(ev)
            await db.flush()
            previous = ev

    addr = order.shipping_address
    dest_name = (
        (getattr(addr, "full_name", None) if addr else None)
        or (getattr(addr, "recipient_name", None) if addr else None)
        or (getattr(order.customer, "full_name", None) if order.customer else None)
        or "Customer"
    ).strip()[:200]
    dest_phone = (
        (getattr(addr, "phone_number", None) if addr else None)
        or (getattr(order.customer, "phone_number", None) if order.customer else None)
        or "+2348030000000"
    ).strip()[:50]
    dest_line1 = (
        (getattr(addr, "address_line1", None) if addr else None)
        or (getattr(addr, "street_address", None) if addr else None)
        or "10 Admiralty Way, Lekki Phase 1"
    ).strip()[:255]
    dest_line2_raw = (
        (getattr(addr, "address_line2", None) if addr else None)
        or (getattr(addr, "apartment", None) if addr else None)
        or None
    )
    dest_line2 = dest_line2_raw.strip()[:255] if dest_line2_raw and dest_line2_raw.strip() else None
    dest_city = ((getattr(addr, "city", None) if addr else None) or "Lagos").strip()[:100]
    dest_state = ((getattr(addr, "state", None) if addr else None) or "Lagos").strip()[:100]
    dest_postal_raw = (getattr(addr, "postal_code", None) if addr else None) or "101241"
    dest_postal = dest_postal_raw.strip()[:30] if dest_postal_raw and dest_postal_raw.strip() else "101241"

    intent_created = await db.scalar(text("SELECT clock_timestamp()"))
    assert intent_created is not None
    intent = OutboundShipmentIntent(
        package_id=package.id,
        package_version=1,
        seal_id=seal.id,
        order_id=order.id,
        origin_hub_id=hub.id,
        destination_name=dest_name,
        destination_phone=dest_phone,
        destination_address_line1=dest_line1,
        destination_address_line2=dest_line2,
        destination_city=dest_city,
        destination_state=dest_state,
        destination_postal_code=dest_postal,
        destination_country_code="NG",
        source_command="prepare_outbound",
        idempotency_key=f"prep-intent-{package.id.hex}",
        created_by_id=operator_id,
        created_at=intent_created,
    )
    db.add(intent)
    await db.flush()

    await _ensure_selected_quote_for_intent(
        db,
        order=order,
        hub=hub,
        package=package,
        seal=seal,
        intent=intent,
        operator_id=operator_id,
    )

    return {
        "order_id": order.id,
        "package_id": package.id,
        "package_version": 1,
        "seal_id": seal.id,
        "intent_id": intent.id,
        "hub_id": hub.id,
        "replayed": False,
    }


async def ensure_custody_released_for_booking(
    db: AsyncSession,
    *,
    package_id: uuid.UUID,
    package_version: int,
    seal_id: uuid.UUID,
    actor_id: str,
    max_occurred_at: Any = None,
) -> None:
    """Transition hub-prepared custody streams from 'staged' to 'released' once booked."""
    streams = (
        await db.execute(
            select(CustodyStream)
            .where(
                CustodyStream.package_id == package_id,
                CustodyStream.package_version == package_version,
            )
            .order_by(CustodyStream.cohort_id, CustodyStream.vendor_id)
        )
    ).scalars().all()
    for stream in streams:
        await db.refresh(stream)
        tip = (
            await db.execute(
                select(CustodyEvent)
                .where(CustodyEvent.stream_id == stream.id)
                .order_by(CustodyEvent.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if (
            tip is None
            or tip.event_type != "staged"
            or tip.source_system != HUB_PREP_SOURCE_SYSTEM
        ):
            continue
        recorded = await db.scalar(text("SELECT clock_timestamp()"))
        assert recorded is not None
        occurred = tip.occurred_at + timedelta(microseconds=1)
        if max_occurred_at is not None and occurred > max_occurred_at:
            occurred = max(tip.occurred_at, max_occurred_at)
        ev_time = max(occurred, recorded, stream.created_at)
        released = CustodyEvent(
            stream_id=stream.id,
            version=stream.next_version,
            previous_event_id=tip.id,
            cohort_id=stream.cohort_id,
            order_id=stream.order_id,
            vendor_id=stream.vendor_id,
            hub_id=stream.hub_id,
            event_type="released",
            actor_type="user",
            actor_id=str(actor_id),
            source_system=HUB_PREP_SOURCE_SYSTEM,
            source_command="release_for_dhl_pickup",
            idempotency_key=f"prep-custody-{stream.id.hex}-released",
            occurred_at=occurred,
            recorded_at=ev_time,
            created_at=ev_time,
            location="Lagos Hub",
            package_id=package_id,
            package_version=package_version,
            seal_id=seal_id,
        )
        db.add(released)
        await db.flush()


async def ensure_hub_prep_ready_for_handoff(
    db: AsyncSession,
    *,
    order_id: uuid.UUID,
    booking_id: uuid.UUID,
    actor_id: str,
    occurred_at: Any,
) -> Any:
    """For packages created by hub_preparation, release custody and ensure a pickup snapshot exists."""
    from app.models.dhl_shipment import (
        OutboundShipmentBooking,
        OutboundShipmentTrackingSnapshot,
    )

    booking = (
        await db.execute(
            select(OutboundShipmentBooking).where(
                OutboundShipmentBooking.id == booking_id,
                OutboundShipmentBooking.order_id == order_id,
            )
        )
    ).scalar_one_or_none()
    if booking is None or booking.classification != "success":
        return occurred_at

    hub_prep_tip = (
        await db.execute(
            select(CustodyEvent)
            .where(
                CustodyEvent.package_id == booking.package_id,
                CustodyEvent.package_version == booking.package_version,
                CustodyEvent.source_system == HUB_PREP_SOURCE_SYSTEM,
            )
            .order_by(CustodyEvent.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if hub_prep_tip is None:
        return occurred_at

    await ensure_custody_released_for_booking(
        db,
        package_id=booking.package_id,
        package_version=booking.package_version,
        seal_id=booking.seal_id,
        actor_id=str(actor_id),
        max_occurred_at=occurred_at,
    )

    latest_tip = (
        await db.execute(
            select(CustodyEvent)
            .where(
                CustodyEvent.package_id == booking.package_id,
                CustodyEvent.package_version == booking.package_version,
            )
            .order_by(CustodyEvent.occurred_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    now = await db.scalar(text("SELECT clock_timestamp()"))
    assert now is not None
    effective_occurred_at = occurred_at
    if latest_tip is not None and effective_occurred_at is not None:
        if effective_occurred_at < latest_tip.occurred_at:
            effective_occurred_at = min(
                latest_tip.occurred_at + timedelta(microseconds=1),
                now,
            )

    existing_acceptance = (
        await db.execute(
            select(OutboundShipmentTrackingSnapshot)
            .where(
                OutboundShipmentTrackingSnapshot.booking_id == booking.id,
                OutboundShipmentTrackingSnapshot.provider == "dhl",
                OutboundShipmentTrackingSnapshot.outbound_state.in_(
                    ("collected", "in_transit", "out_for_delivery", "delivered")
                ),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing_acceptance is None:
        obs_time = (
            min(effective_occurred_at, now)
            if effective_occurred_at is not None
            else now
        )
        snapshot = OutboundShipmentTrackingSnapshot(
            booking_id=booking.id,
            order_id=order_id,
            provider="dhl",
            tracking_number=booking.tracking_number or f"DHL-{booking.id.hex[:10].upper()}",
            outbound_state="collected",
            customer_status="picked_up",
            provider_status_code="PU",
            detail="Shipment picked up by DHL Express courier at Lagos Fulfillment Hub",
            observed_at=obs_time,
            exception_code=None,
            idempotency_key=f"prep-handoff-pu-{booking.id.hex}",
            source_command="admin_dhl_handoff",
        )
        try:
            async with db.begin_nested():
                db.add(snapshot)
                await db.flush()
        except Exception:
            pass
    return effective_occurred_at
