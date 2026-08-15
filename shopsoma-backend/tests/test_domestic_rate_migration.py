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
from sqlalchemy import CheckConstraint, create_engine, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


ROOT = Path(__file__).resolve().parents[1]
HEAD = "c4d5e6f7a8b9"
CURRENT_HEAD_PARENT = "b3c4d5e6f7a8"
PREVIOUS_HEAD = "a2b3c4d5e6f7"
HEAD_PARENT = "a1b2c3d4e5f6"
HEAD_GRANDPARENT = "a0b1c2d3e4f5"
F9_REVISION = "f9d1b3e5a7c9"
QUOTE_REVISION = "e8c0a2d4f6b8"
REVISION = "d7b9f1c3e5a8"
PARENT = "c6a8e0f2b4d7"
FOUNDATION_PARENT = "b5f7d9a2c4e6"
TABLES = (
    "outbound_intent_rate_guards",
    "domestic_rate_attempts",
    "domestic_rate_responses",
    "domestic_rate_offers",
)

_PACKAGE_SPEC = importlib.util.spec_from_file_location(
    "rate_migration_package_helpers",
    Path(__file__).with_name("test_package_custody_persistence.py"),
)
assert _PACKAGE_SPEC is not None and _PACKAGE_SPEC.loader is not None
_PACKAGE = importlib.util.module_from_spec(_PACKAGE_SPEC)
_PACKAGE_SPEC.loader.exec_module(_PACKAGE)


async def _seed_valid_outbound_intent(database_url: str) -> uuid.UUID:
    """Seed one legal ready package and intent using the existing fixture graph."""
    from app.models.user import User, UserRole
    from app.models.vendor import KYCStatus, Vendor

    engine = create_async_engine(
        make_url(database_url).set(drivername="postgresql+asyncpg")
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessions() as session:
            customer = User(
                id=uuid.uuid4(),
                email=f"rate-customer-{uuid.uuid4().hex}@example.test",
                hashed_password="not-used",
                full_name="Rate Migration Customer",
                role=UserRole.CUSTOMER,
                email_verified=True,
                is_active=True,
            )
            operator = User(
                id=uuid.uuid4(),
                email=f"rate-operator-{uuid.uuid4().hex}@example.test",
                hashed_password="not-used",
                full_name="Rate Migration Operator",
                role=UserRole.VENDOR,
                email_verified=True,
                is_active=True,
            )
            session.add_all([customer, operator])
            await session.flush()
            vendor = Vendor(
                id=uuid.uuid4(),
                user_id=operator.id,
                business_name="Rate Migration Vendor",
                kyc_status=KYCStatus.APPROVED,
                approved=True,
            )
            session.add(vendor)
            await session.flush()
            graph = await _PACKAGE._passed_graph(
                session,
                {"user": operator, "vendor": vendor},
                {"user": customer},
                quantity=1,
            )
            package, _version, _item, seal = await _PACKAGE._ready_package(
                session, graph, quantity=1
            )
            sentinel_id = uuid.uuid4()
            await session.execute(
                text(
                    """INSERT INTO outbound_shipment_intents (
                        id, package_id, package_version, seal_id, order_id,
                        origin_hub_id, destination_name, destination_phone,
                        destination_address_line1, destination_address_line2,
                        destination_city, destination_state,
                        destination_postal_code, destination_country_code,
                        source_command, idempotency_key, created_by_id
                    ) VALUES (
                        :id, :package_id, 1, :seal_id, :order_id,
                        :hub_id, 'Migration Sentinel', '+234****0000',
                        '1 Sentinel Street', 'Suite 2', 'Lagos', 'Lagos',
                        '100001', 'NG', 'migration-test', 'migration-sentinel',
                        :created_by_id
                    )"""
                ),
                {
                    "id": sentinel_id,
                    "package_id": package.id,
                    "seal_id": seal.id,
                    "order_id": graph["order"].id,
                    "hub_id": graph["hub"].id,
                    "created_by_id": graph["operator_id"],
                },
            )
            await session.commit()
            return sentinel_id
    finally:
        await engine.dispose()


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
    assert graph.get_heads() == [HEAD]
    assert graph.get_revision(HEAD).down_revision == CURRENT_HEAD_PARENT
    assert graph.get_revision(CURRENT_HEAD_PARENT).down_revision == PREVIOUS_HEAD
    assert graph.get_revision(PREVIOUS_HEAD).down_revision == HEAD_PARENT
    assert graph.get_revision(HEAD_PARENT).down_revision == HEAD_GRANDPARENT
    assert graph.get_revision(HEAD_GRANDPARENT).down_revision == F9_REVISION
    assert graph.get_revision(F9_REVISION).down_revision == QUOTE_REVISION
    assert graph.get_revision(QUOTE_REVISION).down_revision == REVISION
    assert graph.get_revision(REVISION).down_revision == PARENT
    assert graph.get_revision(PARENT).down_revision == FOUNDATION_PARENT
    source = _source()
    assert "Base.metadata" not in source
    assert "app.models" not in source
    assert "op.create_table" not in source
    for table in TABLES:
        assert f"CREATE TABLE {table}" in "\n".join(
            _literal("_CREATE_TABLE_SQL", PARENT)
        )

    destination_upgrade = _literal("_DESTINATION_SNAPSHOT_UPGRADE_DDLS", PARENT)
    disable_index = next(
        index
        for index, statement in enumerate(destination_upgrade)
        if "DISABLE TRIGGER tr_outbound_shipment_intents_immutable" in statement
    )
    backfill_index = next(
        index
        for index, statement in enumerate(destination_upgrade)
        if statement.startswith("UPDATE outbound_shipment_intents")
    )
    enable_index = next(
        index
        for index, statement in enumerate(destination_upgrade)
        if "ENABLE TRIGGER tr_outbound_shipment_intents_immutable" in statement
    )
    assert disable_index < backfill_index < enable_index


def test_domestic_rate_lease_checks_and_functions_have_exact_model_parity() -> None:
    from app.models.domestic_rate_quote import (
        DOMESTIC_RATE_TRIGGER_DDLS,
        DomesticRateAttempt,
    )

    all_constraints = {
        constraint.name: str(constraint.sqltext.compile(dialect=postgresql.dialect()))
        for constraint in DomesticRateAttempt.__table__.constraints
        if isinstance(constraint, CheckConstraint) and constraint.name
    }
    constraints = {
        name: all_constraints[name]
        for name in (
            "ck_domestic_rate_attempts_classification",
            "ck_domestic_rate_attempts_lifecycle",
        )
    }
    parent_attempt_table = next(
        statement
        for statement in _literal("_CREATE_TABLE_SQL", PARENT)
        if statement.startswith("CREATE TABLE domestic_rate_attempts")
    )
    for column_sql in (
        "initiating_actor_type VARCHAR(30) NOT NULL",
        "initiating_actor_id VARCHAR(200) NOT NULL",
        "source_command VARCHAR(100) NOT NULL",
    ):
        assert column_sql in parent_attempt_table
    assert (
        "CONSTRAINT ck_domestic_rate_attempts_identifiers CHECK ("
        + all_constraints["ck_domestic_rate_attempts_identifiers"]
        + ")"
        in parent_attempt_table
    )
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
        "initiating_actor_type",
        "initiating_actor_id",
        "source_command",
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


async def test_domestic_rate_real_upgrade_downgrade_upgrade_cycle() -> None:
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

        # Seed through the repository's legal package fixture at the current head,
        # then return to the pre-rate foundation. The subsequent path remains the
        # real foundation -> parent -> lease revision migration cycle, with this
        # row pre-existing when the destination hash is introduced.
        migrate("upgrade", HEAD)
        sentinel_id = await _seed_valid_outbound_intent(database_url)
        migrate("downgrade", FOUNDATION_PARENT)

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
        target = create_engine(database_url)
        try:
            with target.connect() as connection:
                snapshot_hash = connection.scalar(
                    text(
                        "SELECT destination_snapshot_hash "
                        "FROM outbound_shipment_intents WHERE id=:id"
                    ),
                    {"id": sentinel_id},
                )
                assert isinstance(snapshot_hash, str)
                assert len(snapshot_hash) == 64
        finally:
            target.dispose()
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
