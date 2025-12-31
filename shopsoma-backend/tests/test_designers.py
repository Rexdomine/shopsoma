import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_public_designers_list_only_returns_approved(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from app.core.security import get_password_hash
    from app.models.user import User, UserRole
    from app.models.vendor import Vendor, KYCStatus

    approved_user = User(
        id=uuid.uuid4(),
        email="approved@test.com",
        hashed_password=get_password_hash("VendorPass123"),
        full_name="Approved Vendor",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    pending_user = User(
        id=uuid.uuid4(),
        email="pending@test.com",
        hashed_password=get_password_hash("VendorPass123"),
        full_name="Pending Vendor",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    db_session.add_all([approved_user, pending_user])
    await db_session.flush()

    approved_vendor = Vendor(
        id=uuid.uuid4(),
        user_id=approved_user.id,
        business_name="Approved Brand",
        kyc_status=KYCStatus.APPROVED,
        approved=True,
        total_products=3,
        total_orders=2,
    )
    pending_vendor = Vendor(
        id=uuid.uuid4(),
        user_id=pending_user.id,
        business_name="Pending Brand",
        kyc_status=KYCStatus.PENDING,
        approved=False,
    )
    db_session.add_all([approved_vendor, pending_vendor])
    await db_session.commit()

    response = await client.get("/api/v1/designers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["business_name"] == "Approved Brand"
