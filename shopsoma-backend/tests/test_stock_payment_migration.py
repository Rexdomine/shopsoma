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
                                "'validate_payment_attempt_evidence_write')"
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

        migrate("upgrade", "e8c0a2d4f6b8")
        assert_schema(False, "e8c0a2d4f6b8")
        migrate("upgrade", "f9d1b3e5a7c9")
        assert_schema(True, "f9d1b3e5a7c9")
        migrate("downgrade", "e8c0a2d4f6b8")
        assert_schema(False, "e8c0a2d4f6b8")
        migrate("upgrade", "f9d1b3e5a7c9")
        assert_schema(True, "f9d1b3e5a7c9")
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
