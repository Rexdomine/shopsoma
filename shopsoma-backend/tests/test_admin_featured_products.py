import pytest
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
    import uuid

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
