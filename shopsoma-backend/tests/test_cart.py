"""
Unit tests for Cart API endpoints.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace
from datetime import datetime, timezone
from uuid import uuid4

from app.api.v1.cart import (
    calculate_cart_subtotal,
    calculate_cart_summary,
    reprice_cart_item,
    resolve_cart_purchase_option,
    resolve_cart_item_price,
    resolve_variant_response,
)


def test_default_cart_option_is_rejected_when_variation_records_exist():
    product = SimpleNamespace(
        base_price=100,
        total_stock=10,
        made_to_order=False,
        variants=[],
        variations=[SimpleNamespace(is_active=False)],
    )

    assert resolve_cart_purchase_option(product, "default-product") is None


def test_parent_variation_with_size_stocks_is_not_purchasable():
    size_stock = SimpleNamespace(id="size-stock-id", size="M", stock=1)
    variation = SimpleNamespace(
        id="variation-id", title="M", type="size", color_hex=None,
        price=None, sale_price=None, is_active=True, size_stocks=[size_stock],
    )
    product = SimpleNamespace(
        base_price=100, compare_at_price=None, total_stock=10, made_to_order=True, variants=[],
        variations=[variation],
    )

    assert resolve_cart_purchase_option(product, "variation-id") is None


def test_unrelated_bare_size_variation_remains_purchasable():
    bare_id = uuid4()
    product_id = uuid4()
    bare_size = SimpleNamespace(
        id=bare_id, title="4", type="size", color_hex=None,
        price=None, sale_price=None, is_active=True, size_stocks=[],
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    stocked_size = SimpleNamespace(
        id="stocked-size-id", title="M", type="size", color_hex=None,
        price=None, sale_price=None, is_active=True,
        size_stocks=[SimpleNamespace(id="m-stock-id", size="M", stock=1)],
    )
    product = SimpleNamespace(
        id=product_id,
        base_price=100, compare_at_price=None, total_stock=10, made_to_order=True, variants=[],
        variations=[bare_size, stocked_size],
    )

    option = resolve_cart_purchase_option(product, str(bare_id))

    assert option is not None
    assert option["normalized_variant_id"] == str(bare_id)


def test_parent_variation_is_not_purchasable_when_legacy_variants_exist():
    variation = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000021", title="Red", type="color", color_hex="#f00",
        price=None, sale_price=None, is_active=True, size_stocks=[],
    )
    legacy_variant = SimpleNamespace(id="legacy-id")
    product = SimpleNamespace(
        base_price=100, compare_at_price=None, total_stock=10, made_to_order=True,
        variants=[legacy_variant], variations=[variation],
    )

    assert resolve_cart_purchase_option(product, "00000000-0000-4000-8000-000000000021") is None


def test_bare_size_variation_cart_response_uses_size_axis():
    now = datetime.now(timezone.utc)
    variation = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000022", title="M", type="size", color_hex=None,
        price=None, sale_price=None, is_active=True, size_stocks=[],
        created_at=now, updated_at=now,
    )
    product = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000023", base_price=100, compare_at_price=None, variants=[], variations=[variation],
    )

    response = resolve_variant_response(product, "00000000-0000-4000-8000-000000000022")

    assert response.size == "M"
    assert response.color is None


def test_existing_variation_cart_row_uses_and_persists_current_sale_price():
    variation = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000002",
        title="Red",
        color_hex="#ff0000",
        price=None,
        sale_price=80,
        is_active=True,
        size_stocks=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    product = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000001",
        base_price=100,
        compare_at_price=None,
        total_stock=10,
        made_to_order=False,
        variants=[],
        variations=[variation],
    )
    cart_item = SimpleNamespace(product=product, variant_id="00000000-0000-4000-8000-000000000002", price=100, quantity=2)

    assert resolve_cart_item_price(cart_item) == 80
    assert reprice_cart_item(cart_item) is True
    assert cart_item.price == 80
    assert calculate_cart_summary([cart_item]).subtotal == 160


def test_inherited_variation_sale_uses_product_compare_at_in_cart_pricing():
    variation = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000004",
        title="Red", color_hex="#ff0000", price=None, sale_price=90,
        inherits_price=True, inherits_sale_price=False, is_active=True, size_stocks=[],
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    product = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000005", base_price=80,
        compare_at_price=100, total_stock=10, made_to_order=False,
        variants=[], variations=[variation],
    )
    cart_item = SimpleNamespace(product=product, variant_id=variation.id, price=80, quantity=1)

    assert resolve_cart_item_price(cart_item) == 90
    assert reprice_cart_item(cart_item) is True
    assert cart_item.price == 90


def test_legacy_variant_price_is_preserved_for_null_marker_variation():
    variation = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000002",
        title="M", type="size", color_hex=None, price=None, sale_price=None,
        inherits_price=None, inherits_sale_price=None, is_active=True, size_stocks=[],
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    product = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000001", base_price=100,
        total_stock=10, made_to_order=False, variations=[variation],
        variants=[SimpleNamespace(
            id="00000000-0000-4000-8000-000000000003",
            product_id="00000000-0000-4000-8000-000000000001",
            size="M", color=None, color_hex=None, price=75,
            compare_at_price=None, stock=2, sku=None, is_available=True,
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        )],
    )
    cart_item = SimpleNamespace(
        product=product,
        variant_id="00000000-0000-4000-8000-000000000003",
        price=75, quantity=1,
    )

    assert resolve_cart_item_price(cart_item) == 75


def test_size_stock_cart_variant_inherits_sole_color_hex():
    now = datetime.now(timezone.utc)
    color = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000010",
        title="Black", type="color", color_hex="#000000", price=None,
        sale_price=None, is_active=True, size_stocks=[], created_at=now, updated_at=now,
    )
    size_stock = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000012", size="M", stock=1,
    )
    size = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000011",
        title="M", type="size", color_hex=None, price=None, sale_price=None,
        is_active=True, size_stocks=[size_stock], created_at=now, updated_at=now,
    )
    product = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000001", base_price=100, compare_at_price=None,
        variants=[], variations=[color, size],
    )

    response = resolve_variant_response(product, size_stock.id)

    assert response.color == "Black"
    assert response.color_hex == "#000000"


def test_coupon_subtotal_uses_current_variation_price():
    variation = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000002",
        title="Red",
        color_hex="#ff0000",
        price=100,
        sale_price=80,
        is_active=True,
        size_stocks=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    product = SimpleNamespace(
        id="00000000-0000-4000-8000-000000000001",
        base_price=100,
        compare_at_price=None,
        total_stock=10,
        made_to_order=False,
        variants=[],
        variations=[variation],
    )
    cart_item = SimpleNamespace(product=product, variant_id="00000000-0000-4000-8000-000000000002", price=100, quantity=1)

    assert calculate_cart_subtotal([cart_item]) == 80


@pytest.mark.asyncio
async def test_add_to_cart_rejects_product_from_deactivated_vendor(
    client: AsyncClient,
    admin_user,
    sample_product,
    vendor_user,
):
    deactivate = await client.put(
        f"/api/v1/admin/users/{vendor_user['user'].id}/status?is_active=false",
        headers=admin_user["headers"],
    )
    assert deactivate.status_code == 200

    response = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": str(sample_product.id),
            "variant_id": f"default-{sample_product.id}",
            "quantity": 1,
        },
        headers={"X-Session-ID": "deactivated-vendor-session"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("moderation_status", ["pending", "rejected"])
async def test_add_to_cart_rejects_unapproved_product(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_product,
    moderation_status: str,
):
    """Customer cart access must require product moderation approval."""
    from app.models.product import ModerationStatus

    sample_product.moderation_status = ModerationStatus(moderation_status)
    await db_session.commit()

    response = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": str(sample_product.id),
            "variant_id": f"default-{sample_product.id}",
            "quantity": 1,
        },
        headers={"X-Session-ID": f"unapproved-{moderation_status}-session"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_apply_coupon_rejects_carted_product_after_moderation_revoke(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_product,
):
    session_headers = {"X-Session-ID": "coupon-hidden-product-session"}
    added = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": str(sample_product.id),
            "variant_id": f"default-{sample_product.id}",
            "quantity": 1,
        },
        headers=session_headers,
    )
    assert added.status_code == 200

    from app.models.product import ModerationStatus

    sample_product.moderation_status = ModerationStatus.PENDING
    await db_session.commit()

    response = await client.post(
        "/api/v1/cart/apply-coupon",
        json={"code": "ANY-CODE"},
        headers=session_headers,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Cart is empty"


@pytest.mark.asyncio
async def test_quantity_update_rejects_cart_item_after_vendor_deactivation(
    client: AsyncClient,
    admin_user,
    sample_product,
    vendor_user,
):
    session_headers = {"X-Session-ID": "stale-deactivated-vendor-cart"}
    added = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": str(sample_product.id),
            "variant_id": f"default-{sample_product.id}",
            "quantity": 1,
        },
        headers=session_headers,
    )
    assert added.status_code == 200

    deactivate = await client.put(
        f"/api/v1/admin/users/{vendor_user['user'].id}/status?is_active=false",
        headers=admin_user["headers"],
    )
    assert deactivate.status_code == 200

    stale_cart = await client.get("/api/v1/cart", headers=session_headers)
    assert stale_cart.status_code == 200
    assert stale_cart.json()["items"] == []

    update = await client.patch(
        f"/api/v1/cart/items/{added.json()['id']}",
        json={"quantity": 2},
        headers=session_headers,
    )
    assert update.status_code == 404


@pytest.mark.asyncio
async def test_add_to_cart_with_collection_eager_load(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    """Ensure add-to-cart works when product has a collection attached."""
    from app.models.collection import Collection
    from app.models.product import Product, ProductStatus, ModerationStatus
    import uuid

    collection = Collection(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        name="Test Collection",
        slug="test-collection",
        description="Test collection",
        is_active=True,
    )
    db_session.add(collection)
    await db_session.flush()

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Cart Collection Product",
        description="Product attached to collection",
        base_price=150.00,
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
        collection_id=collection.id,
    )
    db_session.add(product)
    await db_session.commit()

    response = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": str(product.id),
            "variant_id": f"default-{product.id}",
            "quantity": 1,
        },
        headers={"X-Session-ID": "test-session"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["product"]["collection_name"] == collection.name


@pytest.mark.asyncio
async def test_remove_cart_item_with_composite_id(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    """Allow deleting cart items using productId_variantId composite IDs."""
    from app.models.product import Product, ProductStatus, ModerationStatus
    import uuid

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Composite Delete Product",
        description="Test product without variants",
        base_price=120.00,
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.commit()

    add_response = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": str(product.id),
            "variant_id": f"default-{product.id}",
            "quantity": 1,
        },
        headers={"X-Session-ID": "composite-session"},
    )
    assert add_response.status_code == 200

    composite_id = f"{product.id}_default-{product.id}"
    remove_response = await client.delete(
        f"/api/v1/cart/items/{composite_id}",
        headers={"X-Session-ID": "composite-session"},
    )

    assert remove_response.status_code == 200


@pytest.mark.asyncio
async def test_add_to_cart_succeeds_after_single_product_stock_update(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    """Single-product legacy variant stock should become purchasable after vendor stock update."""
    from app.models.product import Product, ProductVariant, ProductStatus, ModerationStatus, ProductType
    import uuid

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Updated Stock Product",
        description="Legacy single product",
        base_price=95.00,
        total_stock=0,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
        product_type=ProductType.SINGLE,
    )
    db_session.add(product)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=product.id,
        size=None,
        color=None,
        inherits_stock=True,
        price=95.00,
        stock=0,
        is_available=False,
    )
    db_session.add(variant)
    await db_session.commit()

    update_response = await client.put(
        f"/api/v1/products/{product.id}",
        json={"total_stock": 5},
        headers=vendor_user["headers"],
    )
    assert update_response.status_code == 200

    response = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": str(product.id),
            "variant_id": str(variant.id),
            "quantity": 1,
        },
        headers={"X-Session-ID": "updated-stock-session"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["variant"]["stock"] == 5
    assert data["quantity"] == 1


@pytest.mark.asyncio
async def test_add_to_cart_blocks_zero_stock_product(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    """Zero-stock products should remain blocked from cart."""
    from app.models.product import Product, ProductVariant, ProductStatus, ModerationStatus, ProductType
    import uuid

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Zero Stock Product",
        description="Still unavailable",
        base_price=55.00,
        total_stock=0,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
        product_type=ProductType.SINGLE,
    )
    db_session.add(product)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=product.id,
        size="M",
        price=55.00,
        stock=0,
        is_available=False,
    )
    db_session.add(variant)
    await db_session.commit()

    response = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": str(product.id),
            "variant_id": str(variant.id),
            "quantity": 1,
        },
        headers={"X-Session-ID": "zero-stock-session"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Product is out of stock"


@pytest.mark.asyncio
async def test_add_to_cart_respects_existing_variant_stock_limits(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
):
    """Legacy variant-specific stock validation should keep working."""
    from app.models.product import Product, ProductVariant, ProductStatus, ModerationStatus, ProductType
    import uuid

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Variant Stock Product",
        description="Variant stock validation",
        base_price=110.00,
        total_stock=99,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
        product_type=ProductType.VARIABLE,
    )
    db_session.add(product)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=product.id,
        size="L",
        price=110.00,
        stock=2,
        is_available=True,
    )
    db_session.add(variant)
    await db_session.commit()

    response = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": str(product.id),
            "variant_id": str(variant.id),
            "quantity": 3,
        },
        headers={"X-Session-ID": "variant-stock-session"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Insufficient stock. Available: 2"


@pytest.mark.asyncio
async def test_validate_cart_and_get_cart_flag_zero_stock_and_active_payment_reservations(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
    monkeypatch,
):
    from datetime import timedelta
    from decimal import Decimal
    from sqlalchemy import select, text
    from app.core.config import settings
    from app.models.address import Address
    from app.models.order import Order
    from app.models.product import ModerationStatus, Product, ProductStatus, ProductType, ProductVariant
    from app.models.shipping_rate import ShippingRate
    from app.models.stock_payment_persistence import (
        PaymentAttempt,
        PaymentAttemptReservation,
        StockReservation,
    )
    import uuid

    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED", True)
    monkeypatch.setattr(settings, "DOMESTIC_CHECKOUT_COHORT_PERCENTAGE", 100)

    address = Address(
        id=uuid.uuid4(),
        user_id=customer_user["user"].id,
        full_name="Other Customer",
        phone_number="08012345678",
        address_line1="1 Test Street",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
    )
    rate = ShippingRate(
        id=uuid.uuid4(),
        name="Standard",
        description="3-5 days",
        base_rate=Decimal("1500.00"),
        country="Nigeria",
        state="Lagos",
        min_delivery_days=3,
        max_delivery_days=5,
        is_active=True,
        is_default=True,
        priority=0,
    )
    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Kester Club Item",
        description="Single stock reservation test",
        base_price=Decimal("45000.00"),
        total_stock=1,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
        product_type=ProductType.SINGLE,
    )
    db_session.add_all([address, rate, product])
    await db_session.flush()

    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=product.id,
        size="M",
        price=Decimal("45000.00"),
        stock=1,
        is_available=True,
    )
    db_session.add(variant)
    product_id = str(product.id)
    variant_id = str(variant.id)
    address_id = str(address.id)
    await db_session.commit()

    session_headers = {"X-Session-ID": "validate-reservation-session"}
    added = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": product_id,
            "variant_id": variant_id,
            "quantity": 1,
        },
        headers=session_headers,
    )
    assert added.status_code == 200

    # Create a competing order, estimate, and reservation via the real checkout endpoints
    created = await client.post(
        "/api/v1/orders",
        headers=customer_user["headers"],
        json={
            "items": [
                {
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "quantity": 1,
                }
            ],
            "shipping_address_id": address_id,
            "currency": "NGN",
        },
    )
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]
    estimate_res = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates",
        headers={**customer_user["headers"], "X-Idempotency-Key": "cart-val-est"},
    )
    assert estimate_res.status_code == 201, estimate_res.text
    estimate_json = estimate_res.json()
    select_res = await client.post(
        f"/api/v1/orders/{order_id}/checkout-estimates/{estimate_json['id']}"
        f"/options/{estimate_json['options'][0]['id']}/select",
        headers={**customer_user["headers"], "X-Idempotency-Key": "cart-val-sel"},
    )
    assert select_res.status_code == 200, select_res.text

    # Before payment initialization, the reservation is unattempted (reclaimable), so cart remains valid
    unattempted_validate = await client.post(
        "/api/v1/cart/validate",
        json={
            "items": [
                {
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "quantity": 1,
                }
            ]
        },
    )
    assert unattempted_validate.status_code == 200
    assert unattempted_validate.json()["is_valid"] is True

    # Once a PaymentAttempt is active, the reservation is non-reclaimable (blocking)
    db_session.expire_all()
    order = await db_session.get(Order, uuid.UUID(order_id))
    reservation = await db_session.scalar(
        select(StockReservation).where(StockReservation.order_id == order.id)
    )
    now = await db_session.scalar(select(text("clock_timestamp()")))
    txid = await db_session.scalar(select(text("txid_current()")))
    attempt = PaymentAttempt(
        id=uuid.uuid4(),
        order_id=order.id,
        customer_id=order.customer_id,
        workflow_cohort="domestic_checkout_v1",
        checkout_estimate_selection_id=order.checkout_estimate_selection_id,
        amount=order.total_amount,
        currency=order.currency,
        provider="paystack",
        provider_reference=f"ref-{uuid.uuid4().hex}",
        state="pending",
        payment_window_seconds=1800,
        authorization_grace_seconds=900,
        expires_at=now + timedelta(seconds=1800),
        authorization_deadline_at=now + timedelta(seconds=2700),
        claim_ttl_seconds=300,
        source_command="initialize_checkout_payment",
        idempotency_key=f"init-{order.id}",
        creation_txid=txid,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(
            attempt_id=attempt.id,
            reservation_id=reservation.id,
            membership_family="domestic_checkout_v1",
            order_id=order.id,
            order_item_id=reservation.order_item_id,
            checkout_estimate_selection_id=order.checkout_estimate_selection_id,
            creation_txid=txid,
        )
    )
    await db_session.commit()

    # Cart validate & GET /cart now report the item as out of stock
    validate_res = await client.post(
        "/api/v1/cart/validate",
        json={
            "items": [
                {
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "quantity": 1,
                }
            ]
        },
    )
    assert validate_res.status_code == 200, validate_res.text
    validate_body = validate_res.json()
    assert validate_body["is_valid"] is False
    assert validate_body["items"][0]["is_in_stock"] is False
    assert validate_body["items"][0]["available_stock"] == 0
    assert validate_body["items"][0]["status"] == "out_of_stock"

    cart_res = await client.get("/api/v1/cart", headers=session_headers)
    assert cart_res.status_code == 200, cart_res.text
    cart_item = cart_res.json()["items"][0]
    assert cart_item["is_in_stock"] is False
    assert cart_item["available_stock"] == 0
    assert "out of stock" in cart_item["stock_issue"].lower()

    # Storefront product detail reflects effective available stock (0) while held
    product_res = await client.get(f"/api/v1/products/{product_id}")
    assert product_res.status_code == 200, product_res.text
    product_body = product_res.json()
    assert product_body["total_stock"] == 0
    assert product_body["variants"][0]["stock"] == 0
    assert product_body["variants"][0]["is_available"] is False

    # Storefront product list also reflects effective available stock (0) while held
    list_res = await client.get("/api/v1/products", params={"search": "Kester Club Item"})
    assert list_res.status_code == 200, list_res.text
    listed_items = list_res.json()["products"]
    assert len(listed_items) == 1
    assert listed_items[0]["total_stock"] == 0
    assert listed_items[0]["variants"][0]["stock"] == 0
    assert listed_items[0]["variants"][0]["is_available"] is False

    # Adding another shopper's cart item against the locked stock is rejected
    second_add = await client.post(
        "/api/v1/cart/items",
        json={
            "product_id": product_id,
            "variant_id": variant_id,
            "quantity": 1,
        },
        headers={"X-Session-ID": "other-shopper-session"},
    )
    assert second_add.status_code == 400
    assert second_add.json()["detail"] == "Product is out of stock"


@pytest.mark.asyncio
async def test_create_order_rejects_unavailable_variant_and_duplicate_overstock_lines(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    customer_user,
):
    from decimal import Decimal
    from app.models.address import Address
    from app.models.product import ModerationStatus, Product, ProductStatus, ProductType, ProductVariant
    from app.models.shipping_rate import ShippingRate
    import uuid

    address = Address(
        id=uuid.uuid4(),
        user_id=customer_user["user"].id,
        full_name="Order Customer",
        phone_number="08012345678",
        address_line1="1 Safe Street",
        city="Lagos",
        state="Lagos",
        country="Nigeria",
    )
    rate = ShippingRate(
        id=uuid.uuid4(),
        name="Standard",
        description="3-5 days",
        base_rate=Decimal("1500.00"),
        country="Nigeria",
        state="Lagos",
        min_delivery_days=3,
        max_delivery_days=5,
        is_active=True,
        is_default=True,
        priority=0,
    )
    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Unavailable Variant Dress",
        description="Variant availability test",
        base_price=Decimal("30000.00"),
        total_stock=1,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
        product_type=ProductType.VARIABLE,
    )
    db_session.add_all([address, rate, product])
    await db_session.flush()

    unavailable_variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=product.id,
        size="S",
        price=Decimal("30000.00"),
        stock=2,
        is_available=False,
    )
    one_left_variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=product.id,
        size="M",
        price=Decimal("30000.00"),
        stock=1,
        is_available=True,
    )
    db_session.add_all([unavailable_variant, one_left_variant])
    await db_session.commit()

    resp_unavailable = await client.post(
        "/api/v1/orders",
        headers=customer_user["headers"],
        json={
            "items": [
                {
                    "product_id": str(product.id),
                    "variant_id": str(unavailable_variant.id),
                    "quantity": 1,
                }
            ],
            "shipping_address_id": str(address.id),
            "shipping_rate_id": str(rate.id),
            "currency": "NGN",
        },
    )
    assert resp_unavailable.status_code == 400
    assert "insufficient stock" in resp_unavailable.json()["detail"].lower()

    resp_duplicate = await client.post(
        "/api/v1/orders",
        headers=customer_user["headers"],
        json={
            "items": [
                {
                    "product_id": str(product.id),
                    "variant_id": str(one_left_variant.id),
                    "quantity": 1,
                },
                {
                    "product_id": str(product.id),
                    "variant_id": str(one_left_variant.id),
                    "quantity": 1,
                },
            ],
            "shipping_address_id": str(address.id),
            "shipping_rate_id": str(rate.id),
            "currency": "NGN",
        },
    )
    assert resp_duplicate.status_code == 400
    assert "insufficient stock" in resp_duplicate.json()["detail"].lower()
