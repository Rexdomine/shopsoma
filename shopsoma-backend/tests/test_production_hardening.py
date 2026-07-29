from pathlib import Path

from httpx import ASGITransport, AsyncClient
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import app as main_app
from app.middleware.rate_limit import RateLimitMiddleware


@pytest.mark.asyncio
async def test_api_health_does_not_expose_key_preview():
    async with AsyncClient(
        transport=ASGITransport(app=main_app),
        base_url="http://test",
    ) as client:
        response = await client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert "paystack_key_preview" not in payload
    assert "paystack_configured" not in payload
    assert "stripe_configured" not in payload
    assert "storage_backend" not in payload


@pytest.mark.asyncio
async def test_rate_limit_middleware_returns_429_after_threshold():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, rate_limit=2, window_seconds=60)

    @app.post("/api/v1/auth/login")
    async def login():
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        first = await test_client.post("/api/v1/auth/login")
        second = await test_client.post("/api/v1/auth/login")
        third = await test_client.post("/api/v1/auth/login")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.headers["retry-after"] == "60"
    assert third.json()["detail"].startswith("Rate limit exceeded")


def test_settings_reject_local_storage_outside_development_without_override():
    with pytest.raises(ValueError, match="USE_LOCAL_STORAGE"):
        Settings(
            SECRET_KEY="test-secret",
            DATABASE_URL="postgresql://user:***@localhost:5432/shopsoma_db",
            ENVIRONMENT="staging",
            USE_LOCAL_STORAGE=True,
            ALLOW_LOCAL_STORAGE_IN_NON_DEV=False,
        )


def test_backend_ci_uses_supported_python_runtime():
    workflow = (
        Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    ).read_text()

    assert "python-version: '3.11'" in workflow
