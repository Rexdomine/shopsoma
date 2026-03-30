import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_admin_can_toggle_featured_product(
    client: AsyncClient,
    admin_user,
    sample_product,
    db_session: AsyncSession,
):
    response = await client.put(
        f"/api/v1/admin/products/{sample_product.id}/feature",
        json={"is_featured": True},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["is_featured"] is True

    await db_session.refresh(sample_product)
    assert sample_product.is_featured is True


@pytest.mark.asyncio
async def test_admin_cannot_feature_unapproved_product(
    client: AsyncClient,
    admin_user,
    vendor_user,
    db_session: AsyncSession,
):
    from app.models.product import Product, ProductStatus, ModerationStatus

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Pending Product",
        description="Pending product description",
        base_price=45.00,
        total_stock=12,
        status=ProductStatus.DRAFT,
        moderation_status=ModerationStatus.PENDING,
    )
    db_session.add(product)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/admin/products/{product.id}/feature",
        json={"is_featured": True},
        headers=admin_user["headers"],
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_product_responses_include_currency(
    client: AsyncClient,
    admin_user,
    vendor_user,
    db_session: AsyncSession,
):
    from app.models.product import Product, ProductStatus, ModerationStatus

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="USD Product",
        description="USD product description",
        base_price=300.00,
        compare_at_price=350.00,
        currency="USD",
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.commit()

    list_response = await client.get(
        "/api/v1/admin/products",
        headers=admin_user["headers"],
    )

    assert list_response.status_code == 200
    list_payload = list_response.json()
    list_item = next(item for item in list_payload["items"] if item["id"] == str(product.id))
    assert list_item["currency"] == "USD"

    detail_response = await client.get(
        f"/api/v1/admin/products/{product.id}",
        headers=admin_user["headers"],
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["currency"] == "USD"


@pytest.mark.asyncio
async def test_admin_product_responses_include_made_to_order_fields(
    client: AsyncClient,
    admin_user,
    vendor_user,
    db_session: AsyncSession,
):
    from app.models.product import Product, ProductStatus, ModerationStatus

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Made To Order Product",
        description="MTO description",
        base_price=500.00,
        currency="USD",
        total_stock=0,
        made_to_order=True,
        made_to_order_timeline="5-7 business days",
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.commit()

    list_response = await client.get(
        "/api/v1/admin/products",
        headers=admin_user["headers"],
    )

    assert list_response.status_code == 200
    list_payload = list_response.json()
    list_item = next(item for item in list_payload["items"] if item["id"] == str(product.id))
    assert list_item["made_to_order"] is True
    assert list_item["made_to_order_timeline"] == "5-7 business days"

    detail_response = await client.get(
        f"/api/v1/admin/products/{product.id}",
        headers=admin_user["headers"],
    )

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["made_to_order"] is True
    assert detail_payload["made_to_order_timeline"] == "5-7 business days"
