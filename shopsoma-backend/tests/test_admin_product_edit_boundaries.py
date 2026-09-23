"""Admin view/edit authorization and atomic validation regressions."""
import uuid

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["title", "base_price", "total_stock", "status", "is_featured"])
async def test_null_required_edit_fields_are_rejected(client, admin_user, sample_product, field):
    url = f"/api/v1/admin/products/{sample_product.id}"
    before = (await client.get(url, headers=admin_user["headers"])).json()
    response = await client.put(url, headers=admin_user["headers"], json={field: None})
    assert response.status_code == 422
    after = (await client.get(url, headers=admin_user["headers"])).json()
    assert after == before


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["anonymous", "vendor", "customer"])
async def test_non_admin_cannot_view_or_edit_private_product(
    client, vendor_user, sample_product, db_session, role,
):
    from app.core.security import create_access_token
    from app.models.user import User, UserRole

    headers = {}
    if role == "vendor":
        headers = vendor_user["headers"]
    elif role == "customer":
        customer = User(
            id=uuid.uuid4(), email="admin-boundary@example.test",
            full_name="Test Customer", role=UserRole.CUSTOMER,
            email_verified=True, is_active=True,
        )
        db_session.add(customer)
        await db_session.commit()
        token = create_access_token(data={"sub": str(customer.id)})
        headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/admin/products/{sample_product.id}"
    for response in (
        await client.get(url, headers=headers),
        await client.put(url, headers=headers, json={"title": "Unauthorized edit"}),
    ):
        assert response.status_code in (401, 403)
    await db_session.refresh(sample_product)
    assert sample_product.title != "Unauthorized edit"


@pytest.mark.asyncio
@pytest.mark.parametrize("moderation", ["pending", "rejected"])
async def test_admin_can_inspect_hidden_products_without_making_them_public(
    client, admin_user, sample_product, db_session, moderation,
):
    from app.models.product import ModerationStatus, ProductStatus

    sample_product.status = ProductStatus.DRAFT
    sample_product.moderation_status = ModerationStatus(moderation)
    await db_session.commit()
    assert (await client.get(f"/api/v1/products/{sample_product.id}")).status_code == 404
    url = f"/api/v1/admin/products/{sample_product.id}"
    response = await client.get(url, headers=admin_user["headers"])
    assert response.status_code == 200
    assert response.json()["moderation_status"] == moderation
    saved = await client.put(url, headers=admin_user["headers"], json={"title": "Admin corrected title"})
    assert saved.status_code == 200
    after = (await client.get(url, headers=admin_user["headers"])).json()
    assert after["moderation_status"] == moderation
    assert after["status"] == "draft"
    assert (await client.get(f"/api/v1/products/{sample_product.id}")).status_code == 404


@pytest.mark.asyncio
async def test_missing_admin_product_returns_404(client, admin_user):
    url = f"/api/v1/admin/products/{uuid.uuid4()}"
    assert (await client.get(url, headers=admin_user["headers"])).status_code == 404
    assert (await client.put(url, headers=admin_user["headers"], json={"title": "Missing product"})).status_code == 404


@pytest.mark.asyncio
async def test_admin_edit_cannot_change_moderation_status_outside_approval_workflow(
    client, admin_user, sample_product, db_session
):
    before = sample_product.moderation_status
    response = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        headers=admin_user["headers"],
        json={"moderation_status": "approved"},
    )
    assert response.status_code == 422
    await db_session.refresh(sample_product)
    assert sample_product.moderation_status == before
    assert sample_product.moderated_at is None
    assert sample_product.moderated_by is None


@pytest.mark.asyncio
async def test_admin_total_stock_edit_syncs_legacy_single_product_variant(
    client, admin_user, sample_product, db_session
):
    from app.models.product import ProductVariant

    variant = ProductVariant(
        product_id=sample_product.id,
        price=sample_product.base_price,
        stock=sample_product.total_stock,
        is_available=True,
    )
    db_session.add(variant)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        headers=admin_user["headers"],
        json={"total_stock": 0},
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(variant)
    assert variant.stock == 0
    assert variant.is_available is False


@pytest.mark.asyncio
async def test_admin_price_edit_syncs_inherited_variation_and_legacy_variant(
    client, admin_user, sample_product, db_session
):
    from app.models.product import Variation, ProductVariant

    sample_product.compare_at_price = 149.99
    await db_session.flush()
    variation = Variation(
        product_id=sample_product.id,
        title="Red",
        type="color",
        price=149.99,
        sale_price=99.99,
        inherits_price=True,
        inherits_sale_price=True,
    )
    variant = ProductVariant(
        product_id=sample_product.id,
        color="red",
        price=149.99,
        stock=sample_product.total_stock,
        is_available=True,
    )
    db_session.add_all([variation, variant])
    await db_session.commit()

    response = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        headers=admin_user["headers"],
        json={"base_price": 12000, "compare_at_price": 15000},
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(variation)
    await db_session.refresh(variant)
    assert variation.price == 15000
    assert variation.sale_price == 12000
    assert variant.price == 12000


@pytest.mark.asyncio
async def test_admin_price_edit_syncs_generic_legacy_variant_without_variation(
    client, admin_user, sample_product, db_session
):
    from app.models.product import ProductVariant

    variant = ProductVariant(
        product_id=sample_product.id,
        price=sample_product.base_price,
        stock=sample_product.total_stock,
        is_available=True,
    )
    db_session.add(variant)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        headers=admin_user["headers"],
        json={"base_price": 12000, "compare_at_price": 15000},
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(variant)
    assert variant.price == 12000
    assert variant.compare_at_price == 15000


@pytest.mark.asyncio
async def test_admin_can_read_legacy_product_with_short_title(
    client, admin_user, sample_product, db_session
):
    sample_product.title = "X"
    await db_session.commit()

    response = await client.get(
        f"/api/v1/admin/products/{sample_product.id}",
        headers=admin_user["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "X"


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["base_price", "compare_at_price"])
async def test_admin_price_edit_rejects_shared_product_ceiling(
    client, admin_user, sample_product, field
):
    response = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        headers=admin_user["headers"],
        json={field: 1000000},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_generic_edit_cannot_change_featured_status(
    client, admin_user, sample_product, db_session
):
    response = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        headers=admin_user["headers"],
        json={"is_featured": True},
    )
    assert response.status_code == 422
    await db_session.refresh(sample_product)
    assert sample_product.is_featured is False
