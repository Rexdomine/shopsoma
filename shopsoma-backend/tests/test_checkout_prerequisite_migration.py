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
CURRENT_HEAD_REVISION = "c4d5e6f7a8b9"


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
    current = script.get_revision(CURRENT_HEAD_REVISION)
    assert current.down_revision == MILESTONE_FOUR_REVISION
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
                "c.evidence_kind,c.evidence_reference,c.notes_hash,r.high_watermark_created_at,"
                "r.high_watermark_order_id,o.created_at "
                "FROM orders o JOIN order_workflow_classifications c ON c.order_id=o.id "
                "JOIN order_workflow_migration_runs r ON r.id=c.migration_run_id "
                "WHERE o.id=:id"
            ),
            {"id": historical_id},
        ).one()
        classification_after = connection.execute(
            text(
                "SELECT order_id,cohort,policy_version,access_mode,evidence_kind,"
                "evidence_reference,migration_run_id,classified_by,notes_hash "
                "FROM order_workflow_classifications ORDER BY order_id"
            )
        ).all()
    assert stable_head_after == stable_head_before
    assert len(rows) == 2
    assert all(
        row[1:]
        == (
            "legacy_pre_bridge",
            "legacy_pre_bridge_v1",
            "authenticated",
            row[0],
            row[0],
        )
        for row in rows
    )
    assert historical[:5] == (
        "legacy_ambiguous_quarantined",
        "legacy_quarantine_v1",
        "legacy_quarantined",
        "migration_ambiguity_quarantine",
        "historical-evidence-unresolved",
    )
    assert len(historical[5]) == 64
    assert historical[6:] == (historical[8], historical_id, historical[8])
    assert set(classification_before) < set(classification_after)
    assert len(classification_after) == len(classification_before) + 1
    engine.dispose()


def test_postgresql_partial_candidate_aborts_without_audit_mutation(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[1])
    engine = create_engine(sync_url)
    customer_id = uuid.uuid4()
    order_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                "VALUES (:customer,:email,'Partial candidate','CUSTOMER',false)"
            ),
            {
                "customer": customer_id,
                "email": f"partial-{uuid.uuid4().hex}@example.test",
            },
        )
        connection.execute(
            text(
                "INSERT INTO orders "
                "(id,order_number,customer_id,workflow_cohort,subtotal,shipping_cost,"
                "tax_amount,discount_amount,total_amount,payment_status,fulfillment_status) "
                "VALUES (:order,:number,:customer,'legacy_pre_bridge',10,0,0,0,10,"
                "'PENDING','order_received')"
            ),
            {
                "order": order_id,
                "number": f"M2-PARTIAL-{uuid.uuid4().hex[:8]}",
                "customer": customer_id,
            },
        )
    failed = _run_alembic(app_url, "upgrade", REVISIONS[-1], expect_success=False)
    assert failed.returncode != 0
    assert "changed-candidate abort: partial workflow classification" in (
        failed.stdout + failed.stderr
    )
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == REVISIONS[1]
        )
        assert connection.execute(
            text(
                "SELECT workflow_cohort,workflow_policy_version,checkout_access_mode "
                "FROM orders WHERE id=:order"
            ),
            {"order": order_id},
        ).one() == ("legacy_pre_bridge", None, None)
        assert (
            connection.scalar(
                text("SELECT count(*) FROM order_workflow_migration_runs")
            )
            == 0
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM order_workflow_classifications")
            )
            == 0
        )
        assert connection.scalar(text("SELECT count(*) FROM order_current_owners")) == 0
    engine.dispose()


def test_postgresql_head_has_exact_orm_ddl_parity(disposable_m2_database) -> None:
    from app.core.base import Base

    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    m2_columns = {
        "orders": {
            "workflow_cohort",
            "workflow_policy_version",
            "checkout_access_mode",
            "checkout_estimate_selection_id",
            "checkout_prerequisites_completed_at",
        },
        "order_items": {
            "inventory_policy",
            "inventory_subject_kind",
            "inventory_subject_id",
            "inventory_source_product_id",
            "inventory_source_catalogue_version",
            "inventory_source_evidence_hash",
            "inventory_policy_snapshot_at",
        },
        "stock_reservations": {
            "workflow_cohort",
            "checkout_estimate_selection_id",
            "inventory_subject_kind",
            "inventory_subject_id",
            "quote_id",
            "quote_selection_id",
            "quote_option_id",
            "intent_id",
        },
        "payment_attempts": {
            "workflow_cohort",
            "checkout_estimate_selection_id",
            "quote_id",
            "quote_selection_id",
            "quote_option_id",
            "intent_id",
        },
        "payment_attempt_reservations": {
            "membership_family",
            "order_id",
            "order_item_id",
            "checkout_estimate_selection_id",
        },
    }
    m2_tables = {
        "checkout_shipping_estimates",
        "checkout_shipping_estimate_options",
        "checkout_shipping_estimate_selections",
        "order_inventory_coverage",
        "order_current_owners",
        "order_guest_capabilities",
        "order_workflow_migration_runs",
        "order_workflow_classifications",
    }
    engine = create_engine(sync_url)
    with engine.connect() as connection:
        database = inspect(connection)
        for table_name in m2_tables | set(m2_columns):
            model = Base.metadata.tables[table_name]
            database_columns = {
                column["name"]: column for column in database.get_columns(table_name)
            }
            selected = (
                set(model.columns.keys())
                if table_name in m2_tables
                else m2_columns[table_name]
            )
            for column_name in selected:
                model_column = model.c[column_name]
                database_column = database_columns[column_name]
                assert model_column.nullable == database_column["nullable"], (
                    table_name,
                    column_name,
                )
                assert model_column.type.compile(connection.dialect) == (
                    database_column["type"].compile(connection.dialect)
                ), (table_name, column_name)

        database_names = set(
            connection.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_%' "
                    "OR conname LIKE 'uq_%' OR conname LIKE 'fk_%'"
                )
            ).scalars()
        ) | set(
            connection.execute(
                text(
                    "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'ix_%' "
                    "OR indexname LIKE 'uq_%'"
                )
            ).scalars()
        )
        for table_name in m2_tables | set(m2_columns):
            model = Base.metadata.tables[table_name]
            for named in (*model.constraints, *model.indexes):
                if named.name and (
                    table_name in m2_tables
                    or named.name.startswith(
                        (
                            "ck_orders_workflow",
                            "ck_orders_checkout",
                            "fk_orders_checkout",
                            "uq_orders_workflow",
                            "ix_orders_workflow",
                            "ix_orders_domestic",
                            "ck_order_items_inventory",
                            "fk_stock_reservations_checkout",
                            "fk_stock_reservations_order_item",
                            "ck_stock_reservations_workflow",
                            "ck_stock_reservations_binding",
                            "ck_stock_reservations_checkout",
                            "uq_stock_reservations_checkout",
                            "fk_payment_attempts_checkout",
                            "ck_payment_attempts_binding",
                            "ck_payment_attempts_checkout",
                            "uq_payment_attempts_checkout",
                            "fk_payment_attempt_reservations_",
                        )
                    )
                ):
                    assert named.name in database_names
    engine.dispose()


def _normalized_finding3_catalog(connection):
    affected_tables = (
        "orders",
        "order_items",
        "checkout_shipping_estimates",
        "checkout_shipping_estimate_options",
        "checkout_shipping_estimate_selections",
        "order_inventory_coverage",
    )
    column_names = {
        "orders": {
            "workflow_cohort",
            "workflow_policy_version",
            "checkout_access_mode",
            "checkout_estimate_selection_id",
            "checkout_prerequisites_completed_at",
        },
        "order_items": {
            "inventory_policy",
            "inventory_subject_kind",
            "inventory_subject_id",
            "inventory_source_product_id",
            "inventory_source_catalogue_version",
            "inventory_source_evidence_hash",
            "inventory_policy_snapshot_at",
        },
    }
    columns = {
        (row.table_name, row.column_name): (
            row.data_type,
            row.not_null,
            re.sub(r"\s+", " ", row.default_expression or "").strip(),
        )
        for row in connection.execute(
            text(
                "SELECT c.relname table_name,a.attname column_name,"
                "format_type(a.atttypid,a.atttypmod) data_type,a.attnotnull not_null,"
                "pg_get_expr(d.adbin,d.adrelid,true) default_expression "
                "FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid "
                "LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                "WHERE c.relname=ANY(:tables) AND a.attnum>0 AND NOT a.attisdropped"
            ),
            {"tables": list(affected_tables)},
        )
        if row.table_name.startswith("checkout_")
        or row.table_name == "order_inventory_coverage"
        or row.column_name in column_names.get(row.table_name, set())
    }
    prefixes = (
        "ck_checkout_",
        "fk_checkout_",
        "uq_checkout_",
        "ck_order_items_inventory",
        "uq_order_items_id_order_inventory",
        "fk_order_inventory_",
        "ck_order_inventory_",
        "uq_order_inventory_",
        "fk_orders_checkout_",
        "ix_checkout_",
        "ix_order_inventory_",
        "ix_orders_domestic_",
    )
    constraints = {
        row.name: (
            row.kind,
            re.sub(r"\s+", " ", row.definition).strip(),
            row.deferrable,
            row.deferred,
            row.validated,
        )
        for row in connection.execute(
            text(
                "SELECT con.conname name,con.contype::text kind,"
                "pg_get_constraintdef(con.oid,true) definition,con.condeferrable deferrable,"
                "con.condeferred deferred,con.convalidated validated "
                "FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid "
                "WHERE c.relname=ANY(:tables)"
            ),
            {"tables": list(affected_tables)},
        )
        if row.name.startswith(prefixes)
    }
    indexes = {
        row.name: re.sub(r"\s+", " ", row.definition).strip()
        for row in connection.execute(
            text(
                "SELECT c.relname name,pg_get_indexdef(c.oid,0,true) definition "
                "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
                "JOIN pg_class t ON t.oid=i.indrelid WHERE t.relname=ANY(:tables)"
            ),
            {"tables": list(affected_tables)},
        )
        if row.name.startswith(prefixes)
    }
    functions = dict(
        connection.execute(
            text(
                "SELECT proname,regexp_replace(pg_get_functiondef(oid),'\\s+',' ','g') "
                "FROM pg_proc WHERE proname=ANY(:names)"
            ),
            {
                "names": [
                    "validate_checkout_estimate_write",
                    "validate_checkout_estimate_option_write",
                    "validate_checkout_estimate_selection_write",
                    "validate_order_item_inventory_snapshot",
                    "validate_checkout_prerequisite_completion",
                ]
            },
        ).all()
    )
    triggers = {
        row.name: (
            re.sub(r"\s+", " ", row.definition).strip(),
            row.deferrable,
            row.deferred,
        )
        for row in connection.execute(
            text(
                "SELECT tgname name,pg_get_triggerdef(oid,true) definition,"
                "tgdeferrable deferrable,tginitdeferred deferred FROM pg_trigger "
                "WHERE NOT tgisinternal AND tgname=ANY(:names)"
            ),
            {
                "names": [
                    "trg_checkout_estimates_truth",
                    "trg_checkout_estimate_options_truth",
                    "trg_checkout_estimate_selections_truth",
                    "trg_order_items_inventory_snapshot",
                    "trg_orders_checkout_completion",
                    "trg_checkout_coverage_completion",
                    "trg_checkout_selection_completion",
                ]
            },
        )
    }
    return columns, constraints, indexes, functions, triggers


def test_finding3_postgresql_migration_and_orm_catalogs_have_exact_parity(
    disposable_m2_database,
) -> None:
    from app.core.base import Base

    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", CURRENT_HEAD_REVISION)
    migrated = create_engine(sync_url)
    model_database = f"shopsoma_m2_model_{uuid.uuid4().hex[:12]}"
    admin_url = sync_url.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.begin() as connection:
        connection.execute(text(f'CREATE DATABASE "{model_database}"'))
    model_engine = create_engine(sync_url.set(database=model_database))
    try:
        Base.metadata.create_all(model_engine)
        with migrated.connect() as migrated_connection, model_engine.connect() as model_connection:
            assert _normalized_finding3_catalog(migrated_connection) == (
                _normalized_finding3_catalog(model_connection)
            )
    finally:
        model_engine.dispose()
        with admin.begin() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name"
                ),
                {"name": model_database},
            )
            connection.execute(text(f'DROP DATABASE "{model_database}"'))
        admin.dispose()
        migrated.dispose()


def _install_domestic_tuple(
    connection, *, include_selection=True, estimate_expiry="30 minutes"
):
    ids = {
        name: uuid.uuid4()
        for name in (
            "vendor_user",
            "customer",
            "vendor",
            "product",
            "order",
            "item",
            "estimate",
            "option",
            "selection",
            "reservation",
            "rate",
        )
    }
    connection.execute(
        text(
            "INSERT INTO users (id,email,full_name,role,is_guest_created) VALUES "
            "(:vendor_user,:vendor_email,'M2 Vendor','VENDOR',false),"
            "(:customer,:customer_email,'M2 Customer','CUSTOMER',false)"
        ),
        {
            **ids,
            "vendor_email": f"m2-v-{uuid.uuid4().hex}@example.test",
            "customer_email": f"m2-c-{uuid.uuid4().hex}@example.test",
        },
    )
    connection.execute(
        text(
            "INSERT INTO vendors (id,user_id,business_name,kyc_status,commission_rate,"
            "approved,store_active,is_onboarding,brand_info_completed,payout_info_completed,"
            "total_products,total_orders,total_revenue) VALUES "
            "(:vendor,:vendor_user,'M2 Vendor','PENDING',10,false,true,true,false,false,0,0,0)"
        ),
        ids,
    )
    connection.execute(
        text(
            "INSERT INTO products (id,vendor_id,title,base_price,currency,total_stock,status,"
            "is_featured,product_type,made_to_order,views_count,orders_count,moderation_status) "
            "VALUES (:product,:vendor,'M2 Product',10,'NGN',5,'DRAFT',false,'SINGLE',false,0,0,'PENDING')"
        ),
        ids,
    )
    connection.execute(
        text(
            "INSERT INTO orders (id,order_number,customer_id,workflow_cohort,"
            "workflow_policy_version,checkout_access_mode,subtotal,shipping_cost,tax_amount,"
            "discount_amount,total_amount,currency,payment_status,fulfillment_status) VALUES "
            "(:order,:number,:customer,'domestic_checkout_v1','domestic_checkout_v1',"
            "'authenticated',10,0,0,0,10,'NGN','PENDING','order_received')"
        ),
        {**ids, "number": f"M2-{uuid.uuid4().hex[:12]}"},
    )
    connection.execute(
        text(
            "INSERT INTO order_items (id,order_id,product_id,vendor_id,product_title,quantity,"
            "unit_price,subtotal,currency,commission_rate,commission_amount,vendor_payout,"
            "fulfillment_status,inventory_policy,inventory_subject_kind,inventory_subject_id,"
            "inventory_source_product_id,inventory_source_catalogue_version,"
            "inventory_source_evidence_hash,inventory_policy_snapshot_at) VALUES "
            "(:item,:order,:product,:vendor,'M2 Product',1,10,10,'NGN',10,1,9,"
            "'order_received','stock_managed','product',:product,:product,'catalogue-v1',"
            ":hash,statement_timestamp())"
        ),
        {**ids, "hash": "a" * 64},
    )
    connection.execute(
        text(
            "INSERT INTO checkout_shipping_estimates (id,order_id,customer_id,"
            "destination_snapshot_hash,order_snapshot_hash,currency,ttl_seconds,expires_at,"
            "source_kind,source_command,idempotency_key,request_fingerprint,schema_version,"
            "created_by_actor_type,created_by_actor_id) VALUES "
            "(:estimate,:order,:customer,:hash,:hash,'NGN',1800,"
            "clock_timestamp()+CAST(:estimate_expiry AS interval),'static_domestic_rate',"
            "'create_estimate',:estimate_key,:hash,'v1','customer',:actor)"
        ),
        {
            **ids,
            "hash": "b" * 64,
            "estimate_key": f"e-{uuid.uuid4().hex}",
            "actor": str(ids["customer"]),
            "estimate_expiry": estimate_expiry,
        },
    )
    connection.execute(
        text(
            "INSERT INTO shipping_rates (id,name,base_rate,country,min_delivery_days,"
            "max_delivery_days,is_active,is_default,priority) VALUES "
            "(:rate,'M2 static rate',1,'Nigeria',2,5,true,false,0)"
        ),
        ids,
    )
    connection.execute(
        text(
            "INSERT INTO checkout_shipping_estimate_options (id,estimate_id,option_key,"
            "service_code,service_label,amount,currency,source_rate_id) VALUES "
            "(:option,:estimate,'standard','standard','Standard',1,'NGN',:rate)"
        ),
        ids,
    )
    if include_selection:
        connection.execute(
            text(
                "INSERT INTO checkout_shipping_estimate_selections (id,estimate_id,option_id,"
                "order_id,customer_id,selected_by_actor_type,selected_by_actor_id,shipping_amount,"
                "currency,source_command,idempotency_key,selected_at) VALUES "
                "(:selection,:estimate,:option,:order,:customer,'customer',:actor,1,'NGN',"
                "'select_estimate',:selection_key,statement_timestamp())"
            ),
            {
                **ids,
                "actor": str(ids["customer"]),
                "selection_key": f"select-{uuid.uuid4().hex}",
            },
        )
        connection.execute(
            text(
                "UPDATE orders SET checkout_estimate_selection_id=:selection WHERE id=:order"
            ),
            ids,
        )
    return ids


def _assert_rejected(connection, statement, parameters) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(Exception):
            connection.execute(text(statement), parameters)
    finally:
        savepoint.rollback()


def _assert_deferred_rejected(connection, statement, parameters) -> None:
    savepoint = connection.begin_nested()
    try:
        with pytest.raises(Exception):
            connection.execute(text(statement), parameters)
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    finally:
        savepoint.rollback()
        connection.execute(text("SET CONSTRAINTS ALL DEFERRED"))


def _wait_until_database_time_reaches(engine, deadline) -> None:
    while True:
        with engine.connect() as observer:
            if observer.scalar(
                text("SELECT clock_timestamp() >= :deadline"), {"deadline": deadline}
            ):
                return


def test_final_repair_migration_run_truth_is_set_once(disposable_m2_database) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    run = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO order_workflow_migration_runs "
                "(id,compatibility_writer_release_id,compatibility_writer_started_at,"
                "migration_revision,deployment_identity,high_watermark_created_at,"
                "high_watermark_order_id) VALUES "
                "(:run,'writer',clock_timestamp(),'a1b2c3d4e5f6','deployment',"
                "clock_timestamp(),:watermark)"
            ),
            {"run": run, "watermark": uuid.uuid4()},
        )
        for assignment in (
            "id=:value",
            "compatibility_writer_release_id='other'",
            "compatibility_writer_started_at=compatibility_writer_started_at+interval '1 second'",
            "migration_revision='other'",
            "deployment_identity='other'",
            "high_watermark_created_at=high_watermark_created_at+interval '1 second'",
            "high_watermark_order_id=:value",
            "created_at=created_at+interval '1 second'",
        ):
            _assert_rejected(
                connection,
                f"UPDATE order_workflow_migration_runs SET {assignment} WHERE id=:run",
                {"run": run, "value": uuid.uuid4()},
            )
        for assignment in (
            "classification_cutover_at=clock_timestamp()",
            "classified_row_count=0",
            "validated_constraints='exact'",
        ):
            _assert_rejected(
                connection,
                f"UPDATE order_workflow_migration_runs SET {assignment} WHERE id=:run",
                {"run": run},
            )
        connection.execute(
            text(
                "UPDATE order_workflow_migration_runs SET "
                "classification_cutover_at=clock_timestamp(),classified_row_count=0,"
                "validated_constraints='exact' WHERE id=:run"
            ),
            {"run": run},
        )
        for assignment in (
            "classification_cutover_at=NULL",
            "classification_cutover_at=classification_cutover_at+interval '1 second'",
            "classified_row_count=NULL",
            "classified_row_count=1",
            "validated_constraints=NULL",
            "validated_constraints='rewritten'",
            "deployment_identity=deployment_identity",
        ):
            _assert_rejected(
                connection,
                f"UPDATE order_workflow_migration_runs SET {assignment} WHERE id=:run",
                {"run": run},
            )
    engine.dispose()


def test_final_repair_completed_order_item_insert_requires_exact_coverage(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        _insert_domestic_reservation(connection, ids)
        connection.execute(
            text(
                "INSERT INTO order_inventory_coverage "
                "(order_item_id,order_id,checkout_estimate_selection_id,inventory_policy,"
                "reservation_id) VALUES (:item,:order,:selection,'stock_managed',:reservation)"
            ),
            ids,
        )
        connection.execute(
            text(
                "UPDATE orders SET checkout_prerequisites_completed_at=clock_timestamp() "
                "WHERE id=:order"
            ),
            ids,
        )
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        _assert_deferred_rejected(
            connection,
            "INSERT INTO order_items "
            "(id,order_id,product_id,vendor_id,product_title,quantity,unit_price,subtotal,"
            "currency,commission_rate,commission_amount,vendor_payout,fulfillment_status,"
            "inventory_policy,inventory_subject_kind,inventory_subject_id,"
            "inventory_source_product_id,inventory_source_catalogue_version,"
            "inventory_source_evidence_hash,inventory_policy_snapshot_at) "
            "SELECT :new_item,order_id,product_id,vendor_id,product_title,quantity,unit_price,"
            "subtotal,currency,commission_rate,commission_amount,vendor_payout,fulfillment_status,"
            "inventory_policy,inventory_subject_kind,inventory_subject_id,"
            "inventory_source_product_id,inventory_source_catalogue_version,"
            "inventory_source_evidence_hash,inventory_policy_snapshot_at "
            "FROM order_items WHERE id=:item",
            {**ids, "new_item": uuid.uuid4()},
        )
    engine.dispose()


def _insert_domestic_reservation(connection, ids):
    connection.execute(
        text(
            "SELECT coordinate_stock_reservation_write("
            ":reservation,:order,:product,NULL,NULL)"
        ),
        ids,
    )
    connection.execute(
        text(
            "INSERT INTO stock_reservations (id,order_id,order_item_id,customer_id,"
            "workflow_cohort,checkout_estimate_selection_id,inventory_subject_kind,"
            "inventory_subject_id,product_id,quantity,unit_price,line_amount,currency,"
            "ttl_seconds,expires_at,state,source_command,idempotency_key,creation_txid) VALUES "
            "(:reservation,:order,:item,:customer,'domestic_checkout_v1',:selection,"
            "'product',:product,:product,1,10,10,'NGN',1800,"
            "statement_timestamp()+interval '30 minutes','active','reserve',:key,txid_current())"
        ),
        {**ids, "key": f"reserve-{uuid.uuid4().hex}"},
    )


def _insert_domestic_attempt(connection, ids):
    connection.execute(
        text("SELECT coordinate_payment_attempt_write(:attempt,:order)"), ids
    )
    connection.execute(
        text(
            "INSERT INTO payment_attempts (id,order_id,customer_id,workflow_cohort,"
            "checkout_estimate_selection_id,amount,currency,provider,provider_reference,"
            "source_command,idempotency_key) VALUES "
            "(:attempt,:order,:customer,'domestic_checkout_v1',:selection,10,'NGN',"
            "'test_provider',:reference,'pay',:key)"
        ),
        {
            **ids,
            "reference": f"m2-{ids['attempt']}",
            "key": f"pay-{uuid.uuid4().hex}",
        },
    )


def test_final_repair_estimate_expiry_is_sampled_after_authoritative_locks(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(
            connection, include_selection=False, estimate_expiry="2 seconds"
        )
        deadline = connection.scalar(
            text(
                "SELECT expires_at FROM checkout_shipping_estimates WHERE id=:estimate"
            ),
            ids,
        )
    blocker = engine.connect()
    blocker_tx = blocker.begin()
    blocker.execute(text("SELECT 1 FROM orders WHERE id=:order FOR UPDATE"), ids)
    started = Event()
    application_name = f"final-estimate-expiry-{uuid.uuid4().hex}"

    def select_estimate() -> str:
        with engine.connect() as worker:
            worker.execute(
                text("SET application_name=:name"), {"name": application_name}
            )
            transaction = worker.begin_nested()
            started.set()
            try:
                worker.execute(
                    text(
                        "INSERT INTO checkout_shipping_estimate_selections "
                        "(id,estimate_id,option_id,order_id,customer_id,selected_by_actor_type,"
                        "selected_by_actor_id,shipping_amount,currency,source_command,"
                        "idempotency_key,selected_at) VALUES (:selection,:estimate,:option,"
                        ":order,:customer,'customer',:actor,1,'NGN','select_estimate',:key,"
                        "statement_timestamp())"
                    ),
                    {
                        **ids,
                        "actor": str(ids["customer"]),
                        "key": f"post-lock-{uuid.uuid4().hex}",
                    },
                )
                transaction.commit()
                return "committed"
            except DBAPIError:
                transaction.rollback()
                return "rejected"

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(select_estimate)
            assert started.wait(timeout=2)
            _wait_until_postgres_worker_is_lock_blocked(engine, application_name)
            _wait_until_database_time_reaches(engine, deadline)
            blocker_tx.commit()
            assert future.result(timeout=5) == "rejected"
    finally:
        if blocker_tx.is_active:
            blocker_tx.rollback()
        blocker.close()
    engine.dispose()


def test_final_repair_guest_claim_expiry_is_sampled_after_authoritative_locks(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_f4_owner(connection)
        deadline = connection.scalar(
            text("SELECT clock_timestamp()+interval '2 seconds'")
        )
        capability = _insert_f4_capability(connection, ids, expires_at=deadline)
        sibling = _insert_f4_capability(connection, ids, scope="read_order")
        claimant = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                "VALUES (:id,:email,'Expiry claimant','CUSTOMER',false)"
            ),
            {"id": claimant, "email": f"expiry-{uuid.uuid4().hex}@example.test"},
        )
    blocker = engine.connect()
    blocker_tx = blocker.begin()
    blocker.execute(
        text("SELECT 1 FROM order_current_owners WHERE order_id=:order FOR UPDATE"), ids
    )
    started = Event()
    application_name = f"final-capability-expiry-{uuid.uuid4().hex}"

    def claim() -> str:
        with engine.connect() as worker:
            worker.execute(
                text("SET application_name=:name"), {"name": application_name}
            )
            transaction = worker.begin_nested()
            started.set()
            try:
                _claim_f4(worker, ids, capability, claimant, "post-lock-expiry")
                transaction.commit()
                return "committed"
            except DBAPIError:
                transaction.rollback()
                return "rejected"

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(claim)
            assert started.wait(timeout=2)
            _wait_until_postgres_worker_is_lock_blocked(engine, application_name)
            _wait_until_database_time_reaches(engine, deadline)
            blocker_tx.commit()
            assert future.result(timeout=5) == "rejected"
    finally:
        if blocker_tx.is_active:
            blocker_tx.rollback()
        blocker.close()
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT current_authenticated_user_id,claim_capability_id,claimed_at,row_version "
                "FROM order_current_owners WHERE order_id=:order"
            ),
            ids,
        ).one() == (None, None, None, 1)
        assert connection.execute(
            text(
                "SELECT count(*) FILTER (WHERE revoked_at IS NOT NULL),"
                "count(*) FILTER (WHERE claimed_at IS NOT NULL) "
                "FROM order_guest_capabilities WHERE id IN (:capability,:sibling)"
            ),
            {"capability": capability, "sibling": sibling},
        ).one() == (0, 0)
    engine.dispose()


def test_final_repair_domestic_rows_cannot_switch_trigger_family(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        ids["attempt"] = uuid.uuid4()
        _insert_domestic_reservation(connection, ids)
        _insert_domestic_attempt(connection, ids)
        connection.execute(
            text(
                "INSERT INTO payment_attempt_reservations "
                "(attempt_id,reservation_id,membership_family,order_id,order_item_id,"
                "checkout_estimate_selection_id) VALUES "
                "(:attempt,:reservation,'domestic_checkout_v1',:order,:item,:selection)"
            ),
            ids,
        )
        for table, target, assignment, expected in (
            (
                "stock_reservations",
                ids["reservation"],
                "workflow_cohort=NULL,order_item_id=NULL,checkout_estimate_selection_id=NULL,"
                "inventory_subject_kind=NULL,inventory_subject_id=NULL",
                "stock reservation identity is immutable",
            ),
            (
                "payment_attempts",
                ids["attempt"],
                "workflow_cohort=NULL,checkout_estimate_selection_id=NULL",
                "payment attempt identity is immutable",
            ),
        ):
            savepoint = connection.begin_nested()
            try:
                with pytest.raises(DBAPIError, match=expected):
                    connection.execute(
                        text(f"UPDATE {table} SET {assignment} WHERE id=:target"),
                        {"target": target},
                    )
            finally:
                savepoint.rollback()
    engine.dispose()


def test_finding5_domestic_reservation_allows_active_to_released(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        _insert_domestic_reservation(connection, ids)
        connection.execute(
            text(
                "UPDATE stock_reservations SET state='released',"
                "terminal_reason='checkout_cancelled',row_version=row_version+1 "
                "WHERE id=:reservation"
            ),
            ids,
        )
        assert connection.execute(
            text(
                "SELECT state,terminal_at IS NOT NULL,row_version "
                "FROM stock_reservations WHERE id=:reservation"
            ),
            ids,
        ).one() == ("released", True, 2)
    engine.dispose()


def test_finding5_domestic_payment_attempt_allows_pending_to_call_started(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        ids["attempt"] = uuid.uuid4()
        _insert_domestic_reservation(connection, ids)
        _insert_domestic_attempt(connection, ids)
        connection.execute(
            text(
                "INSERT INTO payment_attempt_reservations "
                "(attempt_id,reservation_id,membership_family,order_id,order_item_id,"
                "checkout_estimate_selection_id) VALUES "
                "(:attempt,:reservation,'domestic_checkout_v1',:order,:item,:selection)"
            ),
            ids,
        )
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        lease_token = uuid.uuid4()
        connection.execute(
            text(
                "UPDATE payment_attempts SET state='call_started',"
                "lease_token=:lease,row_version=row_version+1 WHERE id=:attempt"
            ),
            {**ids, "lease": lease_token},
        )
        assert connection.execute(
            text(
                "SELECT state,lease_token,call_started_at IS NOT NULL,"
                "claim_expires_at IS NOT NULL,row_version "
                "FROM payment_attempts WHERE id=:attempt"
            ),
            ids,
        ).one() == ("call_started", lease_token, True, True, 2)
    engine.dispose()


def _insert_domestic_membership(connection, ids) -> None:
    connection.execute(
        text(
            "INSERT INTO payment_attempt_reservations "
            "(attempt_id,reservation_id,membership_family,order_id,order_item_id,"
            "checkout_estimate_selection_id) VALUES "
            "(:attempt,:reservation,'domestic_checkout_v1',:order,:item,:selection)"
        ),
        ids,
    )
    connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def _insert_payment_evidence(connection, ids, evidence_type) -> uuid.UUID:
    evidence_id = uuid.uuid4()
    connection.execute(
        text(
            "INSERT INTO payment_attempt_evidence "
            "(id,attempt_id,source,event_id,evidence_type,evidence_hash,observed_at) "
            "VALUES (:evidence,:attempt,'test',:event,:kind,:hash,clock_timestamp())"
        ),
        {
            **ids,
            "evidence": evidence_id,
            "event": f"event-{uuid.uuid4().hex}",
            "kind": evidence_type,
            "hash": "e" * 64,
        },
    )
    return evidence_id


@pytest.mark.parametrize("target_state", ["released", "expired", "consumed"])
def test_finding5_every_domestic_reservation_forward_transition(
    disposable_m2_database, target_state
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        ids["attempt"] = uuid.uuid4()
        _insert_domestic_reservation(connection, ids)
        if target_state == "expired":
            # Fixture-only trigger bypass arranges an elapsed predecessor while
            # preserving the unchanged F9 lifecycle check.  The transition
            # itself below executes with every trigger enabled.
            connection.execute(text("SET LOCAL session_replication_role='replica'"))
            connection.execute(
                text(
                    "UPDATE stock_reservations SET created_at=clock_timestamp()-interval '2 hours',"
                    "expires_at=clock_timestamp()-interval '90 minutes' WHERE id=:reservation"
                ),
                ids,
            )
            connection.execute(text("SET LOCAL session_replication_role='origin'"))
        elif target_state == "consumed":
            _insert_domestic_attempt(connection, ids)
            _insert_domestic_membership(connection, ids)
            evidence = _insert_payment_evidence(connection, ids, "payment_verified")
            connection.execute(text("SET LOCAL session_replication_role='replica'"))
            connection.execute(
                text(
                    "UPDATE payment_attempts SET state='verified',terminal_evidence_id=:evidence,"
                    "terminal_at=clock_timestamp(),row_version=2 WHERE id=:attempt"
                ),
                {**ids, "evidence": evidence},
            )
            connection.execute(text("SET LOCAL session_replication_role='origin'"))
        connection.execute(
            text(
                "UPDATE stock_reservations SET state=:state,terminal_reason=:reason,"
                "row_version=row_version+1 WHERE id=:reservation"
            ),
            {**ids, "state": target_state, "reason": f"test_{target_state}"},
        )
        assert connection.execute(
            text(
                "SELECT state,terminal_at IS NOT NULL,row_version "
                "FROM stock_reservations WHERE id=:reservation"
            ),
            ids,
        ).one() == (target_state, True, 2)
    engine.dispose()


@pytest.mark.parametrize(
    ("old_state", "target_state", "evidence_type"),
    [
        ("pending", "call_started", None),
        ("pending", "expired", None),
        ("pending", "failed", "payment_failed"),
        ("call_started", "failed", "payment_failed"),
        ("call_started", "verified", "payment_verified"),
        ("call_started", "abandoned_unknown", "outcome_unknown"),
        ("abandoned_unknown", "failed", "payment_failed"),
        ("abandoned_unknown", "verified", "payment_verified"),
    ],
)
def test_finding5_every_domestic_payment_attempt_forward_transition(
    disposable_m2_database, old_state, target_state, evidence_type
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        ids["attempt"] = uuid.uuid4()
        _insert_domestic_reservation(connection, ids)
        _insert_domestic_attempt(connection, ids)
        _insert_domestic_membership(connection, ids)
        lease = uuid.uuid4()
        if old_state != "pending" or target_state == "expired":
            # Fixture-only trigger bypass arranges predecessor clock states that
            # cannot be reached during a fast test.  Every asserted transition
            # below runs after restoring origin mode.
            connection.execute(text("SET LOCAL session_replication_role='replica'"))
            if target_state == "expired":
                connection.execute(
                    text(
                        "WITH anchor AS (SELECT clock_timestamp() AS now_at) "
                        "UPDATE payment_attempts SET created_at=anchor.now_at-interval '2 hours',"
                        "expires_at=anchor.now_at-interval '90 minutes',"
                        "authorization_deadline_at=anchor.now_at-interval '75 minutes' "
                        "FROM anchor WHERE id=:attempt"
                    ),
                    ids,
                )
            elif old_state == "call_started":
                claim_delta = (
                    "- interval '1 hour'"
                    if target_state == "abandoned_unknown"
                    else "+ interval '1 hour'"
                )
                connection.execute(
                    text(
                        "UPDATE payment_attempts SET state='call_started',lease_token=:lease,"
                        "call_started_at=clock_timestamp()-interval '2 hours',"
                        f"claim_expires_at=clock_timestamp(){claim_delta},row_version=2 "
                        "WHERE id=:attempt"
                    ),
                    {**ids, "lease": lease},
                )
            else:
                prior_evidence = uuid.uuid4()
                connection.execute(
                    text(
                        "INSERT INTO payment_attempt_evidence "
                        "(id,attempt_id,source,event_id,evidence_type,provider,provider_reference,"
                        "evidence_hash,observed_at,created_at) VALUES "
                        "(:evidence,:attempt,'test',:event,'outcome_unknown','paystack',:reference,"
                        ":hash,clock_timestamp()-interval '1 hour',"
                        "clock_timestamp()-interval '1 hour')"
                    ),
                    {
                        **ids,
                        "evidence": prior_evidence,
                        "event": f"prior-{uuid.uuid4().hex}",
                        "reference": f"m2-{ids['attempt']}",
                        "hash": "d" * 64,
                    },
                )
                connection.execute(
                    text(
                        "UPDATE payment_attempts SET state='abandoned_unknown',"
                        "call_started_at=clock_timestamp()-interval '3 hours',"
                        "terminal_evidence_id=:evidence,terminal_at=clock_timestamp()-interval '1 hour',"
                        "row_version=3 WHERE id=:attempt"
                    ),
                    {**ids, "evidence": prior_evidence},
                )
            connection.execute(text("SET LOCAL session_replication_role='origin'"))
        evidence = (
            _insert_payment_evidence(connection, ids, evidence_type)
            if evidence_type
            else None
        )
        if old_state == "call_started":
            connection.execute(
                text("SELECT set_config('shopsoma.payment_lease_token',:lease,true)"),
                {"lease": str(lease)},
            )
        connection.execute(
            text(
                "UPDATE payment_attempts SET state=:state,terminal_evidence_id=:evidence,"
                "lease_token=CASE WHEN :state='call_started' THEN :lease ELSE lease_token END,"
                "row_version=row_version+1 WHERE id=:attempt"
            ),
            {**ids, "state": target_state, "evidence": evidence, "lease": lease},
        )
        expected_version = {"pending": 1, "call_started": 2, "abandoned_unknown": 3}[
            old_state
        ] + 1
        assert connection.execute(
            text(
                "SELECT state,terminal_at IS NOT NULL,row_version "
                "FROM payment_attempts WHERE id=:attempt"
            ),
            ids,
        ).one() == (target_state, target_state != "call_started", expected_version)
    engine.dispose()


def _finding5_reservation_insert(connection, ids, **overrides):
    values = {
        **ids,
        "reservation": uuid.uuid4(),
        "state": "active",
        "reason": None,
        "terminal_at": None,
        "key": f"f5-reservation-{uuid.uuid4().hex}",
        **overrides,
    }
    connection.execute(
        text(
            "SELECT coordinate_stock_reservation_write("
            ":reservation,:order,:product,NULL,NULL)"
        ),
        values,
    )
    connection.execute(
        text(
            "INSERT INTO stock_reservations (id,order_id,order_item_id,customer_id,"
            "workflow_cohort,checkout_estimate_selection_id,inventory_subject_kind,"
            "inventory_subject_id,product_id,quantity,unit_price,line_amount,currency,"
            "ttl_seconds,expires_at,state,terminal_reason,terminal_at,source_command,"
            "idempotency_key,creation_txid) VALUES (:reservation,:order,:item,:customer,"
            "'domestic_checkout_v1',:selection,'product',:product,:product,1,10,10,'NGN',"
            "1800,statement_timestamp()+interval '30 minutes',:state,:reason,:terminal_at,"
            "'reserve',:key,txid_current())"
        ),
        values,
    )
    return values


def _finding5_attempt_insert(connection, ids, **overrides):
    values = {
        **ids,
        "attempt": uuid.uuid4(),
        "state": "pending",
        "lease": None,
        "terminal_evidence": None,
        "terminal_at": None,
        "reference": f"f5-provider-{uuid.uuid4().hex}",
        "key": f"f5-payment-{uuid.uuid4().hex}",
        **overrides,
    }
    connection.execute(
        text("SELECT coordinate_payment_attempt_write(:attempt,:order)"), values
    )
    connection.execute(
        text(
            "INSERT INTO payment_attempts (id,order_id,customer_id,workflow_cohort,"
            "checkout_estimate_selection_id,amount,currency,provider,provider_reference,"
            "state,lease_token,terminal_evidence_id,terminal_at,source_command,idempotency_key) "
            "VALUES (:attempt,:order,:customer,'domestic_checkout_v1',:selection,10,'NGN',"
            "'test_provider',:reference,:state,:lease,:terminal_evidence,:terminal_at,'pay',:key)"
        ),
        values,
    )
    return values


def _finding5_arrange_call_started(connection, ids):
    lease = uuid.uuid4()
    connection.execute(
        text("SELECT coordinate_payment_attempt_write(:attempt,:order)"), ids
    )
    connection.execute(
        text(
            "UPDATE payment_attempts SET state='call_started',lease_token=:lease,"
            "row_version=row_version+1 WHERE id=:attempt"
        ),
        {**ids, "lease": lease},
    )
    return lease


def _finding5_release_reservation(connection, ids):
    connection.execute(
        text(
            "SELECT coordinate_stock_reservation_write("
            ":reservation,:order,:product,NULL,NULL)"
        ),
        ids,
    )
    connection.execute(
        text(
            "UPDATE stock_reservations SET state='released',terminal_reason='race',"
            "row_version=row_version+1 WHERE id=:reservation"
        ),
        ids,
    )


def test_finding5_postgresql_negative_lifecycle_matrix(disposable_m2_database) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        initial_reservation = _install_domestic_tuple(connection)
        with pytest.raises(Exception):
            with connection.begin_nested():
                _finding5_reservation_insert(
                    connection, initial_reservation, state="released", reason="forged"
                )

        initial_attempt = _install_domestic_tuple(connection)
        _insert_domestic_reservation(connection, initial_attempt)
        with pytest.raises(Exception):
            with connection.begin_nested():
                _finding5_attempt_insert(
                    connection,
                    initial_attempt,
                    state="call_started",
                    lease=uuid.uuid4(),
                )

        reservation_ids = _install_domestic_tuple(connection)
        _insert_domestic_reservation(connection, reservation_ids)
        reservation_mutations = [
            "customer_id=(SELECT customer_id FROM orders WHERE id<>:order LIMIT 1)",
            "workflow_cohort='legacy_pre_bridge'",
            "checkout_estimate_selection_id=NULL",
            "inventory_subject_id=:other",
            "product_id=:other",
            "quantity=2",
            "unit_price=11",
            "currency='USD'",
            "expires_at=expires_at+interval '1 minute'",
            "source_command='changed'",
            "idempotency_key='changed-replay-key'",
            "creation_txid=creation_txid+1",
            "created_at=created_at-interval '1 second'",
        ]
        for assignment in reservation_mutations:
            _assert_rejected(
                connection,
                f"UPDATE stock_reservations SET {assignment},state='released',"
                "terminal_reason='negative',row_version=row_version+1 WHERE id=:reservation",
                {**reservation_ids, "other": uuid.uuid4()},
            )
        for assignment in (
            "state='active',terminal_reason='unexpected',row_version=row_version+1",
            "state='released',terminal_reason=NULL,row_version=row_version+1",
            "state='released',terminal_reason='negative',terminal_at=statement_timestamp(),"
            "row_version=row_version+1",
            "state='released',terminal_reason='negative',row_version=row_version+2",
        ):
            _assert_rejected(
                connection,
                f"UPDATE stock_reservations SET {assignment} WHERE id=:reservation",
                reservation_ids,
            )
        connection.execute(
            text(
                "UPDATE stock_reservations SET state='released',terminal_reason='legal',"
                "row_version=row_version+1 WHERE id=:reservation"
            ),
            reservation_ids,
        )
        _assert_rejected(
            connection,
            "UPDATE stock_reservations SET state='active',terminal_reason=NULL,terminal_at=NULL,"
            "row_version=row_version+1 WHERE id=:reservation",
            reservation_ids,
        )

        payment_ids = _install_domestic_tuple(connection)
        payment_ids["attempt"] = uuid.uuid4()
        _insert_domestic_reservation(connection, payment_ids)
        _insert_domestic_attempt(connection, payment_ids)
        _insert_domestic_membership(connection, payment_ids)
        other = _install_domestic_tuple(connection)
        payment_mutations = [
            ("order_id=:value", other["order"]),
            ("customer_id=:value", other["customer"]),
            ("workflow_cohort='legacy_pre_bridge'", None),
            ("checkout_estimate_selection_id=:value", other["selection"]),
            ("amount=11", None),
            ("currency='USD'", None),
            ("provider='other_provider'", None),
            ("provider_reference='other-reference'", None),
            ("expires_at=expires_at+interval '1 minute'", None),
            ("source_command='changed'", None),
            ("idempotency_key='changed-replay-key'", None),
            ("creation_txid=creation_txid+1", None),
            ("created_at=created_at-interval '1 second'", None),
        ]
        for assignment, value in payment_mutations:
            _assert_rejected(
                connection,
                f"UPDATE payment_attempts SET {assignment},state='failed',"
                "row_version=row_version+1 WHERE id=:attempt",
                {**payment_ids, "value": value},
            )
        for statement in (
            "UPDATE payment_attempts SET state='verified',row_version=row_version+1 "
            "WHERE id=:attempt",
            "UPDATE payment_attempts SET state='abandoned_unknown',row_version=row_version+1 "
            "WHERE id=:attempt",
            "UPDATE payment_attempts SET state='failed',terminal_at=statement_timestamp(),"
            "row_version=row_version+1 WHERE id=:attempt",
        ):
            _assert_rejected(connection, statement, payment_ids)

        wrong_evidence = _insert_payment_evidence(
            connection, payment_ids, "payment_verified"
        )
        _assert_rejected(
            connection,
            "UPDATE payment_attempts SET state='failed',terminal_evidence_id=:evidence,"
            "row_version=row_version+1 WHERE id=:attempt",
            {**payment_ids, "evidence": wrong_evidence},
        )
        lease = _finding5_arrange_call_started(connection, payment_ids)
        failed_evidence = _insert_payment_evidence(
            connection, payment_ids, "payment_failed"
        )
        for presented in (None, uuid.uuid4()):
            savepoint = connection.begin_nested()
            try:
                if presented is not None:
                    connection.execute(
                        text(
                            "SELECT set_config('shopsoma.payment_lease_token',:lease,true)"
                        ),
                        {"lease": str(presented)},
                    )
                with pytest.raises(Exception):
                    connection.execute(
                        text(
                            "UPDATE payment_attempts SET state='failed',"
                            "terminal_evidence_id=:evidence,row_version=row_version+1 "
                            "WHERE id=:attempt"
                        ),
                        {**payment_ids, "evidence": failed_evidence},
                    )
            finally:
                savepoint.rollback()
        connection.execute(text("SET LOCAL session_replication_role='replica'"))
        connection.execute(
            text(
                "UPDATE payment_attempt_evidence SET created_at=call_started_at-interval '1 second',"
                "observed_at=call_started_at-interval '1 second' FROM payment_attempts "
                "WHERE payment_attempt_evidence.id=:evidence AND payment_attempts.id=:attempt"
            ),
            {**payment_ids, "evidence": failed_evidence},
        )
        connection.execute(text("SET LOCAL session_replication_role='origin'"))
        connection.execute(
            text("SELECT set_config('shopsoma.payment_lease_token',:lease,true)"),
            {"lease": str(lease)},
        )
        _assert_rejected(
            connection,
            "UPDATE payment_attempts SET state='failed',terminal_evidence_id=:evidence,"
            "row_version=row_version+1 WHERE id=:attempt",
            {**payment_ids, "evidence": failed_evidence},
        )

        for family, order_id, item_id, selection_id in (
            ("legacy_f9", payment_ids["order"], None, None),
            (
                "domestic_checkout_v1",
                None,
                payment_ids["item"],
                payment_ids["selection"],
            ),
        ):
            _assert_rejected(
                connection,
                "INSERT INTO payment_attempt_reservations "
                "(attempt_id,reservation_id,membership_family,order_id,order_item_id,"
                "checkout_estimate_selection_id) VALUES "
                "(:attempt,:reservation,:family,:order,:item,:selection)",
                {
                    **payment_ids,
                    "family": family,
                    "order": order_id,
                    "item": item_id,
                    "selection": selection_id,
                },
            )
    engine.dispose()


@pytest.mark.parametrize("winner", ["payment", "reservation"])
def test_finding5_postgresql_material_transition_locks_are_deterministic(
    disposable_m2_database, winner
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        _insert_domestic_reservation(connection, ids)
        if winner == "payment":
            ids["attempt"] = uuid.uuid4()
            _insert_domestic_attempt(connection, ids)
            _insert_domestic_membership(connection, ids)

    first = engine.connect()
    second = engine.connect()
    first_tx = first.begin()
    try:
        if winner == "payment":
            _finding5_arrange_call_started(first, ids)
        else:
            _finding5_release_reservation(first, ids)

        savepoint = second.begin_nested()
        try:
            with pytest.raises(DBAPIError) as locked:
                second.execute(
                    text(
                        "SELECT id FROM stock_reservations WHERE id=:reservation "
                        "FOR UPDATE NOWAIT"
                    ),
                    ids,
                )
            assert locked.value.orig.pgcode == "55P03"
        finally:
            savepoint.rollback()
        first_tx.commit()

        if winner == "payment":
            second.execute(
                text(
                    "SELECT coordinate_stock_reservation_write("
                    ":reservation,:order,:product,NULL,NULL)"
                ),
                ids,
            )
            _assert_rejected(
                second,
                "UPDATE stock_reservations SET state='released',terminal_reason='race',"
                "row_version=row_version+1 WHERE id=:reservation",
                ids,
            )
        else:
            with pytest.raises(Exception):
                with second.begin_nested():
                    _finding5_release_reservation(second, ids)
        second.commit()
    finally:
        if first_tx.is_active:
            first_tx.rollback()
        first.close()
        second.close()
    with engine.connect() as connection:
        if winner == "payment":
            assert connection.execute(
                text(
                    "SELECT sr.state,pa.state FROM stock_reservations sr "
                    "JOIN payment_attempt_reservations ar ON ar.reservation_id=sr.id "
                    "JOIN payment_attempts pa ON pa.id=ar.attempt_id "
                    "WHERE sr.id=:reservation"
                ),
                ids,
            ).one() == ("active", "call_started")
        else:
            assert (
                connection.execute(
                    text("SELECT state FROM stock_reservations WHERE id=:reservation"),
                    ids,
                ).scalar_one()
                == "released"
            )
    engine.dispose()


def _normalized_finding5_program(connection):
    function_names = [
        "validate_domestic_checkout_membership_write",
        "validate_domestic_checkout_reservation_write",
        "validate_domestic_checkout_payment_attempt_write",
    ]
    trigger_names = [
        "trg_payment_attempt_reservations_validate_domestic",
        "trg_stock_reservations_validate_legacy_insert",
        "trg_stock_reservations_validate_legacy_update",
        "trg_stock_reservations_validate_delete",
        "trg_stock_reservations_validate_domestic_insert",
        "trg_stock_reservations_validate_domestic_update",
        "trg_payment_attempts_validate_legacy_insert",
        "trg_payment_attempts_validate_legacy_update",
        "trg_payment_attempts_validate_delete",
        "trg_payment_attempts_validate_domestic_insert",
        "trg_payment_attempts_validate_domestic_update",
    ]
    functions = dict(
        connection.execute(
            text(
                "SELECT proname,regexp_replace(pg_get_functiondef(oid),'\\s+',' ','g') "
                "FROM pg_proc WHERE proname=ANY(:names)"
            ),
            {"names": function_names},
        ).all()
    )
    triggers = {
        row.name: re.sub(r"\s+", " ", row.definition).strip()
        for row in connection.execute(
            text(
                "SELECT tgname name,pg_get_triggerdef(oid,true) definition FROM pg_trigger "
                "WHERE NOT tgisinternal AND tgname=ANY(:names)"
            ),
            {"names": trigger_names},
        )
    }
    return functions, triggers


def test_finding5_postgresql_migration_and_orm_lifecycle_programs_have_exact_parity(
    disposable_m2_database,
) -> None:
    from app.core.base import Base

    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    migrated = create_engine(sync_url)
    database = f"shopsoma_m2_f5_model_{uuid.uuid4().hex[:12]}"
    admin = create_engine(
        sync_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.begin() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    model_engine = create_engine(sync_url.set(database=database))
    try:
        Base.metadata.create_all(model_engine)
        with migrated.connect() as left, model_engine.connect() as right:
            migrated_program = _normalized_finding5_program(left)
            assert len(migrated_program[0]) == 3
            assert len(migrated_program[1]) == 11
            assert migrated_program == _normalized_finding5_program(right)
    finally:
        model_engine.dispose()
        with admin.begin() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name"
                ),
                {"name": database},
            )
            connection.execute(text(f'DROP DATABASE "{database}"'))
        admin.dispose()
        migrated.dispose()


def test_finding3_postgresql_estimate_insert_rejects_cross_record_truth(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        valid = _install_domestic_tuple(connection)
        other = _install_domestic_tuple(connection)
        estimate_insert = (
            "INSERT INTO checkout_shipping_estimates (id,order_id,customer_id,"
            "destination_snapshot_hash,order_snapshot_hash,currency,ttl_seconds,expires_at,"
            "source_kind,source_command,idempotency_key,request_fingerprint,schema_version,"
            "created_by_actor_type,created_by_actor_id,supersedes_estimate_id) VALUES "
            "(:new_estimate,:order,:customer,:hash,:hash,:currency,1800,"
            "statement_timestamp()+interval '30 minutes','static_domestic_rate',"
            "'create_estimate',:key,:hash,'v1','customer',:actor,:supersedes)"
        )

        def rejected(**overrides):
            values = {
                **valid,
                "new_estimate": uuid.uuid4(),
                "hash": "f" * 64,
                "currency": "NGN",
                "key": f"finding3-{uuid.uuid4().hex}",
                "actor": str(valid["customer"]),
                "supersedes": None,
                **overrides,
            }
            _assert_rejected(connection, estimate_insert, values)

        rejected(customer=other["customer"])
        rejected(currency="USD")
        rejected(order=other["order"], customer=valid["customer"])
        quarantine_order = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO orders (id,order_number,customer_id,workflow_cohort,"
                "workflow_policy_version,checkout_access_mode,subtotal,shipping_cost,"
                "tax_amount,discount_amount,total_amount,currency,payment_status,"
                "fulfillment_status) VALUES (:id,:number,:customer,"
                "'legacy_ambiguous_quarantined','legacy_quarantine_v1',"
                "'legacy_quarantined',10,0,0,0,10,'NGN','PENDING','order_received')"
            ),
            {
                "id": quarantine_order,
                "number": f"M2-Q-{uuid.uuid4().hex[:12]}",
                "customer": other["customer"],
            },
        )
        rejected(order=quarantine_order, customer=other["customer"])
    engine.dispose()


def test_finding3_postgresql_option_and_selection_snapshots_are_authoritative(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection, include_selection=False)
        option_insert = (
            "INSERT INTO checkout_shipping_estimate_options "
            "(id,estimate_id,option_key,service_code,service_label,amount,currency,"
            "source_rate_id) VALUES (:new_option,:estimate,:option_key,'express','Express',"
            ":amount,:currency,:source_rate_id)"
        )

        for overrides in (
            {"currency": "USD"},
            {"source_rate_id": None},
            {"amount": Decimal("2.00"), "currency": "USD"},
        ):
            _assert_rejected(
                connection,
                option_insert,
                {
                    **ids,
                    "new_option": uuid.uuid4(),
                    "option_key": f"bad-{uuid.uuid4().hex}",
                    "amount": Decimal("2.00"),
                    "currency": "NGN",
                    "source_rate_id": ids["rate"],
                    **overrides,
                },
            )

        selection_insert = (
            "INSERT INTO checkout_shipping_estimate_selections "
            "(id,estimate_id,option_id,order_id,customer_id,selected_by_actor_type,"
            "selected_by_actor_id,shipping_amount,currency,source_command,idempotency_key,"
            "selected_at) VALUES (:new_selection,:estimate,:option,:order,:customer,"
            "'customer',:actor,:amount,:currency,'select_estimate',:key,:selected_at)"
        )

        def reject_selection(**overrides):
            values = {
                **ids,
                "new_selection": uuid.uuid4(),
                "actor": str(ids["customer"]),
                "amount": Decimal("1.00"),
                "currency": "NGN",
                "key": f"bad-selection-{uuid.uuid4().hex}",
                "selected_at": connection.scalar(text("SELECT statement_timestamp()")),
                **overrides,
            }
            _assert_rejected(connection, selection_insert, values)

        reject_selection(amount=Decimal("2.00"))
        reject_selection(currency="USD")
        reject_selection(order=uuid.uuid4())

        # Equality is legal for chronology: selection may occur exactly at estimate creation.
        created_at = connection.scalar(
            text(
                "SELECT created_at FROM checkout_shipping_estimates WHERE id=:estimate"
            ),
            ids,
        )
        connection.execute(
            text(selection_insert),
            {
                **ids,
                "new_selection": ids["selection"],
                "actor": str(ids["customer"]),
                "amount": Decimal("1.00"),
                "currency": "NGN",
                "key": f"equal-boundary-{uuid.uuid4().hex}",
                "selected_at": created_at,
            },
        )
    engine.dispose()


def test_finding3_postgresql_supersession_requires_current_unselected_leaf(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        stale = _install_domestic_tuple(connection, include_selection=False)
        successor = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO checkout_shipping_estimates (id,order_id,customer_id,"
                "destination_snapshot_hash,order_snapshot_hash,currency,ttl_seconds,expires_at,"
                "supersedes_estimate_id,source_kind,source_command,idempotency_key,"
                "request_fingerprint,schema_version,created_by_actor_type,"
                "created_by_actor_id) VALUES (:successor,:order,:customer,:hash,:hash,'NGN',"
                "1800,statement_timestamp()+interval '30 minutes',:estimate,"
                "'static_domestic_rate','refresh_estimate',:key,:hash,'v1','customer',:actor)"
            ),
            {
                **stale,
                "successor": successor,
                "hash": "7" * 64,
                "key": f"successor-{uuid.uuid4().hex}",
                "actor": str(stale["customer"]),
            },
        )
        _assert_rejected(
            connection,
            "INSERT INTO checkout_shipping_estimate_selections "
            "(id,estimate_id,option_id,order_id,customer_id,selected_by_actor_type,"
            "selected_by_actor_id,shipping_amount,currency,source_command,idempotency_key,"
            "selected_at) VALUES (:selection,:estimate,:option,:order,:customer,'customer',"
            ":actor,1,'NGN','select_estimate',:key,statement_timestamp())",
            {
                **stale,
                "actor": str(stale["customer"]),
                "key": f"stale-select-{uuid.uuid4().hex}",
            },
        )

        selected = _install_domestic_tuple(connection)
        _assert_rejected(
            connection,
            "INSERT INTO checkout_shipping_estimates (id,order_id,customer_id,"
            "destination_snapshot_hash,order_snapshot_hash,currency,ttl_seconds,expires_at,"
            "supersedes_estimate_id,source_kind,source_command,idempotency_key,"
            "request_fingerprint,schema_version,created_by_actor_type,created_by_actor_id) "
            "VALUES (:new_estimate,:order,:customer,:hash,:hash,'NGN',1800,"
            "statement_timestamp()+interval '30 minutes',:estimate,'static_domestic_rate',"
            "'refresh_estimate',:key,:hash,'v1','customer',:actor)",
            {
                **selected,
                "new_estimate": uuid.uuid4(),
                "hash": "8" * 64,
                "key": f"selected-predecessor-{uuid.uuid4().hex}",
                "actor": str(selected["customer"]),
            },
        )
    engine.dispose()


def test_finding3_postgresql_option_must_share_estimate_creation_transaction(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection, include_selection=False)
    with engine.begin() as connection:
        _assert_rejected(
            connection,
            "INSERT INTO checkout_shipping_estimate_options "
            "(id,estimate_id,option_key,service_code,service_label,amount,currency,"
            "source_rate_id) VALUES (:id,:estimate,'late','late','Late',2,'NGN',:rate)",
            {**ids, "id": uuid.uuid4()},
        )
    engine.dispose()


def test_finding3_postgresql_inventory_ancestry_and_completion_coverage(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        wrong_item = uuid.uuid4()
        _assert_rejected(
            connection,
            "INSERT INTO order_items (id,order_id,product_id,vendor_id,product_title,"
            "quantity,unit_price,subtotal,currency,commission_rate,commission_amount,"
            "vendor_payout,fulfillment_status,inventory_policy,inventory_subject_kind,"
            "inventory_subject_id,inventory_source_product_id,"
            "inventory_source_catalogue_version,inventory_source_evidence_hash,"
            "inventory_policy_snapshot_at) VALUES (:wrong_item,:order,:product,:vendor,"
            "'Wrong ancestry',1,10,10,'NGN',10,1,9,'order_received','stock_managed',"
            "'product',:other_product,:product,'catalogue-v1',:hash,statement_timestamp())",
            {
                **ids,
                "wrong_item": wrong_item,
                "other_product": uuid.uuid4(),
                "hash": "9" * 64,
            },
        )

        _assert_deferred_rejected(
            connection,
            "UPDATE orders SET checkout_prerequisites_completed_at=statement_timestamp() "
            "WHERE id=:order",
            ids,
        )

        _insert_domestic_reservation(connection, ids)
        mto_item = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO order_items (id,order_id,product_id,vendor_id,product_title,"
                "quantity,unit_price,subtotal,currency,commission_rate,commission_amount,"
                "vendor_payout,fulfillment_status,inventory_policy,inventory_source_product_id,"
                "inventory_source_catalogue_version,inventory_source_evidence_hash,"
                "inventory_policy_snapshot_at) VALUES (:mto_item,:order,:product,:vendor,"
                "'MTO item',1,10,10,'NGN',10,1,9,'order_received','made_to_order',:product,"
                "'catalogue-v1',:hash,statement_timestamp())"
            ),
            {**ids, "mto_item": mto_item, "hash": "6" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO order_inventory_coverage "
                "(order_item_id,order_id,checkout_estimate_selection_id,inventory_policy,"
                "reservation_id) VALUES (:item,:order,:selection,'stock_managed',:reservation)"
            ),
            ids,
        )
        _assert_deferred_rejected(
            connection,
            "UPDATE orders SET checkout_prerequisites_completed_at=statement_timestamp() "
            "WHERE id=:order",
            ids,
        )
        connection.execute(
            text(
                "INSERT INTO order_inventory_coverage "
                "(order_item_id,order_id,checkout_estimate_selection_id,inventory_policy) "
                "VALUES (:mto_item,:order,:selection,'made_to_order')"
            ),
            {**ids, "mto_item": mto_item},
        )
        connection.execute(
            text(
                "UPDATE orders SET checkout_prerequisites_completed_at=statement_timestamp() "
                "WHERE id=:order"
            ),
            ids,
        )
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        for statement, parameters in (
            (
                "DELETE FROM order_inventory_coverage WHERE order_item_id=:item",
                ids,
            ),
            (
                "UPDATE order_inventory_coverage SET checkout_estimate_selection_id=:other "
                "WHERE order_item_id=:item",
                {**ids, "other": uuid.uuid4()},
            ),
            (
                "INSERT INTO order_inventory_coverage (order_item_id,order_id,"
                "checkout_estimate_selection_id,inventory_policy,reservation_id) VALUES "
                "(:item,:order,:selection,'stock_managed',:reservation)",
                ids,
            ),
        ):
            _assert_deferred_rejected(connection, statement, parameters)
    engine.dispose()


def _wait_until_postgres_worker_is_lock_blocked(engine, application_name: str) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with engine.connect() as observer:
            waiting = observer.scalar(
                text(
                    "SELECT count(*) FROM pg_stat_activity WHERE application_name=:name "
                    "AND wait_event_type='Lock'"
                ),
                {"name": application_name},
            )
        if waiting:
            return
        time.sleep(0.02)
    raise AssertionError(
        f"PostgreSQL worker {application_name!r} did not block on a lock"
    )


def test_finding3_postgresql_selection_and_supersession_race_serializes(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection, include_selection=False)

    selector = engine.connect()
    selector_transaction = selector.begin()
    selector.execute(
        text(
            "INSERT INTO checkout_shipping_estimate_selections "
            "(id,estimate_id,option_id,order_id,customer_id,selected_by_actor_type,"
            "selected_by_actor_id,shipping_amount,currency,source_command,idempotency_key,"
            "selected_at) VALUES (:selection,:estimate,:option,:order,:customer,'customer',"
            ":actor,1,'NGN','select_estimate',:key,statement_timestamp())"
        ),
        {
            **ids,
            "actor": str(ids["customer"]),
            "key": f"race-selection-{uuid.uuid4().hex}",
        },
    )
    started = Event()
    application_name = f"finding3-supersession-{uuid.uuid4().hex}"
    successor = uuid.uuid4()

    def supersede() -> str:
        with engine.connect() as worker:
            worker.execute(
                text("SET application_name=:name"), {"name": application_name}
            )
            transaction = worker.begin_nested()
            started.set()
            try:
                worker.execute(
                    text(
                        "INSERT INTO checkout_shipping_estimates "
                        "(id,order_id,customer_id,destination_snapshot_hash,order_snapshot_hash,"
                        "currency,ttl_seconds,expires_at,supersedes_estimate_id,source_kind,"
                        "source_command,idempotency_key,request_fingerprint,schema_version,"
                        "created_by_actor_type,created_by_actor_id) VALUES "
                        "(:successor,:order,:customer,:hash,:hash,'NGN',1800,"
                        "statement_timestamp()+interval '30 minutes',:estimate,"
                        "'static_domestic_rate','refresh_estimate',:key,:hash,'v1','customer',:actor)"
                    ),
                    {
                        **ids,
                        "successor": successor,
                        "hash": "4" * 64,
                        "key": f"race-supersession-{uuid.uuid4().hex}",
                        "actor": str(ids["customer"]),
                    },
                )
                transaction.commit()
                return "committed"
            except Exception:
                transaction.rollback()
                return "rejected"

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(supersede)
            assert started.wait(timeout=2)
            _wait_until_postgres_worker_is_lock_blocked(engine, application_name)
            selector_transaction.commit()
            assert future.result(timeout=5) == "rejected"
    finally:
        if selector_transaction.is_active:
            selector_transaction.rollback()
        selector.close()
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM checkout_shipping_estimate_selections WHERE id=:selection"
                ),
                ids,
            )
            == 1
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM checkout_shipping_estimates WHERE id=:successor"
                ),
                {"successor": successor},
            )
            == 0
        )
    engine.dispose()


def test_finding3_postgresql_completion_and_coverage_mutation_race_serializes(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        _insert_domestic_reservation(connection, ids)
        connection.execute(
            text(
                "INSERT INTO order_inventory_coverage "
                "(order_item_id,order_id,checkout_estimate_selection_id,inventory_policy,"
                "reservation_id) VALUES (:item,:order,:selection,'stock_managed',:reservation)"
            ),
            ids,
        )

    completer = engine.connect()
    completion_transaction = completer.begin()
    completer.execute(
        text(
            "UPDATE orders SET checkout_prerequisites_completed_at=statement_timestamp() "
            "WHERE id=:order"
        ),
        ids,
    )
    completer.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    started = Event()
    mutation_rejected = Event()
    release_worker = Event()
    application_name = f"finding3-coverage-{uuid.uuid4().hex}"
    worker_timeline = {}

    def delete_coverage():
        with engine.connect() as worker:
            worker.execute(
                text("SET application_name=:name"), {"name": application_name}
            )
            worker_timeline["pid"] = worker.scalar(text("SELECT pg_backend_pid()"))
            transaction = worker.begin_nested()
            started.set()
            try:
                worker.execute(
                    text(
                        "DELETE FROM order_inventory_coverage WHERE order_item_id=:item"
                    ),
                    ids,
                )
            except DBAPIError as error:
                transaction.rollback()
                worker_timeline["sqlstate"] = error.orig.pgcode
                worker_timeline["message"] = error.orig.diag.message_primary
                mutation_rejected.set()
                assert release_worker.wait(timeout=2)
                return worker_timeline["sqlstate"], worker_timeline["message"]
            transaction.commit()
            mutation_rejected.set()
            assert release_worker.wait(timeout=2)
            return "committed", None

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(delete_coverage)
            assert started.wait(timeout=2)
            assert mutation_rejected.wait(timeout=2)
            with engine.connect() as observer:
                worker_state = observer.execute(
                    text(
                        "SELECT state,wait_event_type,wait_event,pg_blocking_pids(pid) blockers "
                        "FROM pg_stat_activity WHERE pid=:pid AND application_name=:name"
                    ),
                    {"pid": worker_timeline["pid"], "name": application_name},
                ).one()
                assert worker_state.state == "idle in transaction"
                assert worker_state.wait_event_type == "Client"
                assert worker_state.wait_event == "ClientRead"
                assert worker_state.blockers == []
                assert observer.scalar(
                    text(
                        "SELECT checkout_prerequisites_completed_at IS NULL "
                        "FROM orders WHERE id=:order"
                    ),
                    ids,
                )
                assert (
                    observer.scalar(
                        text(
                            "SELECT count(*) FROM order_inventory_coverage "
                            "WHERE order_item_id=:item"
                        ),
                        ids,
                    )
                    == 1
                )
            assert worker_timeline == {
                "pid": worker_timeline["pid"],
                "sqlstate": "P0001",
                "message": "immutable checkout prerequisite evidence",
            }
            release_worker.set()
            assert future.result(timeout=2) == (
                "P0001",
                "immutable checkout prerequisite evidence",
            )
            completion_transaction.commit()
    finally:
        release_worker.set()
        if completion_transaction.is_active:
            completion_transaction.rollback()
        completer.close()
    with engine.connect() as connection:
        assert connection.scalar(
            text(
                "SELECT checkout_prerequisites_completed_at IS NOT NULL FROM orders WHERE id=:order"
            ),
            ids,
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM order_inventory_coverage WHERE order_item_id=:item"
                ),
                ids,
            )
            == 1
        )
    engine.dispose()


def test_finding3_postgresql_expiry_and_missing_selection_boundaries_fail_closed(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection, include_selection=False)
        _assert_deferred_rejected(
            connection,
            "UPDATE orders SET checkout_prerequisites_completed_at=statement_timestamp() "
            "WHERE id=:order",
            ids,
        )
        expires_at = connection.scalar(
            text(
                "SELECT expires_at FROM checkout_shipping_estimates WHERE id=:estimate"
            ),
            ids,
        )
        _assert_rejected(
            connection,
            "INSERT INTO checkout_shipping_estimate_selections "
            "(id,estimate_id,option_id,order_id,customer_id,selected_by_actor_type,"
            "selected_by_actor_id,shipping_amount,currency,source_command,idempotency_key,"
            "selected_at) VALUES (:selection,:estimate,:option,:order,:customer,'customer',"
            ":actor,1,'NGN','select_estimate',:key,:expires_at)",
            {
                **ids,
                "actor": str(ids["customer"]),
                "key": f"expiry-equality-{uuid.uuid4().hex}",
                "expires_at": expires_at,
            },
        )
    engine.dispose()


def test_postgresql_inventory_snapshot_and_original_owner_are_immutable(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    snapshot_columns = (
        "inventory_policy",
        "inventory_subject_kind",
        "inventory_subject_id",
        "inventory_source_product_id",
        "inventory_source_catalogue_version",
        "inventory_source_evidence_hash",
        "inventory_policy_snapshot_at",
    )

    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        connection.execute(
            text(
                "INSERT INTO order_current_owners (order_id,original_customer_id) "
                "VALUES (:order,:customer)"
            ),
            ids,
        )

        replacements = {
            "inventory_policy": "made_to_order",
            "inventory_subject_kind": None,
            "inventory_subject_id": None,
            "inventory_source_product_id": None,
            "inventory_source_catalogue_version": "catalogue-v2",
            "inventory_source_evidence_hash": "c" * 64,
            "inventory_policy_snapshot_at": "2099-01-01T00:00:00+00:00",
        }
        for column in snapshot_columns:
            _assert_rejected(
                connection,
                f"UPDATE order_items SET {column}=:value WHERE id=:item",
                {**ids, "value": replacements[column]},
            )

        other_customer = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                "VALUES (:id,:email,'Other owner','CUSTOMER',false)"
            ),
            {
                "id": other_customer,
                "email": f"m2-owner-{uuid.uuid4().hex}@example.test",
            },
        )
        _assert_rejected(
            connection,
            "UPDATE order_current_owners SET original_customer_id=:other "
            "WHERE order_id=:order",
            {**ids, "other": other_customer},
        )
        _assert_rejected(
            connection,
            "UPDATE order_current_owners SET order_id=:other_order WHERE order_id=:order",
            {**ids, "other_order": uuid.uuid4()},
        )
        capability_id = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO order_guest_capabilities "
                "(id,order_id,original_customer_id,scope,token_digest,pepper_key_version,"
                "expires_at) VALUES (:capability,:order,:customer,'claim_order',"
                "decode(:digest,'hex'),1,statement_timestamp()+interval '1 day')"
            ),
            {**ids, "capability": capability_id, "digest": "e" * 64},
        )
        connection.execute(
            text(
                "UPDATE order_current_owners SET current_authenticated_user_id=:other,"
                "claim_capability_id=:capability,claim_idempotency_key='claim-once',"
                "claimed_at=statement_timestamp(),row_version=row_version+1 "
                "WHERE order_id=:order"
            ),
            {**ids, "other": other_customer, "capability": capability_id},
        )
        for assignment, value in (
            ("current_authenticated_user_id=:value", ids["customer"]),
            ("claim_capability_id=:value", uuid.uuid4()),
            ("claim_idempotency_key=:value", "changed-claim"),
            ("claimed_at=:value", "2099-01-01T00:00:00+00:00"),
        ):
            _assert_rejected(
                connection,
                f"UPDATE order_current_owners SET {assignment} WHERE order_id=:order",
                {**ids, "value": value},
            )
        _assert_rejected(
            connection,
            "DELETE FROM order_current_owners WHERE order_id=:order",
            ids,
        )

        item_snapshot = connection.execute(
            text(
                "SELECT inventory_policy,inventory_subject_kind,inventory_subject_id,"
                "inventory_source_product_id,inventory_source_catalogue_version,"
                "inventory_source_evidence_hash,inventory_policy_snapshot_at "
                "FROM order_items WHERE id=:item"
            ),
            ids,
        ).one()
        assert item_snapshot[:6] == (
            "stock_managed",
            "product",
            ids["product"],
            ids["product"],
            "catalogue-v1",
            "a" * 64,
        )
        assert item_snapshot[6] is not None
        assert connection.execute(
            text(
                "SELECT original_customer_id,row_version FROM order_current_owners "
                "WHERE order_id=:order"
            ),
            ids,
        ).one() == (ids["customer"], 2)
    engine.dispose()


def test_postgresql_order_delete_cascades_only_its_owner_projection(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        first = {"order": uuid.uuid4(), "customer": uuid.uuid4()}
        second = {"order": uuid.uuid4(), "customer": uuid.uuid4()}
        other_customer = uuid.uuid4()
        for position, ids in enumerate((first, second), start=1):
            connection.execute(
                text(
                    "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                    "VALUES (:customer,:email,'Owner projection customer','CUSTOMER',false)"
                ),
                {**ids, "email": f"m2-owner-{uuid.uuid4().hex}@example.test"},
            )
            connection.execute(
                text(
                    "INSERT INTO orders (id,order_number,customer_id,workflow_cohort,"
                    "workflow_policy_version,checkout_access_mode,subtotal,shipping_cost,"
                    "tax_amount,discount_amount,total_amount,currency,payment_status,"
                    "fulfillment_status) VALUES (:order,:number,:customer,"
                    "'domestic_checkout_v1','domestic_checkout_v1','authenticated',"
                    "10,0,0,0,10,'NGN','PENDING','order_received')"
                ),
                {**ids, "number": f"M2-OWNER-{position}-{uuid.uuid4().hex[:8]}"},
            )
            connection.execute(
                text(
                    "INSERT INTO order_current_owners (order_id,original_customer_id) "
                    "VALUES (:order,:customer)"
                ),
                ids,
            )
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                "VALUES (:customer,:email,'Other owner','CUSTOMER',false)"
            ),
            {
                "customer": other_customer,
                "email": f"m2-other-owner-{uuid.uuid4().hex}@example.test",
            },
        )

        _assert_rejected(
            connection,
            "DELETE FROM order_current_owners WHERE order_id=:order",
            first,
        )
        _assert_rejected(
            connection,
            "UPDATE order_current_owners SET original_customer_id=:other "
            "WHERE order_id=:order",
            {**first, "other": other_customer},
        )
        connection.execute(text("DELETE FROM orders WHERE id=:order"), first)

        assert (
            connection.scalar(
                text("SELECT count(*) FROM order_current_owners WHERE order_id=:order"),
                first,
            )
            == 0
        )
        assert (
            connection.scalar(
                text("SELECT count(*) FROM order_current_owners WHERE order_id=:order"),
                second,
            )
            == 1
        )
    engine.dispose()


def test_postgresql_compatibility_backfill_can_establish_initial_inventory_snapshot(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        compatibility_item = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO order_items (id,order_id,product_id,vendor_id,product_title,"
                "quantity,unit_price,subtotal,currency,commission_rate,commission_amount,"
                "vendor_payout,fulfillment_status) VALUES "
                "(:compatibility_item,:order,:product,:vendor,'Compatibility item',1,10,10,"
                "'NGN',10,1,9,'order_received')"
            ),
            {**ids, "compatibility_item": compatibility_item},
        )
        connection.execute(
            text(
                "UPDATE order_items SET inventory_policy='stock_managed',"
                "inventory_subject_kind='product',inventory_subject_id=:product,"
                "inventory_source_product_id=:product,"
                "inventory_source_catalogue_version='catalogue-v1',"
                "inventory_source_evidence_hash=:hash,"
                "inventory_policy_snapshot_at=statement_timestamp() WHERE id=:compatibility_item"
            ),
            {
                **ids,
                "compatibility_item": compatibility_item,
                "hash": "d" * 64,
            },
        )
        assert (
            connection.scalar(
                text(
                    "SELECT inventory_policy FROM order_items WHERE id=:compatibility_item"
                ),
                {"compatibility_item": compatibility_item},
            )
            == "stock_managed"
        )
        _assert_rejected(
            connection,
            "UPDATE order_items SET inventory_subject_id=:other_product "
            "WHERE id=:compatibility_item",
            {
                "compatibility_item": compatibility_item,
                "other_product": uuid.uuid4(),
            },
        )
        _assert_deferred_rejected(
            connection,
            "INSERT INTO order_items "
            "(id,order_id,product_id,vendor_id,product_title,quantity,unit_price,subtotal,"
            "currency,commission_rate,commission_amount,vendor_payout,fulfillment_status) "
            "VALUES (:incomplete_item,:order,:product,:vendor,'Incomplete item',1,10,10,"
            "'NGN',10,1,9,'order_received')",
            {**ids, "incomplete_item": uuid.uuid4()},
        )
    engine.dispose()


def test_f9_triggers_accept_valid_domestic_binding_family(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        ids["attempt"] = uuid.uuid4()
        _insert_domestic_reservation(connection, ids)
        _insert_domestic_attempt(connection, ids)
        connection.execute(
            text(
                "INSERT INTO payment_attempt_reservations "
                "(attempt_id,reservation_id,membership_family,order_id,order_item_id,"
                "checkout_estimate_selection_id) VALUES "
                "(:attempt,:reservation,'domestic_checkout_v1',:order,:item,:selection)"
            ),
            ids,
        )
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        assert connection.execute(
            text(
                "SELECT sr.workflow_cohort,pa.workflow_cohort "
                "FROM stock_reservations sr CROSS JOIN payment_attempts pa "
                "WHERE sr.id=:reservation AND pa.id=:attempt"
            ),
            ids,
        ).one() == ("domestic_checkout_v1", "domestic_checkout_v1")
    engine.dispose()


def test_postgresql_direct_sql_ownership_and_binding_matrix(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    reservation_insert = (
        "INSERT INTO stock_reservations (id,order_id,order_item_id,customer_id,"
        "workflow_cohort,checkout_estimate_selection_id,inventory_subject_kind,"
        "inventory_subject_id,product_id,variant_id,size_stock_id,quantity,unit_price,"
        "line_amount,currency,ttl_seconds,expires_at,state,source_command,idempotency_key,"
        "creation_txid,quote_id) VALUES (:reservation,:order,:item,:customer,"
        "'domestic_checkout_v1',:selection,:subject_kind,:subject_id,:product,:variant,"
        ":size_stock,1,10,10,'NGN',1800,statement_timestamp()+interval '30 minutes',"
        "'active','reserve',:key,txid_current(),:quote)"
    )
    attempt_insert = (
        "INSERT INTO payment_attempts (id,order_id,customer_id,workflow_cohort,"
        "checkout_estimate_selection_id,amount,currency,provider,provider_reference,"
        "source_command,idempotency_key,quote_id) VALUES "
        "(:attempt,:order,:customer,'domestic_checkout_v1',:selection,:amount,'NGN',"
        "'test_provider',:reference,'pay',:key,:quote)"
    )
    membership_insert = (
        "INSERT INTO payment_attempt_reservations "
        "(attempt_id,reservation_id,membership_family,order_id,order_item_id,"
        "checkout_estimate_selection_id) VALUES "
        "(:attempt,:reservation,'domestic_checkout_v1',:order,:item,:selection)"
    )

    with engine.begin() as connection:
        first = _install_domestic_tuple(connection)
        second = _install_domestic_tuple(connection)
        third = _install_domestic_tuple(connection)

        _assert_deferred_rejected(
            connection,
            "UPDATE orders SET checkout_estimate_selection_id=:other_selection "
            "WHERE id=:order",
            {**first, "other_selection": second["selection"]},
        )
        _assert_rejected(
            connection,
            "INSERT INTO checkout_shipping_estimate_selections "
            "(id,estimate_id,option_id,order_id,customer_id,selected_by_actor_type,"
            "selected_by_actor_id,shipping_amount,currency,source_command,idempotency_key,"
            "selected_at) VALUES (:bad_selection,:estimate,:other_option,:order,:customer,"
            "'customer',:actor,1,'NGN','select_estimate',:key,statement_timestamp())",
            {
                **first,
                "bad_selection": uuid.uuid4(),
                "other_option": second["option"],
                "actor": str(first["customer"]),
                "key": f"cross-estimate-{uuid.uuid4().hex}",
            },
        )

        for ids in (first, second):
            _insert_domestic_reservation(connection, ids)

        def reject_reservation(**overrides):
            values = {
                **first,
                "reservation": uuid.uuid4(),
                "subject_kind": "product",
                "subject_id": first["product"],
                "variant": None,
                "size_stock": None,
                "quote": None,
                "key": f"reject-reserve-{uuid.uuid4().hex}",
                **overrides,
            }
            connection.execute(
                text(
                    "SELECT coordinate_stock_reservation_write("
                    ":reservation,:order,:product,:variant,:size_stock)"
                ),
                values,
            )
            _assert_rejected(connection, reservation_insert, values)

        reject_reservation(item=second["item"])
        reject_reservation(selection=second["selection"])
        reject_reservation(variant=uuid.uuid4())
        reject_reservation(quote=uuid.uuid4())

        _assert_rejected(
            connection,
            "INSERT INTO order_inventory_coverage "
            "(order_item_id,order_id,checkout_estimate_selection_id,inventory_policy,"
            "reservation_id) VALUES (:other_item,:order,:selection,'stock_managed',"
            ":reservation)",
            {**first, "other_item": second["item"]},
        )

        def reject_attempt(ids, **overrides):
            values = {
                **ids,
                "attempt": uuid.uuid4(),
                "amount": 10,
                "quote": None,
                "reference": f"reject-pay-{uuid.uuid4().hex}",
                "key": f"reject-pay-{uuid.uuid4().hex}",
                **overrides,
            }
            connection.execute(
                text("SELECT coordinate_payment_attempt_write(:attempt,:order)"), values
            )
            _assert_rejected(connection, attempt_insert, values)

        reject_attempt(first, amount=11)
        reject_attempt(first, customer=second["customer"])
        reject_attempt(first, order=second["order"])
        reject_attempt(first, selection=second["selection"])
        reject_attempt(first, quote=uuid.uuid4())
        reject_attempt(third)

        for ids in (first, second):
            ids["attempt"] = uuid.uuid4()
            _insert_domestic_attempt(connection, ids)

        for overrides in (
            {"order": second["order"]},
            {"item": second["item"]},
            {"selection": second["selection"]},
        ):
            _assert_deferred_rejected(
                connection,
                membership_insert,
                {**first, **overrides},
            )

        for ids in (first, second):
            connection.execute(text(membership_insert), ids)
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        assert (
            connection.scalar(text("SELECT count(*) FROM payment_attempt_reservations"))
            == 2
        )
    engine.dispose()


def test_postgresql_membership_families_preserve_f9_and_reject_mixed_shapes(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_domestic_tuple(connection)
        ids["attempt"] = uuid.uuid4()
        _insert_domestic_reservation(connection, ids)
        _insert_domestic_attempt(connection, ids)

        connection.execute(
            text(
                "INSERT INTO payment_attempt_reservations (attempt_id,reservation_id) "
                "VALUES (:attempt,:reservation)"
            ),
            ids,
        )
        assert connection.execute(
            text(
                "SELECT membership_family,order_id,order_item_id,"
                "checkout_estimate_selection_id FROM payment_attempt_reservations "
                "WHERE attempt_id=:attempt AND reservation_id=:reservation"
            ),
            ids,
        ).one() == ("legacy_f9", None, None, None)
        _assert_rejected(
            connection,
            "UPDATE payment_attempt_reservations SET membership_family='legacy_f9' "
            "WHERE attempt_id=:attempt AND reservation_id=:reservation",
            ids,
        )
        _assert_rejected(
            connection,
            "DELETE FROM payment_attempt_reservations "
            "WHERE attempt_id=:attempt AND reservation_id=:reservation",
            ids,
        )

        complete = _install_domestic_tuple(connection)
        complete.update(attempt=uuid.uuid4(), reservation=uuid.uuid4())
        _insert_domestic_reservation(connection, complete)
        _insert_domestic_attempt(connection, complete)
        connection.execute(
            text(
                "INSERT INTO payment_attempt_reservations "
                "(attempt_id,reservation_id,membership_family,order_id,order_item_id,"
                "checkout_estimate_selection_id) VALUES "
                "(:attempt,:reservation,'domestic_checkout_v1',:order,:item,:selection)"
            ),
            complete,
        )
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

        for family, order_id, item_id, selection_id in (
            ("legacy_f9", ids["order"], None, None),
            ("domestic_checkout_v1", ids["order"], None, ids["selection"]),
            ("unknown", None, None, None),
        ):
            _assert_rejected(
                connection,
                "INSERT INTO payment_attempt_reservations "
                "(attempt_id,reservation_id,membership_family,order_id,order_item_id,"
                "checkout_estimate_selection_id) VALUES "
                "(:attempt,:reservation,:family,:order,:item,:selection)",
                {
                    **ids,
                    "family": family,
                    "order": order_id,
                    "item": item_id,
                    "selection": selection_id,
                },
            )
    engine.dispose()


def test_postgresql_classifier_freezes_watermark_and_resumes_bounded_batches(
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
    customer_id = uuid.uuid4()
    historical_ids = [uuid.uuid4() for _ in range(3)]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                "VALUES (:id,:email,'Classifier customer','CUSTOMER',false)"
            ),
            {
                "id": customer_id,
                "email": f"classifier-{uuid.uuid4().hex}@example.test",
            },
        )
        for position, order_id in enumerate(historical_ids):
            connection.execute(
                text(
                    "INSERT INTO orders "
                    "(id,order_number,customer_id,subtotal,shipping_cost,tax_amount,"
                    "discount_amount,total_amount,currency,payment_status,"
                    "fulfillment_status,created_at) VALUES "
                    "(:id,:number,:customer,10,0,0,0,10,'NGN','PENDING',"
                    "'order_received',statement_timestamp() - interval '10 seconds' "
                    "+ :offset * interval '1 second')"
                ),
                {
                    "id": order_id,
                    "number": f"M2-CLASSIFY-{uuid.uuid4().hex[:8]}",
                    "customer": customer_id,
                    "offset": position,
                },
            )
        connection.execute(
            text(
                "INSERT INTO order_current_owners "
                "(order_id,original_customer_id) VALUES (:order,:customer)"
            ),
            {"order": historical_ids[0], "customer": customer_id},
        )

    identity = ClassificationRunIdentity(
        compatibility_writer_release_id="classifier-test-release",
        migration_revision=REVISIONS[1],
        deployment_identity="pytest",
    )
    run_id = start_workflow_classification_run(engine, identity)
    assert start_workflow_classification_run(engine, identity) == run_id

    post_writer_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO orders "
                "(id,order_number,customer_id,subtotal,shipping_cost,tax_amount,"
                "discount_amount,total_amount,currency,payment_status,fulfillment_status) "
                "VALUES (:id,:number,:customer,10,0,0,0,10,'NGN','PENDING',"
                "'order_received')"
            ),
            {
                "id": post_writer_id,
                "number": f"M2-POST-{uuid.uuid4().hex[:8]}",
                "customer": customer_id,
            },
        )

    assert classify_workflow_batch(engine, run_id, batch_size=2) == 2
    assert classify_workflow_batch(engine, run_id, batch_size=2) == 1
    assert classify_workflow_batch(engine, run_id, batch_size=2) == 0
    assert finalize_workflow_classification(engine, run_id) == 4

    with engine.connect() as connection:
        run = connection.execute(
            text(
                "SELECT high_watermark_created_at,high_watermark_order_id,"
                "classified_row_count,classification_cutover_at "
                "FROM order_workflow_migration_runs WHERE id=:run"
            ),
            {"run": run_id},
        ).one()
        assert (
            run[0:2]
            == connection.execute(
                text("SELECT created_at,id FROM orders WHERE id=:id"),
                {"id": historical_ids[-1]},
            ).one()
        )
        assert run[2:] == (4, run[3])
        assert run[3] is not None
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM order_workflow_classifications "
                    "WHERE cohort='legacy_ambiguous_quarantined'"
                )
            )
            == 2
        )
        assert connection.execute(
            text(
                "SELECT cohort,evidence_kind FROM order_workflow_classifications "
                "WHERE order_id=:order"
            ),
            {"order": historical_ids[0]},
        ).one() == (
            "legacy_pre_bridge",
            "positive_original_owner_evidence",
        )
        assert connection.execute(
            text(
                "SELECT cohort,evidence_kind FROM order_workflow_classifications "
                "WHERE order_id=:order"
            ),
            {"order": post_writer_id},
        ).one() == (
            "legacy_pre_bridge",
            "positive_release_or_bridge_evidence",
        )
    engine.dispose()


def test_postgresql_classifier_skips_locks_resumes_and_parallel_workers(
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
    customer_id = uuid.uuid4()
    order_ids = [uuid.uuid4() for _ in range(12)]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                "VALUES (:id,:email,'Parallel classifier','CUSTOMER',false)"
            ),
            {
                "id": customer_id,
                "email": f"parallel-classifier-{uuid.uuid4().hex}@example.test",
            },
        )
        for position, order_id in enumerate(order_ids):
            connection.execute(
                text(
                    "INSERT INTO orders "
                    "(id,order_number,customer_id,subtotal,shipping_cost,tax_amount,"
                    "discount_amount,total_amount,currency,payment_status,"
                    "fulfillment_status,created_at) VALUES "
                    "(:id,:number,:customer,10,0,0,0,10,'NGN','PENDING',"
                    "'order_received',statement_timestamp() - interval '30 seconds' "
                    "+ :offset * interval '1 millisecond')"
                ),
                {
                    "id": order_id,
                    "number": f"M2-PARALLEL-{uuid.uuid4().hex[:8]}",
                    "customer": customer_id,
                    "offset": position,
                },
            )

    run_id = start_workflow_classification_run(
        engine,
        ClassificationRunIdentity("parallel-release", REVISIONS[1], "pytest"),
    )
    locked = engine.connect()
    transaction = locked.begin()
    locked.execute(
        text("SELECT id FROM orders WHERE id=:id FOR UPDATE"), {"id": order_ids[0]}
    )
    try:
        assert classify_workflow_batch(engine, run_id, batch_size=1) == 1
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM order_workflow_classifications "
                        "WHERE order_id=:id"
                    ),
                    {"id": order_ids[0]},
                )
                == 0
            )
    finally:
        transaction.rollback()
        locked.close()

    # The first batch is committed; this call is the crash/rerun boundary.
    assert classify_workflow_batch(engine, run_id, batch_size=1) == 1

    def drain_worker() -> int:
        processed = 0
        while True:
            count = classify_workflow_batch(engine, run_id, batch_size=2)
            processed += count
            if count == 0:
                return processed

    with ThreadPoolExecutor(max_workers=2) as executor:
        worker_counts = list(executor.map(lambda _index: drain_worker(), range(2)))

    assert sum(worker_counts) == 10
    assert finalize_workflow_classification(engine, run_id) == 12
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM orders")) == 12
        assert (
            connection.scalar(
                text("SELECT count(*) FROM order_workflow_classifications")
            )
            == 12
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(DISTINCT order_id) FROM order_workflow_classifications"
                )
            )
            == 12
        )
        assert (
            connection.scalar(text("SELECT count(*) FROM order_current_owners")) == 12
        )
    engine.dispose()


def test_postgresql_classifier_changed_candidate_aborts_atomically(
    disposable_m2_database,
) -> None:
    from app.services.orders.workflow_classification import (
        ClassificationConflict,
        ClassificationRunIdentity,
        classify_workflow_batch,
        start_workflow_classification_run,
    )

    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[1])
    engine = create_engine(sync_url)
    customer_id, order_id = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                "VALUES (:id,:email,'Changed candidate','CUSTOMER',false)"
            ),
            {
                "id": customer_id,
                "email": f"changed-classifier-{uuid.uuid4().hex}@example.test",
            },
        )
        connection.execute(
            text(
                "INSERT INTO orders "
                "(id,order_number,customer_id,subtotal,shipping_cost,tax_amount,"
                "discount_amount,total_amount,currency,payment_status,fulfillment_status) "
                "VALUES (:id,:number,:customer,10,0,0,0,10,'NGN','PENDING',"
                "'order_received')"
            ),
            {
                "id": order_id,
                "number": f"M2-CHANGED-{uuid.uuid4().hex[:8]}",
                "customer": customer_id,
            },
        )

    run_id = start_workflow_classification_run(
        engine,
        ClassificationRunIdentity("changed-release", REVISIONS[1], "pytest"),
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO order_workflow_classifications "
                "(order_id,cohort,policy_version,access_mode,evidence_kind,"
                "evidence_reference,migration_run_id,classified_by,notes_hash) VALUES "
                "(:order,'legacy_pre_bridge','legacy_pre_bridge_v1','authenticated',"
                "'positive_release_or_bridge_evidence','changed-evidence',:run,"
                "'milestone_2_backfill',:hash)"
            ),
            {"order": order_id, "run": run_id, "hash": "a" * 64},
        )

    with pytest.raises(ClassificationConflict, match="changed workflow classification"):
        classify_workflow_batch(engine, run_id, batch_size=1)
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT workflow_cohort,workflow_policy_version,checkout_access_mode "
                "FROM orders WHERE id=:id"
            ),
            {"id": order_id},
        ).one() == (None, None, None)
        assert connection.scalar(text("SELECT count(*) FROM order_current_owners")) == 0
    engine.dispose()


def test_postgresql_classifier_reconciliation_refuses_incomplete_cutover(
    disposable_m2_database,
) -> None:
    from app.services.orders.workflow_classification import (
        ClassificationIncomplete,
        ClassificationRunIdentity,
        classify_workflow_batch,
        finalize_workflow_classification,
        start_workflow_classification_run,
    )

    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[1])
    engine = create_engine(sync_url)
    customer_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                "VALUES (:id,:email,'Reconcile classifier','CUSTOMER',false)"
            ),
            {
                "id": customer_id,
                "email": f"reconcile-classifier-{uuid.uuid4().hex}@example.test",
            },
        )
        for _index in range(2):
            connection.execute(
                text(
                    "INSERT INTO orders "
                    "(id,order_number,customer_id,subtotal,shipping_cost,tax_amount,"
                    "discount_amount,total_amount,currency,payment_status,fulfillment_status) "
                    "VALUES (:id,:number,:customer,10,0,0,0,10,'NGN','PENDING',"
                    "'order_received')"
                ),
                {
                    "id": uuid.uuid4(),
                    "number": f"M2-RECONCILE-{uuid.uuid4().hex[:8]}",
                    "customer": customer_id,
                },
            )

    run_id = start_workflow_classification_run(
        engine,
        ClassificationRunIdentity("reconcile-release", REVISIONS[1], "pytest"),
    )
    assert classify_workflow_batch(engine, run_id, batch_size=1) == 1
    # Finalization and the contract migration must both fail closed mid-run.
    with pytest.raises(ClassificationIncomplete, match="reconciliation incomplete"):
        finalize_workflow_classification(engine, run_id)
    failed = _run_alembic(app_url, "upgrade", REVISIONS[-1], expect_success=False)
    assert failed.returncode != 0
    assert "classification reconciliation incomplete" in failed.stdout + failed.stderr

    assert classify_workflow_batch(engine, run_id, batch_size=1) == 1
    assert finalize_workflow_classification(engine, run_id) == 2
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    refused = _run_alembic(app_url, "downgrade", "f9d1b3e5a7c9", expect_success=False)
    assert refused.returncode != 0
    assert (
        "refusing destructive Milestone 2 downgrade" in refused.stdout + refused.stderr
    )
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == REVISIONS[-1]
        )
        assert connection.scalar(text("SELECT count(*) FROM orders")) == 2
        assert (
            connection.scalar(
                text("SELECT count(*) FROM order_workflow_classifications")
            )
            == 2
        )
    engine.dispose()


def test_postgresql_active_writer_has_single_owner_projection_authority(
    disposable_m2_database,
) -> None:
    from app.models.order import Order

    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    customer_id = uuid.uuid4()
    order_id = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                "VALUES (:id,:email,'Single authority customer','CUSTOMER',false)"
            ),
            {
                "id": customer_id,
                "email": f"single-authority-{uuid.uuid4().hex}@example.test",
            },
        )
        connection.execute(
            text(
                "INSERT INTO order_workflow_migration_runs "
                "(id,compatibility_writer_release_id,compatibility_writer_started_at,"
                "migration_revision,deployment_identity) VALUES "
                "(:id,'single-authority-test',statement_timestamp(),"
                "'a2b3c4d5e6f7','pytest')"
            ),
            {"id": uuid.uuid4()},
        )

    with Session(engine) as session:
        order = Order(
            id=order_id,
            order_number=f"M2-SINGLE-{uuid.uuid4().hex[:8]}",
            customer_id=customer_id,
            currency="NGN",
            subtotal=Decimal("10.00"),
            shipping_cost=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            total_amount=Decimal("10.00"),
        )
        session.add(order)
        session.flush()
        session.flush()
        assert (
            session.scalar(
                text(
                    "SELECT count(*) FROM order_current_owners "
                    "WHERE order_id=:order_id"
                ),
                {"order_id": order_id},
            )
            == 1
        )
        assert session.execute(
            text(
                "SELECT workflow_cohort,workflow_policy_version,checkout_access_mode "
                "FROM orders WHERE id=:order_id"
            ),
            {"order_id": order_id},
        ).one() == (
            "legacy_pre_bridge",
            "legacy_pre_bridge_v1",
            "authenticated",
        )
        session.rollback()

    with engine.connect() as connection:
        assert (
            connection.scalar(
                text("SELECT count(*) FROM orders WHERE id=:order_id"),
                {"order_id": order_id},
            )
            == 0
        )
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM order_current_owners "
                    "WHERE order_id=:order_id"
                ),
                {"order_id": order_id},
            )
            == 0
        )
    engine.dispose()


def _insert_f4_capability(
    connection,
    ids,
    *,
    scope="claim_order",
    created_at=None,
    expires_at=None,
    digest=None,
):
    capability = uuid.uuid4()
    connection.execute(
        text(
            "INSERT INTO order_guest_capabilities "
            "(id,order_id,original_customer_id,scope,token_digest,pepper_key_version,"
            "created_at,expires_at) "
            "VALUES (:capability,:order,:customer,:scope,decode(:digest,'hex'),1,"
            "COALESCE(:created_at,statement_timestamp()),"
            "COALESCE(:expires_at,statement_timestamp()+interval '1 day'))"
        ),
        {
            **ids,
            "capability": capability,
            "scope": scope,
            "digest": digest or uuid.uuid4().hex * 2,
            "created_at": created_at,
            "expires_at": expires_at,
        },
    )
    return capability


def _claim_f4(
    connection, ids, capability, user, key, claimed_at="statement_timestamp()"
):
    connection.execute(
        text(
            "UPDATE order_current_owners SET current_authenticated_user_id=:user,"
            "claim_capability_id=:capability,claim_idempotency_key=:key,"
            f"claimed_at={claimed_at},row_version=row_version+1 WHERE order_id=:order"
        ),
        {**ids, "capability": capability, "user": user, "key": key},
    )


def _install_f4_owner(connection):
    ids = _install_domestic_tuple(connection)
    connection.execute(
        text(
            "INSERT INTO order_current_owners (order_id,original_customer_id) "
            "VALUES (:order,:customer)"
        ),
        ids,
    )
    return ids


def test_finding4_postgresql_capability_and_claim_matrix(
    disposable_m2_database,
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_f4_owner(connection)
        other = _install_f4_owner(connection)
        users = {"claimant": uuid.uuid4(), "conflict": uuid.uuid4()}
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) VALUES "
                "(:claimant,:one,'Claimant','CUSTOMER',false),"
                "(:conflict,:two,'Conflict','CUSTOMER',false)"
            ),
            {
                **users,
                "one": f"f4-one-{uuid.uuid4().hex}@example.test",
                "two": f"f4-two-{uuid.uuid4().hex}@example.test",
            },
        )
        capability = _insert_f4_capability(connection, ids)
        for assignment, value in (
            ("id=:value", uuid.uuid4()),
            ("order_id=:value", other["order"]),
            ("original_customer_id=:value", other["customer"]),
            ("scope=:value", "read_order"),
            ("token_digest=decode(:value,'hex')", "f" * 64),
            ("pepper_key_version=:value", 2),
            ("expires_at=:value", "2099-01-01T00:00:00+00:00"),
            ("created_at=:value", "2020-01-01T00:00:00+00:00"),
        ):
            _assert_rejected(
                connection,
                f"UPDATE order_guest_capabilities SET {assignment} WHERE id=:capability",
                {"capability": capability, "value": value},
            )

        _assert_deferred_rejected(
            connection,
            "UPDATE order_current_owners SET current_authenticated_user_id=:user,"
            "claim_capability_id=:capability,claim_idempotency_key='cross-order',"
            "claimed_at=statement_timestamp(),row_version=row_version+1 WHERE order_id=:order",
            {
                "order": other["order"],
                "capability": capability,
                "user": users["claimant"],
            },
        )
        wrong_scope = _insert_f4_capability(connection, ids, scope="read_order")
        expired = _insert_f4_capability(
            connection,
            ids,
            created_at="2020-01-01T00:00:00+00:00",
            expires_at="2020-01-02T00:00:00+00:00",
        )
        revoked = _insert_f4_capability(connection, ids)
        connection.execute(
            text(
                "UPDATE order_guest_capabilities SET revoked_at=statement_timestamp(),"
                "row_version=row_version+1 WHERE id=:capability"
            ),
            {"capability": revoked},
        )
        replaced = _insert_f4_capability(connection, ids)
        replacement = _insert_f4_capability(connection, ids)
        connection.execute(
            text(
                "UPDATE order_guest_capabilities SET replaced_by_id=:replacement,"
                "revoked_at=statement_timestamp(),row_version=row_version+1 WHERE id=:capability"
            ),
            {"capability": replaced, "replacement": replacement},
        )
        for candidate in (wrong_scope, expired, revoked, replaced):
            _assert_rejected(
                connection,
                "UPDATE order_current_owners SET current_authenticated_user_id=:user,"
                "claim_capability_id=:capability,claim_idempotency_key=:key,"
                "claimed_at=statement_timestamp(),row_version=row_version+1 WHERE order_id=:order",
                {
                    **ids,
                    "user": users["claimant"],
                    "capability": candidate,
                    "key": f"invalid-{candidate}",
                },
            )

        for assignment in (
            "last_used_at=statement_timestamp()+interval '1 second'",
            "last_used_at=created_at-interval '1 second'",
            "revoked_at=statement_timestamp()+interval '1 second'",
            "revoked_at=created_at-interval '1 second'",
            "replaced_by_id=:replacement,revoked_at=statement_timestamp()+interval '1 second'",
            "replaced_by_id=:replacement,revoked_at=created_at-interval '1 second'",
        ):
            _assert_rejected(
                connection,
                f"UPDATE order_guest_capabilities SET {assignment},row_version=row_version+1 "
                "WHERE id=:capability",
                {"capability": capability, "replacement": replacement},
            )
        for claim_time in (
            "statement_timestamp()+interval '1 second'",
            "(SELECT created_at-interval '1 second' FROM order_guest_capabilities "
            "WHERE id=:capability)",
        ):
            _assert_rejected(
                connection,
                "UPDATE order_current_owners SET current_authenticated_user_id=:user,"
                "claim_capability_id=:capability,claim_idempotency_key='bad-time',"
                f"claimed_at={claim_time},row_version=row_version+1 WHERE order_id=:order",
                {**ids, "user": users["claimant"], "capability": capability},
            )

        usable = _insert_f4_capability(connection, other, scope="read_order")
        connection.execute(
            text(
                "UPDATE order_guest_capabilities SET last_used_at=statement_timestamp(),"
                "row_version=row_version+1 WHERE id=:capability"
            ),
            {"capability": usable},
        )
        successor = _insert_f4_capability(connection, other, scope="read_order")
        connection.execute(
            text(
                "UPDATE order_guest_capabilities SET replaced_by_id=:successor,"
                "revoked_at=statement_timestamp(),row_version=row_version+1 WHERE id=:capability"
            ),
            {"capability": usable, "successor": successor},
        )
        sibling = _insert_f4_capability(connection, ids, scope="read_order")
        _claim_f4(connection, ids, capability, users["claimant"], "claim-once")
        owner = connection.execute(
            text(
                "SELECT current_authenticated_user_id,claim_capability_id,claim_idempotency_key,"
                "claimed_at,row_version FROM order_current_owners WHERE order_id=:order"
            ),
            ids,
        ).one()
        assert owner[:3] == (users["claimant"], capability, "claim-once")
        assert owner.row_version == 2
        rows = connection.execute(
            text(
                "SELECT id,revoked_at,claimed_by_user_id,claimed_at "
                "FROM order_guest_capabilities WHERE order_id=:order"
            ),
            ids,
        ).all()
        assert rows and all(row.revoked_at is not None for row in rows)
        claimed = next(row for row in rows if row.id == capability)
        assert (claimed.claimed_by_user_id, claimed.claimed_at) == (
            users["claimant"],
            owner.claimed_at,
        )
        assert any(row.id == sibling for row in rows)
        connection.execute(
            text(
                "UPDATE order_current_owners SET current_authenticated_user_id=:user,"
                "claim_capability_id=:capability,claim_idempotency_key=:key,"
                "claimed_at=:claimed_at,row_version=row_version WHERE order_id=:order"
            ),
            {
                **ids,
                "user": users["claimant"],
                "capability": capability,
                "key": "claim-once",
                "claimed_at": owner.claimed_at,
            },
        )
        _assert_rejected(
            connection,
            "UPDATE order_current_owners SET current_authenticated_user_id=:user "
            "WHERE order_id=:order",
            {**ids, "user": users["conflict"]},
        )
        for assignment, parameters in (
            ("claim_capability_id=:value", {"value": sibling}),
            ("claim_idempotency_key=:value", {"value": "different-key"}),
            (
                "claimed_at=:value",
                {"value": owner.claimed_at + timedelta(microseconds=1)},
            ),
        ):
            _assert_rejected(
                connection,
                f"UPDATE order_current_owners SET {assignment} WHERE order_id=:order",
                {**ids, **parameters},
            )
    engine.dispose()


@pytest.mark.parametrize("competing_transition", ["revocation", "replacement"])
def test_finding4_postgresql_claim_and_capability_race_serializes(
    disposable_m2_database, competing_transition
) -> None:
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        ids = _install_f4_owner(connection)
        capability = _insert_f4_capability(connection, ids)
        sibling = _insert_f4_capability(connection, ids, scope="read_order")
        successor = _insert_f4_capability(connection, ids, scope="read_order")
        claimant = uuid.uuid4()
        connection.execute(
            text(
                "INSERT INTO users (id,email,full_name,role,is_guest_created) "
                "VALUES (:id,:email,'Race claimant','CUSTOMER',false)"
            ),
            {"id": claimant, "email": f"f4-race-{uuid.uuid4().hex}@example.test"},
        )

    blocker = engine.connect()
    transaction = blocker.begin()
    blocker.execute(
        text("SELECT 1 FROM order_current_owners WHERE order_id=:order FOR UPDATE"), ids
    )
    started = Event()
    application_name = f"finding4-{competing_transition}-{uuid.uuid4().hex}"

    def revoke():
        with engine.connect() as worker:
            worker.execute(
                text("SET application_name=:name"), {"name": application_name}
            )
            nested = worker.begin_nested()
            started.set()
            try:
                if competing_transition == "revocation":
                    statement = (
                        "UPDATE order_guest_capabilities SET "
                        "revoked_at=statement_timestamp(),row_version=row_version+1 "
                        "WHERE id=:capability"
                    )
                else:
                    statement = (
                        "UPDATE order_guest_capabilities SET replaced_by_id=:successor,"
                        "revoked_at=statement_timestamp(),row_version=row_version+1 "
                        "WHERE id=:capability"
                    )
                worker.execute(
                    text(statement),
                    {"capability": sibling, "successor": successor},
                )
                nested.commit()
                return "revoked"
            except DBAPIError:
                nested.rollback()
                return "rejected"

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(revoke)
            assert started.wait(timeout=2)
            _wait_until_postgres_worker_is_lock_blocked(engine, application_name)
            _claim_f4(blocker, ids, capability, claimant, "race-claim")
            transaction.commit()
            assert future.result(timeout=5) == "rejected"
    finally:
        if transaction.is_active:
            transaction.rollback()
        blocker.close()
    with engine.connect() as connection:
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM order_guest_capabilities "
                    "WHERE order_id=:order AND revoked_at IS NULL"
                ),
                ids,
            )
            == 0
        )
    engine.dispose()


def _normalized_f4_catalog(connection):
    tables = ["order_guest_capabilities", "order_current_owners"]
    prefixes = (
        "ck_order_guest_capabilities_",
        "fk_order_guest_capabilities_",
        "uq_order_guest_capabilities_",
        "ix_order_guest_capabilities_",
        "ck_order_current_owners_",
        "fk_order_current_owners_",
        "uq_order_current_owners_",
    )
    constraints = {
        row.name: re.sub(r"\s+", " ", row.definition).strip()
        for row in connection.execute(
            text(
                "SELECT con.conname name,pg_get_constraintdef(con.oid,true) definition "
                "FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid "
                "WHERE c.relname=ANY(:tables)"
            ),
            {"tables": tables},
        )
        if row.name.startswith(prefixes)
    }
    indexes = {
        row.name: re.sub(r"\s+", " ", row.definition).strip()
        for row in connection.execute(
            text(
                "SELECT c.relname name,pg_get_indexdef(c.oid,0,true) definition "
                "FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid "
                "JOIN pg_class t ON t.oid=i.indrelid WHERE t.relname=ANY(:tables)"
            ),
            {"tables": tables},
        )
        if row.name.startswith(prefixes)
    }
    functions = dict(
        connection.execute(
            text(
                "SELECT proname,regexp_replace(pg_get_functiondef(oid),'\\s+',' ','g') "
                "FROM pg_proc WHERE proname=ANY(:names)"
            ),
            {
                "names": [
                    "validate_order_guest_capability_write",
                    "validate_order_current_owner_claim",
                ]
            },
        ).all()
    )
    triggers = {
        row.name: re.sub(r"\s+", " ", row.definition).strip()
        for row in connection.execute(
            text(
                "SELECT tgname name,pg_get_triggerdef(oid,true) definition FROM pg_trigger "
                "WHERE NOT tgisinternal AND tgname=ANY(:names)"
            ),
            {
                "names": [
                    "trg_order_guest_capabilities_truth",
                    "trg_order_current_owners_claim",
                ]
            },
        )
    }
    return constraints, indexes, functions, triggers


def test_finding4_postgresql_catalog_parity_and_plaintext_absence(
    disposable_m2_database,
) -> None:
    from app.core.base import Base

    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[-1])
    migrated = create_engine(sync_url)
    database = f"shopsoma_m2_f4_model_{uuid.uuid4().hex[:12]}"
    admin = create_engine(
        sync_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin.begin() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    model_engine = create_engine(sync_url.set(database=database))
    try:
        Base.metadata.create_all(model_engine)
        with migrated.connect() as left, model_engine.connect() as right:
            catalog = _normalized_f4_catalog(left)
            assert set(catalog[2]) == {
                "validate_order_guest_capability_write",
                "validate_order_current_owner_claim",
            }
            assert set(catalog[3]) == {
                "trg_order_guest_capabilities_truth",
                "trg_order_current_owners_claim",
            }
            assert "fk_order_current_owners_claim_capability_order" in catalog[0]
            assert "uq_order_guest_capabilities_id_order" in catalog[0]
            assert catalog == _normalized_f4_catalog(right)
            columns = set(
                left.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='order_guest_capabilities'"
                    )
                ).scalars()
            )
            assert not (
                {"token", "plaintext_token", "secret", "bearer_token"} & columns
            )
            definitions = " ".join(_normalized_f4_catalog(left)[2].values()).lower()
            assert "raise log" not in definitions and "raise notice" not in definitions
    finally:
        model_engine.dispose()
        with admin.begin() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=:name"
                ),
                {"name": database},
            )
            connection.execute(text(f'DROP DATABASE "{database}"'))
        admin.dispose()
        migrated.dispose()
