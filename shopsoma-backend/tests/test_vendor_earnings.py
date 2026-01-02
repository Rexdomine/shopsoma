from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_vendor_earnings_summary_and_items(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
):
    from app.models.order import Order, OrderItem, PaymentStatus, FulfillmentStatus
    from app.models.product import Product, ProductStatus
    from app.models.app_setting import AppSetting

    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Test Product",
        base_price=Decimal("100.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)

    delivered_order = Order(
        id=uuid4(),
        order_number="SHP-DELIVERED-1",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("200.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("200.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        created_at=datetime(2025, 1, 10, 9, 0, 0),
        delivered_at=datetime(2025, 1, 15, 12, 0, 0),
    )
    db_session.add(delivered_order)

    delivered_item = OrderItem(
        id=uuid4(),
        order_id=delivered_order.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        variant_details=None,
        unit_price=Decimal("100.00"),
        quantity=2,
        subtotal=Decimal("200.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("20.00"),
        vendor_payout=Decimal("180.00"),
        fulfillment_status=FulfillmentStatus.DELIVERED,
    )
    db_session.add(delivered_item)

    projected_order = Order(
        id=uuid4(),
        order_number="SHP-PROJECTED-1",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("50.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("50.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        created_at=datetime(2025, 1, 20, 9, 0, 0),
    )
    db_session.add(projected_order)

    projected_item = OrderItem(
        id=uuid4(),
        order_id=projected_order.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        variant_details=None,
        unit_price=Decimal("50.00"),
        quantity=1,
        subtotal=Decimal("50.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("5.00"),
        vendor_payout=Decimal("45.00"),
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(projected_item)

    payout_hold_setting = AppSetting(
        id=uuid4(),
        key="payout_hold_days",
        value="0",
    )
    db_session.add(payout_hold_setting)
    await db_session.commit()

    summary_response = await client.get(
        "/api/v1/vendor/earnings/summary",
        params={"start_date": "2025-01-01", "end_date": "2025-01-31"},
        headers=vendor_user["headers"],
    )

    assert summary_response.status_code == 200
    summary_data = summary_response.json()
    assert summary_data["current_earnings"] == 180.0
    assert summary_data["expenses"] == 20.0
    assert summary_data["projected_earnings"] == 45.0

    products_response = await client.get(
        "/api/v1/vendor/earnings/items",
        params={"view": "products", "start_date": "2025-01-01", "end_date": "2025-01-31"},
        headers=vendor_user["headers"],
    )

    assert products_response.status_code == 200
    products_data = products_response.json()
    assert products_data["view"] == "products"
    assert products_data["total"] == 1
    assert products_data["items"][0]["product_title"] == "Test Product"
    assert products_data["items"][0]["withdraw_available"] is True
    assert products_data["items"][0]["withdraw_days_left"] == 0

    orders_response = await client.get(
        "/api/v1/vendor/earnings/items",
        params={"view": "orders", "start_date": "2025-01-01", "end_date": "2025-01-31"},
        headers=vendor_user["headers"],
    )

    assert orders_response.status_code == 200
    orders_data = orders_response.json()
    assert orders_data["view"] == "orders"
    assert orders_data["total"] == 1
    assert orders_data["items"][0]["total_quantity"] == 2
    assert orders_data["items"][0]["total_commission"] == 20.0
    assert orders_data["items"][0]["total_payout"] == 180.0
    assert orders_data["items"][0]["withdraw_available"] is True
    assert orders_data["items"][0]["withdraw_days_left"] == 0


@pytest.mark.asyncio
async def test_vendor_earnings_items_not_paid_out_before_hold(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
):
    from app.models.order import Order, OrderItem, PaymentStatus, FulfillmentStatus
    from app.models.product import Product, ProductStatus
    from app.models.app_setting import AppSetting
    from app.models.payment import Payout, PayoutStatus

    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Hold Product",
        base_price=Decimal("100.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)

    delivered_at = datetime.utcnow() - timedelta(days=1)
    delivered_order = Order(
        id=uuid4(),
        order_number="SHP-DELIVERED-HOLD",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("100.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        created_at=delivered_at,
        delivered_at=delivered_at,
    )
    db_session.add(delivered_order)

    delivered_item = OrderItem(
        id=uuid4(),
        order_id=delivered_order.id,
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
        fulfillment_status=FulfillmentStatus.DELIVERED,
    )
    db_session.add(delivered_item)

    payout_hold_setting = AppSetting(
        id=uuid4(),
        key="payout_hold_days",
        value="14",
    )
    db_session.add(payout_hold_setting)

    completed_payout = Payout(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        payout_period_start=delivered_at.date(),
        payout_period_end=delivered_at.date(),
        total_sales=Decimal("100.00"),
        commission_amount=Decimal("10.00"),
        payout_amount=Decimal("90.00"),
        status=PayoutStatus.COMPLETED,
    )
    db_session.add(completed_payout)
    await db_session.commit()

    products_response = await client.get(
        "/api/v1/vendor/earnings/items",
        params={
            "view": "products",
            "start_date": delivered_at.date().isoformat(),
            "end_date": delivered_at.date().isoformat(),
        },
        headers=vendor_user["headers"],
    )

    assert products_response.status_code == 200
    data = products_response.json()
    assert data["items"][0]["payout_status"] == "available"
    assert data["items"][0]["withdraw_available"] is False
    assert data["items"][0]["withdraw_days_left"] > 0


@pytest.mark.asyncio
async def test_vendor_earnings_items_hold_period_from_delivery_date(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
):
    from app.models.order import Order, OrderItem, PaymentStatus, FulfillmentStatus
    from app.models.product import Product, ProductStatus
    from app.models.app_setting import AppSetting

    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Hold Period Product",
        base_price=Decimal("100.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)

    delivered_at = datetime.utcnow()
    delivered_order = Order(
        id=uuid4(),
        order_number="SHP-DELIVERED-TODAY",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("100.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("100.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        created_at=delivered_at,
        delivered_at=delivered_at,
    )
    db_session.add(delivered_order)

    delivered_item = OrderItem(
        id=uuid4(),
        order_id=delivered_order.id,
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
        fulfillment_status=FulfillmentStatus.DELIVERED,
    )
    db_session.add(delivered_item)

    payout_hold_setting = AppSetting(
        id=uuid4(),
        key="payout_hold_days",
        value="14",
    )
    db_session.add(payout_hold_setting)
    await db_session.commit()

    response = await client.get(
        "/api/v1/vendor/earnings/items",
        params={
            "view": "products",
            "start_date": delivered_at.date().isoformat(),
            "end_date": delivered_at.date().isoformat(),
        },
        headers=vendor_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["withdraw_available"] is False
    assert item["withdraw_days_left"] == 14
