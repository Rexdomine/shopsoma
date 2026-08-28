"""Render startup entrypoint for staged checkout-prerequisite rollout."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services.orders.workflow_classification import (
    ClassificationRunIdentity,
    classify_workflow_batch,
    finalize_workflow_classification,
    start_workflow_classification_run,
)

ROOT = Path(__file__).resolve().parent
PREPARE_REVISION = "a1b2c3d4e5f6"
VALIDATE_REVISION = "a2b3c4d5e6f7"
DEFAULT_BATCH_SIZE = 1000


def _alembic_config(database_url: str | None = None) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
    return config


def _sync_database_url(database_url: str) -> str:
    url = make_url(database_url)
    driver = url.drivername.split("+", 1)[0]
    return url.set(drivername=driver).render_as_string(hide_password=False)


def _identity() -> ClassificationRunIdentity:
    return ClassificationRunIdentity(
        compatibility_writer_release_id=os.environ.get(
            "CHECKOUT_PREREQUISITE_COMPATIBILITY_RELEASE_ID",
            "render-startup",
        ),
        migration_revision=VALIDATE_REVISION,
        deployment_identity=os.environ.get("RENDER_GIT_COMMIT")
        or os.environ.get("RENDER_SERVICE_ID")
        or socket.gethostname(),
    )


def _cutover_already_complete(engine) -> bool:
    with engine.begin() as connection:
        run = connection.execute(
            text(
                "SELECT classification_cutover_at, classified_row_count, validated_constraints "
                "FROM order_workflow_migration_runs "
                "WHERE migration_revision=:revision "
                "ORDER BY classification_cutover_at DESC NULLS LAST, compatibility_writer_started_at DESC "
                "LIMIT 1"
            ),
            {"revision": VALIDATE_REVISION},
        ).one_or_none()
    return bool(
        run is not None
        and run.classification_cutover_at is not None
        and run.classified_row_count is not None
        and run.validated_constraints == "exact order/classification/owner reconciliation"
    )


def run(*, database_url: str | None = None, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
    database_url = database_url or os.environ["DATABASE_URL"]
    config = _alembic_config(database_url)
    command.upgrade(config, PREPARE_REVISION)
    engine = create_engine(_sync_database_url(database_url))
    try:
        if not _cutover_already_complete(engine):
            run_id = start_workflow_classification_run(engine, _identity())
            while classify_workflow_batch(engine, run_id, batch_size=batch_size):
                pass
            finalize_workflow_classification(engine, run_id)
    finally:
        engine.dispose()
    command.upgrade(config, "heads")


if __name__ == "__main__":
    run()
