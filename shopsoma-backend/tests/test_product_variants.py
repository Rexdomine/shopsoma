from decimal import Decimal
import uuid

from app.models.product import (
    Product,
    ProductStatus,
    ModerationStatus,
    ProductVariant,
    Variation,
    SizeStock,
    SizeEnum,
)


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


async def test_admin_create_and_get_variants(
    client,
    db_session,
    admin_user,
    sample_product,
):
    # Admin creates variant
    create_res = await client.post(
        f"/api/v1/admin/products/{sample_product.id}/variants",
        json={
            "size": "L",
            "stock": 8,
            "price": "75.00",
            "is_available": True,
        },
        headers=admin_user["headers"],
    )
    assert create_res.status_code == 201, create_res.text
    create_data = create_res.json()
    variant_id = create_data["variant_id"]

    # Admin gets variants
    get_res = await client.get(
        f"/api/v1/admin/products/{sample_product.id}/variants",
        headers=admin_user["headers"],
    )
    assert get_res.status_code == 200, get_res.text
    get_data = get_res.json()
    assert any(v["id"] == variant_id and v["size"] == "L" and v["stock"] == 8 for v in get_data["variants"])

    # Admin updates variant
    update_res = await client.put(
        f"/api/v1/admin/products/{sample_product.id}/variants/{variant_id}",
        json={"size": "XL", "stock": 12, "price": "80.00"},
        headers=admin_user["headers"],
    )
    assert update_res.status_code == 200, update_res.text

    # Admin deletes variant
    delete_res = await client.delete(
        f"/api/v1/admin/products/{sample_product.id}/variants/{variant_id}",
        headers=admin_user["headers"],
    )
    assert delete_res.status_code == 200, delete_res.text


async def test_admin_and_vendor_size_stock_fallback(
    client,
    db_session,
    admin_user,
    vendor_user,
    sample_product,
):
    variation = Variation(
        id=uuid.uuid4(),
        product_id=sample_product.id,
        title="Standard",
        type="size",
        price=sample_product.base_price,
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
    await db_session.commit()

    # Admin GET variants synthesizes the SizeStock
    admin_get = await client.get(
        f"/api/v1/admin/products/{sample_product.id}/variants",
        headers=admin_user["headers"],
    )
    assert admin_get.status_code == 200, admin_get.text
    admin_variants = admin_get.json()["variants"]
    assert any(v["id"] == str(size_stock.id) and v["size"] == "M" for v in admin_variants)

    # Vendor updates the SizeStock variant
    vendor_update = await client.put(
        f"/api/v1/products/{sample_product.id}/variants/{size_stock.id}",
        json={"stock": 10},
        headers=vendor_user["headers"],
    )
    assert vendor_update.status_code == 200, vendor_update.text
    assert vendor_update.json()["stock"] == 10

    # Admin updates the SizeStock variant
    admin_update = await client.put(
        f"/api/v1/admin/products/{sample_product.id}/variants/{size_stock.id}",
        json={"stock": 15},
        headers=admin_user["headers"],
    )
    assert admin_update.status_code == 200, admin_update.text

    # Vendor deletes the SizeStock variant
    vendor_delete = await client.delete(
        f"/api/v1/products/{sample_product.id}/variants/{size_stock.id}",
        headers=vendor_user["headers"],
    )
    assert vendor_delete.status_code == 204, vendor_delete.text


async def test_create_variant_duplicate_size_rejected(
    client,
    db_session,
    admin_user,
    vendor_user,
    sample_product,
):
    # Vendor creates a size variant
    first_res = await client.post(
        f"/api/v1/products/{sample_product.id}/variants",
        json={"size": "S", "stock": 5, "price": "50.00"},
        headers=vendor_user["headers"],
    )
    assert first_res.status_code == 201, first_res.text

    # Duplicate size for vendor should be rejected
    dup_vendor = await client.post(
        f"/api/v1/products/{sample_product.id}/variants",
        json={"size": "S", "stock": 10, "price": "50.00"},
        headers=vendor_user["headers"],
    )
    assert dup_vendor.status_code == 400, dup_vendor.text

    # Duplicate size for admin should be rejected
    dup_admin = await client.post(
        f"/api/v1/admin/products/{sample_product.id}/variants",
        json={"size": "s", "stock": 10, "price": "50.00"},
        headers=admin_user["headers"],
    )
    assert dup_admin.status_code == 400, dup_admin.text

