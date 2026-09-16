import pytest
from httpx import AsyncClient


BRAND_INFO = {
    "business_phone": "+234****0000",
    "business_description": "Editorial womenswear.",
    "shipping_address": "12 Fashion Avenue, Lagos",
    "returning_address": "12 Fashion Avenue, Lagos",
    "open_days": ["MON"],
    "open_hour": "09:00",
    "close_hour": "17:00",
}

PAYOUT_INFO = {
    "account_type": "Savings",
    "bank_name": "Test Bank",
    "account_number": "0123456789",
    "account_holder": "Test Vendor",
}


@pytest.mark.asyncio
async def test_onboarding_remains_incomplete_without_featured_storefront_image(
    client: AsyncClient,
    incomplete_vendor_user,
):
    brand_response = await client.put(
        "/api/v1/vendor/onboarding/brand-info",
        json=BRAND_INFO,
        headers=incomplete_vendor_user["headers"],
    )
    assert brand_response.status_code == 200
    assert brand_response.json()["is_onboarding"] is True

    payout_response = await client.put(
        "/api/v1/vendor/onboarding/payout-info",
        json=PAYOUT_INFO,
        headers=incomplete_vendor_user["headers"],
    )

    assert payout_response.status_code == 200
    assert payout_response.json()["is_onboarding"] is True
    assert payout_response.json()["onboarding_completed_at"] is None


@pytest.mark.asyncio
async def test_onboarding_completes_after_verified_featured_storefront_image_is_saved(
    client: AsyncClient,
    incomplete_vendor_user,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.api.v1.vendors.image_service.get_image_info", lambda _key: {"size": 1}
    )
    image_url = (
        f"/uploads/vendors/{incomplete_vendor_user['user'].id}/"
        "featured-storefront/storefront.webp"
    )
    brand_response = await client.put(
        "/api/v1/vendor/onboarding/brand-info",
        json={**BRAND_INFO, "featured_storefront_image_url": image_url},
        headers=incomplete_vendor_user["headers"],
    )
    assert brand_response.status_code == 200
    assert brand_response.json()["is_onboarding"] is True

    payout_response = await client.put(
        "/api/v1/vendor/onboarding/payout-info",
        json=PAYOUT_INFO,
        headers=incomplete_vendor_user["headers"],
    )

    assert payout_response.status_code == 200
    assert payout_response.json()["is_onboarding"] is False
    assert payout_response.json()["featured_storefront_image_url"] == image_url
    assert payout_response.json()["onboarding_completed_at"] is not None


@pytest.mark.asyncio
async def test_incomplete_vendor_cannot_bypass_onboarding_with_product_api(
    client: AsyncClient,
    incomplete_vendor_user,
):
    response = await client.post(
        "/api/v1/products",
        json={},
        headers=incomplete_vendor_user["headers"],
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error_code"] == "VENDOR_ONBOARDING_INCOMPLETE"
    assert set(response.json()["detail"]["remaining_requirements"]) == {
        "brand_info",
        "featured_storefront_image",
        "payout_info",
    }


@pytest.mark.asyncio
async def test_brand_info_rejects_arbitrary_or_foreign_featured_storefront_image(
    client: AsyncClient,
    incomplete_vendor_user,
):
    response = await client.put(
        "/api/v1/vendor/onboarding/brand-info",
        json={**BRAND_INFO, "featured_storefront_image_url": "x"},
        headers=incomplete_vendor_user["headers"],
    )
    assert response.status_code == 400

    response = await client.put(
        "/api/v1/vendor/onboarding/brand-info",
        json={
            **BRAND_INFO,
            "featured_storefront_image_url": "/uploads/vendors/foreign-vendor/storefront.webp",
        },
        headers=incomplete_vendor_user["headers"],
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_brand_info_rejects_missing_vendor_storage_object(
    client: AsyncClient,
    incomplete_vendor_user,
):
    response = await client.put(
        "/api/v1/vendor/onboarding/brand-info",
        json={
            **BRAND_INFO,
            "featured_storefront_image_url": (
                f"/uploads/vendors/{incomplete_vendor_user['user'].id}/"
                "featured-storefront/missing.webp"
            ),
        },
        headers=incomplete_vendor_user["headers"],
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_completed_vendor_can_create_product(client, vendor_user):
    response = await client.post(
        "/api/v1/products",
        json={"title": "Safe Product", "base_price": 10, "total_stock": 1},
        headers=vendor_user["headers"],
    )
    assert response.status_code == 201
    assert response.json()["vendor_id"] == str(vendor_user["vendor"].id)
