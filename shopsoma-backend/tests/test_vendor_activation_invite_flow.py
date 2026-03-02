import uuid

import pytest


@pytest.mark.asyncio
async def test_vendor_activation_initiate_returns_already_setup_guidance(client, db_session):
    from app.core.config import settings
    from app.models.user import User, UserRole
    from app.models.vendor import Vendor, KYCStatus

    user = User(
        id=uuid.uuid4(),
        email="active-vendor@test.com",
        hashed_password="hashed-password",
        full_name="Active Vendor",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user.id,
        business_name="Active Vendor Shop",
        approved=True,
        kyc_status=KYCStatus.APPROVED,
    )
    db_session.add(vendor)
    await db_session.commit()

    response = await client.post(
        "/api/v1/vendor/activation/initiate",
        json={"email": user.email},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["account_already_setup"] is True
    assert payload["token"] is None
    assert payload["masked_email"] is None
    assert payload["reset_password_url"] == f"{settings.FRONTEND_BASE_URL}/forgot-password"
    assert payload["support_email"] == settings.ADMIN_EMAIL
    assert "already set up" in payload["message"].lower()


@pytest.mark.asyncio
async def test_admin_can_resend_vendor_activation_for_already_active_vendor(
    client, db_session, admin_user, monkeypatch
):
    from app.models.user import User, UserRole
    from app.models.vendor import Vendor, KYCStatus
    from app.models.vendor_application import VendorApplication
    from app.services.vendor_otp_service import VendorOTPService

    user = User(
        id=uuid.uuid4(),
        email="already-active-vendor@test.com",
        hashed_password="hashed-password",
        full_name="Already Active Vendor",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user.id,
        business_name="Already Active Vendor Shop",
        approved=True,
        kyc_status=KYCStatus.APPROVED,
    )
    db_session.add(vendor)
    await db_session.flush()

    application = VendorApplication(
        id=uuid.uuid4(),
        first_name="Already",
        last_name="Active",
        email=user.email,
        phone_country_code="+234",
        phone_number="8011111111",
        business_name=vendor.business_name,
        business_location="Lagos, Nigeria",
        is_business_registered="No",
        product_categories=["Fashion"],
        local_production_level="High",
        years_in_business="3-5 years",
        status="approved",
        vendor_id=vendor.id,
    )
    db_session.add(application)
    await db_session.commit()

    captured: dict[str, str] = {}

    async def fake_create_and_send_otp(db, vendor_id, email):
        captured["vendor_id"] = str(vendor_id)
        captured["email"] = email
        return None

    monkeypatch.setattr(VendorOTPService, "create_and_send_otp", fake_create_and_send_otp)

    response = await client.post(
        f"/api/v1/admin/vendor-applications/{application.id}/resend-activation",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Activation email resent successfully"
    assert payload["email"] == user.email
    assert payload["account_already_setup"] is True
    assert captured["vendor_id"] == str(vendor.id)
    assert captured["email"] == user.email
