import pytest
from sqlalchemy import select

from app.models.user import User, UserRole
from app.models.audit_log import AuditLog


@pytest.mark.asyncio
async def test_classification_previews_only_customer_and_vendor_accounts(
    client,
    db_session,
    admin_user,
    customer_user,
    vendor_user,
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "staging")

    response = await client.post(
        "/api/v1/admin/test-accounts/classify",
        json={"apply": False},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert response.json()["applied"] is False
    assert response.json()["eligible_count"] == 2
    assert response.json()["pending_count"] == 2

    admin = await db_session.scalar(
        select(User).where(User.role == UserRole.ADMIN)
    )
    assert admin is not None
    assert admin.is_test_account is False


@pytest.mark.asyncio
async def test_classification_is_idempotent_and_audited(
    client,
    db_session,
    admin_user,
    customer_user,
    vendor_user,
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    headers = admin_user["headers"]

    first = await client.post(
        "/api/v1/admin/test-accounts/classify",
        json={"apply": True},
        headers=headers,
    )
    second = await client.post(
        "/api/v1/admin/test-accounts/classify",
        json={"apply": True},
        headers=headers,
    )

    assert first.status_code == 200
    assert first.json()["tagged_count"] == 2
    assert second.status_code == 200
    assert second.json()["tagged_count"] == 0

    for account in (customer_user["user"], vendor_user["user"]):
        await db_session.refresh(account)
        assert account.is_test_account is True
        assert account.test_account_tagged_by == admin_user["user"].id
        assert account.test_account_tag_reason == "staging-wide test data classification"

    admin = await db_session.scalar(
        select(User).where(User.role == UserRole.ADMIN)
    )
    assert admin is not None
    assert admin.is_test_account is False


@pytest.mark.asyncio
async def test_individual_test_account_tag_is_idempotent_and_audited(
    client,
    db_session,
    admin_user,
    customer_user,
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    headers = admin_user["headers"]
    user_id = str(customer_user["user"].id)

    first = await client.post(f"/api/v1/admin/users/{user_id}/test-account", headers=headers)
    second = await client.post(f"/api/v1/admin/users/{user_id}/test-account", headers=headers)

    assert first.status_code == 200
    assert first.json() == {"tagged": True, "is_test_account": True, "user_id": user_id}
    assert second.status_code == 200
    assert second.json() == {"tagged": False, "is_test_account": True, "user_id": user_id}

    audit_rows = await db_session.scalars(
        select(AuditLog).where(
            AuditLog.entity_id == customer_user["user"].id,
            AuditLog.action == "user_test_account_tagged",
        )
    )
    assert len(list(audit_rows)) == 1


@pytest.mark.asyncio
async def test_individual_test_account_tag_rejects_admin(
    client,
    admin_user,
    monkeypatch,
):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    response = await client.post(
        f"/api/v1/admin/users/{admin_user['user'].id}/test-account",
        headers=admin_user["headers"],
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Admin accounts cannot be tagged as test accounts"
