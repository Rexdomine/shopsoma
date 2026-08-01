"""Migration contract for Phase 2A-4B reservation/payment persistence."""

import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import uuid

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "f9d1b3e5a7c9_add_stock_payment_persistence.py"
)


def _source() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_lane_2a_4b_migration_exists_on_the_single_current_head() -> None:
    source = _source()
    tree = ast.parse(source)
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id in {"revision", "down_revision"}
    }
    assert assignments == {
        "revision": "f9d1b3e5a7c9",
        "down_revision": "e8c0a2d4f6b8",
    }


def test_lane_2a_4b_migration_builds_and_reverses_complete_schema() -> None:
    source = _source()
    for table in (
        "stock_reservations",
        "payment_attempts",
        "payment_attempt_reservations",
        "payment_attempt_evidence",
    ):
        assert f'"{table}"' in source
        assert f'op.drop_table("{table}")' in source
    for invariant in (
        "validate_stock_reservation_write",
        "protect_reserved_inventory",
        "protect_reserved_order_item",
        "validate_payment_attempt_write",
        "validate_payment_attempt_membership_write",
        "validate_payment_attempt_exact_reservations",
        "validate_payment_attempt_evidence_write",
        "uq_payment_attempts_active_subject",
        "fk_payment_attempts_terminal_evidence",
    ):
        assert invariant in source
    assert "from app." not in source


def test_lane_2a_4b_migration_names_match_orm_constraints_and_indexes() -> None:
    from app.models.stock_payment_persistence import (
        PaymentAttempt,
        PaymentAttemptEvidence,
        PaymentAttemptReservation,
        StockReservation,
    )

    source = _source()
    for model in (
        StockReservation,
        PaymentAttempt,
        PaymentAttemptReservation,
        PaymentAttemptEvidence,
    ):
        for constraint in model.__table__.constraints:
            if constraint.name:
                assert constraint.name in source
        for index in model.__table__.indexes:
            assert index.name in source


def test_lane_2a_4b_model_trigger_ddl_exactly_matches_frozen_migration() -> None:
    """Metadata/create_all and Alembic must install the same PostgreSQL program."""
    from sqlalchemy import DDL
    from sqlalchemy.dialects.postgresql.asyncpg import dialect

    from app.models.stock_payment_persistence import STOCK_PAYMENT_TRIGGER_DDLS

    helper_path = Path(__file__).parents[1] / "alembic" / "stock_payment_ddl_f9.py"
    spec = importlib.util.spec_from_file_location(
        "stock_payment_ddl_f9_parity", helper_path
    )
    assert spec is not None and spec.loader is not None
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    compiled_model_ddls = tuple(
        str(DDL(statement).compile(dialect=dialect()))
        for statement in STOCK_PAYMENT_TRIGGER_DDLS
    )
    assert compiled_model_ddls == helper.TRIGGER_DDLS
    assert "payment_attempts%ROWTYPE" in "\n".join(compiled_model_ddls)
    assert "%%ROWTYPE" not in "\n".join(compiled_model_ddls)


def test_lane_2a_4b_real_upgrade_downgrade_upgrade_cycle() -> None:
    root = Path(__file__).parents[1]
    base_url = make_url(os.environ["DATABASE_URL"])
    sync_driver = base_url.drivername.split("+", 1)[0]
    admin_url = base_url.set(drivername=sync_driver, database="postgres")
    database = f"shopsoma_stock_payment_cycle_{uuid.uuid4().hex[:10]}"
    database_url = base_url.set(
        drivername=sync_driver, database=database
    ).render_as_string(hide_password=False)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{database}"'))
    try:
        env = os.environ.copy()
        env.update(DATABASE_URL=database_url, SECRET_KEY="stock-payment-migration-test")

        def migrate(command: str, revision: str) -> None:
            result = subprocess.run(
                [sys.executable, "-m", "alembic", command, revision],
                cwd=root,
                env=env,
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr

        def assert_schema(present: bool, revision: str) -> None:
            target = create_engine(database_url)
            try:
                with target.connect() as connection:
                    database_inspector = inspect(connection)
                    tables = set(database_inspector.get_table_names())
                    assert all(
                        (name in tables) is present
                        for name in (
                            "stock_reservations",
                            "payment_attempts",
                            "payment_attempt_reservations",
                            "payment_attempt_evidence",
                            "legacy_inventory_deduction_candidates",
                        )
                    )
                    functions = set(
                        connection.execute(
                            text(
                                "SELECT proname FROM pg_proc WHERE proname IN "
                                "('validate_stock_reservation_write',"
                                "'protect_reserved_inventory','protect_reserved_order_item',"
                                "'protect_reserved_order','validate_payment_attempt_write',"
                                "'validate_payment_attempt_membership_write',"
                                "'validate_payment_attempt_exact_reservations',"
                                "'validate_payment_attempt_evidence_write',"
                                "'validate_legacy_inventory_candidate_write',"
                                "'reconcile_legacy_inventory_deduction')"
                            )
                        ).scalars()
                    )
                    assert bool(functions) is present
                    assert (
                        connection.scalar(
                            text("SELECT version_num FROM alembic_version")
                        )
                        == revision
                    )
            finally:
                target.dispose()

        def selection_validator_definition() -> str:
            target = create_engine(database_url)
            try:
                with target.connect() as connection:
                    definition = connection.scalar(
                        text(
                            "SELECT pg_get_functiondef("
                            "'validate_customer_shipping_quote_selection_write()'::regprocedure)"
                        )
                    )
                    assert definition is not None
                    trigger_function = connection.scalar(
                        text(
                            "SELECT p.proname FROM pg_trigger t "
                            "JOIN pg_proc p ON p.oid=t.tgfoid "
                            "WHERE t.tgrelid='customer_shipping_quote_selections'::regclass "
                            "AND t.tgname='customer_shipping_quote_selections_validate' "
                            "AND NOT t.tgisinternal"
                        )
                    )
                    assert (
                        trigger_function
                        == "validate_customer_shipping_quote_selection_write"
                    )
                    return definition
            finally:
                target.dispose()

        migrate("upgrade", "e8c0a2d4f6b8")
        assert_schema(False, "e8c0a2d4f6b8")
        pre_f9_selection_validator = selection_validator_definition()
        assert "payment_attempts" not in pre_f9_selection_validator
        vendor_user_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        vendor_id = uuid.uuid4()
        product_id = uuid.uuid4()
        made_to_order_product_id = uuid.uuid4()
        current_made_to_order_product_id = uuid.uuid4()
        order_id = uuid.uuid4()
        order_item_id = uuid.uuid4()
        made_to_order_item_id = uuid.uuid4()
        current_made_to_order_item_id = uuid.uuid4()
        target = create_engine(database_url)
        try:
            with target.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (id,email,full_name,role,is_guest_created) VALUES "
                        "(:vendor_user_id,:vendor_email,'Migration Vendor','VENDOR',false),"
                        "(:customer_id,:customer_email,'Migration Customer','CUSTOMER',false)"
                    ),
                    {
                        "vendor_user_id": vendor_user_id,
                        "vendor_email": f"vendor-{uuid.uuid4().hex}@example.test",
                        "customer_id": customer_id,
                        "customer_email": f"customer-{uuid.uuid4().hex}@example.test",
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO vendors "
                        "(id,user_id,business_name,kyc_status,commission_rate,approved,"
                        "store_active,is_onboarding,brand_info_completed,payout_info_completed,"
                        "total_products,total_orders,total_revenue) VALUES "
                        "(:vendor_id,:user_id,'Migration Vendor','PENDING',12.5,false,true,true,"
                        "false,false,0,0,0)"
                    ),
                    {"vendor_id": vendor_id, "user_id": vendor_user_id},
                )
                connection.execute(
                    text(
                        "INSERT INTO products "
                        "(id,vendor_id,title,base_price,currency,total_stock,status,is_featured,"
                        "product_type,made_to_order,views_count,orders_count,moderation_status) "
                        "VALUES (:product_id,:vendor_id,'Migration Product',10,'NGN',0,'DRAFT',"
                        "false,'SINGLE',false,0,0,'PENDING'),"
                        "(:made_to_order_product_id,:vendor_id,'Migration MTO Product',10,'NGN',"
                        "0,'DRAFT',false,'SINGLE',true,0,0,'PENDING'),"
                        "(:current_made_to_order_product_id,:vendor_id,'Migration Current MTO',10,"
                        "'NGN',0,'DRAFT',false,'SINGLE',true,0,0,'PENDING')"
                    ),
                    {
                        "product_id": product_id,
                        "made_to_order_product_id": made_to_order_product_id,
                        "current_made_to_order_product_id": current_made_to_order_product_id,
                        "vendor_id": vendor_id,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO orders "
                        "(id,order_number,customer_id,subtotal,shipping_cost,tax_amount,"
                        "discount_amount,total_amount,payment_status,fulfillment_status) "
                        "VALUES (:order_id,:order_number,:customer_id,20,0,0,0,20,'PENDING',"
                        "'order_received')"
                    ),
                    {
                        "order_id": order_id,
                        "order_number": f"MIG-{uuid.uuid4().hex[:12]}",
                        "customer_id": customer_id,
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO order_items "
                        "(id,order_id,product_id,vendor_id,product_title,quantity,unit_price,"
                        "subtotal,commission_rate,commission_amount,vendor_payout,"
                        "fulfillment_status) VALUES "
                        "(:item_id,:order_id,:product_id,:vendor_id,'Migration Product',2,10,"
                        "20,10,2,18,'order_received'),"
                        "(:made_to_order_item_id,:order_id,:made_to_order_product_id,:vendor_id,"
                        "'Migration MTO Product',1,10,10,10,1,9,'order_received'),"
                        "(:current_made_to_order_item_id,:order_id,"
                        ":current_made_to_order_product_id,:vendor_id,'Migration Current MTO',1,"
                        "10,10,10,1,9,'order_received')"
                    ),
                    {
                        "item_id": order_item_id,
                        "made_to_order_item_id": made_to_order_item_id,
                        "current_made_to_order_item_id": current_made_to_order_item_id,
                        "order_id": order_id,
                        "product_id": product_id,
                        "made_to_order_product_id": made_to_order_product_id,
                        "current_made_to_order_product_id": current_made_to_order_product_id,
                        "vendor_id": vendor_id,
                    },
                )
                # This order item was created while made-to-order, so legacy
                # checkout did not deduct finite stock. The current mutable flag
                # cannot preserve that fact and must not manufacture provenance.
                connection.execute(
                    text(
                        "UPDATE products SET made_to_order=false "
                        "WHERE id=:made_to_order_product_id"
                    ),
                    {"made_to_order_product_id": made_to_order_product_id},
                )
        finally:
            target.dispose()
        migrate("upgrade", "f9d1b3e5a7c9")
        assert_schema(True, "f9d1b3e5a7c9")
        f9_selection_validator = selection_validator_definition()
        assert "payment_attempts" in f9_selection_validator
        target = create_engine(database_url)
        try:
            with target.begin() as connection:
                candidates = dict(
                    connection.execute(
                        text(
                            "SELECT order_item_id, state "
                            "FROM legacy_inventory_deduction_candidates "
                            "WHERE order_item_id IN (:deducted_id,:not_deducted_id,:mto_deducted_id)"
                        ),
                        {
                            "deducted_id": order_item_id,
                            "not_deducted_id": made_to_order_item_id,
                            "mto_deducted_id": current_made_to_order_item_id,
                        },
                    ).all()
                )
                assert candidates == {
                    order_item_id: "unresolved",
                    made_to_order_item_id: "unresolved",
                    current_made_to_order_item_id: "unresolved",
                }
                assert (
                    connection.scalar(
                        text("SELECT count(*) FROM inventory_deduction_events")
                    )
                    == 0
                )

                decisions = (
                    (order_item_id, True, "legacy-deducted"),
                    (made_to_order_item_id, False, "legacy-not-deducted"),
                    (current_made_to_order_item_id, True, "legacy-mto-deducted"),
                )
                for item_id, was_deducted, event_id in decisions:
                    result = connection.scalar(
                        text(
                            "SELECT reconcile_legacy_inventory_deduction("
                            ":item_id,:was_deducted,:source,:event_id,:evidence_hash,:actor_id)"
                        ),
                        {
                            "item_id": item_id,
                            "was_deducted": was_deducted,
                            "source": "legacy_inventory_audit",
                            "event_id": event_id,
                            "evidence_hash": ("a" if was_deducted else "b") * 64,
                            "actor_id": vendor_user_id,
                        },
                    )
                    assert result == ("credited" if was_deducted else "not_deducted")

                resolved = dict(
                    connection.execute(
                        text(
                            "SELECT order_item_id, state "
                            "FROM legacy_inventory_deduction_candidates "
                            "WHERE order_item_id IN (:deducted_id,:not_deducted_id,:mto_deducted_id)"
                        ),
                        {
                            "deducted_id": order_item_id,
                            "not_deducted_id": made_to_order_item_id,
                            "mto_deducted_id": current_made_to_order_item_id,
                        },
                    ).all()
                )
                assert resolved == {
                    order_item_id: "credited",
                    made_to_order_item_id: "not_deducted",
                    current_made_to_order_item_id: "credited",
                }
                credited_items = set(
                    connection.execute(
                        text(
                            "SELECT order_item_id FROM inventory_deduction_events "
                            "WHERE event_type='deducted'"
                        )
                    ).scalars()
                )
                assert credited_items == {order_item_id, current_made_to_order_item_id}
        finally:
            target.dispose()
        migrate("downgrade", "e8c0a2d4f6b8")
        assert_schema(False, "e8c0a2d4f6b8")
        assert selection_validator_definition() == pre_f9_selection_validator
        migrate("upgrade", "f9d1b3e5a7c9")
        assert_schema(True, "f9d1b3e5a7c9")
        assert selection_validator_definition() == f9_selection_validator
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
