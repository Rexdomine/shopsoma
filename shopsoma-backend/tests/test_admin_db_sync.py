import pytest


@pytest.mark.asyncio
async def test_admin_db_sync_returns_success(client, admin_user, monkeypatch):
    from app.api.v1 import settings as settings_api
    from app.core import config

    monkeypatch.setattr(config.settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(config.settings, "DEBUG", True)
    monkeypatch.setattr(
        config.settings,
        "RENDER_DATABASE_URL",
        "postgresql://user:pass@render:5432/shopsoma_staging",
    )
    monkeypatch.setattr(
        config.settings,
        "DATABASE_URL",
        "postgresql://user:pass@localhost:5432/shopsoma_db",
    )

    def fake_run_db_sync(source_url: str, target_url: str) -> None:
        return None

    monkeypatch.setattr(settings_api, "_run_db_sync", fake_run_db_sync)

    response = await client.post(
        "/api/v1/settings/admin/db-sync",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


@pytest.mark.asyncio
async def test_admin_db_sync_blocked_in_production(client, admin_user, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(config.settings, "DEBUG", False)

    response = await client.post(
        "/api/v1/settings/admin/db-sync",
        headers=admin_user["headers"],
    )

    assert response.status_code == 403
