"""Integration tests for the create_international_dhl_order management command."""

from __future__ import annotations

from decimal import Decimal
import uuid

from httpx import AsyncClient
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.checkout_shipping_estimate import (
    CheckoutShippingEstimateOption,
    CheckoutShippingEstimateSelection,
)
from app.models.dhl_shipment import OutboundShipmentBooking
from app.models.order import Order, PaymentStatus
from app.models.package_custody import OutboundShipmentIntent
from app.models.payment import Payment, TransactionStatus
from app.models.product import ModerationStatus, Product, ProductStatus
from app.models.vendor_pickup import VendorPickup
from create_international_dhl_order import (
    DEFAULT_CUSTOMER_EMAIL,
    DEFAULT_PRODUCT_REF,
    build_async_engine_config,
    create_international_dhl_order,
    extract_product_uuid,
)


def test_extract_product_uuid_accepts_staging_url_and_raw_uuid() -> None:
    expected = uuid.UUID("00dcf603-7a97-4649-b8e2-97089ef9f963")
    assert (
        extract_product_uuid(
            "https://shopsoma-staging.onrender.com/products/00dcf603-7a97-4649-b8e2-97089ef9f963"
        )
        == expected
    )
    assert extract_product_uuid(DEFAULT_PRODUCT_REF) == expected


def test_build_async_engine_config_normalizes_render_postgres_url() -> None:
    url, connect_args = build_async_engine_config(
        "postgres://soma_user:secret@dpg-abc123.oregon-postgres.render.com/shopsoma_staging?sslmode=require"
    )
    assert url == (
        "postgresql+asyncpg://soma_user:secret@dpg-abc123.oregon-postgres.render.com/shopsoma_staging"
    )
    assert connect_args == {"ssl": "require"}


@pytest.mark.asyncio
async def test_create_international_dhl_order_to_ghana_selects_dhl_without_creating_shipment(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user: dict,
    admin_user: dict,
) -> None:
    vendor = vendor_user["vendor"]
    admin_token = admin_user["token"]
    target_product_id = uuid.UUID(DEFAULT_PRODUCT_REF)

    existing_product = await db_session.get(Product, target_product_id)
    if existing_product is None:
        product = Product(
            id=target_product_id,
            vendor_id=vendor.id,
            title="Adire Silk Resort Set",
            description="Hand-dyed silk set",
            base_price=Decimal("120000.00"),
            currency="NGN",
            status=ProductStatus.ACTIVE,
            moderation_status=ModerationStatus.APPROVED,
            total_stock=5,
            made_to_order=False,
            weight_kg=Decimal("1.100"),
            length_cm=Decimal("35.000"),
            width_cm=Decimal("25.000"),
            height_cm=Decimal("8.000"),
        )
        db_session.add(product)
        await db_session.commit()

    summary = await create_international_dhl_order(
        db_session,
        email=DEFAULT_CUSTOMER_EMAIL,
        product_ref=f"https://shopsoma-staging.onrender.com/products/{DEFAULT_PRODUCT_REF}",
        currency="USD",
        country="Ghana",
        state="Greater Accra",
        city="Accra",
        address_line1="45 Kofi Annan Street",
        postal_code="00233",
        phone="+233244123456",
        create_user_if_missing=True,
        offline_rate=True,
    )

    assert summary["shipment_created"] is False
    assert summary["delivery_provider"] == "dhl"
    assert summary["destination"]["country_code"] == "GH"
    assert summary["currency"] == "USD"
    assert summary["payment_status"] == "PAID"

    order_id = uuid.UUID(summary["order_id"])
    order = await db_session.get(Order, order_id)
    assert order is not None
    assert order.delivery_provider == "dhl"
    assert order.tracking_number is None
    assert order.payment_status == PaymentStatus.PAID
    assert order.checkout_estimate_selection_id is not None

    # Verify DHL option 'P' (Express Worldwide) is selected
    sel = await db_session.get(
        CheckoutShippingEstimateSelection, order.checkout_estimate_selection_id
    )
    assert sel is not None
    opt = await db_session.get(CheckoutShippingEstimateOption, sel.option_id)
    assert opt is not None
    assert opt.option_key == "dhl:P:P"
    assert opt.provider_metadata["provider"] == "dhl"
    assert opt.provider_metadata["product_code"] == "P"
    assert opt.provider_metadata["destination_country_code"] == "GH"

    # Verify Payment and VendorPickup were created, and NO DHL shipment booking exists
    payment = await db_session.scalar(
        select(Payment).where(Payment.order_id == order_id)
    )
    assert payment is not None
    assert payment.status == TransactionStatus.COMPLETED

    pickup = await db_session.scalar(
        select(VendorPickup).where(VendorPickup.order_id == order_id)
    )
    assert pickup is not None

    bookings = (
        await db_session.scalars(
            select(OutboundShipmentBooking).where(
                OutboundShipmentBooking.order_id == order_id
            )
        )
    ).all()
    assert bookings == []

    # Verify Admin Order Detail loads cleanly and "Prepare Hub Package for DHL" works seamlessly
    detail_res = await client.get(
        f"/api/v1/admin/orders/{order_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert detail_res.status_code == 200, detail_res.text
    assert detail_res.json()["dhl_operations"]["bookings"] == []

    prep_res = await client.post(
        f"/api/v1/admin/orders/{order_id}/dhl/prepare-package",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert prep_res.status_code == 200, prep_res.text
    dhl_ops = prep_res.json()["dhl_operations"]
    assert len(dhl_ops["packages"]) == 1
    assert dhl_ops["packages"][0]["package_state"] == "ready"
    assert dhl_ops["packages"][0]["selection_eligible"] is True
    assert dhl_ops["bookings"] == []  # Still NO shipment booked!

    intent = await db_session.scalar(
        select(OutboundShipmentIntent).where(OutboundShipmentIntent.order_id == order_id)
    )
    assert intent is not None
    assert intent.destination_country_code == "GH"
