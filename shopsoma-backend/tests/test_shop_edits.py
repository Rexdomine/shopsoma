import uuid

import pytest

from app.models.category import Category
from app.models.product import ModerationStatus, Product, ProductStatus
from app.services.shop_edits import SHOP_EDIT_SLUGS, normalize_shop_edit_names


def test_shop_edit_relationship_is_not_eager_by_default():
    assert Product.shop_edit_categories.property.lazy == "select"


def test_shop_edit_names_are_deduplicated_and_stable():
    assert normalize_shop_edit_names(["Party", "casual", "party"]) == ["party", "casual"]


def test_shop_edit_names_reject_unknown_categories():
    try:
        normalize_shop_edit_names(["seasonal"])
    except ValueError as exc:
        assert "Unknown Shop Edit category" in str(exc)
    else:
        raise AssertionError("unknown category must be rejected")


@pytest.mark.asyncio
async def test_admin_replaces_and_removes_shop_edits_and_rejects_vendor_access(
    client, admin_user, vendor_user, sample_product, db_session
):
    root = Category(id=uuid.uuid4(), name="Shop Edits", slug="shop-edits")
    categories = [
        Category(id=uuid.uuid4(), name=name.title(), slug=slug, parent_id=root.id)
        for name, slug in SHOP_EDIT_SLUGS.items()
    ]
    db_session.add_all([root, *categories])
    await db_session.commit()
    product_url = f"/api/v1/admin/products/{sample_product.id}/shop-edits"

    assert (await client.get(product_url, headers=vendor_user["headers"])).status_code == 403
    assert (await client.put(product_url, json={"shop_edits": ["party"]}, headers=vendor_user["headers"])).status_code == 403
    assert (await client.put(product_url, json={"shop_edits": ["seasonal"]}, headers=admin_user["headers"])).status_code == 422

    response = await client.put(
        product_url,
        json={"shop_edits": ["Party", "casual", "party"]},
        headers=admin_user["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["shop_edits"] == ["party", "casual"]

    response = await client.get(product_url, headers=admin_user["headers"])
    assert response.status_code == 200
    assert response.json()["shop_edits"] == ["casual", "party"]

    response = await client.put(product_url, json={"shop_edits": []}, headers=admin_user["headers"])
    assert response.status_code == 200
    assert response.json()["shop_edits"] == []


@pytest.mark.asyncio
async def test_public_shop_edits_filter_is_curated_visible_and_not_duplicated(
    client, db_session, vendor_user
):
    root = Category(id=uuid.uuid4(), name="Shop Edits", slug="shop-edits")
    occasion_wear = Category(
        id=uuid.uuid4(), name="Occasion Wear", slug="shop-edits-occasion-wear", parent_id=root.id
    )
    party = Category(
        id=uuid.uuid4(), name="Party", slug=SHOP_EDIT_SLUGS["party"], parent_id=occasion_wear.id
    )
    normal_category = Category(id=uuid.uuid4(), name="Dresses", slug="dresses")
    db_session.add_all([root, occasion_wear, party, normal_category])

    def product(title, *, status=ProductStatus.ACTIVE, moderation=ModerationStatus.APPROVED):
        return Product(
            id=uuid.uuid4(), vendor_id=vendor_user["vendor"].id, title=title,
            base_price=100, total_stock=2, status=status, moderation_status=moderation,
            category_id=normal_category.id,
        )

    visible = product("Visible curated dress")
    visible.shop_edit_categories = [party]
    pending = product("Pending curated dress", moderation=ModerationStatus.PENDING)
    pending.shop_edit_categories = [party]
    inactive = product("Inactive curated dress", status=ProductStatus.INACTIVE)
    inactive.shop_edit_categories = [party]
    normal_only = product("Normal party dress")
    db_session.add_all([visible, pending, inactive, normal_only])
    await db_session.commit()

    root_response = await client.get(f"/api/v1/products?category_id={root.id}&page_size=100")
    assert root_response.status_code == 200, root_response.text
    assert [item["title"] for item in root_response.json()["products"]] == ["Visible curated dress"]

    leaf_response = await client.get(f"/api/v1/products?category_id={party.id}&page_size=100")
    assert leaf_response.status_code == 200, leaf_response.text
    assert [item["title"] for item in leaf_response.json()["products"]] == ["Visible curated dress"]


@pytest.mark.asyncio
async def test_admin_product_update_validates_shop_edits_before_committing_fields(
    client, admin_user, sample_product
):
    response = await client.put(
        f"/api/v1/admin/products/{sample_product.id}",
        json={"title": "Changed title", "shop_edits": ["not-an-edit"]},
        headers=admin_user["headers"],
    )
    assert response.status_code == 422

    product_response = await client.get(
        f"/api/v1/admin/products/{sample_product.id}", headers=admin_user["headers"]
    )
    assert product_response.status_code == 200
    assert product_response.json()["title"] == "Test Product"
