"""Production Celery worker entrypoint used by worker and beat."""

from celery import Celery

from app.core.config import settings
from app.tasks.checkout_outbox import dispatch_checkout_outbox


celery_app = Celery(
    "shopsoma",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
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
