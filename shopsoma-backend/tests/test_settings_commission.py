import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vendor import Vendor


@pytest.mark.asyncio
async def test_admin_can_update_default_commission_without_touching_existing_vendors(
    client: AsyncClient,
    admin_user,
    vendor_user,
    db_session: AsyncSession,
):
    vendor_user["vendor"].commission_rate = 12.5
    await db_session.commit()

    response = await client.put(
        "/api/v1/settings/admin/commission",
        json={"commission_rate": 18.25},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert response.json()["commission_rate"] == 18.25

    await db_session.refresh(vendor_user["vendor"])
    assert float(vendor_user["vendor"].commission_rate) == 12.5

    get_response = await client.get(
        "/api/v1/settings/admin/commission",
        headers=admin_user["headers"],
    )
    assert get_response.status_code == 200
    assert get_response.json()["commission_rate"] == 18.25


@pytest.mark.asyncio
async def test_admin_can_apply_commission_to_existing_vendors(
    client: AsyncClient,
    admin_user,
    vendor_user,
    db_session: AsyncSession,
):
    response = await client.put(
        "/api/v1/settings/admin/commission",
        json={"commission_rate": 20, "apply_to_existing_vendors": True},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert response.json()["commission_rate"] == 20

    result = await db_session.execute(select(Vendor).where(Vendor.id == vendor_user["vendor"].id))
    vendor = result.scalar_one()
    assert float(vendor.commission_rate) == 20
