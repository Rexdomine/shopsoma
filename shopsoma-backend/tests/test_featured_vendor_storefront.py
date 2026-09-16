from app.models.category import Category
from app.models.product import ModerationStatus, Product, ProductStatus


async def test_admin_can_remove_vendor_from_featured_storefront(
    client,
    db_session,
    admin_user,
    vendor_user,
):
    vendor = vendor_user["vendor"]
    vendor.is_featured_storefront = True
    await db_session.commit()

    response = await client.put(
        f"/api/v1/admin/vendors/{vendor.id}/featured-storefront",
        json={"is_featured_storefront": False},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert response.json()["is_featured_storefront"] is False


async def test_public_featured_storefront_excludes_vendor_without_matching_active_product(
    client,
    db_session,
    vendor_user,
):
    vendor = vendor_user["vendor"]
    vendor.is_featured_storefront = True
    await db_session.commit()

    response = await client.get("/api/v1/designers/featured?category=men")

    assert response.status_code == 200
    assert str(vendor.id) not in {item["id"] for item in response.json()}


async def test_public_featured_storefront_returns_only_matching_public_vendor(
    client,
    db_session,
    vendor_user,
):
    vendor = vendor_user["vendor"]
    vendor.is_featured_storefront = True
    vendor.featured_storefront_image_url = "/uploads/vendors/featured.webp"
    category = Category(name="Men", slug="men", is_active=True)
    db_session.add(category)
    await db_session.flush()
    db_session.add(
        Product(
            vendor_id=vendor.id,
            category_id=category.id,
            title="Featured Menswear",
            base_price=100,
            total_stock=2,
            status=ProductStatus.ACTIVE,
            moderation_status=ModerationStatus.APPROVED,
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/designers/featured?category=men")

    assert response.status_code == 200
    assert response.json() == [{
        "id": str(vendor.id),
        "business_name": vendor.business_name,
        "featured_storefront_image_url": "/uploads/vendors/featured.webp",
        "product_count": 1,
    }]
