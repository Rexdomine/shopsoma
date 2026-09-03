"""
Unit tests for Order review and creation with variation-based variants.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_review_order_with_size_stock_variant(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    """Review order should resolve size_stock-based variants."""
    from app.models.product import Product, ProductStatus, ModerationStatus, Variation, SizeStock, SizeEnum
    from app.models.shipping_rate import ShippingRate
    import uuid

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Variation Product",
        description="Variation product for review",
        base_price=80000.00,
        total_stock=50,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.flush()

    variation = Variation(
        id=uuid.uuid4(),
        product_id=product.id,
        title="Green",
        type="color",
        color_hex="#00FF00",
        price=80000.00,
        is_active=True,
    )
    db_session.add(variation)
    await db_session.flush()

    size_stock = SizeStock(
        id=uuid.uuid4(),
        variation_id=variation.id,
        size=SizeEnum.M,
        stock=5,
    )
    db_session.add(size_stock)

    shipping_rate = ShippingRate(
        id=uuid.uuid4(),
        name="Standard",
        description="Standard shipping",
        base_rate=1500.00,
        country="Nigeria",
        state="Lagos",
        is_active=True,
        is_default=True,
        priority=0,
    )
    db_session.add(shipping_rate)
    await db_session.commit()

    response = await client.post(
        "/api/v1/orders/review",
        json={
            "items": [
                {
                    "product_id": str(product.id),
                    "variant_id": str(size_stock.id),
                    "quantity": 1,
                }
            ],
            "guest_address": {
                "full_name": "Guest User",
                "phone_number": "08000000000",
                "address_line1": "123 Test Street",
                "address_line2": "",
                "city": "Lagos",
                "state": "Lagos",
                "postal_code": "100001",
                "country": "Nigeria",
            },
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["items"][0]["variant_details"]["size"] == "M"
    assert data["items"][0]["variant_details"]["color"] == "Green"


@pytest.mark.asyncio
async def test_create_order_with_size_stock_variant_updates_stock(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    """Create order should accept size_stock variants and decrement stock."""
    from app.models.product import Product, ProductStatus, ModerationStatus, Variation, SizeStock, SizeEnum
    from app.models.shipping_rate import ShippingRate
    import uuid

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Variation Product",
        description="Variation product for create",
        base_price=80000.00,
        total_stock=50,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.flush()

    variation = Variation(
        id=uuid.uuid4(),
        product_id=product.id,
        title="Blue",
        type="color",
        color_hex="#0000FF",
        price=80000.00,
        is_active=True,
    )
    db_session.add(variation)
    await db_session.flush()

    size_stock = SizeStock(
        id=uuid.uuid4(),
        variation_id=variation.id,
        size=SizeEnum.L,
        stock=5,
    )
    db_session.add(size_stock)

    shipping_rate = ShippingRate(
        id=uuid.uuid4(),
        name="Standard",
        description="Standard shipping",
        base_rate=1500.00,
        country="Nigeria",
        state="Lagos",
        is_active=True,
        is_default=True,
        priority=0,
    )
    db_session.add(shipping_rate)
    await db_session.commit()

    response = await client.post(
        "/api/v1/orders",
        json={
            "items": [
                {
                    "product_id": str(product.id),
                    "variant_id": str(size_stock.id),
                    "quantity": 1,
                }
            ],
            "guest_address": {
                "full_name": "Guest User",
                "phone_number": "08000000000",
                "address_line1": "123 Test Street",
                "address_line2": "",
                "city": "Lagos",
                "state": "Lagos",
                "postal_code": "100001",
                "country": "Nigeria",
            },
            "customer_email": "guest@example.com",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["items"][0]["variant_details"]["size"] == "L"
    assert data["items"][0]["variant_details"]["color"] == "Blue"

    await db_session.refresh(size_stock)
    assert size_stock.stock == 4


@pytest.mark.asyncio
async def test_review_order_converts_mixed_currency_items_to_checkout_currency(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    from app.models.product import Product, ProductStatus, ModerationStatus
    from app.models.shipping_rate import ShippingRate
    import uuid

    ngn_product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="NGN Product",
        description="Priced in naira",
        base_price=80000.00,
        currency="NGN",
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    usd_product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="USD Product",
        description="Priced in dollars",
        base_price=300.00,
        currency="USD",
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    shipping_rate = ShippingRate(
        id=uuid.uuid4(),
        name="Standard",
        description="Standard shipping",
        base_rate=1500.00,
        country="Nigeria",
        state="Lagos",
        is_active=True,
        is_default=True,
        priority=0,
    )
    db_session.add_all([ngn_product, usd_product, shipping_rate])
    await db_session.commit()

    response = await client.post(
        "/api/v1/orders/review",
        json={
            "currency": "USD",
            "items": [
                {"product_id": str(ngn_product.id), "quantity": 1},
                {"product_id": str(usd_product.id), "quantity": 1},
            ],
            "guest_address": {
                "full_name": "Guest User",
                "phone_number": "08000000000",
                "address_line1": "123 Test Street",
                "address_line2": "",
                "city": "Lagos",
                "state": "Lagos",
                "postal_code": "100001",
                "country": "Nigeria",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["currency"] == "USD"
    assert payload["items"][0]["currency"] == "USD"
    assert payload["items"][1]["currency"] == "USD"
    assert float(payload["summary"]["subtotal"]) > 300


@pytest.mark.asyncio
async def test_create_order_persists_item_currency(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    from app.models.order import Order, OrderItem
    from app.models.order_guest_capability import OrderCurrentOwner
    from app.models.product import Product, ProductStatus, ModerationStatus
    from app.models.shipping_rate import ShippingRate
    import uuid

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="USD Product",
        description="Priced in dollars",
        base_price=300.00,
        currency="USD",
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    shipping_rate = ShippingRate(
        id=uuid.uuid4(),
        name="Express",
        description="Express shipping",
        base_rate=20.00,
        country="Nigeria",
        state="Lagos",
        is_active=True,
        is_default=True,
        priority=0,
    )
    db_session.add_all([product, shipping_rate])
    await db_session.commit()

    response = await client.post(
        "/api/v1/orders",
        json={
            "currency": "USD",
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "guest_address": {
                "full_name": "Guest User",
                "phone_number": "08000000000",
                "address_line1": "123 Test Street",
                "address_line2": "",
                "city": "Lagos",
                "state": "Lagos",
                "postal_code": "100001",
                "country": "Nigeria",
            },
            "customer_email": "guest@example.com",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["currency"] == "USD"
    assert data["items"][0]["currency"] == "USD"

    persisted_item = (
        await db_session.execute(select(OrderItem).where(OrderItem.order_id == data["id"]))
    ).scalar_one()
    assert persisted_item.currency == "USD"

    persisted_order = await db_session.get(Order, data["id"])
    persisted_owner = await db_session.get(OrderCurrentOwner, data["id"])
    assert persisted_order.workflow_cohort == "legacy_pre_bridge"
    assert persisted_order.workflow_policy_version == "legacy_pre_bridge_v1"
    assert persisted_order.checkout_access_mode == "guest_capability"
    assert persisted_owner.original_customer_id == persisted_order.customer_id


@pytest.mark.asyncio
async def test_create_order_uses_vendor_commission_rate_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    from app.models.order import OrderItem
    from app.models.product import Product, ProductStatus, ModerationStatus
    from app.models.shipping_rate import ShippingRate
    import uuid

    vendor_user["vendor"].commission_rate = 12.5

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Commission Product",
        description="Product with vendor commission",
        base_price=100000.00,
        currency="NGN",
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    shipping_rate = ShippingRate(
        id=uuid.uuid4(),
        name="Standard",
        description="Standard shipping",
        base_rate=1500.00,
        country="Nigeria",
        state="Lagos",
        is_active=True,
        is_default=True,
        priority=0,
    )
    db_session.add_all([product, shipping_rate])
    await db_session.commit()

    response = await client.post(
        "/api/v1/orders",
        json={
            "currency": "NGN",
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "guest_address": {
                "full_name": "Guest User",
                "phone_number": "08000000000",
                "address_line1": "123 Test Street",
                "address_line2": "",
                "city": "Lagos",
                "state": "Lagos",
                "postal_code": "100001",
                "country": "Nigeria",
            },
            "customer_email": "guest@example.com",
        },
    )

    assert response.status_code == 201
    data = response.json()

    persisted_item = (
        await db_session.execute(select(OrderItem).where(OrderItem.order_id == data["id"]))
    ).scalar_one()
    assert float(persisted_item.commission_rate) == 12.5
    assert float(persisted_item.commission_amount) == 12500
    assert float(persisted_item.vendor_payout) == 87500
