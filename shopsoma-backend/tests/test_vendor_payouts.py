from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


@pytest.mark.asyncio
async def test_vendor_can_request_payout(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
):
    from app.models.order import Order, OrderItem, PaymentStatus, FulfillmentStatus
    from app.models.product import Product, ProductStatus, ModerationStatus
    from app.models.app_setting import AppSetting

    vendor = vendor_user["vendor"]
    vendor.bank_name = "Wema Bank"
    vendor.bank_account_number = "1234567890"
    vendor.bank_account_name = "Test Vendor"
    db_session.add(vendor)

    hold_setting = await db_session.execute(
        select(AppSetting).where(AppSetting.key == "payout_hold_days")
    )
    current_setting = hold_setting.scalar_one_or_none()
    if not current_setting:
        db_session.add(
            AppSetting(
                key="payout_hold_days",
                value="14",
                value_type="string",
            )
        )

    product = Product(
        id=uuid4(),
        vendor_id=vendor.id,
        title="Payout Product",
        description="Test payout product",
        base_price=Decimal("100.00"),
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)

    delivered_at = datetime.utcnow() - timedelta(days=20)
    order = Order(
        id=uuid4(),
        order_number="SHP-PAYOUT-1",
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
    db_session.add(order)

    order_item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor.id,
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
    db_session.add(order_item)

    await db_session.commit()

    response = await client.post(
        "/api/v1/vendor/payouts/request",
        json={"amount": 50},
        headers=vendor_user["headers"],
    )

    assert response.status_code == 201
    data = response.json()
    assert float(data["payout_amount"]) == 50.0
    assert data["vendor_id"] == str(vendor_user["vendor"].id)

    detail_response = await client.get(
        f"/api/v1/vendor/payouts/{data['id']}",
        headers=vendor_user["headers"],
    )
    assert detail_response.status_code == 200


@pytest.mark.asyncio
async def test_vendor_payout_requires_14_day_wait(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
):
    from app.models.order import Order, OrderItem, PaymentStatus, FulfillmentStatus
    from app.models.product import Product, ProductStatus, ModerationStatus
    from app.models.app_setting import AppSetting

    vendor = vendor_user["vendor"]
    vendor.bank_name = "Wema Bank"
    vendor.bank_account_number = "1234567890"
    vendor.bank_account_name = "Test Vendor"
    db_session.add(vendor)

    hold_setting = await db_session.execute(
        select(AppSetting).where(AppSetting.key == "payout_hold_days")
    )
    current_setting = hold_setting.scalar_one_or_none()
    if not current_setting:
        db_session.add(
            AppSetting(
                key="payout_hold_days",
                value="14",
                value_type="string",
            )
        )

    product = Product(
        id=uuid4(),
        vendor_id=vendor.id,
        title="Hold Product",
        description="Hold period product",
        base_price=Decimal("100.00"),
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)

    delivered_at = datetime.utcnow() - timedelta(days=5)
    order = Order(
        id=uuid4(),
        order_number="SHP-PAYOUT-2",
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
    db_session.add(order)

    order_item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor.id,
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
    db_session.add(order_item)

    await db_session.commit()

    response = await client.post(
        "/api/v1/vendor/payouts/request",
        json={"amount": 50},
        headers=vendor_user["headers"],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "No available payout balance."


@pytest.mark.asyncio
async def test_vendor_payout_summary_available_same_day(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
):
    from app.models.order import Order, OrderItem, PaymentStatus, FulfillmentStatus
    from app.models.product import Product, ProductStatus, ModerationStatus
    from app.models.app_setting import AppSetting

    vendor = vendor_user["vendor"]
    vendor.bank_name = "Wema Bank"
    vendor.bank_account_number = "1234567890"
    vendor.bank_account_name = "Test Vendor"
    db_session.add(vendor)

    hold_setting = await db_session.execute(
        select(AppSetting).where(AppSetting.key == "payout_hold_days")
    )
    current_setting = hold_setting.scalar_one_or_none()
    if not current_setting:
        db_session.add(
            AppSetting(
                key="payout_hold_days",
                value="0",
                value_type="string",
            )
        )
    else:
        current_setting.value = "0"
        db_session.add(current_setting)

    product = Product(
        id=uuid4(),
        vendor_id=vendor.id,
        title="Summary Product",
        description="Summary payout product",
        base_price=Decimal("100.00"),
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)

    delivered_at = datetime.utcnow()
    order = Order(
        id=uuid4(),
        order_number="SHP-PAYOUT-3",
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
    db_session.add(order)

    order_item = OrderItem(
        id=uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor.id,
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
    db_session.add(order_item)

    await db_session.commit()

    response = await client.get(
        "/api/v1/vendor/payouts/summary",
        headers=vendor_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["current_earnings"] == 90.0
    assert data["available_payout"] == 90.0


@pytest.mark.asyncio
async def test_vendor_can_cancel_pending_payout(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    from app.models.payment import Payout, PayoutStatus

    payout = Payout(
        vendor_id=vendor_user["vendor"].id,
        payout_period_start=datetime.utcnow().date(),
        payout_period_end=datetime.utcnow().date(),
        total_sales=Decimal("100.00"),
        commission_amount=Decimal("10.00"),
        payout_amount=Decimal("90.00"),
        status=PayoutStatus.PENDING,
        notes="Vendor requested payout",
    )
    db_session.add(payout)
    await db_session.commit()
    await db_session.refresh(payout)

    response = await client.post(
        f"/api/v1/vendor/payouts/{payout.id}/cancel",
        headers=vendor_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
