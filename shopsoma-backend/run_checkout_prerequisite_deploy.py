"""Render startup entrypoint for staged checkout-prerequisite rollout."""

from __future__ import annotations

import os
import socket
from contextlib import contextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
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


def _database_revision_includes(config: Config, engine, revision: str) -> bool:
    with engine.connect() as connection:
        if not inspect(connection).has_table("alembic_version"):
            return False
        current_revisions = list(
            connection.execute(text("SELECT version_num FROM alembic_version"))
            .scalars()
            .all()
        )
    if not current_revisions:
        return False
    script = ScriptDirectory.from_config(config)
    pending = [script.get_revision(current) for current in current_revisions]
    seen: set[str] = set()
    while pending:
        current = pending.pop()
        if current is None or current.revision in seen:
            continue
        if current.revision == revision:
            return True
        seen.add(current.revision)
        pending.extend(
            script.get_revision(value)
            for value in current._normalized_down_revisions
            if value
        )
    return False


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


@contextmanager
def _hold_cutover_validation_lock(engine):
    connection = engine.connect()
    transaction = connection.begin()
    try:
        connection.execute(text("LOCK TABLE orders IN SHARE ROW EXCLUSIVE MODE"))
        connection.execute(
            text(
                "LOCK TABLE order_workflow_classifications "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )
        connection.execute(
            text(
                "LOCK TABLE order_current_owners "
                "IN SHARE ROW EXCLUSIVE MODE"
            )
        )
        yield connection
        transaction.commit()
    except Exception:
        transaction.rollback()
        raise
    finally:
        connection.close()


def run(*, database_url: str | None = None, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
    database_url = database_url or os.environ["DATABASE_URL"]
    config = _alembic_config(database_url)
    engine = create_engine(_sync_database_url(database_url))
    try:
        if not _database_revision_includes(config, engine, PREPARE_REVISION):
            command.upgrade(config, PREPARE_REVISION)
        if not _cutover_already_complete(engine):
            run_id = start_workflow_classification_run(engine, _identity())
            while classify_workflow_batch(engine, run_id, batch_size=batch_size):
                pass
            with _hold_cutover_validation_lock(engine) as locked_connection:
                finalize_workflow_classification(engine, run_id)
                config.attributes["connection"] = locked_connection
                try:
                    command.upgrade(config, "heads")
                finally:
                    config.attributes.pop("connection", None)
            return
    finally:
        engine.dispose()
    command.upgrade(config, "heads")


if __name__ == "__main__":
    run()
