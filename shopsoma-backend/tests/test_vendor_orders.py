from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_vendor_order(
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    *,
    order_number: str,
    created_at: datetime,
):
    from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
    from app.models.product import Product, ProductStatus

    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title=f"{order_number} Product",
        base_price=Decimal("100.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid4(),
        order_number=order_number,
        customer_id=customer_user["user"].id,
        subtotal=Decimal("100.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        created_at=created_at,
    )
    db_session.add(order)
    await db_session.flush()

    db_session.add(
        OrderItem(
            id=uuid4(),
            order_id=order.id,
            product_id=product.id,
            vendor_id=vendor_user["vendor"].id,
            product_title=product.title,
            variant_details=None,
            unit_price=Decimal("100.00"),
            quantity=1,
            subtotal=Decimal("100.00"),
            commission_rate=Decimal("10.00"),
            commission_amount=Decimal("10.00"),
            vendor_payout=Decimal("90.00"),
            fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        )
    )
    return order


@pytest.mark.asyncio
async def test_vendor_orders_default_to_newest_first_and_filter_total(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
):
    await _create_vendor_order(
        db_session,
        vendor_user,
        customer_user,
        order_number="SHP-OLDER",
        created_at=datetime(2025, 1, 1, 9, 0, 0),
    )
    await _create_vendor_order(
        db_session,
        vendor_user,
        customer_user,
        order_number="SHP-NEWER",
        created_at=datetime(2025, 1, 2, 9, 0, 0),
    )
    await db_session.commit()

    response = await client.get(
        "/api/v1/vendor/orders",
        headers=vendor_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert [order["order_number"] for order in payload["orders"]] == [
        "SHP-NEWER",
        "SHP-OLDER",
    ]

    search_response = await client.get(
        "/api/v1/vendor/orders",
        params={"search": "NEWER"},
        headers=vendor_user["headers"],
    )

    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["total"] == 1
    assert search_payload["orders"][0]["order_number"] == "SHP-NEWER"
