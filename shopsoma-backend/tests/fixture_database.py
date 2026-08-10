"""Owned disposable PostgreSQL databases for the pytest fixture."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import time
from typing import Any

from sqlalchemy import String, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

_MARKER_APP = "shopsoma-pytest-database-v3"
_MARKER_PREFIX = '{"app":"shopsoma-pytest-database-v3"'
_MAX_IDENTIFIER_BYTES = 63
_MAX_SCAVENGE = 8
_MAX_SCAVENGE_SCAN = 64
_PROCESS_DATABASES: dict[tuple[str, str], "DisposableDatabase"] = {}


def _digest(value: str, size: int = 6) -> str:
    return hashlib.blake2s(value.encode("utf-8"), digest_size=size).hexdigest()


def normalize_name_component(value: object, *, prefix_bytes: int = 8) -> str:
    """Return an ASCII component carrying both normalized text and a full-input hash."""
    raw = str(value)
    normalized = re.sub(r"[^a-z0-9]+", "_", raw.casefold()).strip("_") or "x"
    prefix = normalized.encode("ascii", "ignore")[:prefix_bytes].decode("ascii")
    return f"{prefix}_{_digest(raw)}" if prefix else _digest(raw)


def build_test_database_name(
    base_name: str,
    *,
    worker: str | None = None,
    pid: int | None = None,
    run_id: str | None = None,
    parent_identity: str | None = None,
) -> str:
    """Hash every untrusted component into a collision-resistant PostgreSQL name."""
    logical_base = (
        f"{base_name[:-3]}_test_db"
        if base_name.endswith("_db")
        else f"{base_name}_test_db"
    )
    worker_identity = worker or os.getenv("PYTEST_XDIST_WORKER", "main")
    process_identity = pid if pid is not None else os.getpid()
    run_identity = run_id or os.environ.setdefault(
        "SHOPSOMA_PYTEST_DB_RUN_ID", secrets.token_hex(12)
    )
    parent_identity = parent_identity or "unspecified-parent"
    base_prefix = re.sub(r"[^a-z0-9]+", "_", logical_base.casefold()).strip("_")[:3]
    worker_prefix = re.sub(r"[^a-z0-9]+", "_", worker_identity.casefold()).strip("_")[
        :1
    ]
    combined_identity = "\0".join(
        map(
            str,
            (
                logical_base,
                worker_identity,
                process_identity,
                run_identity,
                parent_identity,
            ),
        )
    )
    name = (
        f"sspt_{base_prefix or 'x'}_{worker_prefix or 'x'}_"
        f"p{_digest(parent_identity)}_i{_digest(combined_identity, size=12)}"
    )
    if len(name.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise AssertionError(
            "test database identifier exceeds PostgreSQL's 63-byte limit"
        )
    return name


def process_start_token(pid: int) -> str | None:
    """Read Linux process start ticks so PID reuse cannot impersonate an owner."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().split()[21]
    except (FileNotFoundError, IndexError, PermissionError, OSError):
        return None


def parent_fingerprint(base_url: URL) -> str:
    """Fingerprint connection identity without retaining or exposing its password."""
    safe = base_url.set(password=None).render_as_string(hide_password=True)
    return _digest(safe, size=16)


def make_owner_marker(base_url: URL, database_name: str) -> dict[str, Any]:
    """Build a signed exact-match ownership marker inherited by xdist children."""
    pid = os.getpid()
    marker = {
        "app": _MARKER_APP,
        "created_ns": time.time_ns(),
        "database": database_name,
        "owner_token": os.environ.setdefault(
            "SHOPSOMA_PYTEST_DB_OWNER_TOKEN", secrets.token_hex(32)
        ),
        "parent": parent_fingerprint(base_url),
        "pid": pid,
        "process_start": process_start_token(pid),
        "run": os.environ.setdefault(
            "SHOPSOMA_PYTEST_DB_RUN_ID", secrets.token_hex(12)
        ),
    }
    return sign_owner_marker(base_url, marker)


def serialize_marker(marker: dict[str, Any]) -> str:
    return json.dumps(marker, sort_keys=True, separators=(",", ":"))


def _ownership_key(base_url: URL) -> bytes:
    password = base_url.password
    if not password:
        raise RuntimeError("test database ownership signing requires a password")
    return hashlib.sha256(f"{_MARKER_APP}\0{password}".encode("utf-8")).digest()


def sign_owner_marker(base_url: URL, marker: dict[str, Any]) -> dict[str, Any]:
    """Sign a marker without persisting the database credential used as authority."""
    unsigned = {key: value for key, value in marker.items() if key != "signature"}
    signature = hmac.new(
        _ownership_key(base_url),
        serialize_marker(unsigned).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {**unsigned, "signature": signature}


def _marker_is_authenticated(base_url: URL, marker: dict[str, Any]) -> bool:
    signature = marker.get("signature")
    if not isinstance(signature, str) or len(signature) != 64:
        return False
    expected = sign_owner_marker(base_url, marker)["signature"]
    return hmac.compare_digest(signature, expected)


def parse_marker(value: object) -> dict[str, Any] | None:
    if not isinstance(value, str) or not value.startswith(_MARKER_PREFIX):
        return None
    try:
        marker = json.loads(value)
    except (TypeError, ValueError):
        return None
    required = {
        "app",
        "created_ns",
        "database",
        "owner_token",
        "parent",
        "pid",
        "process_start",
        "run",
        "signature",
    }
    if (
        not isinstance(marker, dict)
        or set(marker) != required
        or marker["app"] != _MARKER_APP
    ):
        return None
    hex_shapes = {"owner_token": 64, "parent": 32, "run": 24, "signature": 64}
    if any(
        not isinstance(marker[field], str)
        or re.fullmatch(rf"[0-9a-f]{{{length}}}", marker[field]) is None
        for field, length in hex_shapes.items()
    ):
        return None
    if (
        not isinstance(marker["database"], str)
        or len(marker["database"].encode("utf-8")) > _MAX_IDENTIFIER_BYTES
        or re.fullmatch(r"[a-z][a-z0-9_]*", marker["database"]) is None
    ):
        return None
    if (
        type(marker["created_ns"]) is not int
        or marker["created_ns"] <= 0
        or type(marker["pid"]) is not int
        or marker["pid"] <= 0
        or not isinstance(marker["process_start"], str)
        or re.fullmatch(r"[0-9]+", marker["process_start"]) is None
    ):
        return None
    return marker


def marker_is_stale(
    marker: dict[str, Any],
    *,
    base_url: URL,
    database_name: str,
    parent: str,
    now_ns: int,
    minimum_age_seconds: float,
) -> bool:
    """Authorize cleanup only for signed same-cluster markers after age/process death."""
    if (
        marker.get("database") != database_name
        or marker.get("parent") != parent
        or not _marker_is_authenticated(base_url, marker)
    ):
        return False
    created_ns = marker.get("created_ns")
    pid = marker.get("pid")
    if not isinstance(created_ns, int) or not isinstance(pid, int):
        return False
    if now_ns - created_ns < int(minimum_age_seconds * 1_000_000_000):
        return False
    return process_start_token(pid) != marker.get("process_start")


class DisposableDatabase:
    """Create, fence, scavenge, and exactly drop one marked physical database."""

    def __init__(self, base_url: URL) -> None:
        self.base_url = base_url
        driver = base_url.drivername.split("+", 1)[0]
        self.admin_url = base_url.set(drivername=driver, database="postgres")
        self.name = build_test_database_name(
            base_url.database or "postgres",
            parent_identity=parent_fingerprint(base_url),
        )
        self.marker = make_owner_marker(base_url, self.name)
        self.marker_text = serialize_marker(self.marker)
        self._scavenge_cursor = ""

    def _admin(self):
        return create_engine(
            self.admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
        )

    @staticmethod
    def _quote(connection, identifier: str) -> str:
        return connection.dialect.identifier_preparer.quote(identifier)

    def _terminate_and_drop(self, connection, name: str) -> None:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname=:name AND pid<>pg_backend_pid()"
            ),
            {"name": name},
        )
        connection.exec_driver_sql(
            f"DROP DATABASE IF EXISTS {self._quote(connection, name)}"
        )

    def scavenge(self) -> int:
        """Bound cleanup of aged databases left by SIGKILLed workers."""
        minimum_age = float(os.getenv("SHOPSOMA_PYTEST_DB_STALE_SECONDS", "3600"))
        removed = 0
        engine = self._admin()
        try:
            with engine.connect() as connection:
                rows = connection.execute(
                    text(
                        "SELECT d.datname, shobj_description(d.oid, 'pg_database') "
                        "FROM pg_database d "
                        "WHERE shobj_description(d.oid, 'pg_database') LIKE :prefix "
                        "AND d.datname > :cursor "
                        "ORDER BY d.datname LIMIT :limit"
                    ),
                    {
                        "prefix": f"{_MARKER_PREFIX[:-1]}%",
                        "cursor": self._scavenge_cursor,
                        "limit": _MAX_SCAVENGE_SCAN,
                    },
                ).all()
                if not rows:
                    self._scavenge_cursor = ""
                for name, raw_marker in rows:
                    if removed >= _MAX_SCAVENGE:
                        break
                    self._scavenge_cursor = name
                    marker = parse_marker(raw_marker)
                    if marker and marker_is_stale(
                        marker,
                        base_url=self.base_url,
                        database_name=name,
                        parent=self.marker["parent"],
                        now_ns=time.time_ns(),
                        minimum_age_seconds=minimum_age,
                    ):
                        self._terminate_and_drop(connection, name)
                        removed += 1
        finally:
            engine.dispose()
        return removed

    def create(self) -> str:
        """Create new; never reuse an existing database or blindly replace a collision."""
        self.scavenge()
        engine = self._admin()
        try:
            with engine.connect() as connection:
                existing = connection.execute(
                    text(
                        "SELECT shobj_description(oid, 'pg_database') "
                        "FROM pg_database WHERE datname=:name"
                    ),
                    {"name": self.name},
                ).scalar()
                if existing is not None:
                    marker = parse_marker(existing)
                    stale = marker and marker_is_stale(
                        marker,
                        base_url=self.base_url,
                        database_name=self.name,
                        parent=self.marker["parent"],
                        now_ns=time.time_ns(),
                        minimum_age_seconds=float(
                            os.getenv("SHOPSOMA_PYTEST_DB_STALE_SECONDS", "3600")
                        ),
                    )
                    if not stale:
                        raise RuntimeError(
                            "refusing to reuse an existing test database"
                        )
                    self._terminate_and_drop(connection, self.name)
                quoted_name = self._quote(connection, self.name)
                connection.exec_driver_sql(f"CREATE DATABASE {quoted_name}")
                marker_literal = String().literal_processor(connection.dialect)
                if marker_literal is None:
                    raise RuntimeError("database dialect cannot quote marker literal")
                connection.exec_driver_sql(
                    f"COMMENT ON DATABASE {quoted_name} IS {marker_literal(self.marker_text)}"
                )
        finally:
            engine.dispose()
        return self.name

    def assert_owned(self) -> None:
        engine = self._admin()
        try:
            with engine.connect() as connection:
                actual = connection.execute(
                    text(
                        "SELECT shobj_description(oid, 'pg_database') "
                        "FROM pg_database WHERE datname=:name"
                    ),
                    {"name": self.name},
                ).scalar()
                if actual != self.marker_text:
                    raise RuntimeError("test database ownership marker mismatch")
        finally:
            engine.dispose()

    def fence_sessions(self) -> None:
        """Terminate only sessions attached to this exact, still-owned database."""
        engine = self._admin()
        try:
            with engine.connect() as connection:
                actual = connection.execute(
                    text(
                        "SELECT shobj_description(oid, 'pg_database') "
                        "FROM pg_database WHERE datname=:name"
                    ),
                    {"name": self.name},
                ).scalar()
                if actual != self.marker_text:
                    raise RuntimeError(
                        "refusing to fence sessions without exact ownership"
                    )
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname=:name AND pid<>pg_backend_pid()"
                    ),
                    {"name": self.name},
                )
        finally:
            engine.dispose()

    def drop(self) -> None:
        """Drop only this exact marked database, fencing every exact-DB session."""
        engine = self._admin()
        try:
            with engine.connect() as connection:
                actual = connection.execute(
                    text(
                        "SELECT shobj_description(oid, 'pg_database') "
                        "FROM pg_database WHERE datname=:name"
                    ),
                    {"name": self.name},
                ).scalar()
                if actual is None:
                    return
                if actual != self.marker_text:
                    raise RuntimeError(
                        "refusing to drop database with foreign ownership marker"
                    )
                self._terminate_and_drop(connection, self.name)
        finally:
            engine.dispose()


def get_process_database(base_url: URL) -> tuple[DisposableDatabase, bool]:
    """Create once per process/worker and reuse only the same live Python object.

    Some hermetic migration tests load ``conftest.py`` under a temporary module
    name. That must not create a second lifecycle owner for the same physical
    database. This registry is process-local and never authorizes reuse based
    only on a database name or marker.
    """
    candidate = DisposableDatabase(base_url)
    key = (parent_fingerprint(base_url), candidate.name)
    existing = _PROCESS_DATABASES.get(key)
    if existing is not None:
        return existing, False
    candidate.create()
    _PROCESS_DATABASES[key] = candidate
    return candidate, True
