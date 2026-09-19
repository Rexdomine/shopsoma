from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_access_token_expires_delta,
    get_refresh_token_expires_delta,
)


def _token_lifetime_seconds(payload: dict) -> int:
    return int(payload["exp"]) - int(payload["iat"])


def test_customer_access_token_expiry_uses_long_duration() -> None:
    token = create_access_token({"sub": "1", "email": "customer@example.com", "role": "customer"})
    payload = decode_token(token)

    assert payload is not None
    expected = int(get_access_token_expires_delta("customer").total_seconds())
    assert _token_lifetime_seconds(payload) >= expected - 5


def test_vendor_access_token_expiry_uses_default_duration() -> None:
    token = create_access_token({"sub": "2", "email": "vendor@example.com", "role": "vendor"})
    payload = decode_token(token)

    assert payload is not None
    expected = int(get_access_token_expires_delta("vendor").total_seconds())
    assert expected == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert _token_lifetime_seconds(payload) >= expected - 5


def test_customer_refresh_token_expiry_uses_long_duration() -> None:
    token = create_refresh_token({"sub": "3", "email": "customer@example.com", "role": "customer"})
    payload = decode_token(token)

    assert payload is not None
    expected = int(get_refresh_token_expires_delta("customer").total_seconds())
    assert _token_lifetime_seconds(payload) >= expected - 5


async def test_refresh_accepts_json_body(client, customer_user) -> None:
    user = customer_user["user"]
    refresh_token = create_refresh_token({
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
    })

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0


async def test_refresh_still_accepts_query_token(client, customer_user) -> None:
    user = customer_user["user"]
    refresh_token = create_refresh_token({
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
    })

    response = await client.post(
        "/api/v1/auth/refresh",
        params={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
