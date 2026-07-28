"""Static parity and real PostgreSQL lifecycle for domestic rate evidence."""

import ast
import hashlib
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


ROOT = Path(__file__).resolve().parents[1]
REVISION = "d7b9f1c3e5a8"
PARENT = "c6a8e0f2b4d7"
FOUNDATION_PARENT = "b5f7d9a2c4e6"
FOUNDATION_SHA256 = "afa3d9dcc4fc6c29d5f0044888cf7ae368df9ed50f00986bdd1ed2c0d6650a1e"
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


def _source(revision_id: str = REVISION) -> str:
    revision = _scripts().get_revision(revision_id)
    assert revision is not None
    return Path(revision.path).read_text()


def _literal(name: str, revision_id: str = REVISION):
    tree = ast.parse(_source(revision_id))
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
    assert graph.get_revision(PARENT).down_revision == FOUNDATION_PARENT
    foundation = _source(PARENT).encode()
    assert hashlib.sha256(foundation).hexdigest() == FOUNDATION_SHA256
    source = _source()
    assert "Base.metadata" not in source
    assert "app.models" not in source
    assert "op.create_table" not in source
    for table in TABLES:
        assert f"CREATE TABLE {table}" in "\n".join(
            _literal("_CREATE_TABLE_SQL", PARENT)
        )


def test_domestic_rate_lease_checks_and_functions_have_exact_model_parity() -> None:
    from app.models.domestic_rate_quote import (
        DOMESTIC_RATE_TRIGGER_DDLS,
        DomesticRateAttempt,
    )

    constraints = {
        constraint.name: str(constraint.sqltext.compile(dialect=postgresql.dialect()))
        for constraint in DomesticRateAttempt.__table__.constraints
        if constraint.name
        in {
            "ck_domestic_rate_attempts_classification",
            "ck_domestic_rate_attempts_lifecycle",
        }
    }
    assert (
        _literal("_NEW_CLASSIFICATION_CHECK")
        == constraints["ck_domestic_rate_attempts_classification"]
    )
    assert (
        _literal("_NEW_LIFECYCLE_CHECK")
        == constraints["ck_domestic_rate_attempts_lifecycle"]
    )

    names = (
        "validate_domestic_rate_attempt_insert",
        "validate_domestic_rate_attempt_mutation",
        "validate_domestic_rate_attempt_response_shape",
    )
    model_functions = tuple(
        statement.replace("%%", "%")
        .strip()
        .replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
        for statement in DOMESTIC_RATE_TRIGGER_DDLS
        if any(f"CREATE FUNCTION {name}" in statement for name in names)
    )
    assert _literal("_NEW_FUNCTION_DDLS") == model_functions


def test_domestic_rate_migration_contains_only_normalized_safe_evidence() -> None:
    sql = "\n".join(
        _literal("_CREATE_TABLE_SQL", PARENT)
        + _literal("_CREATE_INDEX_SQL", PARENT)
        + _literal("_TRIGGER_DDLS", PARENT)
        + _literal("_NEW_FUNCTION_DDLS")
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
        "claim_expires_at := claimed_at_value + new.claim_ttl_seconds",
        "classification_value in ('pending','failure','abandoned')",
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

        migrate("upgrade", FOUNDATION_PARENT)

        def assert_tables(present: bool, leases: bool = False) -> None:
            target = create_engine(database_url)
            attempt_columns: set[str] = set()
            try:
                with target.connect() as connection:
                    names = set(inspect(connection).get_table_names())
                    intent_columns = {
                        column["name"]
                        for column in inspect(connection).get_columns(
                            "outbound_shipment_intents"
                        )
                    }
                    functions = set(
                        connection.execute(
                            text(
                                "SELECT proname FROM pg_proc WHERE proname LIKE "
                                "'validate_domestic_rate%' OR proname="
                                "'reject_domestic_rate_evidence_mutation'"
                            )
                        ).scalars()
                    )
                    if present:
                        attempt_columns = {
                            column["name"]
                            for column in inspect(connection).get_columns(
                                "domestic_rate_attempts"
                            )
                        }
                assert all((table in names) is present for table in TABLES)
                assert bool(functions) is present
                assert ("destination_snapshot_hash" in intent_columns) is present
                if present:
                    assert ("claim_ttl_seconds" in attempt_columns) is leases
                    assert ("claim_expires_at" in attempt_columns) is leases
            finally:
                target.dispose()

        assert_tables(False)
        migrate("upgrade", PARENT)
        assert_tables(True, leases=False)
        migrate("upgrade", REVISION)
        assert_tables(True, leases=True)
        migrate("downgrade", PARENT)
        assert_tables(True, leases=False)
        migrate("upgrade", REVISION)
        assert_tables(True, leases=True)
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
