from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_vendor_collection_lifecycle(
    client: AsyncClient,
    db_session: AsyncSession,
    vendor_user,
    sample_product,
):
    from app.models.vendor_pickup import VendorNotification

    create_response = await client.post(
        "/api/v1/collections",
        json={
            "name": "Test Collection",
            "description": "Collection description",
            "banner_image_url": "https://example.com/banner.jpg",
        },
        headers=vendor_user["headers"],
    )

    assert create_response.status_code == 201
    collection_data = create_response.json()
    collection_id = collection_data["id"]
    assert collection_data["banner_image_url"] == "https://example.com/banner.jpg"

    notification_result = await db_session.execute(
        VendorNotification.__table__.select().where(
            VendorNotification.vendor_id == vendor_user["vendor"].id,
            VendorNotification.notification_type == "collection_created",
        )
    )
    notification = notification_result.first()
    assert notification is not None

    add_response = await client.post(
        f"/api/v1/collections/{collection_id}/products",
        json={"product_ids": [str(sample_product.id)]},
        headers=vendor_user["headers"],
    )
    assert add_response.status_code == 200
    assert add_response.json()["updated_count"] == 1

    list_response = await client.get(
        f"/api/v1/collections/{collection_id}/products",
        headers=vendor_user["headers"],
    )
    assert list_response.status_code == 200
    list_data = list_response.json()
    assert list_data["total"] == 1
    assert list_data["items"][0]["id"] == str(sample_product.id)

    available_response = await client.get(
        f"/api/v1/collections/{collection_id}/available-products",
        headers=vendor_user["headers"],
    )
    assert available_response.status_code == 200
    available_data = available_response.json()
    assert available_data["total"] == 0

    archive_response = await client.patch(
        f"/api/v1/collections/{collection_id}",
        json={"is_active": False},
        headers=vendor_user["headers"],
    )
    assert archive_response.status_code == 200
    assert archive_response.json()["is_active"] is False
