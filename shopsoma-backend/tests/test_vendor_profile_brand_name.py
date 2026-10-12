import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.schemas.vendor import VendorProfileUpdate


def test_vendor_profile_update_schema_trimming_and_validation():
    # Valid trimmed
    update = VendorProfileUpdate(business_name="  My Brand  ")
    assert update.business_name == "My Brand"

    # Valid boundary 2 chars
    update_min = VendorProfileUpdate(business_name="AB")
    assert update_min.business_name == "AB"

    # Valid boundary 255 chars
    update_max = VendorProfileUpdate(business_name="A" * 255)
    assert update_max.business_name == "A" * 255

    # Blank / whitespace only
    with pytest.raises(ValidationError):
        VendorProfileUpdate(business_name="   ")

    # Empty
    with pytest.raises(ValidationError):
        VendorProfileUpdate(business_name="")

    # Too short
    with pytest.raises(ValidationError):
        VendorProfileUpdate(business_name="A")

    # Too long
    with pytest.raises(ValidationError):
        VendorProfileUpdate(business_name="A" * 256)


@pytest.mark.asyncio
async def test_vendor_can_update_brand_name_and_persist(
    client: AsyncClient,
    vendor_user,
):
    original_vendor = vendor_user["vendor"]
    original_phone = original_vendor.business_phone

    response = await client.put(
        "/api/v1/vendor/profile",
        json={"business_name": "  Updated Boutique Name  "},
        headers=vendor_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["business_name"] == "Updated Boutique Name"
    # Unchanged fields remain preserved
    assert data["business_phone"] == original_phone

    # Verify persistence via GET /profile
    get_response = await client.get(
        "/api/v1/vendor/profile",
        headers=vendor_user["headers"],
    )
    assert get_response.status_code == 200
    assert get_response.json()["business_name"] == "Updated Boutique Name"


@pytest.mark.asyncio
async def test_vendor_profile_update_rejects_blank_or_invalid_brand_name(
    client: AsyncClient,
    vendor_user,
):
    # Blank
    response = await client.put(
        "/api/v1/vendor/profile",
        json={"business_name": "   "},
        headers=vendor_user["headers"],
    )
    assert response.status_code == 422

    # Too short
    response = await client.put(
        "/api/v1/vendor/profile",
        json={"business_name": "A"},
        headers=vendor_user["headers"],
    )
    assert response.status_code == 422

    # Too long
    response = await client.put(
        "/api/v1/vendor/profile",
        json={"business_name": "A" * 256},
        headers=vendor_user["headers"],
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_vendor_profile_update_requires_vendor_authentication(
    client: AsyncClient,
    customer_user,
):
    # Unauthenticated
    unauth_response = await client.put(
        "/api/v1/vendor/profile",
        json={"business_name": "Hacker Brand"},
    )
    assert unauth_response.status_code in (401, 403)

    # Customer user cannot access vendor profile update
    customer_response = await client.put(
        "/api/v1/vendor/profile",
        json={"business_name": "Customer Attempt"},
        headers=customer_user["headers"],
    )
    assert customer_response.status_code == 403
