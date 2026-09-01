"""Production Celery worker entrypoint used by worker and beat."""

from celery import Celery

from app.core.config import Settings, settings
from app.tasks.checkout_outbox import dispatch_checkout_outbox


def resolve_celery_connection_urls(config: Settings) -> tuple[str, str]:
    """Resolve dedicated Celery URLs with an explicit local Redis fallback."""
    redis_url = (config.REDIS_URL or "").strip()
    broker_url = config.CELERY_BROKER_URL.strip() or redis_url
    backend_url = config.CELERY_RESULT_BACKEND.strip() or redis_url

    if not broker_url or not backend_url:
        if config.ENVIRONMENT.lower() in {"development", "test"}:
            local_redis_url = (
                f"redis://{config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}"
            )
            broker_url = broker_url or local_redis_url
            backend_url = backend_url or local_redis_url
        else:
            raise ValueError(
                "Celery broker and result backend must be configured outside "
                "development/test"
            )

    return broker_url, backend_url


broker_url, backend_url = resolve_celery_connection_urls(settings)
celery_app = Celery(
    "shopsoma",
    broker=broker_url,
    backend=backend_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "dispatch-checkout-outbox": {
            "task": "app.tasks.checkout_outbox.dispatch_checkout_outbox",
            "schedule": 15.0,
        }
    },
)
celery_app.task(
    name="app.tasks.checkout_outbox.dispatch_checkout_outbox",
    ignore_result=True,
)(dispatch_checkout_outbox)
