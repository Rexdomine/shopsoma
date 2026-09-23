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
async def test_admin_product_detail_serializes_legacy_variants_with_product_contract(
    client: AsyncClient,
    admin_user,
    vendor_user,
    db_session: AsyncSession,
):
    from app.models.product import Product, ProductStatus, ModerationStatus, ProductVariant

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"]["id"] if isinstance(vendor_user["vendor"], dict) else vendor_user["vendor"].id,
        title="Legacy Variant Product",
        description="Product with a legacy variant",
        base_price=100.00,
        compare_at_price=125.00,
        currency="USD",
        total_stock=2,
        status=ProductStatus.DRAFT,
        moderation_status=ModerationStatus.PENDING,
        moderation_notes="Needs review",
    )
    variant = ProductVariant(product=product, size="M", color="Black", price=90.00, stock=2, is_available=True)
    db_session.add_all([product, variant])
    await db_session.commit()
    response = await client.get(f"/api/v1/admin/products/{product.id}", headers=admin_user["headers"])
    assert response.status_code == 200
    payload = response.json()
    assert payload["category_id"] is None
    assert payload["moderation_notes"] == "Needs review"
    assert payload["vendor_name"] == vendor_user["vendor"].business_name
    assert payload["currency"] == "USD"
    assert payload["variants"][0]["is_available"] is True
    assert payload["variants"][0]["price"] == "90.00"
    assert payload["variations"] == []
    assert payload["images"] == []


@pytest.mark.asyncio
async def test_admin_product_edit_is_allowlisted_and_reads_back(
    client: AsyncClient,
    admin_user,
    sample_product,
):
    response = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        json={
            "title": "Updated Admin Product",
            "description": "Updated description",
            "category_id": None,
            "base_price": 120,
            "compare_at_price": None,
            "total_stock": 7,
            "status": "draft",
            "is_featured": True,
        },
        headers=admin_user["headers"],
    )
    assert response.status_code == 200
    assert response.json()["product_id"] == str(sample_product.id)

    read_back = await client.get(
        f"/api/v1/admin/products/{sample_product.id}",
        headers=admin_user["headers"],
    )
    assert read_back.status_code == 200
    payload = read_back.json()
    assert payload["title"] == "Updated Admin Product"
    assert payload["base_price"] == "120.00"
    assert payload["compare_at_price"] is None
    assert payload["moderation_status"] == "approved"
    assert payload["total_stock"] == 7


@pytest.mark.asyncio
async def test_admin_product_edit_rejects_protected_and_invalid_fields(
    client: AsyncClient,
    admin_user,
    sample_product,
):
    protected = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        json={"vendor_id": str(sample_product.vendor_id)},
        headers=admin_user["headers"],
    )
    assert protected.status_code == 422

    invalid_price = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        json={"base_price": 200, "compare_at_price": 100},
        headers=admin_user["headers"],
    )
    assert invalid_price.status_code == 422

    fabricated_inventory = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        json={"inventory_quantity": 99},
        headers=admin_user["headers"],
    )
    assert fabricated_inventory.status_code == 422


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
