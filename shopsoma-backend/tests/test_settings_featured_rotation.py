import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_can_update_featured_rotation_settings(
    client: AsyncClient,
    admin_user,
):
    response = await client.put(
        "/api/v1/settings/admin/featured-rotation",
        json={"rotation_minutes": 15},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["rotation_minutes"] == 15

    public_response = await client.get("/api/v1/settings/public/featured-rotation")
    assert public_response.status_code == 200
    public_data = public_response.json()
    assert public_data["rotation_minutes"] == 15
