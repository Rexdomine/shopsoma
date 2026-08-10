"""Owned disposable PostgreSQL databases for the pytest fixture."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Any

from sqlalchemy import String, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.pool import NullPool

_MARKER_APP = "shopsoma-pytest-database-v4"
_MARKER_PREFIX = '{"app":"shopsoma-pytest-database-v4"'
_MAX_IDENTIFIER_BYTES = 63
_MAX_SCAVENGE = 8
_MAX_SCAVENGE_SCAN = 64
_PUBLICATION_LEASE_WAIT_SECONDS = 10.0
_PUBLICATION_LEASE_POLL_SECONDS = 0.02
_NAME_PREFIX = "sspt_"
_NAME_AUTH_HEX = 18
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
        f"p{_digest(parent_identity)}_i{_digest(combined_identity, size=8)}"
    )
    if len(name.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise AssertionError(
            "test database identifier exceeds PostgreSQL's 63-byte limit"
        )
    return name


def advisory_lock_key(lease_token: str, database_name: str, parent: str) -> int:
    """Derive a signed PostgreSQL advisory-lock key from authenticated identity."""
    identity = "\0".join((_MARKER_APP, lease_token, database_name, parent))
    return int.from_bytes(
        hashlib.blake2b(identity.encode("utf-8"), digest_size=8).digest(),
        byteorder="big",
        signed=True,
    )


def parent_fingerprint(base_url: URL) -> str:
    """Fingerprint connection identity without retaining or exposing its password."""
    safe = base_url.set(password=None).render_as_string(hide_password=True)
    return _digest(safe, size=16)


def make_owner_marker(base_url: URL, database_name: str) -> dict[str, Any]:
    """Build a signed exact-match ownership marker inherited by xdist children."""
    pid = os.getpid()
    owner_token = os.environ.setdefault(
        "SHOPSOMA_PYTEST_DB_OWNER_TOKEN", secrets.token_hex(32)
    )
    lease_token = secrets.token_hex(32)
    parent = parent_fingerprint(base_url)
    marker = {
        "app": _MARKER_APP,
        "created_ns": time.time_ns(),
        "database": database_name,
        "lease_key": advisory_lock_key(lease_token, database_name, parent),
        "lease_token": lease_token,
        "owner_token": owner_token,
        "parent": parent,
        "pid": pid,
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


def authenticate_database_name(base_url: URL, unsigned_name: str) -> str:
    """Embed proof that an otherwise-unmarked name belongs to this fixture authority."""
    tag = hmac.new(
        _ownership_key(base_url),
        (
            f"{_MARKER_APP}\0database-name\0{parent_fingerprint(base_url)}\0"
            f"{unsigned_name}"
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:_NAME_AUTH_HEX]
    name = f"{unsigned_name}_a{tag}"
    if len(name.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise AssertionError(
            "authenticated test database identifier exceeds PostgreSQL's 63-byte limit"
        )
    return name


def database_name_is_authenticated(base_url: URL, name: str) -> bool:
    """Accept only fixture names carrying a password-derived authentication tag."""
    match = re.fullmatch(
        rf"(?P<unsigned>{re.escape(_NAME_PREFIX)}[a-z0-9_]+)_a"
        rf"(?P<tag>[0-9a-f]{{{_NAME_AUTH_HEX}}})",
        name,
    )
    if match is None:
        return False
    return hmac.compare_digest(
        name, authenticate_database_name(base_url, match.group("unsigned"))
    )


def publication_lock_key(database_name: str, parent: str) -> int:
    """Derive the deterministic lock that fences CREATE-to-COMMENT publication."""
    identity = "\0".join((_MARKER_APP, "publication", database_name, parent))
    return int.from_bytes(
        hashlib.blake2b(identity.encode("utf-8"), digest_size=8).digest(),
        byteorder="big",
        signed=True,
    )


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
        "lease_key",
        "lease_token",
        "owner_token",
        "parent",
        "pid",
        "run",
        "signature",
    }
    if (
        not isinstance(marker, dict)
        or set(marker) != required
        or marker["app"] != _MARKER_APP
    ):
        return None
    hex_shapes = {
        "lease_token": 64,
        "owner_token": 64,
        "parent": 32,
        "run": 24,
        "signature": 64,
    }
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
        or type(marker["lease_key"]) is not int
        or not -(2**63) <= marker["lease_key"] < 2**63
        or marker["lease_key"]
        != advisory_lock_key(
            marker["lease_token"], marker["database"], marker["parent"]
        )
    ):
        return None
    return marker


def marker_is_cleanup_candidate(
    marker: dict[str, Any],
    *,
    base_url: URL,
    database_name: str,
    parent: str,
    now_ns: int,
    minimum_age_seconds: float,
) -> bool:
    """Validate signed same-cluster ownership and the minimum cleanup age."""
    if (
        marker.get("database") != database_name
        or marker.get("parent") != parent
        or not _marker_is_authenticated(base_url, marker)
    ):
        return False
    created_ns = marker.get("created_ns")
    if not isinstance(created_ns, int):
        return False
    if now_ns - created_ns < int(minimum_age_seconds * 1_000_000_000):
        return False
    return True


class DisposableDatabase:
    """Create, fence, scavenge, and exactly drop one marked physical database."""

    def __init__(self, base_url: URL) -> None:
        self.base_url = base_url
        driver = base_url.drivername.split("+", 1)[0]
        self.admin_url = base_url.set(drivername=driver, database="postgres")
        parent = parent_fingerprint(base_url)
        self.name = authenticate_database_name(
            base_url,
            build_test_database_name(
                base_url.database or "postgres",
                parent_identity=parent,
            ),
        )
        self.marker = make_owner_marker(base_url, self.name)
        self.marker_text = serialize_marker(self.marker)
        self._scavenge_cursor = ""
        self._lease_engine = None
        self._lease_connection = None
        self._publication_lease_held = False

    def _admin(self):
        return create_engine(
            self.admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool
        )

    def _acquire_owner_lease(self) -> None:
        """Hold cluster-visible liveness for this owner until drop or process death."""
        if self._lease_connection is not None:
            return
        engine = self._admin()
        connection = engine.connect()
        try:
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": self.marker["lease_key"]},
            )
            if not acquired:
                raise RuntimeError(
                    "refusing to reuse an existing live test database lease"
                )
        except BaseException:
            connection.close()
            engine.dispose()
            raise
        self._lease_engine = engine
        self._lease_connection = connection

    def _release_owner_lease(self) -> None:
        connection = self._lease_connection
        engine = self._lease_engine
        self._lease_connection = None
        self._lease_engine = None
        if connection is None:
            return
        try:
            connection.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": self.marker["lease_key"]},
            )
        finally:
            connection.close()
            if engine is not None:
                engine.dispose()

    def _acquire_publication_lease(self) -> None:
        """Fence the non-transactional CREATE DATABASE / COMMENT publication gap."""
        connection = self._lease_connection
        if connection is None:
            raise RuntimeError("owner lease is required before database publication")
        if self._publication_lease_held:
            return
        key = publication_lock_key(self.name, self.marker["parent"])
        deadline = time.monotonic() + _PUBLICATION_LEASE_WAIT_SECONDS
        while True:
            acquired = connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
            )
            if acquired:
                self._publication_lease_held = True
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("another test database creator is still publishing")
            time.sleep(_PUBLICATION_LEASE_POLL_SECONDS)

    def _release_publication_lease(self) -> None:
        connection = self._lease_connection
        if not self._publication_lease_held:
            return
        if connection is None:
            raise RuntimeError("lost fixture publication connection")
        released = connection.scalar(
            text("SELECT pg_advisory_unlock(:key)"),
            {"key": publication_lock_key(self.name, self.marker["parent"])},
        )
        self._publication_lease_held = False
        if not released:
            raise RuntimeError("lost fixture publication lease")

    @staticmethod
    def _try_acquire_marker_lease(connection, marker: dict[str, Any]) -> bool:
        return bool(
            connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": marker["lease_key"]},
            )
        )

    @staticmethod
    def _release_marker_lease(connection, marker: dict[str, Any]) -> None:
        released = connection.scalar(
            text("SELECT pg_advisory_unlock(:key)"),
            {"key": marker["lease_key"]},
        )
        if not released:
            raise RuntimeError("lost fixture cleanup lease before database drop")

    @staticmethod
    def _quote(connection, identifier: str) -> str:
        return connection.dialect.identifier_preparer.quote(identifier)

    @staticmethod
    def _database_marker_text(connection, name: str) -> str | None:
        """Read the authoritative marker while holding the candidate cleanup lease."""
        return connection.execute(
            text(
                "SELECT shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname=:name"
            ),
            {"name": name},
        ).scalar()

    @staticmethod
    def _database_marker_row(connection, name: str) -> tuple[bool, str | None]:
        row = connection.execute(
            text(
                "SELECT shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname=:name"
            ),
            {"name": name},
        ).first()
        return (False, None) if row is None else (True, row[0])

    def _try_acquire_publication_lease(self, connection, name: str) -> bool:
        return bool(
            connection.scalar(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": publication_lock_key(name, self.marker["parent"])},
            )
        )

    def _release_candidate_publication_lease(self, connection, name: str) -> None:
        released = connection.scalar(
            text("SELECT pg_advisory_unlock(:key)"),
            {"key": publication_lock_key(name, self.marker["parent"])},
        )
        if not released:
            raise RuntimeError("lost fixture orphan-publication cleanup lease")

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
                        "WHERE (shobj_description(d.oid, 'pg_database') LIKE :prefix "
                        "OR (shobj_description(d.oid, 'pg_database') IS NULL "
                        "AND d.datname LIKE :name_prefix)) "
                        "AND d.datname > :cursor "
                        "ORDER BY d.datname LIMIT :limit"
                    ),
                    {
                        "prefix": f"{_MARKER_PREFIX[:-1]}%",
                        "name_prefix": f"{_NAME_PREFIX}%",
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
                    if raw_marker is None and database_name_is_authenticated(
                        self.base_url, name
                    ):
                        if not self._try_acquire_publication_lease(connection, name):
                            continue
                        try:
                            exists, current = self._database_marker_row(
                                connection, name
                            )
                            if not exists or current is not None:
                                continue
                            self._terminate_and_drop(connection, name)
                            removed += 1
                        finally:
                            self._release_candidate_publication_lease(connection, name)
                        continue
                    if (
                        marker
                        and marker_is_cleanup_candidate(
                            marker,
                            base_url=self.base_url,
                            database_name=name,
                            parent=self.marker["parent"],
                            now_ns=time.time_ns(),
                            minimum_age_seconds=minimum_age,
                        )
                        and self._try_acquire_marker_lease(connection, marker)
                    ):
                        try:
                            if (
                                self._database_marker_text(connection, name)
                                != raw_marker
                            ):
                                continue
                            self._terminate_and_drop(connection, name)
                            removed += 1
                        finally:
                            self._release_marker_lease(connection, marker)
        finally:
            engine.dispose()
        return removed

    def create(self) -> str:
        """Create new; recover only authenticated orphans from interrupted publication."""
        self._acquire_owner_lease()
        try:
            self.scavenge()
            engine = self._admin()
            try:
                with engine.connect() as connection:
                    exists, existing = self._database_marker_row(connection, self.name)
                    if exists and existing is None:
                        if not database_name_is_authenticated(self.base_url, self.name):
                            raise RuntimeError(
                                "refusing to replace an unauthenticated unmarked database"
                            )
                        self._acquire_publication_lease()
                        current_exists, current = self._database_marker_row(
                            connection, self.name
                        )
                        if current_exists and current is not None:
                            raise RuntimeError(
                                "refusing to replace an unmarked database whose "
                                "ownership changed while acquiring its publication lease"
                            )
                        if current_exists:
                            self._terminate_and_drop(connection, self.name)
                    elif existing is not None:
                        marker = parse_marker(existing)
                        if not marker or not marker_is_cleanup_candidate(
                            marker,
                            base_url=self.base_url,
                            database_name=self.name,
                            parent=self.marker["parent"],
                            now_ns=time.time_ns(),
                            minimum_age_seconds=float(
                                os.getenv("SHOPSOMA_PYTEST_DB_STALE_SECONDS", "3600")
                            ),
                        ):
                            raise RuntimeError(
                                "refusing to reuse an existing test database"
                            )
                        if not self._try_acquire_marker_lease(connection, marker):
                            raise RuntimeError(
                                "refusing to reuse an existing test database"
                            )
                        try:
                            if (
                                self._database_marker_text(connection, self.name)
                                != existing
                            ):
                                raise RuntimeError(
                                    "refusing to replace a test database whose "
                                    "ownership changed while acquiring its lease"
                                )
                            self._terminate_and_drop(connection, self.name)
                        finally:
                            self._release_marker_lease(connection, marker)
                    self._acquire_publication_lease()
                    appeared, _ = self._database_marker_row(connection, self.name)
                    if appeared:
                        raise RuntimeError(
                            "refusing to create a test database whose name became occupied "
                            "while acquiring its publication lease"
                        )
                    quoted_name = self._quote(connection, self.name)
                    connection.exec_driver_sql(f"CREATE DATABASE {quoted_name}")
                    marker_literal = String().literal_processor(connection.dialect)
                    if marker_literal is None:
                        raise RuntimeError(
                            "database dialect cannot quote marker literal"
                        )
                    connection.exec_driver_sql(
                        f"COMMENT ON DATABASE {quoted_name} IS "
                        f"{marker_literal(self.marker_text)}"
                    )
            finally:
                engine.dispose()
            self._release_publication_lease()
        except BaseException:
            self._release_publication_lease()
            self._release_owner_lease()
            raise
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
            self._release_owner_lease()


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
