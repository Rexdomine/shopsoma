import uuid

import pytest
from sqlalchemy import select

from datetime import datetime, timedelta, timezone
import asyncio
import html
from urllib.parse import quote

from sqlalchemy.ext.asyncio import async_sessionmaker
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.vendor import Vendor
from app.models.vendor_application import VendorApplication
from app.models.vendor_otp import VendorOTP
from app.services.email_service import EmailService, email_service


@pytest.fixture(autouse=True)
def forbid_real_email(monkeypatch):
    """Every provider call must be explicitly opted into by a test fake."""
    unexpected = []

    async def fail_provider(*args, **kwargs):
        unexpected.append((args, kwargs))
        raise AssertionError("Unexpected email provider call")

    monkeypatch.setattr(EmailService, "send_email", fail_provider)
    yield
    # Services may catch provider exceptions, so also assert at teardown.
    assert not unexpected, "A test reached an unconfigured email provider seam"


@pytest.fixture
async def approved_invitee(db_session, admin_user, monkeypatch):
    """Exercise real approval, password hashing, OTP generation and persistence."""
    from app.services.vendor_application_service import VendorApplicationService

    codes = []

    async def capture_otp(email, otp_code, expiry_minutes):
        codes.append(otp_code)
        return True

    monkeypatch.setattr(email_service, "send_vendor_otp_email", capture_otp)
    application = VendorApplication(
        first_name="A <Vendor>",
        last_name='& "Partner"',
        email="approved+invite@example.com",
        phone_country_code="+234",
        phone_number="8011111111",
        business_name="Approved Test Shop",
        business_location="Lagos",
        is_business_registered="No",
        product_categories=["Fashion"],
        local_production_level="High",
        years_in_business="3-5 years",
        status="pending",
    )
    db_session.add(application)
    await db_session.commit()
    application = await VendorApplicationService.approve_application(
        db_session, application.id, admin_user["user"].id
    )
    vendor = await db_session.get(Vendor, application.vendor_id)
    user = await db_session.get(User, vendor.user_id)
    await db_session.refresh(user)
    assert user.hashed_password and user.hashed_password.startswith("$2")
    assert not user.is_active and not user.email_verified
    assert application.activation_email_sent is True and len(codes) == 1
    return application, vendor, user, codes


def resend_paths(application, vendor):
    return (
        f"/api/v1/admin/vendors/{vendor.id}/resend-activation",
        f"/api/v1/admin/vendor-applications/{application.id}/resend-activation",
    )


async def assert_eligibility(client, headers, vendor, expected):
    listing = await client.get("/api/v1/admin/vendors", headers=headers)
    detail = await client.get(f"/api/v1/admin/vendors/{vendor.id}", headers=headers)
    assert listing.status_code == detail.status_code == 200
    listed = next(row for row in listing.json()["items"] if row["id"] == str(vendor.id))
    assert listed["activation_resend_eligible"] is expected
    assert detail.json()["activation_resend_eligible"] is expected


def persisted_columns(model):
    return {
        column.key: getattr(model, column.key) for column in model.__table__.columns
    }


async def resend_logs(session, vendor_id):
    return list(
        (
            await session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.entity_id == vendor_id,
                    AuditLog.action.in_(
                        (
                            "vendor_activation_email_resend_attempt",
                            "vendor_activation_email_resend_result",
                        )
                    ),
                )
                .order_by(AuditLog.created_at)
            )
        ).all()
    )


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
    assert (
        response.json()["detail"]
        == "Unable to send verification code. Please try again."
    )
    otp = (
        await db_session.execute(select(VendorOTP).where(VendorOTP.email == user.email))
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
    assert (
        response.json()["detail"]
        == "Unable to send verification code. Please try again."
    )

    otp = (
        await db_session.execute(select(VendorOTP).where(VendorOTP.email == user.email))
    ).scalar_one()
    assert otp.is_used is True
    assert otp.can_verify() is False


@pytest.mark.asyncio
async def test_vendor_activation_initiate_returns_already_setup_guidance(
    client, db_session
):
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
    assert (
        payload["reset_password_url"] == f"{settings.FRONTEND_BASE_URL}/forgot-password"
    )
    assert payload["support_email"] == settings.ADMIN_EMAIL
    assert "already set up" in payload["message"].lower()


@pytest.mark.asyncio
async def test_admin_resend_active_vendor_is_rejected_without_provider_call(
    client, db_session, admin_user, monkeypatch
):
    from app.models.user import User, UserRole
    from app.models.vendor import Vendor, KYCStatus
    from app.models.vendor_application import VendorApplication
    from app.services.email_service import email_service

    user = User(
        id=uuid.uuid4(),
        email="already-active-vendor@test.com",
        hashed_password="hashed",
        full_name="Active",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user.id,
        business_name="Active Shop",
        approved=True,
        kyc_status=KYCStatus.APPROVED,
    )
    db_session.add(vendor)
    await db_session.flush()
    application = VendorApplication(
        id=uuid.uuid4(),
        first_name="Active",
        last_name="Vendor",
        email=user.email,
        phone_country_code="+234",
        phone_number="8011111111",
        business_name=vendor.business_name,
        business_location="Lagos",
        is_business_registered="No",
        product_categories=["Fashion"],
        local_production_level="High",
        years_in_business="3-5 years",
        status="approved",
        vendor_id=vendor.id,
    )
    db_session.add(application)
    await db_session.commit()
    called = False

    async def provider(*args):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(
        email_service, "send_vendor_activation_invitation_email", provider
    )
    response = await client.post(
        f"/api/v1/admin/vendor-applications/{application.id}/resend-activation",
        headers=admin_user["headers"],
    )
    assert response.status_code == 409
    assert called is False


@pytest.mark.asyncio
async def test_vendor_activation_requires_verified_one_time_password_setup_token(
    client, db_session, monkeypatch
):
    """Only a post-OTP capability may set the password, and it cannot replay."""
    from datetime import timedelta

    from app.core.security import create_access_token, decode_token, verify_password
    from app.models.user import User, UserRole
    from app.models.vendor import KYCStatus, Vendor

    user = User(
        id=uuid.uuid4(),
        email="verified-token-vendor@test.com",
        hashed_password=None,
        full_name="Verified Token Vendor",
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
            business_name="Verified Token Vendor Shop",
            approved=True,
            kyc_status=KYCStatus.PENDING,
            is_onboarding=True,
        )
    )
    await db_session.commit()

    initiation_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "purpose": "vendor_activation"},
        expires_delta=timedelta(minutes=30),
    )
    rejected = await client.post(
        "/api/v1/vendor/activation/set-password",
        json={"activation_token": initiation_token, "password": "Persisted!Pass2026"},
    )
    assert rejected.status_code == 401

    from app.services.vendor_otp_service import VendorOTPService

    captured = {}

    async def capture_otp(email, otp_code, expiry_minutes):
        captured["code"] = otp_code
        return True

    monkeypatch.setattr(
        "app.services.email_service.email_service.send_vendor_otp_email", capture_otp
    )
    vendor = await db_session.scalar(select(Vendor).where(Vendor.user_id == user.id))
    await VendorOTPService.create_and_send_otp(db_session, vendor.id, user.email)
    verified = await client.post(
        "/api/v1/vendor/activation/verify-otp",
        json={"token": initiation_token, "otp_code": captured["code"]},
    )
    assert verified.status_code == 200
    password_setup_token = verified.json()["activation_token"]
    decoded_password_setup_token = decode_token(password_setup_token)
    assert decoded_password_setup_token is not None
    assert decoded_password_setup_token["purpose"] == "vendor_activation_password"
    assert password_setup_token != initiation_token

    password = "Persisted!Pass2026"
    accepted = await client.post(
        "/api/v1/vendor/activation/set-password",
        json={"activation_token": password_setup_token, "password": password},
    )
    assert accepted.status_code == 200
    await db_session.refresh(user)
    assert user.hashed_password and verify_password(password, user.hashed_password)

    replay = await client.post(
        "/api/v1/vendor/activation/set-password",
        json={"activation_token": password_setup_token, "password": "Another!Pass2026"},
    )
    assert replay.status_code == 409

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert login.status_code == 200


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
        data={
            "sub": str(user.id),
            "email": user.email,
            "purpose": "vendor_activation_password",
        },
        expires_delta=timedelta(minutes=15),
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


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", [0, 1])
async def test_approved_invitation_template_preserves_persisted_state(
    client, db_session, admin_user, approved_invitee, monkeypatch, entrypoint
):
    from app.core.config import settings

    application, vendor, user, _ = approved_invitee
    otp = await db_session.scalar(
        select(VendorOTP).where(VendorOTP.vendor_id == vendor.id)
    )
    before = [persisted_columns(obj) for obj in (user, vendor, otp)]
    sent = []

    async def accept(email, name, subject, html_content):
        sent.append((email, name, subject, html_content))
        return True

    monkeypatch.setattr(email_service, "send_email", accept)
    await assert_eligibility(client, admin_user["headers"], vendor, True)
    response = await client.post(
        resend_paths(application, vendor)[entrypoint], headers=admin_user["headers"]
    )
    assert response.status_code == 200, response.text
    assert "accepted by provider" in response.json()["message"]
    assert response.json()["email"] == user.email
    assert response.json()["account_already_setup"] is False
    assert len(sent) == 1
    email, name, subject, body = sent[0]
    expected_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/vendor/otp?email={quote(user.email, safe='')}"
    assert email == user.email and name == user.full_name
    assert subject == "Activate your Shopsoma vendor account"
    assert f'href="{html.escape(expected_url, quote=True)}"' in body
    assert "%2B" in body and "%40" in body
    assert html.escape(user.full_name) in body and user.full_name not in body
    assert "Verification Code" not in body
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with session_factory() as observer:
        fresh = [await observer.get(type(obj), obj.id) for obj in (user, vendor, otp)]
        assert [persisted_columns(obj) for obj in fresh] == before
        assert (
            len(
                (
                    await observer.scalars(
                        select(VendorOTP).where(VendorOTP.vendor_id == vendor.id)
                    )
                ).all()
            )
            == 1
        )
        logs = await resend_logs(observer, vendor.id)
        attempt = next(log for log in logs if log.action.endswith("_attempt"))
        result = next(log for log in logs if log.action.endswith("_result"))
        assert len(logs) == 2
        assert attempt.user_id == result.user_id == admin_user["user"].id
        assert result.new_values["delivery"] == "provider_accepted"
        assert result.new_values["attempt_id"] == str(attempt.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "blocked_state",
    [
        "active",
        "pending",
        "store_inactive",
        "paused",
        "deleted",
        "onboarding_false",
        "onboarding_completed",
        "user_deactivated",
        "wrong_role",
    ],
)
async def test_guard_matches_list_detail_and_both_mutations(
    client, db_session, admin_user, approved_invitee, monkeypatch, blocked_state
):
    from app.models.user import UserRole

    application, vendor, user, _ = approved_invitee
    now = datetime.now(timezone.utc)
    if blocked_state == "active":
        user.is_active = True
    elif blocked_state == "pending":
        vendor.approved = False
    elif blocked_state == "store_inactive":
        vendor.store_active = False
    elif blocked_state == "paused":
        vendor.store_paused_at = now
    elif blocked_state == "deleted":
        vendor.store_deleted_at = now
    elif blocked_state == "onboarding_false":
        vendor.is_onboarding = False
    elif blocked_state == "onboarding_completed":
        vendor.onboarding_completed_at = now
    elif blocked_state == "wrong_role":
        user.role = UserRole.CUSTOMER
    else:
        db_session.add(
            AuditLog(
                user_id=admin_user["user"].id,
                action="user_deactivated",
                entity_type="user",
                entity_id=user.id,
            )
        )
    await db_session.commit()
    calls = []

    async def unexpected_send(*args, **kwargs):
        calls.append(args)
        return True

    monkeypatch.setattr(email_service, "send_email", unexpected_send)
    await assert_eligibility(client, admin_user["headers"], vendor, False)
    for path in resend_paths(application, vendor):
        response = await client.post(path, headers=admin_user["headers"])
        assert response.status_code == 409, response.text
    assert calls == []
    assert await resend_logs(db_session, vendor.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["anonymous", "customer", "vendor"])
async def test_resend_authorization_both_entrypoints(
    client, db_session, approved_invitee, role
):
    from app.core.security import create_access_token, get_password_hash
    from app.models.user import UserRole

    application, vendor, _, _ = approved_invitee
    headers = {}
    if role != "anonymous":
        actor = User(
            email=f"{role}-actor@example.com",
            role=UserRole(role),
            full_name="Unauthorized actor",
            is_active=True,
            hashed_password=get_password_hash("Unauthorized!123"),
        )
        db_session.add(actor)
        await db_session.commit()
        token = create_access_token(
            data={"sub": str(actor.id), "email": actor.email, "role": role}
        )
        headers = {"Authorization": f"Bearer {token}"}
    for path in resend_paths(application, vendor):
        response = await client.post(path, headers=headers)
        assert response.status_code in (401, 403), response.text
    assert await resend_logs(db_session, vendor.id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["vendors", "vendor-applications"])
async def test_resend_missing_target(client, admin_user, resource):
    response = await client.post(
        f"/api/v1/admin/{resource}/{uuid.uuid4()}/resend-activation",
        headers=admin_user["headers"],
    )
    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("entrypoint", [0, 1])
@pytest.mark.parametrize("outcome", ["accepted", "false", "timeout"])
async def test_durable_attempt_result_and_shared_cooldown(
    client, db_session, admin_user, approved_invitee, monkeypatch, entrypoint, outcome
):
    application, vendor, user, _ = approved_invitee
    paths = resend_paths(application, vendor)
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    observed_attempts = []

    async def provider(*args, **kwargs):
        # A distinct real connection must see the attempt before provider IO.
        async with session_factory() as observer:
            logs = await resend_logs(observer, vendor.id)
            assert len(logs) == 1
            attempt = logs[0]
            assert attempt.action == "vendor_activation_email_resend_attempt"
            assert attempt.entity_type == "vendor" and attempt.entity_id == vendor.id
            assert attempt.user_id == admin_user["user"].id
            assert attempt.new_values == {"email": user.email, "delivery": "pending"}
            observed_attempts.append(attempt.id)
        if outcome == "timeout":
            raise TimeoutError("Provider acknowledgement lost")
        return outcome == "accepted"

    monkeypatch.setattr(email_service, "send_email", provider)
    response = await client.post(paths[entrypoint], headers=admin_user["headers"])
    assert response.status_code == (
        200 if outcome == "accepted" else 503
    ), response.text
    assert len(observed_attempts) == 1
    async with session_factory() as observer:
        logs = await resend_logs(observer, vendor.id)
        assert len(logs) == 2
        result = next(log for log in logs if log.action.endswith("_result"))
        assert result.entity_type == "vendor" and result.entity_id == vendor.id
        assert result.user_id == admin_user["user"].id
        assert result.new_values["attempt_id"] == str(observed_attempts[0])
        assert result.new_values["email"] == user.email
        assert result.new_values["delivery"] == (
            "provider_accepted" if outcome == "accepted" else "unknown"
        )
        if outcome == "timeout":
            assert result.new_values["error"] == "TimeoutError"
    for path in (paths[1 - entrypoint], paths[entrypoint]):
        retry = await client.post(path, headers=admin_user["headers"])
        assert retry.status_code == 429, retry.text
    assert len(observed_attempts) == 1
    assert len(await resend_logs(db_session, vendor.id)) == 2


@pytest.mark.asyncio
async def test_concurrent_entrypoints_only_send_once_with_independent_sessions(
    client, db_session, admin_user, approved_invitee, monkeypatch
):
    from sqlalchemy import text
    from app.core.database import get_db
    from app.main import app

    application, vendor, _, _ = approved_invitee
    paths = resend_paths(application, vendor)
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    old_override = app.dependency_overrides[get_db]
    sessions = []
    request_pids = []
    entered_provider = asyncio.Event()
    release_provider = asyncio.Event()
    calls = []

    async def independent_db():
        async with session_factory() as session:
            sessions.append(session)
            request_pids.append(await session.scalar(text("SELECT pg_backend_pid()")))
            yield session

    async def provider(*args, **kwargs):
        calls.append(args)
        entered_provider.set()
        await asyncio.wait_for(release_provider.wait(), 10)
        return True

    app.dependency_overrides[get_db] = independent_db
    monkeypatch.setattr(email_service, "send_email", provider)
    second_task = None
    first = asyncio.create_task(client.post(paths[0], headers=admin_user["headers"]))
    try:
        await asyncio.wait_for(entered_provider.wait(), 10)
        second_task = asyncio.create_task(
            client.post(paths[1], headers=admin_user["headers"])
        )

        async def wait_for_second_lock():
            async with session_factory() as observer:
                while True:
                    if len(request_pids) == 2:
                        wait_type = await observer.scalar(
                            text(
                                "SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"
                            ),
                            {"pid": request_pids[1]},
                        )
                        await observer.rollback()
                        if wait_type == "Lock":
                            return
                    assert (
                        not second_task.done()
                    ), "Second resend bypassed provider-held locks"
                    await asyncio.sleep(0.02)

        await asyncio.wait_for(wait_for_second_lock(), 5)
        release_provider.set()
        second = await asyncio.wait_for(second_task, 10)
        assert second.status_code == 429, second.text
        response = await asyncio.wait_for(first, 10)
        assert response.status_code == 200, response.text
        assert len(sessions) == 2 and sessions[0] is not sessions[1]
        assert len(calls) == 1
        async with session_factory() as observer:
            assert len(await resend_logs(observer, vendor.id)) == 2
    finally:
        release_provider.set()
        if not first.done():
            first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        if second_task is not None:
            if not second_task.done():
                second_task.cancel()
            await asyncio.gather(second_task, return_exceptions=True)
        app.dependency_overrides[get_db] = old_override


@pytest.mark.asyncio
async def test_real_invitation_otp_password_login_and_verified_intermediate_state(
    client, db_session, admin_user, approved_invitee, monkeypatch
):
    from app.core.security import verify_password

    application, vendor, user, codes = approved_invitee
    paths = resend_paths(application, vendor)
    calls = []

    async def provider(*args, **kwargs):
        calls.append(args)
        return True

    monkeypatch.setattr(email_service, "send_email", provider)
    response = await client.post(paths[0], headers=admin_user["headers"])
    assert response.status_code == 200, response.text
    # Simulate the old approval OTP expiring before following the new invitation.
    otp = await db_session.scalar(
        select(VendorOTP).where(VendorOTP.vendor_id == vendor.id)
    )
    otp.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    await db_session.commit()
    initiated = await client.post(
        "/api/v1/vendor/activation/initiate", json={"email": user.email}
    )
    assert initiated.status_code == 200, initiated.text
    assert len(codes) == 2
    token = initiated.json()["token"]
    premature = await client.post(
        "/api/v1/vendor/activation/set-password",
        json={"activation_token": token, "password": "Activated!Pass2026"},
    )
    assert premature.status_code == 401
    verified = await client.post(
        "/api/v1/vendor/activation/verify-otp",
        json={"token": token, "otp_code": codes[-1]},
    )
    assert verified.status_code == 200, verified.text
    await db_session.refresh(user)
    assert user.email_verified is True and user.is_active is False
    assert user.hashed_password.startswith("$2")
    await assert_eligibility(client, admin_user["headers"], vendor, True)
    for log in await resend_logs(db_session, vendor.id):
        if log.action.endswith("_attempt"):
            log.created_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    await db_session.commit()
    resent = await client.post(paths[1], headers=admin_user["headers"])
    assert resent.status_code == 200, resent.text
    assert len(codes) == 2
    password = "Activated!Pass2026"
    setup_token = verified.json()["activation_token"]
    activated = await client.post(
        "/api/v1/vendor/activation/set-password",
        json={"activation_token": setup_token, "password": password},
    )
    assert activated.status_code == 200, activated.text
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with session_factory() as observer:
        persisted = await observer.get(User, user.id)
        assert persisted.is_active and verify_password(
            password, persisted.hashed_password
        )
    login = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": password}
    )
    assert login.status_code == 200 and login.json()["access_token"]
    replay = await client.post(
        "/api/v1/vendor/activation/set-password",
        json={"activation_token": setup_token, "password": "Replacement!123"},
    )
    assert replay.status_code == 409
    await assert_eligibility(client, admin_user["headers"], vendor, False)
    for path in paths:
        assert (
            await client.post(path, headers=admin_user["headers"])
        ).status_code == 409
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("locked_model", [User, Vendor], ids=["user", "vendor"])
async def test_resend_waits_for_locked_state_then_rechecks_eligibility(
    db_session, admin_user, approved_invitee, locked_model
):
    """A stale ORM object must not let a concurrent account/store change slip through."""
    from fastapi import HTTPException
    from app.api.v1.admin import _resend_vendor_activation_safely
    from sqlalchemy import text

    _, vendor, user, _ = approved_invitee
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    target_id = user.id if locked_model is User else vendor.id
    async with factory() as writer, factory() as requester:
        stale = await requester.get(locked_model, target_id)
        assert stale is not None
        actor = await requester.get(User, admin_user["user"].id)
        # Capture the request connection so pg_stat_activity can prove it waited
        # for a real PostgreSQL lock instead of relying on a scheduling sleep.
        request_pid = await requester.scalar(text("SELECT pg_backend_pid()"))
        locked = await writer.scalar(
            select(locked_model).where(locked_model.id == target_id).with_for_update()
        )
        if locked_model is User:
            locked.is_active = True
        else:
            locked.store_active = False
        await writer.flush()
        request = asyncio.create_task(
            _resend_vendor_activation_safely(vendor.id, actor, requester)
        )
        try:

            async def wait_until_lock_blocked():
                async with factory() as observer:
                    while True:
                        wait_type = await observer.scalar(
                            text(
                                "SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"
                            ),
                            {"pid": request_pid},
                        )
                        await observer.rollback()
                        if wait_type == "Lock":
                            return
                        assert (
                            not request.done()
                        ), "Resend bypassed the locked eligibility row"
                        await asyncio.sleep(0.02)

            await asyncio.wait_for(wait_until_lock_blocked(), 5)
            await writer.commit()
            with pytest.raises(HTTPException) as rejected:
                await asyncio.wait_for(request, 5)
            assert rejected.value.status_code == 409
            await requester.rollback()
            assert await resend_logs(requester, vendor.id) == []
        finally:
            if not request.done():
                request.cancel()
            await asyncio.gather(request, return_exceptions=True)


async def block_activation(session, vendor, user, state):
    if state == "deactivated":
        session.add(
            AuditLog(
                user_id=user.id,
                action="user_deactivated",
                entity_type="user",
                entity_id=user.id,
            )
        )
    elif state == "paused":
        vendor.store_paused_at = datetime.now(timezone.utc)
    elif state == "deleted":
        vendor.store_deleted_at = datetime.now(timezone.utc)
    elif state == "completed":
        vendor.onboarding_completed_at = datetime.now(timezone.utc)
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "boundary", ["initiate", "resend-otp", "verify-otp", "set-password"]
)
@pytest.mark.parametrize("state", ["deactivated", "paused", "deleted", "completed"])
async def test_late_ineligibility_at_every_public_boundary(
    client, db_session, approved_invitee, boundary, state
):
    _, vendor, user, codes = approved_invitee
    initiated = await client.post(
        "/api/v1/vendor/activation/initiate", json={"email": user.email}
    )
    token = initiated.json()["token"]
    body = {"token": token, "otp_code": codes[-1]}
    if boundary == "initiate":
        body = {"email": user.email}
    if boundary == "set-password":
        verified = await client.post("/api/v1/vendor/activation/verify-otp", json=body)
        body = {
            "activation_token": verified.json()["activation_token"],
            "password": "Changed!Password123",
        }
    original_hash, original_verified = user.hashed_password, user.email_verified
    await block_activation(db_session, vendor, user, state)
    response = await client.post(f"/api/v1/vendor/activation/{boundary}", json=body)
    assert response.status_code == 409, response.text
    await db_session.refresh(user)
    assert not user.is_active and user.hashed_password == original_hash
    assert user.email_verified == original_verified
    assert len(codes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["resend-otp", "verify-otp", "set-password"])
@pytest.mark.parametrize("identity", ["email", "subject", "invalid_uuid"])
async def test_activation_token_must_match_current_identity(
    client, db_session, approved_invitee, boundary, identity
):
    from app.core.security import create_access_token

    _, _, user, codes = approved_invitee
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "purpose": (
            "vendor_activation_password"
            if boundary == "set-password"
            else "vendor_activation"
        ),
    }
    if identity == "email":
        user.email = "changed@example.com"
        await db_session.commit()
    else:
        payload["sub"] = str(uuid.uuid4()) if identity == "subject" else "not-a-uuid"
    token = create_access_token(data=payload)
    body = {"token": token, "otp_code": codes[-1]}
    if boundary == "set-password":
        body = {"activation_token": token, "password": "Changed!Password123"}
    response = await client.post(f"/api/v1/vendor/activation/{boundary}", json=body)
    assert response.status_code == 401, response.text
    assert len(codes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["initiate", "resend-otp", "verify-otp"])
async def test_public_rechecks_after_otp_helper_commit(
    client, db_session, approved_invitee, monkeypatch, boundary
):
    _, vendor, user, codes = approved_invitee
    initiated = await client.post(
        "/api/v1/vendor/activation/initiate", json={"email": user.email}
    )
    body = {"token": initiated.json()["token"], "otp_code": codes[-1]}
    if boundary == "initiate":
        otp = await db_session.scalar(
            select(VendorOTP).where(VendorOTP.vendor_id == vendor.id)
        )
        otp.is_used = True
        await db_session.commit()
        body = {"email": user.email}
    original_commit = db_session.commit
    changed = False
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def commit_then_pause():
        nonlocal changed
        await original_commit()
        if not changed:
            changed = True
            async with factory() as writer:
                fresh = await writer.get(Vendor, vendor.id)
                fresh.store_paused_at = datetime.now(timezone.utc)
                await writer.commit()

    monkeypatch.setattr(db_session, "commit", commit_then_pause)
    response = await client.post(f"/api/v1/vendor/activation/{boundary}", json=body)
    assert response.status_code == 409, response.text
    await db_session.refresh(user)
    assert not user.email_verified and not user.is_active


@pytest.mark.asyncio
async def test_admin_rechecks_after_durable_attempt_before_dispatch(
    client, db_session, admin_user, approved_invitee, monkeypatch
):
    _, vendor, user, _ = approved_invitee
    original_commit = db_session.commit
    changed = False
    calls = []
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def commit_then_pause():
        nonlocal changed
        await original_commit()
        if not changed:
            changed = True
            async with factory() as writer:
                fresh = await writer.get(Vendor, vendor.id)
                fresh.store_paused_at = datetime.now(timezone.utc)
                await writer.commit()

    async def provider(*args, **kwargs):
        calls.append(args)
        return True

    monkeypatch.setattr(db_session, "commit", commit_then_pause)
    monkeypatch.setattr(email_service, "send_email", provider)
    response = await client.post(
        f"/api/v1/admin/vendors/{vendor.id}/resend-activation",
        headers=admin_user["headers"],
    )
    assert response.status_code == 409, response.text
    assert calls == []
    logs = await resend_logs(db_session, vendor.id)
    assert len(logs) == 2
    attempt = next(log for log in logs if log.action.endswith("_attempt"))
    result = next(log for log in logs if log.action.endswith("_result"))
    assert result.new_values["attempt_id"] == str(attempt.id)
    assert result.new_values["delivery"] == "skipped_ineligible"


@pytest.mark.asyncio
@pytest.mark.parametrize("locked_model", [User, Vendor], ids=["user", "vendor"])
async def test_provider_await_holds_eligibility_rows(
    client, db_session, admin_user, approved_invitee, monkeypatch, locked_model
):
    from sqlalchemy import text

    _, vendor, user, _ = approved_invitee
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    target_id = user.id if locked_model is User else vendor.id
    calls = []

    async def provider(*args, **kwargs):
        async with factory() as observer:
            assert len(await resend_logs(observer, vendor.id)) == 1
        async with factory() as writer:
            await writer.execute(text("SET LOCAL lock_timeout = '150ms'"))
            with pytest.raises(Exception, match="lock timeout"):
                await writer.execute(
                    locked_model.__table__.update()
                    .where(locked_model.id == target_id)
                    .values(
                        **(
                            {"is_active": True}
                            if locked_model is User
                            else {"store_active": False}
                        )
                    )
                )
            await writer.rollback()
        calls.append(True)
        return True

    monkeypatch.setattr(email_service, "send_email", provider)
    response = await client.post(
        f"/api/v1/admin/vendors/{vendor.id}/resend-activation",
        headers=admin_user["headers"],
    )
    assert response.status_code == 200, response.text
    assert calls == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True], ids=["single", "bulk"])
async def test_audit_only_deactivation_waits_for_identity_lock(
    db_session, admin_user, approved_invitee, bulk
):
    from app.api.v1.admin import toggle_user_status, bulk_update_user_status, BulkUserStatusUpdate
    from sqlalchemy import text

    _, vendor, user, _ = approved_invitee
    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with factory() as holder, factory() as writer:
        await holder.execute(select(User).where(User.id == user.id).with_for_update())
        await writer.execute(text("SET LOCAL lock_timeout = '150ms'"))
        with pytest.raises(Exception, match="lock timeout"):
            if bulk:
                await bulk_update_user_status(
                    BulkUserStatusUpdate(user_ids=[user.id], is_active=False),
                    admin_user["user"], writer,
                )
            else:
                await toggle_user_status(user.id, False, admin_user["user"], writer)
        await writer.rollback()


@pytest.mark.asyncio
async def test_bulk_deactivation_of_inactive_invitee_revokes_existing_capability(
    client, db_session, admin_user, approved_invitee
):
    from app.core.security import create_access_token

    _, vendor, user, _ = approved_invitee
    password_before = user.hashed_password
    token = create_access_token(data={
        "sub": str(user.id), "email": user.email,
        "purpose": "vendor_activation_password",
    })
    response = await client.put(
        "/api/v1/admin/users/status/bulk",
        headers=admin_user["headers"],
        json={"user_ids": [str(user.id)], "is_active": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated_count"] == 0
    assert response.json()["results"][0]["status"] == "unchanged"
    audit = await db_session.scalar(select(AuditLog).where(
        AuditLog.entity_id == user.id,
        AuditLog.entity_type == "user",
        AuditLog.action == "user_deactivated",
    ))
    assert audit is not None
    assert audit.user_id == admin_user["user"].id
    assert audit.old_values == audit.new_values == {"is_active": False}
    await assert_eligibility(client, admin_user["headers"], vendor, False)
    redeemed = await client.post("/api/v1/vendor/activation/set-password", json={
        "activation_token": token, "password": "BlockedRecovery!123",
    })
    assert redeemed.status_code == 409, redeemed.text
    await db_session.refresh(user)
    assert not user.is_active and user.hashed_password == password_before
