import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_admin_can_update_payout_hold_days(
    client: AsyncClient,
    admin_user,
):
    response = await client.put(
        "/api/v1/settings/admin/payout-hold",
        json={"hold_days": 7},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["hold_days"] == 7

    response = await client.get(
        "/api/v1/settings/admin/payout-hold",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert response.json()["hold_days"] == 7
