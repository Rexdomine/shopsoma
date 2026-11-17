"""Management command to create an international order with DHL selected (without booking a shipment).

Default target values (matching staging test scenario):
  - Customer email : testingkayode@gmail.com
  - Product        : 00dcf603-7a97-4649-b8e2-97089ef9f963
  - Destination    : 45 Kofi Annan Street, Accra, Greater Accra, Ghana (GH)
  - Carrier        : DHL Express Worldwide (Product 'P') selected — NO shipment created

Usage examples:
  1. Run inside Render Staging Shell (uses server DATABASE_URL automatically):
     python create_international_dhl_order.py

  2. Run locally against Render Staging DB (prompts for External DB URL if not passed):
     python create_international_dhl_order.py --staging
     python create_international_dhl_order.py --database-url "postgresql://user:pass@host.render.com/dbname"

  3. Customize currency, quantity, address, or payment state:
     python create_international_dhl_order.py --currency USD --quantity 1
     python create_international_dhl_order.py --currency NGN --unpaid
     python create_international_dhl_order.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import os
import re
import sys
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

# Ensure backend root is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.api.v1.orders import (
    TAX_RATE,
    _convert_currency,
    _get_usd_to_ngn_rate,
    _inventory_snapshot,
    generate_order_number,
    resolve_order_variant,
)
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.address import Address, AddressType
from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimate,
    CheckoutShippingEstimateOption,
    CheckoutShippingEstimateSelection,
)
from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.models.product import Product, Variation
from app.models.product_logistics_profile import ProductLogisticsProfile
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.services.commission import get_vendor_commission_rate
from app.services.dhl.client import DHLAPIError, DHLClient
from app.services.dhl.hub_preparation import prepare_dhl_hub_package_for_order
from app.services.fulfillment.contracts import resolve_country_code
from app.services.orders.vendor_fulfilment import start_verified_order_fulfilment

DEFAULT_PRODUCT_REF = "00dcf603-7a97-4649-b8e2-97089ef9f963"
DEFAULT_CUSTOMER_EMAIL = "testingkayode@gmail.com"
DEFAULT_COUNTRY = "Ghana"
DEFAULT_STATE = "Greater Accra"
DEFAULT_CITY = "Accra"
DEFAULT_ADDRESS_LINE1 = "45 Kofi Annan Street"
DEFAULT_POSTAL_CODE = "00233"
DEFAULT_PHONE = "+233244123456"
DEFAULT_RECIPIENT_FALLBACK = "Bello Karimu"
DEFAULT_GHANA_FALLBACK_NGN_RATE = Decimal("86599.12")

_UUID_PATTERN = re.compile(
    r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})"
)


@dataclass(frozen=True)
class ResolvedDhlExportQuote:
    product_code: str
    service_code: str
    service_label: str
    shipping_amount: Decimal
    currency: str
    transit_days: int
    estimated_delivery_date: date
    source: str  # "mydhl_live" | "manual_override" | "fallback_estimate"


def extract_product_uuid(raw_product: str) -> uuid.UUID:
    """Extract product UUID from either a raw UUID or a full product URL."""
    match = _UUID_PATTERN.search(raw_product.strip())
    if not match:
        raise ValueError(
            f"Could not extract a valid product UUID from: {raw_product!r}"
        )
    return uuid.UUID(match.group(1))


def build_async_engine_config(raw_url: str) -> tuple[str, dict[str, Any]]:
    """Normalize PostgreSQL URL for SQLAlchemy asyncpg, including Render SSL params."""
    url = raw_url.strip()
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    parts = urlsplit(url)
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)
    connect_args: dict[str, Any] = {}
    filtered_pairs: list[tuple[str, str]] = []
    ssl_requested = False

    for key, val in query_pairs:
        if key.lower() == "sslmode":
            if val.lower() not in ("disable", "allow"):
                ssl_requested = True
            continue
        filtered_pairs.append((key, val))

    hostname = (parts.hostname or "").lower()
    if ssl_requested or hostname.endswith(".render.com") or ".oregon-postgres.render.com" in hostname or ".frankfurt-postgres.render.com" in hostname:
        connect_args["ssl"] = "require"

    normalized_url = urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(filtered_pairs),
            parts.fragment,
        )
    )
    return normalized_url, connect_args


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _next_business_ship_date(today: date | None = None) -> date:
    candidate = (today or datetime.now(timezone.utc).date()) + timedelta(days=1)
    while candidate.weekday() >= 5:  # Skip Saturday (5) & Sunday (6)
        candidate += timedelta(days=1)
    return candidate


async def _pick_purchasable_variant_if_needed(
    db: AsyncSession,
    product: Product,
    *,
    explicit_variant_id: str | None,
    quantity: int,
) -> dict[str, Any]:
    """Resolve an explicit variant/size_stock or automatically choose the first purchasable one."""
    if explicit_variant_id:
        return await resolve_order_variant(db, product, str(uuid.UUID(explicit_variant_id.strip())))

    # 1. Check active variations with size_stocks first
    if product.variations:
        for variation in product.variations:
            if not getattr(variation, "is_active", True):
                continue
            size_stocks = list(getattr(variation, "size_stocks", None) or [])
            if size_stocks:
                for ss in size_stocks:
                    if product.made_to_order or (ss.stock or 0) >= quantity:
                        return await resolve_order_variant(db, product, str(ss.id))
                # Fallback to first size_stock if stock check is bypassed or MTO
                return await resolve_order_variant(db, product, str(size_stocks[0].id))

        # Standalone variation without size_stocks/variants
        if not product.variants:
            active_variations = [
                v for v in product.variations if getattr(v, "is_active", True)
            ]
            chosen_var = active_variations[0] if active_variations else product.variations[0]
            return await resolve_order_variant(db, product, str(chosen_var.id))

    # 2. Check legacy ProductVariant rows
    if product.variants:
        for pv in product.variants:
            if product.made_to_order or (pv.stock or 0) >= quantity:
                return await resolve_order_variant(db, product, str(pv.id))
        return await resolve_order_variant(db, product, str(product.variants[0].id))

    # 3. Single product without variations/variants
    return {
        "variant_id": None,
        "unit_price": product.base_price,
        "stock": max(product.total_stock or 0, 999999) if product.made_to_order else (product.total_stock or 0),
        "variant_details": None,
        "stock_source": "product",
        "stock_id": product.id,
    }


async def _resolve_parcel_dimensions(
    db: AsyncSession,
    *,
    product: Product,
    quantity: int,
) -> tuple[float, float, float, float]:
    """Determine parcel weight (kg) and dimensions (cm) for rating."""
    profile = await db.scalar(
        select(ProductLogisticsProfile).where(
            ProductLogisticsProfile.product_id == product.id
        )
    )
    qty = max(quantity, 1)
    if profile is not None:
        weight = float(Decimal(str(profile.weight_kg)) * qty)
        length = float(Decimal(str(profile.length_cm)))
        width = float(Decimal(str(profile.width_cm)))
        height = float(min(Decimal(str(profile.height_cm)) * qty, Decimal("120.0")))
        return max(weight, 0.2), max(length, 10.0), max(width, 10.0), max(height, 2.0)

    weight_unit = Decimal(str(product.weight_kg)) if product.weight_kg else Decimal("0.800")
    length_cm = Decimal(str(product.length_cm)) if product.length_cm else Decimal("35.0")
    width_cm = Decimal(str(product.width_cm)) if product.width_cm else Decimal("25.0")
    height_unit = Decimal(str(product.height_cm)) if product.height_cm else Decimal("8.0")
    return (
        max(float(weight_unit * qty), 0.2),
        max(float(length_cm), 10.0),
        max(float(width_cm), 10.0),
        max(float(min(height_unit * qty, Decimal("120.0"))), 2.0),
    )


async def _quote_dhl_export_rate(
    *,
    dest_country_code: str,
    dest_city: str,
    dest_state: str,
    dest_postal_code: str,
    dest_address_line1: str,
    weight_kg: float,
    length_cm: float,
    width_cm: float,
    height_cm: float,
    order_currency: str,
    usd_to_ngn_rate: Decimal,
    manual_shipping_cost: Decimal | None = None,
    offline_rate: bool = False,
) -> ResolvedDhlExportQuote:
    """Fetch a live DHL Express Worldwide ('P') rate without booking any shipment."""
    ship_date = _next_business_ship_date()
    default_eta = ship_date + timedelta(days=3)

    if manual_shipping_cost is not None:
        return ResolvedDhlExportQuote(
            product_code="P",
            service_code="P",
            service_label="DHL Express Worldwide",
            shipping_amount=_quantize_money(manual_shipping_cost),
            currency=order_currency,
            transit_days=3,
            estimated_delivery_date=default_eta,
            source="manual_override",
        )

    if not offline_rate and settings.dhl_configured:
        payload = {
            "plannedShippingDateAndTime": f"{ship_date.isoformat()}T12:00:00GMT+01:00",
            "unitOfMeasurement": "metric",
            "isCustomsDeclarable": dest_country_code != "NG",
            "accounts": [
                {
                    "typeCode": "shipper",
                    "number": settings.DHL_EXPORT_ACCOUNT_NUMBER.get_secret_value(),
                }
            ],
            "customerDetails": {
                "shipperDetails": {
                    "postalCode": "101241",
                    "cityName": "Lagos",
                    "countryCode": "NG",
                    "provinceCode": "Lagos",
                    "addressLine1": "14 Ademola Adetokunbo Street",
                },
                "receiverDetails": {
                    "postalCode": (dest_postal_code or "00000")[:12],
                    "cityName": dest_city[:45],
                    "countryCode": dest_country_code,
                    "provinceCode": dest_state[:35],
                    "addressLine1": dest_address_line1[:45],
                },
            },
            "packages": [
                {
                    "weight": round(weight_kg, 3),
                    "dimensions": {
                        "length": round(length_cm, 2),
                        "width": round(width_cm, 2),
                        "height": round(height_cm, 2),
                    },
                }
            ],
        }
        try:
            client = DHLClient(config=settings)
            response = await client.request_json("POST", "/rates", json=payload)
            products = response.get("products") or []
            chosen = next(
                (p for p in products if str(p.get("productCode", "")).upper() == "P"),
                products[0] if products else None,
            )
            if chosen:
                product_code = str(chosen.get("productCode") or "P").strip()
                service_code = str(chosen.get("localProductCode") or product_code).strip()
                raw_label = str(chosen.get("productName") or "EXPRESS WORLDWIDE").strip()
                service_label = (
                    "DHL Express Worldwide"
                    if raw_label.upper() == "EXPRESS WORLDWIDE"
                    else raw_label
                )

                prices = chosen.get("totalPrice") or []
                selected_price_entry = None
                for pref_type in ("BILLC", "PULCL", "BASEC"):
                    selected_price_entry = next(
                        (
                            entry
                            for entry in prices
                            if entry.get("currencyType") == pref_type
                            and entry.get("price")
                        ),
                        None,
                    )
                    if selected_price_entry:
                        break
                if selected_price_entry is None and prices:
                    selected_price_entry = prices[0]

                if selected_price_entry and selected_price_entry.get("price"):
                    raw_amount = Decimal(str(selected_price_entry["price"]))
                    raw_curr = str(selected_price_entry.get("priceCurrency") or "NGN").upper()
                    if raw_curr in ("NGN", "USD"):
                        converted = _convert_currency(
                            raw_amount, raw_curr, order_currency, usd_to_ngn_rate
                        )
                    else:
                        converted = _convert_currency(
                            DEFAULT_GHANA_FALLBACK_NGN_RATE,
                            "NGN",
                            order_currency,
                            usd_to_ngn_rate,
                        )

                    eta_date = default_eta
                    transit_days = 3
                    caps = chosen.get("deliveryCapabilities") or {}
                    eta_raw = caps.get("estimatedDeliveryDateAndTime")
                    if isinstance(eta_raw, str) and len(eta_raw) >= 10:
                        try:
                            eta_date = date.fromisoformat(eta_raw[:10])
                            transit_days = max((eta_date - ship_date).days, 1)
                        except ValueError:
                            pass
                    elif caps.get("totalTransitDays"):
                        try:
                            transit_days = max(int(caps["totalTransitDays"]), 1)
                            eta_date = ship_date + timedelta(days=transit_days)
                        except (TypeError, ValueError):
                            pass

                    return ResolvedDhlExportQuote(
                        product_code=product_code,
                        service_code=service_code,
                        service_label=service_label,
                        shipping_amount=_quantize_money(converted),
                        currency=order_currency,
                        transit_days=transit_days,
                        estimated_delivery_date=eta_date,
                        source="mydhl_live",
                    )
        except DHLAPIError as exc:
            print(
                f"  [!] Live MyDHL rate lookup failed (status={exc.status_code}); "
                "falling back to standard Ghana DHL Express Worldwide estimate."
            )
        except Exception as exc:
            print(
                f"  [!] Live MyDHL rate lookup unavailable ({exc}); "
                "falling back to standard Ghana DHL Express Worldwide estimate."
            )

    fallback_amount = _convert_currency(
        DEFAULT_GHANA_FALLBACK_NGN_RATE,
        "NGN",
        order_currency,
        usd_to_ngn_rate,
    )
    return ResolvedDhlExportQuote(
        product_code="P",
        service_code="P",
        service_label="DHL Express Worldwide",
        shipping_amount=_quantize_money(fallback_amount),
        currency=order_currency,
        transit_days=3,
        estimated_delivery_date=default_eta,
        source="fallback_estimate",
    )


async def create_international_dhl_order(
    db: AsyncSession,
    *,
    email: str = DEFAULT_CUSTOMER_EMAIL,
    product_ref: str = DEFAULT_PRODUCT_REF,
    variant_id: str | None = None,
    quantity: int = 1,
    currency: str = "USD",
    country: str = DEFAULT_COUNTRY,
    state: str = DEFAULT_STATE,
    city: str = DEFAULT_CITY,
    address_line1: str = DEFAULT_ADDRESS_LINE1,
    address_line2: str | None = None,
    postal_code: str = DEFAULT_POSTAL_CODE,
    phone: str = DEFAULT_PHONE,
    recipient_name: str | None = None,
    shipping_cost_override: Decimal | None = None,
    mark_paid: bool = True,
    prepare_hub_package: bool = False,
    create_user_if_missing: bool = False,
    offline_rate: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create an international order with DHL selected, without creating a DHL shipment."""
    if quantity <= 0:
        raise ValueError("quantity must be at least 1")

    order_currency = currency.strip().upper()
    if order_currency not in ("USD", "NGN"):
        raise ValueError("currency must be 'USD' or 'NGN'")

    dest_country_code = resolve_country_code(country)
    if dest_country_code == "NG":
        raise ValueError(
            "Destination resolved to Nigeria ('NG'); provide an export country such as 'Ghana'"
        )

    product_uuid = extract_product_uuid(product_ref)

    # 1. Resolve Customer
    clean_email = email.strip().lower()
    customer = await db.scalar(
        select(User).where(func.lower(User.email) == clean_email)
    )
    if customer is None:
        if not create_user_if_missing:
            raise LookupError(
                f"Customer account '{clean_email}' was not found in this database. "
                "If targeting Render Staging, pass --staging or --database-url <RENDER_EXTERNAL_DB_URL>, "
                "or pass --create-user-if-missing to create the account."
            )
        customer = User(
            email=clean_email,
            hashed_password=get_password_hash(f"TempPass!{uuid.uuid4().hex[:10]}"),
            full_name=(recipient_name or DEFAULT_RECIPIENT_FALLBACK).strip(),
            phone_number=phone.strip(),
            role=UserRole.CUSTOMER,
            is_active=True,
            email_verified=True,
        )
        db.add(customer)
        await db.flush()

    # 2. Resolve Product & Vendor
    product = await db.scalar(
        select(Product)
        .options(
            selectinload(Product.vendor).selectinload(Vendor.user),
            selectinload(Product.variants),
            selectinload(Product.variations).selectinload(Variation.size_stocks),
            selectinload(Product.category),
        )
        .where(Product.id == product_uuid)
    )
    if product is None:
        raise LookupError(
            f"Product '{product_uuid}' was not found in this database. "
            "Make sure you are connected to the Staging database (--staging or --database-url)."
        )
    if product.vendor is None:
        raise ValueError(f"Product '{product.title}' ({product.id}) has no associated vendor")

    resolved_variant = await _pick_purchasable_variant_if_needed(
        db,
        product,
        explicit_variant_id=variant_id,
        quantity=quantity,
    )

    # 3. Resolve Pricing & DHL Export Rate (Rate quote ONLY — NO shipment created)
    usd_to_ngn_rate = await _get_usd_to_ngn_rate(db)
    source_currency = (product.currency or "NGN").strip().upper()
    unit_price_decimal = _convert_currency(
        Decimal(str(resolved_variant["unit_price"])),
        source_currency,
        order_currency,
        usd_to_ngn_rate,
    )
    item_subtotal = _quantize_money(unit_price_decimal * Decimal(quantity))

    weight_kg, length_cm, width_cm, height_cm = await _resolve_parcel_dimensions(
        db, product=product, quantity=quantity
    )
    dhl_quote = await _quote_dhl_export_rate(
        dest_country_code=dest_country_code,
        dest_city=city.strip(),
        dest_state=state.strip(),
        dest_postal_code=postal_code.strip(),
        dest_address_line1=address_line1.strip(),
        weight_kg=weight_kg,
        length_cm=length_cm,
        width_cm=width_cm,
        height_cm=height_cm,
        order_currency=order_currency,
        usd_to_ngn_rate=usd_to_ngn_rate,
        manual_shipping_cost=shipping_cost_override,
        offline_rate=offline_rate,
    )

    shipping_cost = dhl_quote.shipping_amount
    tax_amount = _quantize_money((item_subtotal + shipping_cost) * TAX_RATE)
    discount_amount = Decimal("0.00")
    total_amount = _quantize_money(item_subtotal + shipping_cost + tax_amount - discount_amount)

    resolved_recipient = (
        (recipient_name or "").strip()
        or (customer.full_name or "").strip()
        or DEFAULT_RECIPIENT_FALLBACK
    )

    if dry_run:
        await db.rollback()
        return {
            "dry_run": True,
            "order_id": None,
            "order_number": "(dry-run)",
            "customer_id": str(customer.id),
            "customer_email": customer.email,
            "product_id": str(product.id),
            "product_title": product.title,
            "variant_details": resolved_variant["variant_details"],
            "quantity": quantity,
            "destination": {
                "recipient": resolved_recipient,
                "address_line1": address_line1.strip(),
                "address_line2": address_line2.strip() if address_line2 else None,
                "city": city.strip(),
                "state": state.strip(),
                "postal_code": postal_code.strip(),
                "country": country.strip(),
                "country_code": dest_country_code,
                "phone": phone.strip(),
            },
            "currency": order_currency,
            "subtotal": str(item_subtotal),
            "shipping_cost": str(shipping_cost),
            "tax_amount": str(tax_amount),
            "total_amount": str(total_amount),
            "dhl_service": f"{dhl_quote.service_label} (Product {dhl_quote.product_code})",
            "dhl_quote_source": dhl_quote.source,
            "estimated_delivery_date": dhl_quote.estimated_delivery_date.isoformat(),
            "payment_status": "PAID" if mark_paid else "PENDING",
            "shipment_created": False,
        }

    # 4. Create or Reuse Shipping Address on Customer
    clean_line2 = address_line2.strip() if address_line2 and address_line2.strip() else None
    existing_address = await db.scalar(
        select(Address).where(
            Address.user_id == customer.id,
            func.lower(Address.country) == country.strip().lower(),
            func.lower(Address.city) == city.strip().lower(),
            func.lower(Address.address_line1) == address_line1.strip().lower(),
        )
    )
    if existing_address is not None:
        shipping_address = existing_address
        shipping_address.full_name = resolved_recipient
        shipping_address.phone_number = phone.strip()
        shipping_address.state = state.strip()
        shipping_address.postal_code = postal_code.strip() or None
        if clean_line2 is not None:
            shipping_address.address_line2 = clean_line2
        await db.flush()
    else:
        shipping_address = Address(
            user_id=customer.id,
            address_type=AddressType.SHIPPING,
            full_name=resolved_recipient,
            phone_number=phone.strip(),
            address_line1=address_line1.strip(),
            address_line2=clean_line2,
            city=city.strip(),
            state=state.strip(),
            postal_code=postal_code.strip() or None,
            country=country.strip(),
            is_default=False,
        )
        db.add(shipping_address)
        await db.flush()

    # 5. Create Order & OrderItem (with domestic_checkout_v1 workflow so CheckoutShippingEstimate triggers pass)
    db_now = await db.scalar(text("SELECT clock_timestamp()"))
    assert db_now is not None

    order_number = generate_order_number()
    new_order = Order(
        order_number=order_number,
        customer_id=customer.id,
        workflow_cohort="domestic_checkout_v1",
        workflow_policy_version="domestic_checkout_v1",
        checkout_access_mode="authenticated",
        shipping_address_id=shipping_address.id,
        billing_address_id=shipping_address.id,
        currency=order_currency,
        subtotal=item_subtotal,
        shipping_cost=shipping_cost,
        tax_amount=tax_amount,
        discount_amount=discount_amount,
        total_amount=total_amount,
        payment_status=PaymentStatus.PAID if mark_paid else PaymentStatus.PENDING,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        delivery_provider="dhl",
        tracking_number=None,  # Explicitly None: shipment is NOT created yet
        estimated_delivery_date=dhl_quote.estimated_delivery_date,
        confirmed_at=db_now if mark_paid else None,
        customer_notes=f"International DHL Express order to {city.strip()}, {country.strip()} ({dest_country_code})",
        admin_notes=(
            f"[{db_now.isoformat()}] Created via create_international_dhl_order management command. "
            f"DHL Express ({dhl_quote.product_code} - {dhl_quote.service_label}) selected; shipment NOT booked yet."
        ),
    )
    db.add(new_order)
    await db.flush()

    commission_rate = get_vendor_commission_rate(product.vendor)
    commission_amount = _quantize_money(item_subtotal * (commission_rate / Decimal("100")))
    vendor_payout = _quantize_money(item_subtotal - commission_amount)

    inv_snapshot = _inventory_snapshot(
        product,
        stock_source=resolved_variant["stock_source"],
        stock_id=resolved_variant["stock_id"],
    )
    order_item = OrderItem(
        order_id=new_order.id,
        product_id=product.id,
        variant_id=resolved_variant["variant_id"],
        vendor_id=product.vendor_id,
        product_title=product.title,
        variant_details=resolved_variant["variant_details"],
        unit_price=unit_price_decimal,
        currency=order_currency,
        quantity=quantity,
        subtotal=item_subtotal,
        commission_rate=commission_rate,
        commission_amount=commission_amount,
        vendor_payout=vendor_payout,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        **inv_snapshot,
    )
    db.add(order_item)
    await db.flush()

    # 6. Persist DHL Checkout Estimate, Option & Selection (selects DHL without creating a shipment)
    est_created_at = await db.scalar(text("SELECT clock_timestamp()"))
    assert est_created_at is not None

    dest_hash = hashlib.sha256(
        f"{dest_country_code}|{state.strip()}|{city.strip()}|{postal_code.strip()}|{address_line1.strip()}".encode(
            "utf-8"
        )
    ).hexdigest()
    order_snap_hash = hashlib.sha256(
        f"{new_order.id}|{product.id}|{quantity}|{order_currency}|{item_subtotal}".encode(
            "utf-8"
        )
    ).hexdigest()
    req_fingerprint = hashlib.sha256(
        f"mgmt-dhl-est:{new_order.id}:{dest_hash}:{order_snap_hash}".encode("utf-8")
    ).hexdigest()

    estimate = CheckoutShippingEstimate(
        order_id=new_order.id,
        customer_id=customer.id,
        destination_snapshot_hash=dest_hash,
        order_snapshot_hash=order_snap_hash,
        currency=order_currency,
        ttl_seconds=1800,
        expires_at=est_created_at + timedelta(seconds=1800),
        supersedes_estimate_id=None,
        source_kind="sandbox_normalized",
        source_reference=f"dhl-export-{dest_country_code.lower()}",
        source_command="create_checkout_estimate",
        idempotency_key=f"mgmt-est-{new_order.id.hex}",
        request_fingerprint=req_fingerprint,
        schema_version="checkout-estimate-v1",
        created_by_actor_type="customer",
        created_by_actor_id=str(customer.id),
        created_at=est_created_at,
    )
    db.add(estimate)
    await db.flush()

    option_key = f"dhl:{dhl_quote.product_code}:{dhl_quote.service_code}"
    option = CheckoutShippingEstimateOption(
        estimate_id=estimate.id,
        option_key=option_key,
        service_code=dhl_quote.service_code,
        service_label=dhl_quote.service_label,
        amount=shipping_cost,
        currency=order_currency,
        min_delivery_days=dhl_quote.transit_days,
        max_delivery_days=dhl_quote.transit_days,
        source_rate_id=None,
        provider_metadata={
            "provider": "dhl",
            "product_code": dhl_quote.product_code,
            "service_code": dhl_quote.service_code,
            "destination_country_code": dest_country_code,
            "transit_days": dhl_quote.transit_days,
            "estimated_delivery_date": dhl_quote.estimated_delivery_date.isoformat(),
            "quote_source": dhl_quote.source,
        },
        created_at=est_created_at,
    )
    db.add(option)
    await db.flush()

    sel_now = await db.scalar(text("SELECT clock_timestamp()"))
    assert sel_now is not None
    selection = CheckoutShippingEstimateSelection(
        estimate_id=estimate.id,
        option_id=option.id,
        order_id=new_order.id,
        customer_id=customer.id,
        selected_by_actor_type="customer",
        selected_by_actor_id=str(customer.id),
        shipping_amount=shipping_cost,
        currency=order_currency,
        source_command="select_checkout_estimate_option",
        idempotency_key=f"mgmt-sel-{new_order.id.hex}",
        selected_at=max(sel_now, est_created_at),
    )
    db.add(selection)
    await db.flush()

    # Bind selection onto Order (must happen after selection flush per trg_checkout_estimate_selections_truth)
    new_order.checkout_estimate_selection_id = selection.id
    await db.flush()

    # 7. Record Payment & Internal Vendor Fulfilment if Paid (still NO DHL shipment booked)
    if mark_paid:
        gateway = (
            PaymentGateway.STRIPE
            if order_currency == "USD"
            else PaymentGateway.PAYSTACK
        )
        payment = Payment(
            order_id=new_order.id,
            payment_gateway=gateway,
            transaction_id=f"MGMT-INTL-{order_number}",
            payment_method="card",
            amount=total_amount,
            currency=order_currency,
            status=TransactionStatus.COMPLETED,
            completed_at=sel_now,
            gateway_response={
                "source": "create_international_dhl_order",
                "destination_country": dest_country_code,
                "delivery_provider": "dhl",
                "dhl_product_code": dhl_quote.product_code,
                "dhl_shipment_booked": False,
            },
        )
        db.add(payment)
        await db.flush()

        await start_verified_order_fulfilment(db, order_id=new_order.id)

    hub_prep_info: dict[str, Any] | None = None
    if prepare_hub_package and mark_paid:
        hub_prep_info = await prepare_dhl_hub_package_for_order(
            db,
            order_id=new_order.id,
        )

    await db.commit()

    return {
        "dry_run": False,
        "order_id": str(new_order.id),
        "order_number": new_order.order_number,
        "customer_id": str(customer.id),
        "customer_email": customer.email,
        "product_id": str(product.id),
        "product_title": product.title,
        "variant_details": resolved_variant["variant_details"],
        "quantity": quantity,
        "address_id": str(shipping_address.id),
        "destination": {
            "recipient": resolved_recipient,
            "address_line1": shipping_address.address_line1,
            "address_line2": shipping_address.address_line2,
            "city": shipping_address.city,
            "state": shipping_address.state,
            "postal_code": shipping_address.postal_code,
            "country": shipping_address.country,
            "country_code": dest_country_code,
            "phone": shipping_address.phone_number,
        },
        "currency": order_currency,
        "subtotal": str(item_subtotal),
        "shipping_cost": str(shipping_cost),
        "tax_amount": str(tax_amount),
        "total_amount": str(total_amount),
        "delivery_provider": new_order.delivery_provider,
        "dhl_service": f"{dhl_quote.service_label} (Product {dhl_quote.product_code})",
        "dhl_quote_source": dhl_quote.source,
        "checkout_estimate_selection_id": str(selection.id),
        "estimated_delivery_date": dhl_quote.estimated_delivery_date.isoformat(),
        "payment_status": new_order.payment_status.value,
        "hub_package_prepared": hub_prep_info is not None,
        "shipment_created": False,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create an international order (default: Ghana) with DHL Express selected "
            "and NO shipment booked."
        )
    )
    parser.add_argument(
        "--email",
        default=DEFAULT_CUSTOMER_EMAIL,
        help=f"Customer account email (default: {DEFAULT_CUSTOMER_EMAIL})",
    )
    parser.add_argument(
        "--product",
        dest="product_ref",
        default=DEFAULT_PRODUCT_REF,
        help=(
            "Product UUID or full product URL "
            f"(default: {DEFAULT_PRODUCT_REF})"
        ),
    )
    parser.add_argument(
        "--variant-id",
        default=None,
        help="Optional variation / size_stock / product_variant UUID (auto-selected if omitted)",
    )
    parser.add_argument(
        "--quantity",
        type=int,
        default=1,
        help="Order item quantity (default: 1)",
    )
    parser.add_argument(
        "--currency",
        choices=["USD", "NGN", "usd", "ngn"],
        default="USD",
        help="Order & payment currency: USD or NGN (default: USD)",
    )
    parser.add_argument(
        "--country",
        default=DEFAULT_COUNTRY,
        help=f"Destination country name or ISO-2 code (default: {DEFAULT_COUNTRY})",
    )
    parser.add_argument(
        "--state",
        default=DEFAULT_STATE,
        help=f"Destination state/region (default: {DEFAULT_STATE})",
    )
    parser.add_argument(
        "--city",
        default=DEFAULT_CITY,
        help=f"Destination city (default: {DEFAULT_CITY})",
    )
    parser.add_argument(
        "--address-line1",
        default=DEFAULT_ADDRESS_LINE1,
        help=f"Street address line 1 (default: {DEFAULT_ADDRESS_LINE1})",
    )
    parser.add_argument(
        "--address-line2",
        default=None,
        help="Optional apartment / suite / house number",
    )
    parser.add_argument(
        "--postal-code",
        default=DEFAULT_POSTAL_CODE,
        help=f"Destination postal code (default: {DEFAULT_POSTAL_CODE})",
    )
    parser.add_argument(
        "--phone",
        default=DEFAULT_PHONE,
        help=f"Recipient international phone number (default: {DEFAULT_PHONE})",
    )
    parser.add_argument(
        "--recipient-name",
        default=None,
        help="Recipient full name (defaults to customer's full_name or 'Bello Karimu')",
    )
    parser.add_argument(
        "--shipping-cost",
        type=Decimal,
        default=None,
        help="Optional manual shipping cost in order currency (skips live MyDHL /rates call)",
    )
    parser.add_argument(
        "--offline-rate",
        action="store_true",
        help="Use offline fallback rate instead of calling live MyDHL POST /rates",
    )
    parser.add_argument(
        "--unpaid",
        action="store_true",
        help="Leave order in PENDING payment status instead of marking PAID",
    )
    parser.add_argument(
        "--prepare-hub-package",
        action="store_true",
        help=(
            "Also prepare the Hub package/seal/intent immediately (only use when running "
            "inside the target server shell where DHL_DOMESTIC_SANDBOX_COHORT_IDS matches)"
        ),
    )
    parser.add_argument(
        "--create-user-if-missing",
        action="store_true",
        help="Create the customer user account if it does not exist yet",
    )
    parser.add_argument(
        "--staging",
        action="store_true",
        help=(
            "Connect to Render Staging database (uses RENDER_DATABASE_URL / STAGING_DATABASE_URL "
            "if set, otherwise prompts for Render External Database URL)"
        ),
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Explicit PostgreSQL DATABASE_URL override (e.g. Render External Database URL)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate user, product, address, and DHL rate without writing to the database",
    )
    return parser.parse_args(argv)


def _resolve_target_database_url(args: argparse.Namespace) -> str:
    if args.database_url:
        return args.database_url.strip()
    if args.staging:
        env_staging = (
            os.environ.get("STAGING_DATABASE_URL", "").strip()
            or settings.RENDER_DATABASE_URL.strip()
        )
        if env_staging:
            return env_staging
        print("\n" + "=" * 72)
        print("CONNECT TO RENDER STAGING DATABASE")
        print("=" * 72)
        print("Paste your Render Staging 'External Database URL' (starts with postgres:// or postgresql://)")
        pasted = input("External DATABASE_URL: ").strip()
        if not pasted:
            raise ValueError("DATABASE_URL cannot be empty when --staging is used")
        return pasted
    return settings.ASYNC_DATABASE_URL or settings.DATABASE_URL


async def _async_main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    raw_db_url = _resolve_target_database_url(args)
    async_db_url, connect_args = build_async_engine_config(raw_db_url)

    print("\n" + "=" * 72)
    print("CREATE INTERNATIONAL DHL ORDER (NO SHIPMENT BOOKED)")
    print("=" * 72)
    print(f"Database : {settings.get_masked_db_url(async_db_url)}")
    print(f"Customer : {args.email}")
    print(f"Product  : {args.product_ref}")
    print(f"Lane     : Lagos, NG -> {args.city}, {args.country}")
    print("-" * 72)

    engine = create_async_engine(
        async_db_url,
        echo=False,
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    try:
        async with session_factory() as db:
            summary = await create_international_dhl_order(
                db,
                email=args.email,
                product_ref=args.product_ref,
                variant_id=args.variant_id,
                quantity=args.quantity,
                currency=args.currency,
                country=args.country,
                state=args.state,
                city=args.city,
                address_line1=args.address_line1,
                address_line2=args.address_line2,
                postal_code=args.postal_code,
                phone=args.phone,
                recipient_name=args.recipient_name,
                shipping_cost_override=args.shipping_cost,
                mark_paid=not args.unpaid,
                prepare_hub_package=args.prepare_hub_package,
                create_user_if_missing=args.create_user_if_missing,
                offline_rate=args.offline_rate,
                dry_run=args.dry_run,
            )
    finally:
        await engine.dispose()

    dest = summary["destination"]
    print("\nSUCCESS!" if not summary["dry_run"] else "\nDRY RUN COMPLETE (nothing written):")
    print(f"  Order Number       : {summary['order_number']}")
    print(f"  Order ID           : {summary['order_id']}")
    print(f"  Customer           : {summary['customer_email']} ({summary['customer_id']})")
    print(f"  Product            : {summary['product_title']} (x{summary['quantity']})")
    if summary.get("variant_details"):
        print(f"  Variant Selected   : {summary['variant_details']}")
    print(
        f"  Destination        : {dest['recipient']} — {dest['address_line1']}, "
        f"{dest['city']}, {dest['state']}, {dest['country']} [{dest['country_code']}]"
    )
    print(f"  Carrier Selected   : {summary['dhl_service']} [source={summary['dhl_quote_source']}]")
    print(f"  Shipment Created?  : NO (delivery_provider='dhl', tracking_number=None)")
    print(f"  Estimated Delivery : {summary['estimated_delivery_date']}")
    print(f"  Currency           : {summary['currency']}")
    print(f"  Subtotal           : {summary['currency']} {summary['subtotal']}")
    print(f"  DHL Shipping       : {summary['currency']} {summary['shipping_cost']}")
    print(f"  Tax (7.5%)         : {summary['currency']} {summary['tax_amount']}")
    print(f"  Total              : {summary['currency']} {summary['total_amount']}")
    print(f"  Payment Status     : {summary['payment_status']}")
    if summary.get("order_id"):
        print(
            f"\n  Staging Admin URL  : "
            f"https://shopsoma-staging.onrender.com/admin/orders/{summary['order_id']}"
        )
    print("=" * 72 + "\n")
    return 0


def main() -> None:
    try:
        raise SystemExit(asyncio.run(_async_main()))
    except (LookupError, ValueError) as exc:
        print(f"\n[ERROR] {exc}\n", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
