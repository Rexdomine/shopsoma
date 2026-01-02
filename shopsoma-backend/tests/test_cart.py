"""
Unit tests for Cart API endpoints.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


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
