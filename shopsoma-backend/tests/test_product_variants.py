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


async def test_update_variant_price_updates_inherited_matching_variation(
    client,
    db_session,
    vendor_user,
    sample_product,
):
    from app.models.product import Variation

    variation = Variation(
        product_id=sample_product.id,
        title="Red",
        type="color",
        price=sample_product.base_price,
        sale_price=sample_product.compare_at_price,
        inherits_price=True,
        inherits_sale_price=True,
    )
    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=sample_product.id,
        color="red",
        price=sample_product.base_price,
        inherits_price=True,
    )
    db_session.add_all([variation, variant])
    await db_session.commit()

    response = await client.put(
        f"/api/v1/products/{sample_product.id}/variants/{variant.id}",
        json={"price": "88.00"},
        headers=vendor_user["headers"],
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(variant)
    await db_session.refresh(variation)
    assert variant.price == 88
    assert variant.inherits_price is False
    assert variation.price == 88
    assert variation.sale_price is None
    assert variation.inherits_price is False
    assert variation.inherits_sale_price is False


async def test_update_variant_price_and_color_match_submitted_axis(
    client,
    db_session,
    vendor_user,
    sample_product,
):
    from app.models.product import Variation

    old_variation = Variation(
        product_id=sample_product.id,
        title="Red",
        type="color",
        price=sample_product.base_price,
        inherits_price=True,
        inherits_sale_price=True,
    )
    new_variation = Variation(
        product_id=sample_product.id,
        title="Blue",
        type="color",
        price=sample_product.base_price,
        inherits_price=True,
        inherits_sale_price=True,
    )
    variant = ProductVariant(
        id=uuid.uuid4(),
        product_id=sample_product.id,
        color="red",
        price=sample_product.base_price,
        inherits_price=True,
    )
    db_session.add_all([old_variation, new_variation, variant])
    await db_session.commit()

    response = await client.put(
        f"/api/v1/products/{sample_product.id}/variants/{variant.id}",
        json={"price": "88.00", "color": "blue"},
        headers=vendor_user["headers"],
    )

    assert response.status_code == 200, response.text
    await db_session.refresh(variant)
    await db_session.refresh(old_variation)
    await db_session.refresh(new_variation)
    assert variant.color == "blue"
    assert old_variation.inherits_price is True
    assert new_variation.price == 88
    assert new_variation.inherits_price is False
    assert new_variation.inherits_sale_price is False
