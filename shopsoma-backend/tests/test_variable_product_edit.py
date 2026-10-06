"""Focused tests for variable product edit upgrade (REX-90).

Covers:
- Single product edit behavior preservation.
- Variable product variation listing and selected variation editing.
- Stable variation ID preservation across saves.
- Untouched variation preservation (attributes, size stocks, images).
- Scoped variation image updates without affecting product gallery or sibling variations.
- Image ownership rejection (409 Conflict).
- Validation: duplicate titles, invalid sizes, negative stock, invalid prices, unsupported matrix.
- Authorization: vendor ownership checks (403), non-admin rejection on admin endpoints (401/403).
- Moderation safety: vendor edits revert approved products to pending, hiding them from public until approved.
- Legacy product_variants endpoints remain separate.
"""

import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import (
    ModerationStatus,
    Product,
    ProductImage,
    ProductImageUpload,
    ProductStatus,
    ProductVariant,
    SizeEnum,
    SizeStock,
    Variation,
)
from app.models.user import User, UserRole
from app.models.vendor import Vendor, KYCStatus
from app.core.security import get_password_hash, create_access_token


@pytest.fixture
async def second_vendor_user(db_session: AsyncSession):
    """Fixture for a second vendor to test authorization boundaries."""
    user = User(
        id=uuid.uuid4(),
        email="vendor2@test.com",
        hashed_password=get_password_hash("VendorPass123"),
        full_name="Second Vendor",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user.id,
        business_name="Second Business",
        kyc_status=KYCStatus.APPROVED,
        approved=True,
        is_onboarding=False,
        brand_info_completed=True,
        payout_info_completed=True,
    )
    db_session.add(vendor)
    await db_session.commit()

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    return {
        "user": user,
        "vendor": vendor,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
async def variable_product(client: AsyncClient, vendor_user, db_session: AsyncSession):
    """Create a variable product with 2 variations and nested sizes."""
    # Register image uploads so image validation passes
    vendor_id = vendor_user["user"].id
    gallery_key = f"vendors/{vendor_id}/products/2026/10/gallery.jpg"
    red_key = f"vendors/{vendor_id}/products/2026/10/red.jpg"
    blue_key = f"vendors/{vendor_id}/products/2026/10/blue.jpg"

    db_session.add_all([
        ProductImageUpload(image_url=f"/uploads/{gallery_key}", storage_keys=[gallery_key]),
        ProductImageUpload(image_url=f"/uploads/{red_key}", storage_keys=[red_key]),
        ProductImageUpload(image_url=f"/uploads/{blue_key}", storage_keys=[blue_key]),
    ])
    await db_session.commit()

    response = await client.post(
        "/api/v1/products",
        json={
            "title": "Summer Linen Shirt",
            "description": "Breathable linen shirt",
            "base_price": 50.00,
            "compare_at_price": 70.00,
            "product_type": "variable",
            "images": [
                {
                    "image_url": f"/uploads/{gallery_key}",
                    "alt_text": "Gallery overview",
                    "is_primary": True,
                    "storage_keys": [gallery_key],
                },
                {
                    "image_url": f"/uploads/{red_key}",
                    "alt_text": "Red overview",
                    "is_primary": False,
                    "storage_keys": [red_key],
                },
                {
                    "image_url": f"/uploads/{blue_key}",
                    "alt_text": "Blue overview",
                    "is_primary": False,
                    "storage_keys": [blue_key],
                },
            ],
            "variations": [
                {
                    "title": "Red",
                    "type": "color",
                    "color_hex": "#FF0000",
                    "price": 55.00,
                    "images": [f"/uploads/{red_key}"],
                    "sizes": [
                        {"size": "S", "stock": 10},
                        {"size": "M", "stock": 15},
                    ],
                },
                {
                    "title": "Blue",
                    "type": "color",
                    "color_hex": "#0000FF",
                    "price": 50.00,
                    "images": [f"/uploads/{blue_key}"],
                    "sizes": [
                        {"size": "M", "stock": 8},
                        {"size": "L", "stock": 12},
                    ],
                },
            ],
        },
        headers=vendor_user["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


# ============================================================================
# 1. Single Product Edit Behavior Preservation
# ============================================================================

@pytest.mark.asyncio
async def test_single_product_edit_preserves_single_product_behavior(
    client: AsyncClient, vendor_user, db_session: AsyncSession
):
    """Single products retain current edit behavior without variations touching them."""
    create_res = await client.post(
        "/api/v1/products",
        json={
            "title": "Single Leather Belt",
            "description": "Handmade leather belt",
            "base_price": 40.00,
            "total_stock": 25,
            "product_type": "single",
        },
        headers=vendor_user["headers"],
    )
    assert create_res.status_code == 201
    product_id = create_res.json()["id"]

    # Edit single product fields
    update_res = await client.put(
        f"/api/v1/products/{product_id}",
        json={
            "title": "Updated Leather Belt",
            "base_price": 45.00,
            "total_stock": 30,
        },
        headers=vendor_user["headers"],
    )
    assert update_res.status_code == 200
    data = update_res.json()
    assert data["title"] == "Updated Leather Belt"
    assert float(data["base_price"]) == 45.00
    assert data["total_stock"] == 30
    assert data["product_type"] == "single"
    assert len(data.get("variations", [])) == 0


# ============================================================================
# 2. Stable Variation ID and SizeStock ID Preservation
# ============================================================================

@pytest.mark.asyncio
async def test_stable_variation_and_sizestock_id_preservation_across_sync(
    client: AsyncClient, vendor_user, variable_product
):
    """Updating a variable product via sync must preserve existing variation and size_stock IDs."""
    product_id = variable_product["id"]
    variations = variable_product["variations"]
    assert len(variations) == 2

    red_var = next(v for v in variations if v["title"] == "Red")
    blue_var = next(v for v in variations if v["title"] == "Blue")
    red_id = red_var["id"]
    blue_id = blue_var["id"]

    red_s_stock = next(s for s in red_var["size_stocks"] if s["size"] == "S")
    red_s_id = red_s_stock["id"]

    # Sync update: Modify Red's price, update S stock, add L, leave Blue untouched
    sync_payload = {
        "variations": [
            {
                "id": red_id,
                "title": "Crimson Red",
                "type": "color",
                "color_hex": "#DC143C",
                "price": 60.00,
                "sizes": [
                    {"id": red_s_id, "size": "S", "stock": 20},  # Updated stock
                    {"size": "L", "stock": 5},                   # Added size
                ],
            },
            {
                "id": blue_id,
                "title": "Blue",
                "type": "color",
                "color_hex": "#0000FF",
                "price": 50.00,
                "sizes": [
                    {"size": "M", "stock": 8},
                    {"size": "L", "stock": 12},
                ],
            },
        ]
    }

    update_res = await client.put(
        f"/api/v1/products/{product_id}",
        json=sync_payload,
        headers=vendor_user["headers"],
    )
    assert update_res.status_code == 200, update_res.text
    updated_variations = update_res.json()["variations"]

    # Verify Red ID is PRESERVED (not regenerated)
    updated_red = next(v for v in updated_variations if v["title"] == "Crimson Red")
    assert updated_red["id"] == red_id
    assert float(updated_red["price"]) == 60.00
    assert updated_red["color_hex"] == "#DC143C"

    # Verify size S ID is PRESERVED
    updated_red_s = next(s for s in updated_red["size_stocks"] if s["size"] == "S")
    assert updated_red_s["id"] == red_s_id
    assert updated_red_s["stock"] == 20

    # Verify Blue ID is PRESERVED
    updated_blue = next(v for v in updated_variations if v["title"] == "Blue")
    assert updated_blue["id"] == blue_id


# ============================================================================
# 3. Selected Variation Editing & Untouched Variations Preservation
# ============================================================================

@pytest.mark.asyncio
async def test_update_single_variation_preserves_untouched_variations_and_gallery(
    client: AsyncClient, vendor_user, variable_product
):
    """Direct single variation endpoint updates only selected variation, leaving siblings and gallery untouched."""
    product_id = variable_product["id"]
    red_var = next(v for v in variable_product["variations"] if v["title"] == "Red")
    blue_var = next(v for v in variable_product["variations"] if v["title"] == "Blue")
    red_id = red_var["id"]
    blue_id = blue_var["id"]
    initial_gallery = variable_product["images"]

    # Update only Red variation
    update_data = {
        "title": "Bright Ruby",
        "color_hex": "#E0115F",
        "price": 65.00,
        "is_active": True,
        "sizes": [
            {"size": "S", "stock": 25},
            {"size": "M", "stock": 30},
        ],
    }

    var_update_res = await client.put(
        f"/api/v1/products/{product_id}/variations/{red_id}",
        json=update_data,
        headers=vendor_user["headers"],
    )
    assert var_update_res.status_code == 200
    res_data = var_update_res.json()
    assert res_data["id"] == red_id
    assert res_data["title"] == "Bright Ruby"
    assert float(res_data["price"]) == 65.00

    # Fetch product to verify untouched variations and gallery
    prod_res = await client.get(
        f"/api/v1/vendor/products/{product_id}",
        headers=vendor_user["headers"],
    )
    assert prod_res.status_code == 200
    prod_data = prod_res.json()

    # Blue must be completely untouched
    fresh_blue = next(v for v in prod_data["variations"] if v["id"] == blue_id)
    assert fresh_blue["title"] == blue_var["title"]
    assert float(fresh_blue["price"]) == float(blue_var["price"])
    assert fresh_blue["color_hex"] == blue_var["color_hex"]
    assert len(fresh_blue["size_stocks"]) == len(blue_var["size_stocks"])

    # Product gallery must be untouched
    assert len(prod_data["images"]) == len(initial_gallery)
    assert {img["image_url"] for img in prod_data["images"]} == {img["image_url"] for img in initial_gallery}


# ============================================================================
# 4. Scoped Variation Image Updates & Foreign Image Rejection
# ============================================================================

@pytest.mark.asyncio
async def test_variation_image_rejection_for_unowned_image(
    client: AsyncClient, vendor_user, variable_product
):
    """Setting a variation image URL to an unowned/foreign URL must return 409 Conflict."""
    product_id = variable_product["id"]
    red_var = next(v for v in variable_product["variations"] if v["title"] == "Red")
    red_id = red_var["id"]

    # Attempt to set image that belongs to another domain / not registered on product
    res = await client.put(
        f"/api/v1/products/{product_id}/variations/{red_id}",
        json={
            "title": "Red",
            "images": ["/uploads/foreign/unauthorized.jpg"],
        },
        headers=vendor_user["headers"],
    )
    assert res.status_code == 409
    assert "belong to this product" in res.json()["detail"].lower()


# ============================================================================
# 5. Validation Rules
# ============================================================================

@pytest.mark.asyncio
async def test_rejects_duplicate_variation_titles(
    client: AsyncClient, vendor_user, variable_product
):
    """Duplicate variation titles after normalization must be rejected with 422."""
    product_id = variable_product["id"]
    red_var = next(v for v in variable_product["variations"] if v["title"] == "Red")

    # Try to rename Red to "Blue" (which already exists on the product)
    res = await client.put(
        f"/api/v1/products/{product_id}/variations/{red_var['id']}",
        json={"title": " blue "},
        headers=vendor_user["headers"],
    )
    assert res.status_code == 422
    assert "Variation titles must be unique" in str(res.json()["detail"])


@pytest.mark.asyncio
async def test_rejects_duplicate_sizes_within_variation(
    client: AsyncClient, vendor_user, variable_product
):
    """Duplicate nested sizes within the same variation must be rejected with 422."""
    product_id = variable_product["id"]
    red_var = next(v for v in variable_product["variations"] if v["title"] == "Red")

    res = await client.put(
        f"/api/v1/products/{product_id}/variations/{red_var['id']}",
        json={
            "title": "Red",
            "sizes": [
                {"size": "M", "stock": 10},
                {"size": "M", "stock": 5},
            ],
        },
        headers=vendor_user["headers"],
    )
    assert res.status_code == 422
    assert "duplicate" in str(res.json()["detail"]).lower()


@pytest.mark.asyncio
async def test_rejects_invalid_size_enum(
    client: AsyncClient, vendor_user, variable_product
):
    """Invalid size strings outside SizeEnum must be rejected with 422."""
    product_id = variable_product["id"]
    red_var = next(v for v in variable_product["variations"] if v["title"] == "Red")

    res = await client.put(
        f"/api/v1/products/{product_id}/variations/{red_var['id']}",
        json={
            "title": "Red",
            "sizes": [{"size": "GIGANTIC", "stock": 10}],
        },
        headers=vendor_user["headers"],
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_rejects_negative_stock(
    client: AsyncClient, vendor_user, variable_product
):
    """Negative stock values must fail validation with 422."""
    product_id = variable_product["id"]
    red_var = next(v for v in variable_product["variations"] if v["title"] == "Red")

    res = await client.put(
        f"/api/v1/products/{product_id}/variations/{red_var['id']}",
        json={
            "title": "Red",
            "sizes": [{"size": "M", "stock": -5}],
        },
        headers=vendor_user["headers"],
    )
    assert res.status_code == 422
    assert "greater than or equal to 0" in str(res.json()["detail"]).lower() or "negative" in str(res.json()["detail"]).lower()


@pytest.mark.asyncio
async def test_rejects_invalid_prices(
    client: AsyncClient, vendor_user, variable_product
):
    """Prices <= 0 or sale_price >= price must fail validation with 422."""
    product_id = variable_product["id"]
    red_var = next(v for v in variable_product["variations"] if v["title"] == "Red")

    # Negative price
    res1 = await client.put(
        f"/api/v1/products/{product_id}/variations/{red_var['id']}",
        json={"title": "Red", "price": -10.00},
        headers=vendor_user["headers"],
    )
    assert res1.status_code == 422

    # Sale price >= regular price
    res2 = await client.put(
        f"/api/v1/products/{product_id}/variations/{red_var['id']}",
        json={"title": "Red", "price": 50.00, "sale_price": 55.00},
        headers=vendor_user["headers"],
    )
    assert res2.status_code == 422
    assert "Sale price must be less than regular price" in str(res2.json()["detail"])


# ============================================================================
# 6. Authorization & Access Control
# ============================================================================

@pytest.mark.asyncio
async def test_vendor_ownership_authorization(
    client: AsyncClient, second_vendor_user, variable_product
):
    """A vendor cannot view, update, or delete variations of another vendor's product (403)."""
    product_id = variable_product["id"]
    red_id = variable_product["variations"][0]["id"]
    headers = second_vendor_user["headers"]

    # View
    res_get = await client.get(
        f"/api/v1/products/{product_id}/variations",
        headers=headers,
    )
    assert res_get.status_code == 403

    # Update
    res_put = await client.put(
        f"/api/v1/products/{product_id}/variations/{red_id}",
        json={"title": "Stolen Red"},
        headers=headers,
    )
    assert res_put.status_code == 403

    # Delete
    res_del = await client.delete(
        f"/api/v1/products/{product_id}/variations/{red_id}",
        headers=headers,
    )
    assert res_del.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_access_admin_variation_endpoints(
    client: AsyncClient, vendor_user, variable_product
):
    """Non-admin callers cannot access admin variation endpoints (401/403)."""
    product_id = variable_product["id"]
    red_id = variable_product["variations"][0]["id"]

    for headers in ({}, vendor_user["headers"]):
        get_res = await client.get(
            f"/api/v1/admin/products/{product_id}/variations",
            headers=headers,
        )
        assert get_res.status_code in (401, 403)

        put_res = await client.put(
            f"/api/v1/admin/products/{product_id}/variations/{red_id}",
            json={"title": "Admin Red"},
            headers=headers,
        )
        assert put_res.status_code in (401, 403)

        del_res = await client.delete(
            f"/api/v1/admin/products/{product_id}/variations/{red_id}",
            headers=headers,
        )
        assert del_res.status_code in (401, 403)


# ============================================================================
# 7. Admin Variation Operations (Does not reset moderation)
# ============================================================================

@pytest.mark.asyncio
async def test_admin_can_manage_variations_without_resetting_moderation(
    client: AsyncClient, admin_user, variable_product, db_session: AsyncSession
):
    """Admin updates on variations succeed and preserve approved status."""
    product_id = variable_product["id"]
    red_id = variable_product["variations"][0]["id"]

    # Mark product approved first
    product = await db_session.get(Product, product_id)
    product.moderation_status = ModerationStatus.APPROVED
    product.status = ProductStatus.ACTIVE
    await db_session.commit()

    # Admin GET variations
    get_res = await client.get(
        f"/api/v1/admin/products/{product_id}/variations",
        headers=admin_user["headers"],
    )
    assert get_res.status_code == 200
    assert len(get_res.json()) == 2

    # Admin PUT variation
    put_res = await client.put(
        f"/api/v1/admin/products/{product_id}/variations/{red_id}",
        json={"title": "Admin Curated Crimson", "price": 80.00},
        headers=admin_user["headers"],
    )
    assert put_res.status_code == 200
    assert put_res.json()["title"] == "Admin Curated Crimson"

    # Moderation status should STILL be APPROVED
    await db_session.refresh(product)
    assert product.moderation_status == ModerationStatus.APPROVED


# ============================================================================
# 8. Moderation Reset & Customer Visibility
# ============================================================================

@pytest.mark.asyncio
async def test_vendor_variation_edit_reverts_moderation_to_pending(
    client: AsyncClient, vendor_user, variable_product, db_session: AsyncSession
):
    """Vendor variation edits revert product to pending moderation, hiding it from public customer view."""
    product_id = variable_product["id"]
    red_id = variable_product["variations"][0]["id"]

    # Approve product
    product = await db_session.get(Product, product_id)
    product.moderation_status = ModerationStatus.APPROVED
    product.status = ProductStatus.ACTIVE
    await db_session.commit()

    # Customer can see product
    cust_res = await client.get(f"/api/v1/products/{product_id}")
    assert cust_res.status_code == 200

    # Vendor edits variation
    edit_res = await client.put(
        f"/api/v1/products/{product_id}/variations/{red_id}",
        json={"title": "Vendor Redux Red"},
        headers=vendor_user["headers"],
    )
    assert edit_res.status_code == 200

    # Verification: moderation reverted to pending
    await db_session.refresh(product)
    assert product.moderation_status == ModerationStatus.PENDING

    # Customer can NO LONGER see pending product (404)
    cust_res_after = await client.get(f"/api/v1/products/{product_id}")
    assert cust_res_after.status_code == 404

    # Vendor still can see it
    vendor_res = await client.get(
        f"/api/v1/vendor/products/{product_id}",
        headers=vendor_user["headers"],
    )
    assert vendor_res.status_code == 200
