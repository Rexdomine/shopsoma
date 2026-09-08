"""Lane 2A-3D migration graph, parity, scope, and real PostgreSQL cycle."""

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
REVISION = "b5f7d9a2c4e6"
PARENT = "a4e6c8f1b3d5"
TABLES = (
    "hub_packages",
    "hub_package_versions",
    "hub_package_items",
    "hub_package_seals",
    "custody_streams",
    "custody_events",
    "outbound_shipment_intents",
    "outbound_shipment_intent_invalidations",
)


def scripts() -> ScriptDirectory:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def _revision_source() -> str:
    revision = scripts().get_revision(REVISION)
    assert revision is not None
    return Path(revision.path).read_text()


def _literal_assignment(name: str):
    tree = ast.parse(_revision_source())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"missing static migration assignment {name}")


def test_lane_3d_has_linear_phase_2b_child() -> None:
    graph = scripts()
    assert graph.get_heads() == ["1c2b3d4e"]
    assert graph.get_revision("1c2b3d4e").down_revision == "e6f7a8b9c0d1"
    assert graph.get_revision("e6f7a8b9c0d1").down_revision == "d5e6f7a8b9c0"
    assert graph.get_revision("f9d1b3e5a7c9").down_revision == "e8c0a2d4f6b8"
    assert graph.get_revision("e8c0a2d4f6b8").down_revision == "d7b9f1c3e5a8"
    assert graph.get_revision(REVISION).down_revision == PARENT
    assert graph.get_revision("c6a8e0f2b4d7").down_revision == REVISION
    assert graph.get_revision("d7b9f1c3e5a8").down_revision == "c6a8e0f2b4d7"


def test_lane_3d_schema_and_guard_contract() -> None:
    create_sql = "\n".join(_literal_assignment("_CREATE_TABLE_SQL"))
    index_sql = "\n".join(_literal_assignment("_CREATE_INDEX_SQL"))
    trigger_sql = "\n".join(_literal_assignment("_TRIGGER_DDLS"))
    source = _revision_source()

    for table in TABLES:
        assert f"CREATE TABLE {table}" in create_sql
        assert f'op.drop_table("{table}")' in source
    for token in (
        "uq_hub_package_seals_active",
        "uq_outbound_shipment_intents_active",
    ):
        assert token in index_sql
    for token in (
        "FOR UPDATE",
        "s.state='qc_passed'",
        "i.decision='pass'",
        "current_version",
        "previous_event_id",
        "package quantity exceeds terminal passed inspection quantity",
        "custody chain fork",
        "active outbound intent must be invalidated before seal retirement",
        "pg_trigger_depth()",
        "clock_timestamp()",
    ):
        assert token in trigger_sql
    for token in (
        "evidence_ref",
        "evidence_hash",
        "destination_country_code",
    ):
        assert token in create_sql

    lowered = (create_sql + index_sql + trigger_sql).lower()
    for forbidden in (
        "dhl",
        "carrier_account",
        "account_number",
        "tracking_number",
        "label_url",
        "booking_id",
        "pickup_request",
        "public_url",
        "signed_url",
        "upload_url",
        "file_data",
    ):
        assert forbidden not in lowered


def test_lane_3d_trigger_bodies_have_exact_model_migration_parity() -> None:
    from app.models.package_custody import (
        PACKAGE_CUSTODY_DROP_DDLS,
        PACKAGE_CUSTODY_TRIGGER_DDLS,
    )

    expected_triggers = tuple(
        statement.replace("%%", "%").strip()
        for statement in PACKAGE_CUSTODY_TRIGGER_DDLS
    )
    historical_triggers = _literal_assignment("_TRIGGER_DDLS")
    current_intent_trigger = next(
        statement
        for statement in expected_triggers
        if statement.startswith("CREATE FUNCTION validate_outbound_intent_insert()")
    )
    current_custody_trigger = next(
        statement
        for statement in expected_triggers
        if statement.startswith("CREATE FUNCTION validate_custody_event_insert()")
    )
    historical_without_evolved_intent_or_custody = tuple(
        statement
        for statement in historical_triggers
        if not statement.startswith("CREATE FUNCTION validate_outbound_intent_insert()")
        and not statement.startswith("CREATE FUNCTION validate_custody_event_insert()")
    )
    current_without_evolved_intent_or_custody = tuple(
        statement
        for statement in expected_triggers
        if statement not in (current_intent_trigger, current_custody_trigger)
    )
    assert historical_without_evolved_intent_or_custody == current_without_evolved_intent_or_custody

    domestic_revision = scripts().get_revision("c6a8e0f2b4d7")
    assert domestic_revision is not None
    domestic_tree = ast.parse(Path(domestic_revision.path).read_text())

    def domestic_literal(name: str):
        for node in domestic_tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name
                for target in node.targets
            ):
                return ast.literal_eval(node.value)
        raise AssertionError(name)

    historical_intent_trigger = next(
        statement
        for statement in historical_triggers
        if statement.startswith("CREATE FUNCTION validate_outbound_intent_insert()")
    )
    assert historical_intent_trigger.replace(
        "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
    ) == domestic_literal("_RESTORE_OUTBOUND_INTENT_INSERT_DDL")
    assert (
        current_intent_trigger.replace(
            "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
        )
        == domestic_literal("_DESTINATION_SNAPSHOT_UPGRADE_DDLS")[-1]
    )
    repair_source = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "e6f7a8b9c0d1_repair_domestic_rate_custody_guards.py"
    ).read_text()
    assert current_custody_trigger.replace(
        "CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1
    ) in repair_source
    assert _literal_assignment("_DROP_FUNCTION_DDLS") == tuple(
        PACKAGE_CUSTODY_DROP_DDLS
    )
    created_functions = {
        statement.split("CREATE FUNCTION ", 1)[1].split("(", 1)[0]
        for statement in expected_triggers
        if statement.startswith("CREATE FUNCTION ")
    }
    dropped_functions = {
        statement.split("DROP FUNCTION IF EXISTS ", 1)[1].split("(", 1)[0]
        for statement in PACKAGE_CUSTODY_DROP_DDLS
    }
    assert dropped_functions == created_functions


def test_lane_3d_tables_and_indexes_have_exact_model_migration_parity() -> None:
    from app.models.package_custody import (
        CustodyEvent,
        CustodyStream,
        HubPackage,
        HubPackageItem,
        HubPackageSeal,
        HubPackageVersion,
        OutboundShipmentIntent,
        OutboundShipmentIntentInvalidation,
    )

    tables = (
        HubPackage.__table__,
        HubPackageVersion.__table__,
        HubPackageItem.__table__,
        HubPackageSeal.__table__,
        CustodyStream.__table__,
        CustodyEvent.__table__,
        OutboundShipmentIntent.__table__,
        OutboundShipmentIntentInvalidation.__table__,
    )
    dialect = postgresql.dialect()
    expected_tables = tuple(
        str(CreateTable(table).compile(dialect=dialect)).strip() for table in tables
    )
    expected_indexes = tuple(
        str(CreateIndex(index).compile(dialect=dialect)).strip()
        for table in tables
        for index in sorted(table.indexes, key=lambda candidate: candidate.name or "")
    )
    historical_tables = _literal_assignment("_CREATE_TABLE_SQL")
    evolved_prefix = "CREATE TABLE outbound_shipment_intents"
    assert tuple(
        statement
        for statement in historical_tables
        if not statement.startswith(evolved_prefix)
    ) == tuple(
        statement
        for statement in expected_tables
        if not statement.startswith(evolved_prefix)
    )
    historical_intent = next(
        statement
        for statement in historical_tables
        if statement.startswith(evolved_prefix)
    )
    current_intent = next(
        statement
        for statement in expected_tables
        if statement.startswith(evolved_prefix)
    )
    assert "destination_snapshot_hash" not in historical_intent
    assert "destination_snapshot_hash" in current_intent
    assert _literal_assignment("_CREATE_INDEX_SQL") == expected_indexes


def test_lane_3d_real_hermetic_postgresql_migration_cycle() -> None:
    """Upgrade/downgrade/upgrade on a fresh database and preserve old data."""
    config_spec = importlib.util.spec_from_file_location(
        "lane3d_test_config", ROOT / "tests/conftest.py"
    )
    assert config_spec is not None and config_spec.loader is not None
    test_config = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(test_config)

    base_url = make_url(test_config.TEST_DATABASE_URL)
    sync_driver = base_url.drivername.split("+", 1)[0]
    admin_url = base_url.set(drivername=sync_driver, database="postgres")
    database = f"shopsoma_lane3d_{uuid.uuid4().hex[:12]}"
    database_url = base_url.set(
        drivername=sync_driver, database=database
    ).render_as_string(hide_password=False)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    try:
        env = os.environ.copy()
        env.update(DATABASE_URL=database_url, SECRET_KEY="lane3d-migration-test-secret")

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
                    current = connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
                assert current == revision
            finally:
                target.dispose()

        migrate("upgrade", PARENT)
        sentinel_id = uuid.uuid4()
        sentinel_key = f"lane3d-existing-{uuid.uuid4().hex}"
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

        def assert_snapshot_and_schema(*, lane3d_present: bool) -> None:
            target = create_engine(database_url)
            try:
                with target.connect() as connection:
                    assert (
                        connection.scalar(
                            text("SELECT value FROM app_settings WHERE id=:id"),
                            {"id": sentinel_id},
                        )
                        == "preexisting"
                    )
                    names = set(inspect(connection).get_table_names())
                assert all((table in names) is lane3d_present for table in TABLES)
            finally:
                target.dispose()

        migrate("upgrade", REVISION)
        assert_snapshot_and_schema(lane3d_present=True)
        migrate("downgrade", PARENT)
        assert_snapshot_and_schema(lane3d_present=False)
        migrate("upgrade", REVISION)
        assert_snapshot_and_schema(lane3d_present=True)
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
