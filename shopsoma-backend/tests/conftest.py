"""
Pytest configuration and fixtures for testing
"""

import pytest
import asyncio
import atexit
import os
from typing import AsyncGenerator, Awaitable, Callable, Generator
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.core.database import get_db
from app.core.base import Base
from app.core.config import settings
from tests.fixture_database import build_test_database_name, get_process_database


def _build_test_database_name(base_name: str) -> str:
    return build_test_database_name(base_name)


_ASYNCPG_ONLY_QUERY_FIELDS = {
    "command_timeout",
    "direct_tls",
    "max_cacheable_statement_size",
    "max_cached_statement_lifetime",
    "prepared_statement_cache_size",
    "statement_cache_size",
}


def build_sync_database_url(base_url: URL, database_name: str) -> URL:
    """Build a libpq URL, structurally removing asyncpg-only parameters."""
    query = dict(base_url.query)
    async_ssl = query.pop("ssl", None)
    if async_ssl is not None and "sslmode" not in query:
        query["sslmode"] = async_ssl
    for field in _ASYNCPG_ONLY_QUERY_FIELDS:
        query.pop(field, None)
    return base_url.set(
        drivername=base_url.drivername.split("+", 1)[0],
        database=database_name,
        query=query,
    )


def build_async_database_url(base_url: URL, database_name: str) -> URL:
    """Build an asyncpg URL, structurally removing libpq-only parameters."""
    query = dict(base_url.query)
    sync_sslmode = query.pop("sslmode", None)
    if sync_sslmode is not None and "ssl" not in query:
        query["ssl"] = sync_sslmode
    # asyncpg has no application_name keyword; callers may use server_settings
    # explicitly when that behavior is required.
    query.pop("application_name", None)
    return base_url.set(
        drivername="postgresql+asyncpg", database=database_name, query=query
    )


def _resolve_db_url() -> "URL":
    base_url = make_url(settings.DATABASE_URL)
    password_override = os.getenv("POSTGRES_PASSWORD")
    if password_override:
        return base_url.set(password=password_override)
    if base_url.password:
        return base_url
    return base_url.set(password="shopsoma_dev_password")


# Test database URL
RESOLVED_DB_URL = _resolve_db_url()
TEST_DATABASE_LIFECYCLE, _TEST_DATABASE_CREATED = get_process_database(RESOLVED_DB_URL)
TEST_DATABASE_NAME = TEST_DATABASE_LIFECYCLE.name
if _TEST_DATABASE_CREATED:
    atexit.register(TEST_DATABASE_LIFECYCLE.drop)
ASYNC_DRIVER = "postgresql+asyncpg"
_SYNC_TEST_DATABASE_URL = build_sync_database_url(RESOLVED_DB_URL, TEST_DATABASE_NAME)
TEST_DATABASE_URL = _SYNC_TEST_DATABASE_URL.render_as_string(hide_password=False)
_ASYNC_TEST_DATABASE_URL = build_async_database_url(
    RESOLVED_DB_URL, TEST_DATABASE_NAME
).render_as_string(hide_password=False)

# Create test engine
test_engine = create_async_engine(
    _ASYNC_TEST_DATABASE_URL, poolclass=NullPool, echo=False
)

TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

_CATALOG_SQL = """
WITH user_namespaces AS (
  SELECT oid,nspname FROM pg_namespace
  WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'
), objects(kind, identity, definition) AS (
  SELECT 'schema', nspname, nspname FROM user_namespaces
  UNION ALL SELECT 'extension', e.extname, e.extversion || ':' || n.nspname
    FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
  UNION ALL SELECT 'relation', n.nspname||'.'||c.relname,
    c.relkind::text || ':' || c.relpersistence::text || ':' ||
    COALESCE(c.reloptions::text,'') || ':' || c.relowner::regrole::text || ':' ||
    COALESCE(c.relacl::text,'') || ':' || c.relrowsecurity::text || ':' ||
    c.relforcerowsecurity::text || ':' || c.relreplident::text || ':' ||
    c.relispartition::text || ':' ||
    COALESCE(pg_get_expr(c.relpartbound,c.oid,true),'') || ':' ||
    COALESCE(pg_get_partkeydef(c.oid),'')
    FROM pg_class c JOIN user_namespaces n ON n.oid=c.relnamespace
    WHERE c.relkind IN ('r','p','S','v','m')
  UNION ALL SELECT 'view', n.nspname||'.'||c.relname, pg_get_viewdef(c.oid, true)
    FROM pg_class c JOIN user_namespaces n ON n.oid=c.relnamespace
    WHERE c.relkind IN ('v','m')
  UNION ALL SELECT 'function', n.nspname||'.'||p.proname||'('||
    pg_get_function_identity_arguments(p.oid)||')', pg_get_functiondef(p.oid)
    FROM pg_proc p JOIN user_namespaces n ON n.oid=p.pronamespace
  UNION ALL SELECT 'trigger', n.nspname||'.'||c.relname||'.'||t.tgname,
    t.tgenabled::text || ':' || pg_get_triggerdef(t.oid, true)
    FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
    JOIN user_namespaces n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal
  UNION ALL SELECT 'policy', n.nspname||'.'||c.relname||'.'||p.polname,
    p.polcmd::text || ':' || p.polpermissive::text || ':' || p.polroles::text || ':' ||
    COALESCE(pg_get_expr(p.polqual,p.polrelid,true),'') || ':' ||
    COALESCE(pg_get_expr(p.polwithcheck,p.polrelid,true),'')
    FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
    JOIN user_namespaces n ON n.oid=c.relnamespace
  UNION ALL SELECT 'rule', n.nspname||'.'||c.relname||'.'||r.rulename,
    r.ev_enabled::text || ':' || pg_get_ruledef(r.oid, true)
    FROM pg_rewrite r JOIN pg_class c ON c.oid=r.ev_class
    JOIN user_namespaces n ON n.oid=c.relnamespace WHERE r.rulename <> '_RETURN'
  UNION ALL SELECT 'index', n.nspname||'.'||c.relname, pg_get_indexdef(c.oid)
    FROM pg_class c JOIN user_namespaces n ON n.oid=c.relnamespace
    WHERE c.relkind='i'
  UNION ALL SELECT 'constraint', n.nspname||'.'||r.relname||'.'||co.conname,
    co.contype::text || ':' || co.condeferrable::text || ':' ||
    co.condeferred::text || ':' || pg_get_constraintdef(co.oid, true)
    FROM pg_constraint co JOIN pg_class r ON r.oid=co.conrelid
    JOIN user_namespaces n ON n.oid=r.relnamespace
  UNION ALL SELECT 'column', n.nspname||'.'||c.relname||'.'||a.attname,
    format_type(a.atttypid,a.atttypmod)||':'||a.attnotnull::text||':'||
    a.attidentity::text||':'||a.attgenerated::text||':'||
    COALESCE(pg_get_expr(d.adbin,d.adrelid),'')
    FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
    JOIN user_namespaces n ON n.oid=c.relnamespace
    LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
    WHERE a.attnum>0 AND NOT a.attisdropped AND c.relkind IN ('r','p','v','m')
  UNION ALL SELECT 'type', n.nspname||'.'||t.typname,
    t.typtype::text||':'||t.typcategory::text||':'||t.typbasetype::regtype::text||':'||
    COALESCE((SELECT string_agg(e.enumlabel,',' ORDER BY e.enumsortorder)
              FROM pg_enum e WHERE e.enumtypid=t.oid),'')
    FROM pg_type t JOIN user_namespaces n ON n.oid=t.typnamespace
    WHERE t.typtype IN ('e','d','c') AND NOT EXISTS
      (SELECT 1 FROM pg_class c WHERE c.reltype=t.oid AND c.relkind IN ('r','p','v','m'))
  UNION ALL SELECT 'sequence', n.nspname||'.'||c.relname,
    s.seqtypid::regtype::text||':'||s.seqstart||':'||s.seqincrement||':'||
    s.seqmax||':'||s.seqmin||':'||s.seqcache||':'||s.seqcycle::text||':'||
    COALESCE(dep.refobjid::regclass::text,'standalone')
    FROM pg_class c JOIN user_namespaces n ON n.oid=c.relnamespace
    JOIN pg_sequence s ON s.seqrelid=c.oid
    LEFT JOIN pg_depend dep ON dep.objid=c.oid AND dep.classid='pg_class'::regclass
      AND dep.refclassid='pg_class'::regclass AND dep.deptype IN ('a','i')
)
SELECT kind,identity,definition FROM objects ORDER BY kind,identity,definition
"""
_CONNECTION_FINGERPRINT_SQL = """
SELECT current_database(), current_user, inet_server_addr()::text,
       inet_server_port(), current_setting('server_version_num')
"""
_catalog_baseline: dict[str, tuple] | None = None


def _sync_catalog(connection) -> dict[str, tuple]:
    return {
        "connection": tuple(
            connection.execute(text(_CONNECTION_FINGERPRINT_SQL)).one()
        ),
        "objects": tuple(tuple(row) for row in connection.execute(text(_CATALOG_SQL))),
    }


async def _async_catalog(connection=None) -> dict[str, tuple]:
    if connection is None:
        async with test_engine.connect() as owned_connection:
            return await _async_catalog(owned_connection)
    return {
        "connection": tuple(
            (await connection.execute(text(_CONNECTION_FINGERPRINT_SQL))).one()
        ),
        "objects": tuple(
            tuple(row) for row in (await connection.execute(text(_CATALOG_SQL)))
        ),
    }


async def _assert_catalog_baseline(connection=None) -> None:
    if _catalog_baseline is None:
        raise RuntimeError("fixture catalog baseline was not installed")
    current = await _async_catalog(connection)
    drift = [
        name for name, value in current.items() if value != _catalog_baseline[name]
    ]
    if drift:
        raise RuntimeError(f"test database catalog drift detected: {', '.join(drift)}")


async def _truncate_user_tables() -> None:
    """Discover and truncate every ordinary public table in one bounded statement."""
    async with test_engine.begin() as connection:
        await connection.execute(text("SET LOCAL lock_timeout = '5s'"))
        await connection.execute(text("SET LOCAL statement_timeout = '30s'"))
        rows = (
            await connection.execute(
                text(
                    "SELECT n.nspname, c.relname FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='public' AND c.relkind IN ('r', 'p') "
                    "ORDER BY n.nspname, c.relname"
                )
            )
        ).all()
        preparer = connection.dialect.identifier_preparer
        if rows:
            targets = ", ".join(
                f"{preparer.quote_schema(schema)}.{preparer.quote(table)}"
                for schema, table in rows
            )
            await connection.execute(
                text(f"TRUNCATE TABLE {targets} RESTART IDENTITY CASCADE")
            )
        standalone = (
            await connection.execute(
                text(
                    "SELECT n.nspname,c.relname,s.seqstart FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "JOIN pg_sequence s ON s.seqrelid=c.oid "
                    "LEFT JOIN pg_depend d ON d.objid=c.oid "
                    "AND d.classid='pg_class'::regclass "
                    "AND d.refclassid='pg_class'::regclass AND d.deptype IN ('a','i') "
                    "WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' "
                    "AND d.objid IS NULL ORDER BY n.nspname,c.relname"
                )
            )
        ).all()
        for schema, sequence, start in standalone:
            qualified = f"{preparer.quote_schema(schema)}.{preparer.quote(sequence)}"
            await connection.execute(
                text(f"ALTER SEQUENCE {qualified} RESTART WITH {int(start)}")
            )


@pytest.fixture(scope="session", autouse=True)
def _session_database_schema() -> Generator[None, None, None]:
    """Install the metadata, functions, and triggers once per pytest process."""
    global _catalog_baseline
    sync_url = build_sync_database_url(RESOLVED_DB_URL, TEST_DATABASE_NAME)
    sync_engine = create_engine(sync_url, poolclass=NullPool)
    try:
        with sync_engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("SET LOCAL statement_timeout = '120s'"))
            Base.metadata.create_all(connection)
        with sync_engine.connect() as connection:
            _catalog_baseline = _sync_catalog(connection)
        yield
        with sync_engine.connect() as connection:
            current = _sync_catalog(connection)
        drift = [
            name for name, value in current.items() if value != _catalog_baseline[name]
        ]
        if drift:
            raise RuntimeError(
                f"test database catalog drift detected at session end: {', '.join(drift)}"
            )
    finally:
        sync_engine.dispose()
        asyncio.run(test_engine.dispose())
        TEST_DATABASE_LIFECYCLE.drop()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a real session after bounded committed-state cleanup; no outer rollback."""
    await asyncio.to_thread(TEST_DATABASE_LIFECYCLE.fence_sessions)
    await _assert_catalog_baseline()
    await _truncate_user_tables()
    try:
        async with TestSessionLocal() as session:
            try:
                yield session
            finally:
                await session.rollback()
    finally:
        # Run even when the test fails: schema/function/trigger drift is never
        # silently carried into the next node.
        await _assert_catalog_baseline()


@pytest.fixture
def fixture_reset_database() -> Callable[[], Awaitable[None]]:
    return _truncate_user_tables


@pytest.fixture
def fixture_catalog_assert() -> Callable[[], Awaitable[None]]:
    return _assert_catalog_baseline


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with test database"""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
async def vendor_user(client: AsyncClient, db_session: AsyncSession):
    """Create a vendor user and get auth token"""
    from app.models.user import User, UserRole
    from app.models.vendor import Vendor, KYCStatus
    from app.core.security import get_password_hash, create_access_token
    import uuid

    # Create user
    user = User(
        id=uuid.uuid4(),
        email="vendor@test.com",
        hashed_password=get_password_hash("VendorPass123"),
        full_name="Test Vendor",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    # Create vendor
    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user.id,
        business_name="Test Business",
        kyc_status=KYCStatus.APPROVED,
        approved=True,
    )
    db_session.add(vendor)
    await db_session.commit()

    # Create token
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    return {
        "user": user,
        "vendor": vendor,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
async def customer_user(client: AsyncClient, db_session: AsyncSession):
    """Create a customer user and get auth token"""
    from app.models.user import User, UserRole
    from app.core.security import get_password_hash, create_access_token
    import uuid

    user = User(
        id=uuid.uuid4(),
        email="customer@test.com",
        hashed_password=get_password_hash("CustomerPass123"),
        full_name="Test Customer",
        role=UserRole.CUSTOMER,
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    return {
        "user": user,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
async def admin_user(client: AsyncClient, db_session: AsyncSession):
    """Create an admin user and get auth token"""
    from app.models.user import User, UserRole
    from app.core.security import get_password_hash, create_access_token
    import uuid

    user = User(
        id=uuid.uuid4(),
        email="admin@test.com",
        hashed_password=get_password_hash("AdminPass123"),
        full_name="Test Admin",
        role=UserRole.ADMIN,
        email_verified=True,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    return {
        "user": user,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture
async def sample_product(vendor_user, db_session: AsyncSession):
    """Create a sample product for testing"""
    from app.models.product import Product, ProductStatus, ModerationStatus
    import uuid

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Test Product",
        description="Test product description",
        base_price=99.99,
        total_stock=100,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    return product
