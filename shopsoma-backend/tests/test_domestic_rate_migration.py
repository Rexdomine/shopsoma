"""Static parity and real PostgreSQL lifecycle for domestic rate evidence."""

import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import uuid

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateIndex, CreateTable


ROOT = Path(__file__).resolve().parents[1]
REVISION = "c6a8e0f2b4d7"
PARENT = "b5f7d9a2c4e6"
TABLES = (
    "outbound_intent_rate_guards",
    "domestic_rate_attempts",
    "domestic_rate_responses",
    "domestic_rate_offers",
)


def _scripts() -> ScriptDirectory:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def _source() -> str:
    revision = _scripts().get_revision(REVISION)
    assert revision is not None
    return Path(revision.path).read_text()


def _literal(name: str):
    tree = ast.parse(_source())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing static assignment {name}")


def test_domestic_rate_migration_is_the_single_linear_static_head() -> None:
    graph = _scripts()
    assert graph.get_heads() == [REVISION]
    assert graph.get_revision(REVISION).down_revision == PARENT
    source = _source()
    assert "Base.metadata" not in source
    assert "app.models" not in source
    assert "op.create_table" not in source
    for table in TABLES:
        assert f"CREATE TABLE {table}" in "\n".join(_literal("_CREATE_TABLE_SQL"))
        assert f'op.drop_table("{table}")' in source


def test_domestic_rate_tables_indexes_and_triggers_have_exact_static_parity() -> None:
    from app.models.domestic_rate_quote import (
        DOMESTIC_RATE_DROP_DDLS,
        DOMESTIC_RATE_TRIGGER_DDLS,
        DomesticRateAttempt,
        DomesticRateOffer,
        DomesticRateResponse,
        OutboundIntentRateGuard,
    )

    tables = (
        OutboundIntentRateGuard.__table__,
        DomesticRateAttempt.__table__,
        DomesticRateResponse.__table__,
        DomesticRateOffer.__table__,
    )
    dialect = postgresql.dialect()
    assert _literal("_CREATE_TABLE_SQL") == tuple(
        str(CreateTable(table).compile(dialect=dialect)).strip() for table in tables
    )
    assert _literal("_CREATE_INDEX_SQL") == tuple(
        str(CreateIndex(index).compile(dialect=dialect)).strip()
        for table in tables
        for index in sorted(table.indexes, key=lambda item: item.name or "")
    )
    assert _literal("_TRIGGER_DDLS") == tuple(
        statement.replace("%%", "%").strip() for statement in DOMESTIC_RATE_TRIGGER_DDLS
    )
    assert _literal("_DROP_FUNCTION_DDLS") == DOMESTIC_RATE_DROP_DDLS
    from app.models.package_custody import PACKAGE_CUSTODY_TRIGGER_DDLS

    original_invalidation = next(
        statement.replace("%%", "%").strip()
        for statement in PACKAGE_CUSTODY_TRIGGER_DDLS
        if statement.strip().startswith(
            "CREATE FUNCTION validate_outbound_intent_invalidation_insert()"
        )
    )
    assert _literal(
        "_RESTORE_OUTBOUND_INVALIDATION_DDL"
    ) == original_invalidation.replace(
        "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
    )


def test_domestic_rate_migration_contains_only_normalized_safe_evidence() -> None:
    sql = "\n".join(
        _literal("_CREATE_TABLE_SQL")
        + _literal("_CREATE_INDEX_SQL")
        + _literal("_TRIGGER_DDLS")
    ).lower()
    for required in (
        "on delete restrict",
        "numeric(18, 4)",
        "environment = 'sandbox'",
        "provider = 'dhl'",
        "destination_country_code = 'ng'",
        "rate evidence is append-only",
        "success response requires at least one offer",
        "no-service response cannot contain offers",
        "expires_at = received_at + ttl_seconds * interval '1 second'",
    ):
        assert required in sql
    for forbidden in (
        "json",
        "payload",
        "credential",
        "account_number",
        "account_value",
        "api_key",
        "password",
        "opaque_value",
        "seal_value",
        "destination_name",
        "destination_phone",
        "destination_address",
    ):
        assert forbidden not in sql


def test_domestic_rate_real_upgrade_downgrade_upgrade_cycle() -> None:
    config_spec = importlib.util.spec_from_file_location(
        "rate_test_config", ROOT / "tests/conftest.py"
    )
    assert config_spec is not None and config_spec.loader is not None
    test_config = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(test_config)

    base_url = make_url(test_config.TEST_DATABASE_URL)
    sync_driver = base_url.drivername.split("+", 1)[0]
    admin_url = base_url.set(drivername=sync_driver, database="postgres")
    database = f"shopsoma_rate_cycle_{uuid.uuid4().hex[:12]}"
    database_url = base_url.set(
        drivername=sync_driver, database=database
    ).render_as_string(hide_password=False)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    try:
        env = os.environ.copy()
        env.update(DATABASE_URL=database_url, SECRET_KEY="rate-migration-test-secret")

        def migrate(command: str, revision: str) -> None:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", command, revision],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            target = create_engine(database_url)
            try:
                with target.connect() as connection:
                    assert (
                        connection.scalar(
                            text("SELECT version_num FROM alembic_version")
                        )
                        == revision
                    )
            finally:
                target.dispose()

        migrate("upgrade", PARENT)

        def assert_tables(present: bool) -> None:
            target = create_engine(database_url)
            try:
                with target.connect() as connection:
                    names = set(inspect(connection).get_table_names())
                    functions = set(
                        connection.execute(
                            text(
                                "SELECT proname FROM pg_proc WHERE proname LIKE "
                                "'validate_domestic_rate%' OR proname="
                                "'reject_domestic_rate_evidence_mutation'"
                            )
                        ).scalars()
                    )
                assert all((table in names) is present for table in TABLES)
                assert bool(functions) is present
            finally:
                target.dispose()

        migrate("upgrade", REVISION)
        assert_tables(True)
        migrate("downgrade", PARENT)
        assert_tables(False)
        migrate("upgrade", REVISION)
        assert_tables(True)
    finally:
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname=:database AND pid<>pg_backend_pid()"
                ),
                {"database": database},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database}"'))
        admin.dispose()
