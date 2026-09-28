"""Milestone 2 sequential migration and downgrade-safety contracts."""

import ast
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from threading import Event
import uuid
from datetime import timedelta
from decimal import Decimal

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session


ROOT = Path(__file__).parents[1]
REVISIONS = (
    "a0b1c2d3e4f5",
    "a1b2c3d4e5f6",
    "a2b3c4d5e6f7",
)
MILESTONE_FOUR_REVISION = "b3c4d5e6f7a8"
FREE_SHIPPING_REVISION = "c4d5e6f7a8b9"
PREVIOUS_HEAD_REVISION = "e6f7a8b9c0d1"
CURRENT_HEAD_REVISION = "v5w6x7y8z9a0"


def _script():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_milestone_two_revisions_are_sequential_from_current_head() -> None:
    script = _script()
    revisions = [script.get_revision(revision) for revision in REVISIONS]
    assert [revision.down_revision for revision in revisions] == [
        "f9d1b3e5a7c9",
        REVISIONS[0],
        REVISIONS[1],
    ]
    milestone_four = script.get_revision(MILESTONE_FOUR_REVISION)
    assert milestone_four.down_revision == REVISIONS[-1]
    free_shipping = script.get_revision(FREE_SHIPPING_REVISION)
    assert free_shipping.down_revision == MILESTONE_FOUR_REVISION
    current = script.get_revision(CURRENT_HEAD_REVISION)
    assert current.down_revision == "u4v5w6x7y8z9"
    assert script.get_revision("n1o2p3q4r5s6").down_revision == "m0n1o2p3q4r5"
    previous_head = script.get_revision(PREVIOUS_HEAD_REVISION)
    assert previous_head.down_revision == "d5e6f7a8b9c0"
    assert script.get_revision("d5e6f7a8b9c0").down_revision == FREE_SHIPPING_REVISION
    assert script.get_current_head() == CURRENT_HEAD_REVISION


def test_expand_validate_contract_and_safe_downgrade_are_frozen() -> None:
    script = _script()
    sources = [
        Path(script.get_revision(revision).path).read_text() for revision in REVISIONS
    ]
    combined = "\n".join(sources)
    for table in (
        "checkout_shipping_estimates",
        "checkout_shipping_estimate_options",
        "checkout_shipping_estimate_selections",
        "order_current_owners",
        "order_guest_capabilities",
        "order_inventory_coverage",
        "order_workflow_migration_runs",
        "order_workflow_classifications",
    ):
        assert table in combined
    assert "NOT VALID" in combined
    assert "VALIDATE CONSTRAINT" in combined
    assert "refusing destructive Milestone 2 downgrade" in combined
    assert "legacy_ambiguous_quarantined" in combined
    validate_source = sources[-1]
    assert "UPDATE orders SET" not in validate_source
    assert "FOR candidate IN" not in validate_source
    assert "classification reconciliation incomplete" in validate_source


def test_migrations_are_self_contained_and_import_no_application_modules() -> None:
    script = _script()
    for revision in REVISIONS:
        source = Path(script.get_revision(revision).path).read_text()
        tree = ast.parse(source)
        application_imports = [
            ast.get_source_segment(source, node)
            for node in ast.walk(tree)
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and (node.module == "app" or node.module.startswith("app."))
            )
            or (
                isinstance(node, ast.Import)
                and any(
                    alias.name == "app" or alias.name.startswith("app.")
                    for alias in node.names
                )
            )
        ]
        assert application_imports == []


def _run_alembic(database_url: str, *arguments: str, expect_success: bool = True):
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if expect_success:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture
def disposable_m2_database():
    configured = os.environ.get("DATABASE_URL")
    if not configured:
        pytest.skip("DATABASE_URL is required for PostgreSQL migration evidence")
    app_url = make_url(configured).set(drivername="postgresql+asyncpg")
    sync_url = app_url.set(drivername="postgresql+psycopg2")
    database_name = f"shopsoma_m2_{uuid.uuid4().hex[:12]}"
    admin = create_engine(
        sync_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    try:
        yield (
            app_url.set(database=database_name).render_as_string(hide_password=False),
            sync_url.set(database=database_name),
        )
    finally:
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity WHERE datname=:name"
                ),
                {"name": database_name},
            )
            connection.execute(text(f'DROP DATABASE "{database_name}"'))
        admin.dispose()


def test_real_postgresql_pre_writer_cycle_and_populated_refusal(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    _run_alembic(app_url, "downgrade", "f9d1b3e5a7c9")
    _run_alembic(app_url, "upgrade", REVISIONS[-1])

    engine = create_engine(sync_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO order_workflow_migration_runs "
                "(id,compatibility_writer_release_id,compatibility_writer_started_at,"
                "migration_revision,deployment_identity) "
                "VALUES (:id,'test-writer',statement_timestamp(),"
                "'a2b3c4d5e6f7','test')"
            ),
            {"id": uuid.uuid4()},
        )
    failed = _run_alembic(app_url, "downgrade", "f9d1b3e5a7c9", expect_success=False)
    assert failed.returncode != 0
    assert "refusing destructive Milestone 2 downgrade" in failed.stdout + failed.stderr
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM order_workflow_migration_runs")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == REVISIONS[-1]
        )
    engine.dispose()


def test_f9_program_is_preserved_and_downgrade_restores_exact_topology(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", "f9d1b3e5a7c9")
    engine = create_engine(sync_url)

    def function_definitions(connection):
        return dict(
            connection.execute(
                text(
                    "SELECT proname,pg_get_functiondef(oid) FROM pg_proc "
                    "WHERE proname IN ('validate_stock_reservation_write',"
                    "'validate_payment_attempt_write')"
                )
            ).all()
        )

    def trigger_program(connection):
        return {
            (row[0], row[1]): (row[2], row[3])
            for row in connection.execute(
                text(
                    "SELECT c.relname,t.tgname,p.proname,pg_get_triggerdef(t.oid) "
                    "FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                    "JOIN pg_proc p ON p.oid=t.tgfoid "
                    "WHERE c.relname IN ('stock_reservations','payment_attempts') "
                    "AND NOT t.tgisinternal"
                )
            ).all()
        }

    with engine.connect() as connection:
        predecessor_functions = function_definitions(connection)
        predecessor_triggers = trigger_program(connection)
    assert set(predecessor_functions) == {
        "validate_stock_reservation_write",
        "validate_payment_attempt_write",
    }
    assert (
        predecessor_triggers[("stock_reservations", "trg_stock_reservations_validate")][
            0
        ]
        == "validate_stock_reservation_write"
    )
    assert (
        predecessor_triggers[("payment_attempts", "trg_payment_attempts_validate")][0]
        == "validate_payment_attempt_write"
    )

    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    sources = [
        Path(_script().get_revision(revision).path)
        .read_text()
        .split("def downgrade", 1)[0]
        for revision in REVISIONS
    ]
    upgrade_source = "\n".join(sources)
    expected_functions = set(
        re.findall(r"CREATE (?:OR REPLACE )?FUNCTION\s+([a-z_]+)", upgrade_source)
    )
    expected_functions.remove("protect_order_current_owner")
    expected_triggers = set(
        re.findall(r"CREATE (?:CONSTRAINT )?TRIGGER\s+([a-z_]+)", upgrade_source)
    )
    expected_triggers -= {
        "order_guest_capabilities_no_delete",
        "order_current_owners_identity_immutable",
    }
    with engine.connect() as connection:
        assert function_definitions(connection) == predecessor_functions
        installed_functions = set(
            connection.execute(
                text("SELECT proname FROM pg_proc WHERE proname = ANY(:names)"),
                {"names": sorted(expected_functions)},
            ).scalars()
        )
        installed_triggers = set(
            connection.execute(
                text(
                    "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
                    "AND tgname = ANY(:names)"
                ),
                {"names": sorted(expected_triggers)},
            ).scalars()
        )
        head_triggers = trigger_program(connection)
    assert installed_functions == expected_functions
    assert installed_triggers == expected_triggers
    for operation in ("insert", "update"):
        assert (
            head_triggers[
                (
                    "stock_reservations",
                    f"trg_stock_reservations_validate_legacy_{operation}",
                )
            ][0]
            == "validate_stock_reservation_write"
        )
    assert (
        head_triggers[("stock_reservations", "trg_stock_reservations_validate_delete")][
            0
        ]
        == "validate_stock_reservation_write"
    )
    for operation in ("insert", "update"):
        assert (
            head_triggers[
                (
                    "payment_attempts",
                    f"trg_payment_attempts_validate_legacy_{operation}",
                )
            ][0]
            == "validate_payment_attempt_write"
        )
    assert (
        head_triggers[("payment_attempts", "trg_payment_attempts_validate_delete")][0]
        == "validate_payment_attempt_write"
    )
    for table in ("stock_reservations", "payment_attempts"):
        for operation in ("insert", "update"):
            definition = head_triggers[
                (table, f"trg_{table}_validate_legacy_{operation}")
            ][1]
            assert f"BEFORE {operation.upper()}" in definition
            if operation == "insert":
                assert "old.workflow_cohort" not in definition.lower()
    assert (
        "BEFORE DELETE"
        in head_triggers[
            ("stock_reservations", "trg_stock_reservations_validate_delete")
        ][1]
    )
    assert (
        "BEFORE DELETE"
        in head_triggers[("payment_attempts", "trg_payment_attempts_validate_delete")][
            1
        ]
    )

    _run_alembic(app_url, "downgrade", REVISIONS[1])
    with engine.connect() as connection:
        restored_owner_function = connection.scalar(
            text(
                "SELECT pg_get_functiondef(oid) FROM pg_proc "
                "WHERE proname='protect_order_current_owner'"
            )
        )
        restored_triggers = {
            row[0]: row[1]
            for row in connection.execute(
                text(
                    "SELECT t.tgname,p.proname FROM pg_trigger t "
                    "JOIN pg_proc p ON p.oid=t.tgfoid "
                    "WHERE NOT t.tgisinternal AND t.tgname IN "
                    "('order_guest_capabilities_no_delete',"
                    "'order_current_owners_identity_immutable')"
                )
            )
        }
        restored_claim_fk = connection.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname='fk_order_current_owners_claim_capability'"
            )
        )
    assert "immutable original owner identity" in restored_owner_function
    assert restored_triggers == {
        "order_guest_capabilities_no_delete": (
            "protect_append_only_checkout_prerequisite"
        ),
        "order_current_owners_identity_immutable": "protect_order_current_owner",
    }
    assert restored_claim_fk == (
        "FOREIGN KEY (claim_capability_id) REFERENCES "
        "order_guest_capabilities(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED "
        "NOT VALID"
    )

    _run_alembic(app_url, "downgrade", "f9d1b3e5a7c9")
    with engine.connect() as connection:
        assert function_definitions(connection) == predecessor_functions
        assert trigger_program(connection) == predecessor_triggers
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM pg_proc WHERE proname IN "
                    "('validate_domestic_checkout_reservation_write',"
                    "'validate_domestic_checkout_payment_attempt_write')"
                )
            )
            == 0
        )
    engine.dispose()


def test_postgresql_compatibility_writer_classifies_concurrent_inserts(
    disposable_m2_database,
) -> None:
    from app.services.orders.workflow_classification import (
        ClassificationRunIdentity,
        classify_workflow_batch,
        finalize_workflow_classification,
        start_workflow_classification_run,
    )

    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[1])
    engine = create_engine(sync_url)
    customer_ids = (uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    historical_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) VALUES "
                "(:one,:one_email,'One','CUSTOMER',false),"
                "(:two,:two_email,'Two','CUSTOMER',false),"
                "(:historical,:historical_email,'Historical','CUSTOMER',false)"
            ),
            {
                "one": customer_ids[0],
                "one_email": f"m2-{uuid.uuid4().hex}@example.test",
                "two": customer_ids[1],
                "two_email": f"m2-{uuid.uuid4().hex}@example.test",
                "historical": customer_ids[2],
                "historical_email": f"m2-{uuid.uuid4().hex}@example.test",
            },
        )
        connection.execute(
            text(
                "INSERT INTO orders "
                "(id,order_number,customer_id,subtotal,shipping_cost,tax_amount,"
                "discount_amount,total_amount,payment_status,fulfillment_status) "
                "VALUES (:id,:number,:customer,10,0,0,0,10,'PENDING','order_received')"
            ),
            {
                "id": historical_id,
                "number": f"M2-{uuid.uuid4().hex[:12]}",
                "customer": customer_ids[2],
            },
        )

    run_id = start_workflow_classification_run(
        engine,
        ClassificationRunIdentity("test-writer", REVISIONS[1], "test-deployment"),
    )
    order_ids = (uuid.uuid4(), uuid.uuid4())

    def insert_order(index: int) -> None:
        worker = create_engine(sync_url)
        try:
            with worker.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO orders "
                        "(id,order_number,customer_id,subtotal,shipping_cost,tax_amount,"
                        "discount_amount,total_amount,payment_status,fulfillment_status) "
                        "VALUES (:id,:number,:customer,10,0,0,0,10,'PENDING',"
                        "'order_received')"
                    ),
                    {
                        "id": order_ids[index],
                        "number": f"M2-{uuid.uuid4().hex[:12]}",
                        "customer": customer_ids[index],
                    },
                )
        finally:
            worker.dispose()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(insert_order, range(2)))

    with pytest.raises(
        Exception, match="compatibility writer requires legacy workflow truth"
    ):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO orders "
                    "(id,order_number,customer_id,workflow_cohort,workflow_policy_version,"
                    "checkout_access_mode,subtotal,shipping_cost,tax_amount,discount_amount,"
                    "total_amount,payment_status,fulfillment_status) VALUES "
                    "(:id,:number,:customer,'domestic_checkout_v1','domestic_checkout_v1',"
                    "'authenticated',10,0,0,0,10,'PENDING','order_received')"
                ),
                {
                    "id": uuid.uuid4(),
                    "number": f"M2-{uuid.uuid4().hex[:12]}",
                    "customer": customer_ids[0],
                },
            )

    with engine.begin() as connection:
        classification_before = connection.execute(
            text(
                "SELECT order_id,cohort,policy_version,access_mode,evidence_kind,"
                "evidence_reference,migration_run_id,classified_by,notes_hash "
                "FROM order_workflow_classifications ORDER BY order_id"
            )
        ).all()
        _assert_rejected(
            connection,
            "UPDATE orders SET workflow_cohort='legacy_ambiguous_quarantined' "
            "WHERE id=:id",
            {"id": historical_id},
        )
        _assert_rejected(
            connection,
            "UPDATE orders SET workflow_policy_version='changed' WHERE id=:id",
            {"id": order_ids[0]},
        )
        assert connection.scalar(
            text("SELECT count(*) FROM order_workflow_classifications")
        ) == len(classification_before)

    assert classify_workflow_batch(engine, run_id, batch_size=1) == 1
    assert classify_workflow_batch(engine, run_id, batch_size=1) == 0
    assert finalize_workflow_classification(engine, run_id) == 3
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    with engine.connect() as connection:
        stable_head_before = (
            connection.execute(
                text(
                    "SELECT order_id,cohort,policy_version,access_mode,evidence_kind,"
                    "evidence_reference,migration_run_id,classified_by,notes_hash "
                    "FROM order_workflow_classifications ORDER BY order_id"
                )
            ).all(),
            connection.execute(
                text(
                    "SELECT id,high_watermark_created_at,high_watermark_order_id,"
                    "classified_row_count FROM order_workflow_migration_runs ORDER BY id"
                )
            ).all(),
            connection.execute(
                text(
                    "SELECT order_id,original_customer_id,current_authenticated_user_id,"
                    "row_version FROM order_current_owners ORDER BY order_id"
                )
            ).all(),
        )
    _run_alembic(app_url, "upgrade", REVISIONS[-1])

    with engine.connect() as connection:
        stable_head_after = (
            connection.execute(
                text(
                    "SELECT order_id,cohort,policy_version,access_mode,evidence_kind,"
                    "evidence_reference,migration_run_id,classified_by,notes_hash "
                    "FROM order_workflow_classifications ORDER BY order_id"
                )
            ).all(),
            connection.execute(
                text(
                    "SELECT id,high_watermark_created_at,high_watermark_order_id,"
                    "classified_row_count FROM order_workflow_migration_runs ORDER BY id"
                )
            ).all(),
            connection.execute(
                text(
                    "SELECT order_id,original_customer_id,current_authenticated_user_id,"
                    "row_version FROM order_current_owners ORDER BY order_id"
                )
            ).all(),
        )
        rows = connection.execute(
            text(
                "SELECT o.id,o.workflow_cohort,o.workflow_policy_version,"
                "o.checkout_access_mode,owner.order_id,c.order_id "
                "FROM orders o "
                "LEFT JOIN order_current_owners owner ON owner.order_id=o.id "
                "LEFT JOIN order_workflow_classifications c ON c.order_id=o.id "
                "WHERE o.id IN (:one,:two) ORDER BY o.id"
            ),
            {"one": order_ids[0], "two": order_ids[1]},
        ).all()
        historical = connection.execute(
            text(
                "SELECT o.workflow_cohort,o.workflow_policy_version,o.checkout_access_mode,"
                "c.evidence_kind,c.evidence_reference,…38882 tokens truncated…ssert script.get_revision("a1b2c3d4e5f6").down_revision == EXPAND_REVISION
    assert script.get_revision(EXPAND_REVISION).down_revision == F9_REVISION
    assert script.get_revision(F9_REVISION).down_revision == REVISION
    revision = script.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PARENT

    source = MIGRATION.read_text()
    assert "Base.metadata" not in source
    assert "app.models" not in source
    assert "op.create_table" not in source
    assert 'down_revision = "d7b9f1c3e5a8"' in source
    for table in TABLES:
        assert f"CREATE TABLE {table}" in source
        assert f"DROP TABLE {table}" in source
    assert "CREATE FUNCTION validate_customer_shipping_quote_write" in source
    assert "CREATE FUNCTION validate_customer_shipping_quote_option_write" in source
    assert "CREATE FUNCTION validate_customer_shipping_quote_selection_write" in source
    assert "CREATE FUNCTION assert_customer_shipping_quote_has_options" in source
    assert "protect_customer_shipping_quote_order_owner" in source
    assert source.index(
        "FOR UPDATE;\\n    event_at := clock_timestamp()"
    ) < source.index("IF event_at >= quote.expires_at")


def test_customer_quote_model_and_migration_table_shape_match() -> None:
    from app.models.customer_shipping_quote import (
        CustomerShippingQuote,
        CustomerShippingQuoteOption,
        CustomerShippingQuoteSelection,
    )

    source = MIGRATION.read_text()
    for model in (
        CustomerShippingQuote,
        CustomerShippingQuoteOption,
        CustomerShippingQuoteSelection,
    ):
        table = model.__table__
        create_block = source.split(f"CREATE TABLE {table.name} (", 1)[1].split(
            ");", 1
        )[0]
        for column in table.columns:
            assert column.name in create_block, (table.name, column.name)
        for constraint in table.constraints:
            if constraint.name:
                assert constraint.name in create_block, (table.name, constraint.name)
        for index in table.indexes:
            assert index.name in source, (table.name, index.name)


def test_customer_quote_migration_parent_head_parent_head_real_postgresql() -> None:
    root = Path(__file__).parents[1]
    config_spec = importlib.util.spec_from_file_location(
        "quote_test_config", root / "tests/conftest.py"
    )
    assert config_spec is not None and config_spec.loader is not None
    test_config = importlib.util.module_from_spec(config_spec)
    config_spec.loader.exec_module(test_config)

    base_url = make_url(test_config.TEST_DATABASE_URL)
    sync_driver = base_url.drivername.split("+", 1)[0]
    admin_url = base_url.set(drivername=sync_driver, database="postgres")
    database = f"shopsoma_quote_cycle_{uuid.uuid4().hex[:12]}"
    database_url = base_url.set(
        drivername=sync_driver, database=database
    ).render_as_string(hide_password=False)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}"'))

    env = os.environ.copy()
    env.update(DATABASE_URL=database_url, SECRET_KEY="quote-migration-test-secret")

    def migrate(operation: str, revision: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", operation, revision],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    try:
        migrate("upgrade", PARENT)
        engine = create_engine(database_url)
        try:
            before = set(inspect(engine).get_table_names())
            assert not (set(TABLES) & before)
            assert set(PHASE_2B_TABLES) <= before

            migrate("upgrade", "head")
            after = set(inspect(engine).get_table_names())
            assert set(TABLES) <= after
            assert set(PHASE_2B_TABLES) <= after
            with engine.connect() as connection:
                assert (
                    connection.scalar(text("SELECT count(*) FROM alembic_version")) == 1
                )
                assert (
                    connection.scalar(text("SELECT version_num FROM alembic_version"))
                    == HEAD
                )
                quote_trigger_count = connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal "
                        "AND tgrelid IN ('customer_shipping_quotes'::regclass, "
                        "'customer_shipping_quote_options'::regclass, "
                        "'customer_shipping_quote_selections'::regclass)"
                    )
                )
                assert quote_trigger_count == 5

            migrate("downgrade", PARENT)
            downgraded = set(inspect(engine).get_table_names())
            assert not (set(TABLES) & downgraded)
            assert set(PHASE_2B_TABLES) <= downgraded

            migrate("upgrade", "head")
            assert set(TABLES) <= set(inspect(engine).get_table_names())
        finally:
            engine.dispose()
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
