import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_usd_order(db_session: AsyncSession, admin_user, customer_user, vendor_user):
    from app.models.address import Address, AddressType
    from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
    from app.models.payment import Payment, PaymentGateway, TransactionStatus
    from app.models.product import ModerationStatus, Product, ProductStatus

    shipping_address = Address(
        id=uuid.uuid4(),
        user_id=customer_user["user"].id,
        address_type=AddressType.SHIPPING,
        full_name="USD Customer",
        phone_number="08000000000",
        address_line1="12 River Trent Close",
        city="Abuja",
        state="FCT",
        postal_code="900001",
        country="Nigeria",
        is_default=True,
    )
    db_session.add(shipping_address)
    await db_session.flush()

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="USD Admin Order Product",
        description="USD priced product",
        base_price=Decimal("300.00"),
        currency="USD",
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number="SHP-ADMIN-USD-TEST",
        customer_id=customer_user["user"].id,
        shipping_address_id=shipping_address.id,
        billing_address_id=shipping_address.id,
        currency="USD",
        subtotal=Decimal("300.00"),
        shipping_cost=Decimal("3.45"),
        tax_amount=Decimal("22.76"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("326.21"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.flush()

    order_item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        unit_price=Decimal("300.00"),
        currency="USD",
        quantity=1,
        subtotal=Decimal("300.00"),
        commission_rate=Decimal("15.00"),
        commission_amount=Decimal("45.00"),
        vendor_payout=Decimal("255.00"),
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order_item)

    payment = Payment(
        id=uuid.uuid4(),
        order_id=order.id,
        payment_gateway=PaymentGateway.STRIPE,
        transaction_id=f"pi_{uuid.uuid4().hex}",
        payment_method="card",
        amount=Decimal("326.21"),
        currency="USD",
        status=TransactionStatus.COMPLETED,
    )
    db_session.add(payment)
    await db_session.commit()

    return order


@pytest.mark.asyncio
async def test_admin_order_detail_includes_currency_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
    customer_user,
    vendor_user,
):
    order = await _create_usd_order(db_session, admin_user, customer_user, vendor_user)

    response = await client.get(
        f"/api/v1/admin/orders/{order.id}",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["currency"] == "USD"
    assert payload["total_amount"] == "326.21"
    assert payload["subtotal"] == "300.00"
    assert payload["shipping_address"]["full_name"] == "USD Customer"
    assert payload["shipping_address"]["street_address"] == "12 River Trent Close"
    assert payload["items"][0]["currency"] == "USD"
    assert payload["items"][0]["unit_price"] == "300.00"


@pytest.mark.asyncio
async def test_admin_order_detail_prefers_payment_currency_for_legacy_orders(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
    customer_user,
    vendor_user,
):
    from app.models.order import OrderItem

    order = await _create_usd_order(db_session, admin_user, customer_user, vendor_user)
    order.currency = "NGN"
    order_item = (
        await db_session.execute(select(OrderItem).where(OrderItem.order_id == order.id))
    ).scalar_one()
    order_item.currency = "NGN"
    await db_session.commit()

    response = await client.get(
        f"/api/v1/admin/orders/{order.id}",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["currency"] == "USD"
    assert payload["items"][0]["currency"] == "USD"


@pytest.mark.asyncio
async def test_admin_order_status_update_returns_updated_usd_order(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
    customer_user,
    vendor_user,
    monkeypatch,
):
    from app.api.v1 import admin_orders as admin_orders_api

    order = await _create_usd_order(db_session, admin_user, customer_user, vendor_user)

    async def _noop_notify_status_change(self, order, new_status, pickup_details=None):
        return None

    class _NoopConnectionManager:
        def get_connection_count(self, order_id: str) -> int:
            return 0

        async def send_order_update(self, order_id: str, data: dict):
            return None

    monkeypatch.setattr(
        admin_orders_api.OrderNotificationService,
        "notify_status_change",
        _noop_notify_status_change,
    )
    monkeypatch.setattr(
        admin_orders_api,
        "get_connection_manager",
        lambda: _NoopConnectionManager(),
    )

    response = await client.patch(
        f"/api/v1/admin/orders/{order.id}/status",
        headers=admin_user["headers"],
        json={"fulfillment_status": "preparing_for_pickup"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["currency"] == "USD"
    assert payload["fulfillment_status"] == "preparing_for_pickup"
    assert payload["items"][0]["currency"] == "USD"
