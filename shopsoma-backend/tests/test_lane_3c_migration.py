"""Migration graph, source contract, and real cycle for Lane 2A-3C persistence."""

import os
from pathlib import Path
import subprocess
import uuid

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REVISION = "a4e6c8f1b3d5"
PARENT = "9d3e5f7a1b2c"


def _scripts() -> ScriptDirectory:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_lane_3c_is_only_linear_head() -> None:
    scripts = _scripts()
    assert scripts.get_heads() == [REVISION]
    assert scripts.get_revision(REVISION).down_revision == PARENT


def test_lane_3c_migration_is_additive_symmetric_private_and_narrow() -> None:
    revision = _scripts().get_revision(REVISION)
    assert revision is not None
    source = Path(revision.path).read_text()
    tables = (
        "hub_receipt_sessions",
        "hub_receipt_items",
        "hub_discrepancies",
        "hub_qc_sessions",
        "hub_qc_inspections",
        "hub_evidence",
        "hub_remediations",
    )
    assert source.count("op.create_table(") == len(tables)
    for table in tables:
        assert f'"{table}"' in source
        assert f'op.drop_table("{table}")' in source
    assert '"uq_inbound_transfers_hub_identity"' in source
    assert "FOR UPDATE" in source
    assert "CREATE TRIGGER" in source
    assert "DROP TRIGGER IF EXISTS" in source
    lowered = source.lower()
    for forbidden in (
        "dhl",
        "credential",
        "public_url",
        "upload_url",
        "signed_url",
        "file_data",
        "package_composition",
        "seal_number",
        "custody_event",
    ):
        assert forbidden not in lowered


def test_lane_3c_real_hermetic_postgresql_migration_cycle() -> None:
    """Exercise both directions on a fresh database that is always destroyed."""
    admin_url = "postgresql://shopsoma@127.0.0.1:55432/postgres"
    database = f"lane3c_cycle_{uuid.uuid4().hex}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        try:
            with admin.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{database}"'))
        except OperationalError as exc:
            pytest.skip(f"local PostgreSQL is unavailable: {exc}")

        database_url = f"postgresql://shopsoma@127.0.0.1:55432/{database}"
        env = os.environ.copy()
        env.update(DATABASE_URL=database_url, SECRET_KEY="***")

        def migrate(command: str, revision: str) -> None:
            result = subprocess.run(
                [str(BACKEND_ROOT / ".venv/bin/alembic"), command, revision],
                cwd=BACKEND_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            target = create_engine(database_url)
            try:
                with target.connect() as connection:
                    current = connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
                assert current == revision
            finally:
                target.dispose()

        migrate("upgrade", PARENT)
        sentinel_id = uuid.uuid4()
        sentinel_key = f"lane3c-existing-{uuid.uuid4().hex}"
        target = create_engine(database_url)
        try:
            with target.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO app_settings (id, key, value) "
                        "VALUES (:id, :key, :value)"
                    ),
                    {"id": sentinel_id, "key": sentinel_key, "value": "preexisting"},
                )
        finally:
            target.dispose()

        def assert_preexisting_snapshot_readable() -> None:
            target = create_engine(database_url)
            try:
                with target.connect() as connection:
                    value = connection.scalar(
                        text("SELECT value FROM app_settings WHERE id = :id"),
                        {"id": sentinel_id},
                    )
                assert value == "preexisting"
            finally:
                target.dispose()

        migrate("upgrade", REVISION)
        assert_preexisting_snapshot_readable()
        migrate("downgrade", PARENT)
        assert_preexisting_snapshot_readable()
        migrate("upgrade", REVISION)
        assert_preexisting_snapshot_readable()
    finally:
        try:
            with admin.connect() as connection:
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :database AND pid <> pg_backend_pid()"
                    ),
                    {"database": database},
                )
                connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
        finally:
            admin.dispose()
