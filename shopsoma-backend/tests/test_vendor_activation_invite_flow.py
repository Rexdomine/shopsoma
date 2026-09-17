import uuid

import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_vendor_activation_resend_rejects_undelivered_otp_and_invalidates_it(
    client, db_session, monkeypatch
):
    """Resend must expose provider failure without leaving a usable OTP."""
    from datetime import timedelta

    from app.core.security import create_access_token
    from app.models.user import User, UserRole
    from app.models.vendor import Vendor, KYCStatus
    from app.models.vendor_otp import VendorOTP

    user = User(
        id=uuid.uuid4(),
        email="resend-delivery-failed-vendor@test.com",
        hashed_password="hashed-password",
        full_name="Resend Delivery Failed Vendor",
        role=UserRole.VENDOR,
        email_verified=False,
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()
    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user.id,
        business_name="Resend Delivery Failed Vendor Shop",
        approved=True,
        kyc_status=KYCStatus.PENDING,
        is_onboarding=True,
    )
    db_session.add(vendor)
    await db_session.commit()

    async def delivery_rejected(*_args, **_kwargs):
        return False

    monkeypatch.setattr(
        "app.services.vendor_otp_service.email_service.send_vendor_otp_email",
        delivery_rejected,
    )
    activation_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "purpose": "vendor_activation"},
        expires_delta=timedelta(minutes=30),
    )

    response = await client.post(
        "/api/v1/vendor/activation/resend-otp",
        json={"token": activation_token},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Unable to send verification code. Please try again."
    otp = (
        await db_session.execute(
            select(VendorOTP).where(VendorOTP.email == user.email)
        )
    ).scalar_one()
    assert otp.is_used is True


@pytest.mark.asyncio
async def test_vendor_activation_initiate_rejects_undelivered_otp_and_invalidates_it(
    client, db_session, monkeypatch
):
    """A provider rejection must not leave a usable OTP behind or claim delivery."""
    from app.models.user import User, UserRole
    from app.models.vendor import Vendor, KYCStatus
    from app.models.vendor_otp import VendorOTP

    user = User(
        id=uuid.uuid4(),
        email="delivery-failed-vendor@test.com",
        hashed_password="hashed-password",
        full_name="Delivery Failed Vendor",
        role=UserRole.VENDOR,
        email_verified=False,
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()

    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user.id,
        business_name="Delivery Failed Vendor Shop",
        approved=True,
        kyc_status=KYCStatus.PENDING,
        is_onboarding=True,
    )
    db_session.add(vendor)
    await db_session.commit()

    async def delivery_rejected(*_args, **_kwargs):
        return False

    monkeypatch.setattr(
        "app.services.vendor_otp_service.email_service.send_vendor_otp_email",
        delivery_rejected,
    )

    response = await client.post(
        "/api/v1/vendor/activation/initiate",
        json={"email": user.email},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Unable to send verification code. Please try again."

    otp = (
        await db_session.execute(
            select(VendorOTP).where(VendorOTP.email == user.email)
        )
    ).scalar_one()
    assert otp.is_used is True
    assert otp.can_verify() is False




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

    from app.services.vendor_otp_service import OTPDeliveryError

    async def delivery_failed(*_args, **_kwargs):
        raise OTPDeliveryError("provider rejected handoff")

    monkeypatch.setattr(VendorOTPService, "create_and_send_otp", delivery_failed)
    failed_response = await client.post(
        f"/api/v1/admin/vendor-applications/{application.id}/resend-activation",
        headers=admin_user["headers"],
    )

    assert failed_response.status_code == 503
    assert failed_response.json()["detail"] == "Unable to send activation email. Please try again."


@pytest.mark.asyncio
async def test_vendor_activation_password_persists_for_fresh_login(client, db_session):
    """The activation password must be stored in the field used by login."""
    from datetime import timedelta

    from app.core.security import create_access_token, verify_password
    from app.models.user import User, UserRole
    from app.models.vendor import KYCStatus, Vendor

    user = User(
        id=uuid.uuid4(),
        email="activation-login-vendor@test.com",
        hashed_password=None,
        full_name="Activation Login Vendor",
        role=UserRole.VENDOR,
        email_verified=False,
        is_active=False,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(
        Vendor(
            id=uuid.uuid4(),
            user_id=user.id,
            business_name="Activation Login Vendor Shop",
            approved=True,
            kyc_status=KYCStatus.PENDING,
            is_onboarding=True,
        )
    )
    await db_session.commit()

    activation_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "purpose": "vendor_activation"},
        expires_delta=timedelta(minutes=30),
    )
    password = "Persisted!Pass2026"

    set_password_response = await client.post(
        "/api/v1/vendor/activation/set-password",
        json={"activation_token": activation_token, "password": password},
    )

    assert set_password_response.status_code == 200
    await db_session.refresh(user)
    assert user.hashed_password
    assert verify_password(password, user.hashed_password)

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert login_response.status_code == 200
    assert login_response.json()["access_token"]
