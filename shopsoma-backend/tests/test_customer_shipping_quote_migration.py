"""Real PostgreSQL lifecycle proof for Phase 2A-4A quote persistence."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import uuid

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url


REVISION = "e8c0a2d4f6b8"
HEAD = "f9d1b3e5a7c9"
PARENT = "d7b9f1c3e5a8"
MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / f"{REVISION}_add_customer_shipping_quote_persistence.py"
)
TABLES = (
    "customer_shipping_quotes",
    "customer_shipping_quote_options",
    "customer_shipping_quote_selections",
)
PHASE_2B_TABLES = (
    "outbound_intent_rate_guards",
    "domestic_rate_attempts",
    "domestic_rate_responses",
    "domestic_rate_offers",
)


def _migration_helpers():
    path = Path(__file__).with_name("test_domestic_rate_migration.py")
    spec = importlib.util.spec_from_file_location("quote_migration_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_customer_quote_revision_is_single_linear_head_and_owns_explicit_ddl() -> None:
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [HEAD]
    assert script.get_revision(HEAD).down_revision == REVISION
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
