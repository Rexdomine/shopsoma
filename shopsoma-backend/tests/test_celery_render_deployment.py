from pathlib import Path

import pytest
import yaml

from app.celery_app import resolve_celery_connection_urls
from app.core.config import Settings


TASK_NAME = "app.tasks.checkout_outbox.dispatch_checkout_outbox"
ROOT = Path(__file__).resolve().parents[2]


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "SECRET_KEY": "unit-test-secret",
        "DATABASE_URL": "postgresql://unit:unit@localhost:5432/shopsoma_unit",
        "ENVIRONMENT": "development",
        "REDIS_URL": None,
        "CELERY_BROKER_URL": "",
        "CELERY_RESULT_BACKEND": "",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def env_by_key(service: dict[str, object]) -> dict[str, dict[str, object]]:
    return {item["key"]: item for item in service.get("envVars", [])}


def test_celery_dedicated_urls_take_precedence_over_redis_fallback() -> None:
    config = make_settings(
        CELERY_BROKER_URL="redis://broker.internal:6379/1",
        CELERY_RESULT_BACKEND="redis://backend.internal:6379/2",
        REDIS_URL="redis://fallback.internal:6379/0",
    )

    assert resolve_celery_connection_urls(config) == (
        "redis://broker.internal:6379/1",
        "redis://backend.internal:6379/2",
    )


def test_celery_uses_redis_url_for_each_missing_dedicated_url() -> None:
    fallback = "redis://redis:6379/0"

    assert resolve_celery_connection_urls(make_settings(REDIS_URL=fallback)) == (
        fallback,
        fallback,
    )
    assert resolve_celery_connection_urls(
        make_settings(
            CELERY_BROKER_URL="redis://broker.internal:6379/1",
            REDIS_URL=fallback,
        )
    ) == ("redis://broker.internal:6379/1", fallback)


def test_celery_uses_local_redis_only_in_development_or_test() -> None:
    assert resolve_celery_connection_urls(make_settings()) == (
        "redis://localhost:6379/0",
        "redis://localhost:6379/0",
    )
    assert resolve_celery_connection_urls(
        make_settings(
            ENVIRONMENT="test",
            USE_LOCAL_STORAGE=True,
            ALLOW_LOCAL_STORAGE_IN_NON_DEV=True,
        )
    ) == (
        "redis://localhost:6379/0",
        "redis://localhost:6379/0",
    )


def test_celery_fails_closed_without_urls_outside_development_or_test() -> None:
    config = make_settings(
        ENVIRONMENT="staging",
        USE_LOCAL_STORAGE=True,
        ALLOW_LOCAL_STORAGE_IN_NON_DEV=True,
    )

    with pytest.raises(ValueError, match="Celery broker and result backend") as error:
        resolve_celery_connection_urls(config)

    assert "redis://" not in str(error.value)


def test_render_blueprint_wires_canonical_checkout_outbox_consumers() -> None:
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}

    redis_services = [
        service
        for service in services.values()
        if service["type"] in {"keyvalue", "redis"}
    ]
    assert len(redis_services) == 1
    redis_service = redis_services[0]
    redis_name = redis_service["name"]

    database_names = {database["name"] for database in blueprint["databases"]}
    assert database_names

    worker = services["shopsoma-staging-checkout-outbox-worker"]
    beat = services["shopsoma-staging-checkout-outbox-beat"]
    assert worker["type"] == "worker"
    assert beat["type"] == "worker"

    for service, process in ((worker, "worker"), (beat, "beat")):
        command = service["startCommand"]
        assert "-A app.celery_app:celery_app" in command
        assert f" {process} " in command
        assert "alembic" not in command.lower()
        assert "uvicorn" not in command.lower()
        assert "app.main" not in command.lower()

        env = env_by_key(service)
        assert env["DATABASE_URL"]["fromDatabase"]["name"] in database_names
        for key in ("CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
            assert env[key]["fromService"] == {
                "type": redis_service["type"],
                "name": redis_name,
                "property": "connectionString",
            }

    from app.celery_app import celery_app

    assert TASK_NAME in celery_app.tasks
    scheduled_tasks = {
        entry["task"] for entry in celery_app.conf.beat_schedule.values()
    }
    assert scheduled_tasks == {TASK_NAME}

    wired_text = " ".join(
        [worker["startCommand"], beat["startCommand"], *scheduled_tasks]
    ).lower()
    for forbidden in ("dhl", "stripe", "paystack", "email", "brevo", "shipbubble"):
        assert forbidden not in wired_text


def test_render_api_and_checkout_consumers_share_supported_python_runtime() -> None:
    blueprint = yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}
    worker = services["shopsoma-staging-checkout-outbox-worker"]
    beat = services["shopsoma-staging-checkout-outbox-beat"]
    web = services["shopsoma-staging-api"]

    worker_version = env_by_key(worker)["PYTHON_VERSION"]["value"]
    beat_version = env_by_key(beat)["PYTHON_VERSION"]["value"]
    web_version = env_by_key(web)["PYTHON_VERSION"]["value"]

    assert web_version == worker_version == beat_version
    assert tuple(map(int, str(web_version).split("."))) >= (3, 10)
