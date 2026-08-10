"""Behavior regressions for the owned session-installed PostgreSQL fixture."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

import pytest
from sqlalchemy import String, create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from tests.fixture_database import (
    _MAX_SCAVENGE,
    DisposableDatabase,
    build_test_database_name,
    make_owner_marker,
    marker_is_stale,
    parse_marker,
    sign_owner_marker,
    serialize_marker,
)


_SUBPROCESS_TIMEOUT = 180


def _probe_environment() -> tuple[dict[str, str], str, str]:
    run_id = uuid.uuid4().hex[:24]
    owner_token = uuid.uuid4().hex + uuid.uuid4().hex
    environment = os.environ.copy()
    environment.pop("PYTEST_XDIST_WORKER", None)
    environment.pop("PYTEST_XDIST_WORKER_COUNT", None)
    environment.update(
        SHOPSOMA_PYTEST_DB_RUN_ID=run_id,
        SHOPSOMA_PYTEST_DB_OWNER_TOKEN=owner_token,
    )
    return environment, run_id, owner_token


def _owned_probe_databases(run_id: str, owner_token: str):
    from tests.conftest import RESOLVED_DB_URL

    lifecycle = DisposableDatabase(RESOLVED_DB_URL)
    engine = lifecycle._admin()
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT d.datname, shobj_description(d.oid, 'pg_database') "
                    "FROM pg_database d WHERE shobj_description(d.oid, 'pg_database') "
                    "LIKE :prefix ORDER BY d.datname"
                ),
                {"prefix": '{"app":"shopsoma-pytest-database-v3"%'},
            ).all()
    finally:
        engine.dispose()
    owned = []
    for name, raw_marker in rows:
        marker = parse_marker(raw_marker)
        if marker and marker["run"] == run_id and marker["owner_token"] == owner_token:
            owned.append((name, marker, raw_marker))
    return owned


def _drop_owned_probe_databases(run_id: str, owner_token: str) -> None:
    """Best-effort exact-marker cleanup for every database made by a probe."""
    from tests.conftest import RESOLVED_DB_URL

    for name, marker, marker_text in _owned_probe_databases(run_id, owner_token):
        lifecycle = DisposableDatabase(RESOLVED_DB_URL)
        lifecycle.name = name
        lifecycle.marker = marker
        lifecycle.marker_text = marker_text
        lifecycle.drop()


def _replace_database_marker(lifecycle: DisposableDatabase, marker: dict) -> None:
    """Install a test marker and keep exact-owner cleanup aligned with it."""
    lifecycle.marker = marker
    lifecycle.marker_text = serialize_marker(marker)
    admin = lifecycle._admin()
    try:
        with admin.connect() as connection:
            literal = String().literal_processor(connection.dialect)
            assert literal is not None
            connection.exec_driver_sql(
                f"COMMENT ON DATABASE {lifecycle._quote(connection, lifecycle.name)} "
                f"IS {literal(lifecycle.marker_text)}"
            )
    finally:
        admin.dispose()


@contextmanager
def _probe_file(source: str):
    path = Path(__file__).parent / f"_fixture_probe_{uuid.uuid4().hex}.py"
    path.write_text(source)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


def _run_probe(path: Path, environment: dict[str, str], *extra: str):
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--tb=short", *extra, str(path)],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=_SUBPROCESS_TIMEOUT,
        check=False,
    )


def test_database_names_hash_every_hostile_component_and_fit_postgres() -> None:
    hostile = 'db"; DROP DATABASE postgres; --' + "界" * 100
    names = {
        build_test_database_name(
            hostile,
            worker=f'gw{i}"/界',
            pid=10_000 + i,
            run_id=("🔥" * 100) + str(i),
        )
        for i in range(200)
    }
    assert len(names) == 200
    assert all(len(name.encode("utf-8")) <= 63 for name in names)
    assert all(name.isascii() and '"' not in name and ";" not in name for name in names)
    assert build_test_database_name("é", worker="gw0", pid=1, run_id="x") != (
        build_test_database_name("e\u0011", worker="gw0", pid=1, run_id="x")
    )


def test_database_names_bind_distinct_parent_clusters_and_fit_postgres() -> None:
    common = dict(worker="gw0", pid=1234, run_id="r" * 200)
    first = build_test_database_name(
        "database" * 100, parent_identity="cluster-a" * 100, **common
    )
    second = build_test_database_name(
        "database" * 100, parent_identity="cluster-b" * 100, **common
    )
    assert first != second
    assert len(first.encode("ascii")) <= 63
    assert len(second.encode("ascii")) <= 63


def test_owner_marker_rejects_malformed_weak_and_extra_fields() -> None:
    from tests.conftest import RESOLVED_DB_URL

    marker = make_owner_marker(RESOLVED_DB_URL, "probe")
    assert parse_marker(serialize_marker(marker)) == marker
    assert parse_marker("not-json") is None
    assert parse_marker(serialize_marker({**marker, "owner_token": "weak"})) is None
    assert parse_marker(serialize_marker({**marker, "secret": "***"})) is None


@pytest.mark.parametrize(
    ("field", "hostile"),
    (
        ("database", True),
        ("database", "bad/name"),
        ("database", "x" * 64),
        ("parent", True),
        ("parent", "g" * 32),
        ("run", True),
        ("run", "z" * 24),
        ("owner_token", True),
        ("owner_token", "z" * 64),
        ("process_start", True),
        ("process_start", None),
        ("process_start", "-1"),
        ("created_ns", True),
        ("created_ns", 0),
        ("created_ns", "1"),
        ("pid", True),
        ("pid", 0),
        ("pid", "1"),
        ("signature", "G" * 64),
    ),
)
def test_signed_hostile_marker_shapes_are_rejected_before_staleness(
    field, hostile
) -> None:
    from tests.conftest import RESOLVED_DB_URL

    marker = make_owner_marker(RESOLVED_DB_URL, "valid_database")
    hostile_marker = {**marker, field: hostile}
    if field != "signature":
        hostile_marker = sign_owner_marker(RESOLVED_DB_URL, hostile_marker)
    assert parse_marker(serialize_marker(hostile_marker)) is None


def test_structural_urls_normalize_sync_style_parameters_for_each_driver() -> None:
    from sqlalchemy.engine import make_url
    from tests.conftest import build_async_database_url, build_sync_database_url

    base = make_url(
        "postgresql://user:***@localhost/source?"
        "sslmode=require&application_name=fixture&target_session_attrs=read-write"
    )
    sync = build_sync_database_url(base, "target")
    async_url = build_async_database_url(base, "target")

    assert sync.drivername == "postgresql"
    assert sync.database == "target"
    assert dict(sync.query) == {
        "sslmode": "require",
        "application_name": "fixture",
        "target_session_attrs": "read-write",
    }
    assert async_url.drivername == "postgresql+asyncpg"
    assert async_url.database == "target"
    assert dict(async_url.query) == {
        "ssl": "require",
        "target_session_attrs": "read-write",
    }


def test_structural_urls_normalize_asyncpg_style_parameters_for_each_driver() -> None:
    from sqlalchemy.engine import make_url
    from tests.conftest import build_async_database_url, build_sync_database_url

    base = make_url(
        "postgresql+asyncpg://user:***@localhost/source?"
        "ssl=verify-full&command_timeout=30&statement_cache_size=0&"
        "target_session_attrs=read-write"
    )
    sync = build_sync_database_url(base, "target")
    async_url = build_async_database_url(base, "target")

    assert sync.drivername == "postgresql"
    assert sync.database == "target"
    assert dict(sync.query) == {
        "sslmode": "verify-full",
        "target_session_attrs": "read-write",
    }
    assert async_url.drivername == "postgresql+asyncpg"
    assert async_url.database == "target"
    assert dict(async_url.query) == {
        "ssl": "verify-full",
        "command_timeout": "30",
        "statement_cache_size": "0",
        "target_session_attrs": "read-write",
    }


def test_scavenger_requires_matching_owner_parent_age_and_dead_process(
    monkeypatch,
) -> None:
    from tests.conftest import RESOLVED_DB_URL

    marker = make_owner_marker(RESOLVED_DB_URL, "probe")
    now = marker["created_ns"] + 10_000_000_000
    monkeypatch.setattr("tests.fixture_database.process_start_token", lambda _pid: None)
    arguments = dict(
        marker=marker,
        base_url=RESOLVED_DB_URL,
        database_name="probe",
        parent=marker["parent"],
        now_ns=now,
        minimum_age_seconds=1,
    )
    assert marker_is_stale(**arguments)
    cross_run = sign_owner_marker(RESOLVED_DB_URL, {**marker, "owner_token": "x" * 64})
    assert marker_is_stale(**{**arguments, "marker": cross_run})
    assert not marker_is_stale(
        **{**arguments, "marker": {**marker, "owner_token": "tampered" * 8}}
    )
    assert not marker_is_stale(
        **{**arguments, "marker": {**marker, "signature": "0" * 64}}
    )
    assert not marker_is_stale(**{**arguments, "database_name": "foreign"})
    assert not marker_is_stale(**{**arguments, "parent": "foreign"})
    assert not marker_is_stale(**{**arguments, "minimum_age_seconds": 60})


def test_existing_live_owned_database_is_never_blindly_reused() -> None:
    from tests.conftest import RESOLVED_DB_URL, TEST_DATABASE_NAME

    duplicate = DisposableDatabase(RESOLVED_DB_URL)
    assert duplicate.name == TEST_DATABASE_NAME
    with pytest.raises(RuntimeError, match="refusing to reuse"):
        duplicate.create()


@pytest.mark.parametrize("outcome", ["pass", "fail"])
def test_subprocess_normal_and_failing_exit_drop_database(outcome: str) -> None:
    environment, run_id, owner_token = _probe_environment()
    assertion = (
        "assert True"
        if outcome == "pass"
        else "assert False, 'intentional probe failure'"
    )
    source = f"""
import pytest

@pytest.mark.asyncio
async def test_probe(db_session):
    {assertion}
"""
    try:
        with _probe_file(source) as path:
            result = _run_probe(path, environment)
        expected_code = 0 if outcome == "pass" else 1
        assert result.returncode == expected_code, (result.stdout + result.stderr)[
            -4000:
        ]
        if outcome == "fail":
            assert "intentional probe failure" in result.stdout
        assert _owned_probe_databases(run_id, owner_token) == []
    finally:
        _drop_owned_probe_databases(run_id, owner_token)


def test_sigkill_remnant_is_scavenged_only_after_owned_age_threshold(
    tmp_path, monkeypatch
) -> None:
    from tests.conftest import RESOLVED_DB_URL

    environment, run_id, owner_token = _probe_environment()
    ready = tmp_path / "sigkill-ready"
    source = f"""
import time

def test_probe():
    open({str(ready)!r}, "w").write("ready")
    while True:
        time.sleep(0.1)
"""
    process = None
    try:
        with _probe_file(source) as path:
            process = subprocess.Popen(
                [sys.executable, "-m", "pytest", "-q", str(path)],
                cwd=Path(__file__).parents[1],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            deadline = time.monotonic() + 60
            while (
                not ready.exists()
                and process.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            assert ready.exists(), "SIGKILL probe did not reach its test body"
            remnants = _owned_probe_databases(run_id, owner_token)
            assert len(remnants) == 1
            os.killpg(process.pid, signal.SIGKILL)
            assert process.wait(timeout=10) == -signal.SIGKILL

        monkeypatch.setenv("SHOPSOMA_PYTEST_DB_RUN_ID", uuid.uuid4().hex[:24])
        monkeypatch.setenv(
            "SHOPSOMA_PYTEST_DB_OWNER_TOKEN", uuid.uuid4().hex + uuid.uuid4().hex
        )
        monkeypatch.setenv("SHOPSOMA_PYTEST_DB_STALE_SECONDS", "3600")
        assert DisposableDatabase(RESOLVED_DB_URL).scavenge() == 0
        assert len(_owned_probe_databases(run_id, owner_token)) == 1
        monkeypatch.setenv("SHOPSOMA_PYTEST_DB_STALE_SECONDS", "0")
        assert DisposableDatabase(RESOLVED_DB_URL).scavenge() == 1
        assert _owned_probe_databases(run_id, owner_token) == []
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)
        _drop_owned_probe_databases(run_id, owner_token)


def test_stale_owned_collision_replaces_standalone_function(monkeypatch) -> None:
    from tests.conftest import RESOLVED_DB_URL

    run_id = uuid.uuid4().hex[:24]
    owner_token = uuid.uuid4().hex + uuid.uuid4().hex
    monkeypatch.setenv("SHOPSOMA_PYTEST_DB_RUN_ID", run_id)
    monkeypatch.setenv("SHOPSOMA_PYTEST_DB_OWNER_TOKEN", owner_token)
    monkeypatch.setenv("SHOPSOMA_PYTEST_DB_STALE_SECONDS", "0")
    original = DisposableDatabase(RESOLVED_DB_URL)
    replacement = None
    replacement_created = False
    try:
        original.create()
        engine = create_engine(
            RESOLVED_DB_URL.set(drivername="postgresql", database=original.name),
            poolclass=NullPool,
        )
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql(
                    "CREATE FUNCTION fixture_stale_collision() RETURNS integer "
                    "LANGUAGE sql AS 'SELECT 1'"
                )
        finally:
            engine.dispose()

        stale_marker = sign_owner_marker(
            RESOLVED_DB_URL,
            {
                **original.marker,
                "created_ns": 1,
                "pid": 2_147_483_647,
                "process_start": "1",
            },
        )
        original.marker = stale_marker
        original.marker_text = serialize_marker(stale_marker)
        admin = original._admin()
        try:
            with admin.connect() as connection:
                literal = String().literal_processor(connection.dialect)
                assert literal is not None
                connection.exec_driver_sql(
                    f"COMMENT ON DATABASE {original._quote(connection, original.name)} "
                    f"IS {literal(original.marker_text)}"
                )
        finally:
            admin.dispose()

        replacement = DisposableDatabase(RESOLVED_DB_URL)
        assert replacement.name == original.name
        replacement.create()
        replacement_created = True
        engine = create_engine(
            RESOLVED_DB_URL.set(drivername="postgresql", database=replacement.name),
            poolclass=NullPool,
        )
        try:
            with engine.connect() as connection:
                assert (
                    connection.scalar(
                        text("SELECT to_regprocedure('fixture_stale_collision()')")
                    )
                    is None
                )
        finally:
            engine.dispose()
    finally:
        try:
            if replacement is not None and replacement_created:
                replacement.drop()
        finally:
            _drop_owned_probe_databases(run_id, owner_token)


def test_scavenger_cleanup_is_bounded_to_one_batch(monkeypatch) -> None:
    from tests.conftest import RESOLVED_DB_URL

    lifecycles = []
    monkeypatch.setenv("SHOPSOMA_PYTEST_DB_STALE_SECONDS", "9999999999")
    try:
        for _ in range(_MAX_SCAVENGE + 1):
            monkeypatch.setenv("SHOPSOMA_PYTEST_DB_RUN_ID", uuid.uuid4().hex[:24])
            monkeypatch.setenv(
                "SHOPSOMA_PYTEST_DB_OWNER_TOKEN",
                uuid.uuid4().hex + uuid.uuid4().hex,
            )
            lifecycle = DisposableDatabase(RESOLVED_DB_URL)
            lifecycle.create()
            lifecycles.append(lifecycle)

        for lifecycle in lifecycles:
            _replace_database_marker(
                lifecycle,
                sign_owner_marker(
                    RESOLVED_DB_URL,
                    {
                        **lifecycle.marker,
                        "created_ns": 1,
                        "pid": 2_147_483_647,
                        "process_start": "1",
                    },
                ),
            )

        monkeypatch.setenv("SHOPSOMA_PYTEST_DB_RUN_ID", uuid.uuid4().hex[:24])
        monkeypatch.setenv(
            "SHOPSOMA_PYTEST_DB_OWNER_TOKEN",
            uuid.uuid4().hex + uuid.uuid4().hex,
        )
        monkeypatch.setenv("SHOPSOMA_PYTEST_DB_STALE_SECONDS", "0")
        scavenger = DisposableDatabase(RESOLVED_DB_URL)
        assert scavenger.scavenge() == _MAX_SCAVENGE
        assert scavenger.scavenge() == 1
        assert scavenger.scavenge() == 0
    finally:
        for lifecycle in lifecycles:
            lifecycle.drop()


def test_scavenger_cursor_reaches_stale_marker_after_rejected_page(monkeypatch) -> None:
    from tests.conftest import RESOLVED_DB_URL

    scavenger = DisposableDatabase(RESOLVED_DB_URL)
    monkeypatch.setattr("tests.fixture_database._MAX_SCAVENGE_SCAN", 2)
    monkeypatch.setenv("SHOPSOMA_PYTEST_DB_STALE_SECONDS", "0")
    rejected_names = [f"aa_fixture_rejected_{index}" for index in range(2)]
    stale_name = "az_fixture_valid_stale"
    admin = scavenger._admin()
    try:
        with admin.connect() as connection:
            literal = String().literal_processor(connection.dialect)
            assert literal is not None
            for name in [*rejected_names, stale_name]:
                connection.exec_driver_sql(
                    f"CREATE DATABASE {scavenger._quote(connection, name)}"
                )
            rejected_marker = '{"app":"shopsoma-pytest-database-v3","bad":true}'
            for name in rejected_names:
                connection.exec_driver_sql(
                    f"COMMENT ON DATABASE {scavenger._quote(connection, name)} "
                    f"IS {literal(rejected_marker)}"
                )
            stale = sign_owner_marker(
                RESOLVED_DB_URL,
                {
                    **make_owner_marker(RESOLVED_DB_URL, stale_name),
                    "created_ns": 1,
                    "pid": 2_147_483_647,
                    "process_start": "1",
                },
            )
            connection.exec_driver_sql(
                f"COMMENT ON DATABASE {scavenger._quote(connection, stale_name)} "
                f"IS {literal(serialize_marker(stale))}"
            )

        assert scavenger.scavenge() == 0
        assert scavenger.scavenge() == 1
    finally:
        with admin.connect() as connection:
            for name in [*rejected_names, stale_name]:
                exists = connection.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname=:name"),
                    {"name": name},
                )
                if exists:
                    scavenger._terminate_and_drop(connection, name)
        admin.dispose()


def test_xdist_workers_use_unique_databases_and_drop_all_of_them(tmp_path) -> None:
    environment, run_id, owner_token = _probe_environment()
    ready_dir = tmp_path / "xdist-ready"
    ready_dir.mkdir()
    release = tmp_path / "xdist-release"
    source = f"""
import os
from pathlib import Path
import time
import pytest

@pytest.mark.parametrize("slot", [0, 1])
def test_probe(slot):
    from tests.conftest import TEST_DATABASE_NAME
    worker = os.environ["PYTEST_XDIST_WORKER"]
    Path({str(ready_dir)!r}, worker).write_text(TEST_DATABASE_NAME)
    deadline = time.monotonic() + 45
    while not Path({str(release)!r}).exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert Path({str(release)!r}).exists()
"""
    process = None
    try:
        with _probe_file(source) as path:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-n2",
                    "--dist=load",
                    str(path),
                ],
                cwd=Path(__file__).parents[1],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            deadline = time.monotonic() + 90
            while (
                len(list(ready_dir.iterdir())) < 2
                and process.poll() is None
                and time.monotonic() < deadline
            ):
                time.sleep(0.05)
            ready_files = list(ready_dir.iterdir())
            assert len(ready_files) == 2, "xdist did not activate two workers"
            names = {ready_path.read_text() for ready_path in ready_files}
            assert len(names) == 2
            active_names = {
                name for name, _, _ in _owned_probe_databases(run_id, owner_token)
            }
            # The xdist controller imports conftest too, so it owns one additional
            # disposable DB. The two reported worker DBs must still be distinct.
            assert names < active_names
            assert len(active_names) == 3
            release.write_text("release")
            output, _ = process.communicate(timeout=_SUBPROCESS_TIMEOUT)
            assert process.returncode == 0, output[-4000:]
        assert _owned_probe_databases(run_id, owner_token) == []
    finally:
        release.write_text("release")
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=10)
        _drop_owned_probe_databases(run_id, owner_token)


@pytest.mark.asyncio
async def test_commits_are_visible_and_reset_is_order_independent(
    db_session, fixture_reset_database
):
    email = f"fixture-commit-{uuid.uuid4().hex}@example.test"
    await db_session.execute(
        text(
            "INSERT INTO users "
            "(id,email,hashed_password,full_name,role,is_active,email_verified,"
            "is_guest_created,created_at,updated_at) "
            "VALUES (:id,:email,'hash','Fixture Commit','CUSTOMER',true,true,false,now(),now())"
        ),
        {"id": uuid.uuid4(), "email": email},
    )
    await db_session.commit()
    factory = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    async with factory() as observer:
        assert (
            await observer.scalar(
                text("SELECT count(*) FROM users WHERE email=:email"), {"email": email}
            )
            == 1
        )
    await fixture_reset_database()
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM users WHERE email=:email"), {"email": email}
        )
        == 0
    )


@pytest.mark.asyncio
async def test_raw_ddl_table_rows_are_found_by_single_truncate(
    db_session, fixture_reset_database
):
    await db_session.execute(
        text("CREATE TABLE fixture_raw_rows (id bigserial PRIMARY KEY,value text)")
    )
    await db_session.execute(text("INSERT INTO fixture_raw_rows(value) VALUES ('x')"))
    await db_session.commit()
    try:
        await fixture_reset_database()
        assert (
            await db_session.scalar(text("SELECT count(*) FROM fixture_raw_rows")) == 0
        )
    finally:
        await db_session.execute(text("DROP TABLE IF EXISTS fixture_raw_rows CASCADE"))
        await db_session.commit()


@pytest.mark.asyncio
async def test_standalone_sequence_is_reset_or_fixture_fails_closed(
    db_session, fixture_reset_database
):
    await db_session.execute(text("CREATE SEQUENCE fixture_standalone START WITH 7"))
    await db_session.commit()
    try:
        assert (
            await db_session.scalar(text("SELECT nextval('fixture_standalone')")) == 7
        )
        await db_session.commit()
        await fixture_reset_database()
        assert (
            await db_session.scalar(text("SELECT nextval('fixture_standalone')")) == 7
        )
    finally:
        await db_session.execute(text("DROP SEQUENCE IF EXISTS fixture_standalone"))
        await db_session.commit()


_DDL_DRIFT_CASES = (
    (
        "table_columns_defaults_constraints_indexes",
        "CREATE TABLE fixture_drift_table (id integer DEFAULT 2 CONSTRAINT fixture_positive CHECK(id>0)); "
        "CREATE INDEX fixture_drift_index ON fixture_drift_table(id)",
        "DROP TABLE IF EXISTS fixture_drift_table CASCADE",
    ),
    (
        "sequence",
        "CREATE SEQUENCE fixture_drift_sequence",
        "DROP SEQUENCE IF EXISTS fixture_drift_sequence",
    ),
    (
        "view",
        "CREATE VIEW fixture_drift_view AS SELECT 1 AS id",
        "DROP VIEW IF EXISTS fixture_drift_view",
    ),
    (
        "materialized_view",
        "CREATE MATERIALIZED VIEW fixture_drift_matview AS SELECT 1 AS id",
        "DROP MATERIALIZED VIEW IF EXISTS fixture_drift_matview",
    ),
    (
        "type",
        "CREATE TYPE fixture_drift_type AS ENUM ('x')",
        "DROP TYPE IF EXISTS fixture_drift_type",
    ),
    (
        "schema",
        "CREATE SCHEMA fixture_drift_schema",
        "DROP SCHEMA IF EXISTS fixture_drift_schema CASCADE",
    ),
    (
        "function",
        "CREATE FUNCTION fixture_drift_function() RETURNS integer LANGUAGE sql AS 'SELECT 1'",
        "DROP FUNCTION IF EXISTS fixture_drift_function()",
    ),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "_label,setup,cleanup", _DDL_DRIFT_CASES, ids=[case[0] for case in _DDL_DRIFT_CASES]
)
async def test_every_persistent_raw_ddl_class_fails_closed(
    db_session, fixture_catalog_assert, _label, setup, cleanup
):
    for statement in setup.split(";"):
        if statement.strip():
            await db_session.execute(text(statement))
    await db_session.commit()
    try:
        with pytest.raises(RuntimeError, match="catalog drift"):
            await fixture_catalog_assert()
    finally:
        await db_session.execute(text(cleanup))
        await db_session.commit()
    await fixture_catalog_assert()


async def _baseline_security_table(db_session) -> str:
    """Return a quoted installed table whose security metadata starts clean."""
    table = await db_session.scalar(
        text(
            "SELECT format('%I.%I', n.nspname, c.relname) FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='r' "
            "AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity "
            "AND NOT has_table_privilege('public', c.oid, 'SELECT') "
            "AND NOT EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid=c.oid) "
            "AND NOT EXISTS (SELECT 1 FROM pg_rewrite r "
            "                WHERE r.ev_class=c.oid AND r.rulename<>'_RETURN') "
            "ORDER BY c.oid LIMIT 1"
        )
    )
    assert table is not None, "session-installed baseline needs a security-clean table"
    return table


@pytest.mark.asyncio
async def test_relation_owner_drift_on_baseline_table_fails_closed(
    db_session, fixture_catalog_assert
) -> None:
    table = await _baseline_security_table(db_session)
    original_owner = await db_session.scalar(
        text(
            "SELECT quote_ident(c.relowner::regrole::text) FROM pg_class c "
            "WHERE c.oid=to_regclass(:table)"
        ),
        {"table": table},
    )
    assert original_owner != "pg_database_owner"
    try:
        await db_session.execute(
            text(f"ALTER TABLE {table} OWNER TO pg_database_owner")
        )
        with pytest.raises(RuntimeError, match="catalog drift"):
            await fixture_catalog_assert(db_session)
    finally:
        await db_session.rollback()
    await fixture_catalog_assert()


@pytest.mark.asyncio
async def test_relation_acl_drift_on_baseline_table_fails_closed(
    db_session, fixture_catalog_assert
) -> None:
    table = await _baseline_security_table(db_session)
    try:
        await db_session.execute(text(f"GRANT SELECT ON TABLE {table} TO PUBLIC"))
        with pytest.raises(RuntimeError, match="catalog drift"):
            await fixture_catalog_assert(db_session)
    finally:
        await db_session.rollback()
    await fixture_catalog_assert()


@pytest.mark.asyncio
async def test_rls_force_rls_and_policy_drift_on_baseline_table_fail_closed(
    db_session, fixture_catalog_assert
) -> None:
    table = await _baseline_security_table(db_session)
    mutations = (
        "ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        "CREATE POLICY fixture_drift_policy ON {table} USING (true)",
    )
    for setup in mutations:
        try:
            await db_session.execute(text(setup.format(table=table)))
            with pytest.raises(RuntimeError, match="catalog drift"):
                await fixture_catalog_assert(db_session)
        finally:
            await db_session.rollback()
        await fixture_catalog_assert()


@pytest.mark.asyncio
async def test_non_view_rule_drift_on_baseline_table_fails_closed(
    db_session, fixture_catalog_assert
) -> None:
    table = await _baseline_security_table(db_session)
    try:
        await db_session.execute(
            text(
                f"CREATE RULE fixture_drift_rule AS ON INSERT TO {table} "
                "DO ALSO NOTHING"
            )
        )
        with pytest.raises(RuntimeError, match="catalog drift"):
            await fixture_catalog_assert(db_session)
    finally:
        await db_session.rollback()
    await fixture_catalog_assert()


@pytest.mark.asyncio
async def test_named_trigger_sentinel_rejects_a_forbidden_write(db_session) -> None:
    name = "tr_outbound_intent_rate_guards_write"
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM pg_trigger WHERE tgname=:name AND NOT tgisinternal"
            ),
            {"name": name},
        )
        == 1
    )
    with pytest.raises(DBAPIError, match="rate subject guard is server-maintained"):
        await db_session.execute(
            text(
                "INSERT INTO outbound_intent_rate_guards(intent_id,is_invalidated) "
                "VALUES (:id,false)"
            ),
            {"id": uuid.uuid4()},
        )
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_session_fence_terminates_an_exact_database_leak() -> None:
    from tests.conftest import TEST_DATABASE_LIFECYCLE, test_engine

    leaked = await test_engine.connect()
    try:
        await leaked.execute(text("SELECT 1"))
        await asyncio.to_thread(TEST_DATABASE_LIFECYCLE.fence_sessions)
        try:
            await leaked.execute(text("SELECT 1"))
        except (
            Exception
        ) as exc:  # asyncpg may surface termination before SQLAlchemy translates it
            assert type(exc).__module__.startswith(("asyncpg", "sqlalchemy"))
        else:
            pytest.fail("owned database session remained usable after exact fencing")
    finally:
        await leaked.close()


@pytest.mark.asyncio
async def test_database_has_exact_strong_ownership_marker(db_session) -> None:
    from tests.conftest import TEST_DATABASE_LIFECYCLE

    marker = await db_session.scalar(
        text(
            "SELECT shobj_description(oid,'pg_database') FROM pg_database WHERE datname=current_database()"
        )
    )
    assert marker == TEST_DATABASE_LIFECYCLE.marker_text
    assert "password" not in marker.lower()
    assert "postgresql://" not in marker.lower()
