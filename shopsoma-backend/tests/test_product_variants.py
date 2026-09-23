from decimal import Decimal
import uuid

from app.models.product import Product, ProductStatus, ModerationStatus, ProductVariant


async def test_update_variant_scopes_to_product_id(
    client,
    db_session,
    vendor_user,
    sample_product
):
    other_product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Other Product",
        description="Other product description",
        base_price=Decimal("59.99"),
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(other_product)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=sample_product.id,
        price=Decimal("99.99"),
        stock=5,
    )
    db_session.add(variant)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/products/{other_product.id}/variants/{variant.id}",
        json={"price": "120.00"},
        headers=vendor_user["headers"],
    )

    assert response.status_code == 404


async def test_delete_variant_scopes_to_product_id(
    client,
    db_session,
    vendor_user,
    sample_product
):
    other_product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Other Product",
        description="Other product description",
        base_price=Decimal("59.99"),
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(other_product)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=sample_product.id,
        price=Decimal("99.99"),
        stock=5,
    )
    db_session.add(variant)
    await db_session.commit()

    response = await client.delete(
        f"/api/v1/products/{other_product.id}/variants/{variant.id}",
        headers=vendor_user["headers"],
    )

    assert response.status_code == 404


async def test_update_variant_clears_stock_inheritance_on_explicit_inventory_edit(
    client,
    db_session,
    vendor_user,
    sample_product,
):
    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=sample_product.id,
        price=Decimal("99.99"),
        inherits_stock=True,
        stock=sample_product.total_stock,
        is_available=True,
    )
    db_session.add(variant)
    await db_session.commit()

    response = await client.put(
        f"/api/v1/products/{sample_product.id}/variants/{variant.id}",
        json={"stock": 3},
        headers=vendor_user["headers"],
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(variant)
    assert variant.stock == 3
    assert variant.inherits_stock is False
