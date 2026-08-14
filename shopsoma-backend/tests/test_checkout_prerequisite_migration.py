"""Milestone 2 sequential migration and downgrade-safety contracts."""

import ast
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


ROOT = Path(__file__).parents[1]
REVISIONS = (
    "a0b1c2d3e4f5",
    "a1b2c3d4e5f6",
    "a2b3c4d5e6f7",
)


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
    assert script.get_current_head() == REVISIONS[-1]


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


def test_migrations_are_self_contained_and_do_not_import_application_code() -> None:
    script = _script()
    for revision in REVISIONS:
        source = Path(script.get_revision(revision).path).read_text()
        ast.parse(source)
        assert "from app." not in source
        assert "import app." not in source


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
    expected_triggers = set(
        re.findall(r"CREATE (?:CONSTRAINT )?TRIGGER\s+([a-z_]+)", upgrade_source)
    )
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
    assert (
        head_triggers[("stock_reservations", "trg_stock_reservations_validate_legacy")][
            0
        ]
        == "validate_stock_reservation_write"
    )
    assert (
        head_triggers[("stock_reservations", "trg_stock_reservations_validate_delete")][
            0
        ]
        == "validate_stock_reservation_write"
    )
    assert (
        head_triggers[("payment_attempts", "trg_payment_attempts_validate_legacy")][0]
        == "validate_payment_attempt_write"
    )
    assert (
        head_triggers[("payment_attempts", "trg_payment_attempts_validate_delete")][0]
        == "validate_payment_attempt_write"
    )
    assert (
        "INSERT OR UPDATE"
        in head_triggers[
            ("stock_reservations", "trg_stock_reservations_validate_legacy")
        ][1]
    )
    assert (
        "INSERT OR UPDATE"
        in head_triggers[("payment_attempts", "trg_payment_attempts_validate_legacy")][
            1
        ]
    )
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
    app_url, sync_url = disposable_m2_database
    _run_alembic(app_url, "upgrade", REVISIONS[1])
    engine = create_engine(sync_url)
    run_id = uuid.uuid4()
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
        connection.execute(
            text(
                "INSERT INTO order_workflow_migration_runs "
                "(id,compatibility_writer_release_id,compatibility_writer_started_at,"
                "migration_revision,deployment_identity) "
                "VALUES (:id,'test-writer',statement_timestamp(),"
                "'a1b2c3d4e5f6','test-deployment')"
            ),
            {"id": run_id},
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


def _install_domestic_tuple(connection):
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
            "statement_timestamp()+interval '30 minutes','static_domestic_rate',"
            "'create_estimate',:estimate_key,:hash,'v1','customer',:actor)"
        ),
        {
            **ids,
            "hash": "b" * 64,
            "estimate_key": f"e-{uuid.uuid4().hex}",
            "actor": str(ids["customer"]),
        },
    )
    connection.execute(
        text(
            "INSERT INTO checkout_shipping_estimate_options (id,estimate_id,option_key,"
            "service_code,service_label,amount,currency) VALUES "
            "(:option,:estimate,'standard','standard','Standard',1,'NGN')"
        ),
        ids,
    )
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
