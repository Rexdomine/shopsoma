"""
Pytest configuration and fixtures for testing
"""
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.core.database import get_db
from app.core.base import Base
from app.core.config import settings

# Test database URL
TEST_DATABASE_URL = settings.DATABASE_URL.replace("shopsoma_db", "shopsoma_test_db")
if TEST_DATABASE_URL.startswith("postgresql://"):
    TEST_DATABASE_URL = TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    echo=False
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session
        await session.rollback()

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create test client with test database"""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
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
        is_active=True
    )
    db_session.add(user)
    await db_session.flush()

    # Create vendor
    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user.id,
        business_name="Test Business",
        kyc_status=KYCStatus.APPROVED,
        approved=True
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
        "headers": {"Authorization": f"Bearer {token}"}
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
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    return {
        "user": user,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"}
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
        is_active=True
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )

    return {
        "user": user,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"}
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
        moderation_status=ModerationStatus.APPROVED
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    return product
