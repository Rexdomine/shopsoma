from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_vendor_analytics_summary_chart_and_stats(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
):
    from app.models.order import Order, OrderItem, PaymentStatus, FulfillmentStatus
    from app.models.product import Product, ProductStatus
    from app.models.user import User, UserRole
    from app.core.security import get_password_hash
    from app.models.wishlist import Wishlist

    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Analytics Product",
        base_price=Decimal("100.00"),
        status=ProductStatus.ACTIVE,
    )
    db_session.add(product)

    returning_customer = customer_user["user"]
    new_customer = User(
        id=uuid4(),
        email="newcustomer@test.com",
        hashed_password=get_password_hash("CustomerPass123"),
        full_name="New Customer",
        role=UserRole.CUSTOMER,
        email_verified=True,
        is_active=True
    )
    db_session.add(new_customer)

    prior_order = Order(
        id=uuid4(),
        order_number="SHP-PRIOR-1",
        customer_id=returning_customer.id,
        subtotal=Decimal("50.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("50.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        created_at=datetime(2024, 12, 15, 9, 0, 0),
    )
    db_session.add(prior_order)

    prior_item = OrderItem(
        id=uuid4(),
        order_id=prior_order.id,
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
    db_session.add(prior_item)

    range_order_a = Order(
        id=uuid4(),
        order_number="SHP-RANGE-1",
        customer_id=returning_customer.id,
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
    range_order_b = Order(
        id=uuid4(),
        order_number="SHP-RANGE-2",
        customer_id=new_customer.id,
        subtotal=Decimal("150.00"),
        shipping_cost=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("150.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.DELIVERED,
        created_at=datetime(2025, 1, 20, 9, 0, 0),
        delivered_at=datetime(2025, 1, 21, 12, 0, 0),
    )
    db_session.add_all([range_order_a, range_order_b])

    order_item_a = OrderItem(
        id=uuid4(),
        order_id=range_order_a.id,
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
    order_item_b = OrderItem(
        id=uuid4(),
        order_id=range_order_b.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        variant_details=None,
        unit_price=Decimal("150.00"),
        quantity=1,
        subtotal=Decimal("150.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("15.00"),
        vendor_payout=Decimal("135.00"),
        fulfillment_status=FulfillmentStatus.DELIVERED,
    )
    db_session.add_all([order_item_a, order_item_b])

    wishlist_a = Wishlist(
        id=uuid4(),
        user_id=returning_customer.id,
        product_id=product.id,
        created_at=datetime(2025, 1, 5, 10, 0, 0),
    )
    wishlist_b = Wishlist(
        id=uuid4(),
        user_id=new_customer.id,
        product_id=product.id,
        created_at=datetime(2025, 1, 18, 10, 0, 0),
    )
    db_session.add_all([wishlist_a, wishlist_b])

    await db_session.commit()

    params = {"start_date": "2025-01-01", "end_date": "2025-01-31"}

    summary_response = await client.get(
        "/api/v1/vendor/analytics/summary",
        params=params,
        headers=vendor_user["headers"],
    )
    assert summary_response.status_code == 200
    summary_data = summary_response.json()
    assert summary_data["total_revenue"] == 350.0

    stats_response = await client.get(
        "/api/v1/vendor/analytics/stats",
        params=params,
        headers=vendor_user["headers"],
    )
    assert stats_response.status_code == 200
    stats_data = stats_response.json()
    assert stats_data["total_products_sold"] == 3
    assert stats_data["wishlisted_products"] == 2
    assert stats_data["returning_customers"] == 1
    assert stats_data["new_customers"] == 1

    chart_response = await client.get(
        "/api/v1/vendor/analytics/chart",
        params={"range": "1M", **params},
        headers=vendor_user["headers"],
    )
    assert chart_response.status_code == 200
    chart_data = chart_response.json()
    total_revenue = sum(point["revenue"] for point in chart_data["points"])
    total_expenses = sum(point["expenses"] for point in chart_data["points"])
    assert round(total_revenue, 2) == 350.0
    assert round(total_expenses, 2) == 35.0
