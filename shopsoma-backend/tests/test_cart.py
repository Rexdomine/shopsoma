"""
Unit tests for Cart API endpoints.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace

from app.api.v1.cart import (
    calculate_cart_subtotal,
    calculate_cart_summary,
    reprice_cart_item,
    resolve_cart_item_price,
)


def test_existing_variation_cart_row_uses_and_persists_current_sale_price():
    variation = SimpleNamespace(
        id="variation-id", price=None, sale_price=80, is_active=True, size_stocks=[]
    )
    product = SimpleNamespace(
        base_price=100,
        total_stock=10,
        made_to_order=False,
        variants=[],
        variations=[variation],
    )
    cart_item = SimpleNamespace(product=product, variant_id="variation-id", price=100, quantity=2)

    assert resolve_cart_item_price(cart_item) == 80
    assert reprice_cart_item(cart_item) is True
    assert cart_item.price == 80
    assert calculate_cart_summary([cart_item]).subtotal == 160


def test_coupon_subtotal_uses_current_variation_price():
    variation = SimpleNamespace(
        id="variation-id", price=100, sale_price=80, is_active=True, size_stocks=[]
    )
    product = SimpleNamespace(
        base_price=100,
        total_stock=10,
        made_to_order=False,
        variants=[],
        variations=[variation],
    )
    cart_item = SimpleNamespace(product=product, variant_id="variation-id", price=100, quantity=1)

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
        size="M",
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
