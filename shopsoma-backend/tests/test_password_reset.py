import uuid
from urllib.parse import urlparse, parse_qs

import pytest

from app.core.security import (
    create_password_reset_token,
    verify_password_reset_token,
    verify_password,
)
from app.models.user import User, UserRole
from app.services.email_service import email_service


@pytest.mark.asyncio
async def test_password_reset_request_sends_email(client, db_session, monkeypatch):
    user = User(
        id=uuid.uuid4(),
        email="resetme@example.com",
        hashed_password="$2b$12$1bIvzAPj16sGZQb4qfZ4MOqX7j1F7uT8ZPhMcf1ZAT4fZbAq5Tv2u",
        full_name="Reset User",
        role=UserRole.CUSTOMER,
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    captured = {}

    async def fake_send(email, name, reset_link, expires_minutes):
        captured["email"] = email
        captured["reset_link"] = reset_link
        captured["expires_minutes"] = expires_minutes
        return True

    monkeypatch.setattr(email_service, "send_password_reset_email", fake_send)

    response = await client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": user.email}
    )

    assert response.status_code == 200
    assert captured["email"] == user.email
    parsed = urlparse(captured["reset_link"])
    token = parse_qs(parsed.query).get("token", [None])[0]
    assert token
    assert verify_password_reset_token(token) == user.email


@pytest.mark.asyncio
async def test_password_reset_confirm_updates_password(client, db_session):
    user = User(
        id=uuid.uuid4(),
        email="resetconfirm@example.com",
        hashed_password="$2b$12$1bIvzAPj16sGZQb4qfZ4MOqX7j1F7uT8ZPhMcf1ZAT4fZbAq5Tv2u",
        full_name="Reset Confirm",
        role=UserRole.CUSTOMER,
        email_verified=True,
        is_active=True,
        is_guest_created=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_password_reset_token(user.email, 60)
    response = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": token, "new_password": "NewPass123"}
    )

    assert response.status_code == 200

    await db_session.refresh(user)
    assert verify_password("NewPass123", user.hashed_password)
    assert user.is_guest_created is False


@pytest.mark.asyncio
async def test_password_reset_confirm_invalid_token(client):
    response = await client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": "invalid", "new_password": "NewPass123"}
    )

    assert response.status_code == 400
