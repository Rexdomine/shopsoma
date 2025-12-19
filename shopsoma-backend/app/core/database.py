"""
Database configuration and session management

IMPORTANT: This async engine and Alembic (in alembic/env.py) MUST use the same database.
- settings.DATABASE_URL is the single source of truth (sync PostgreSQL URL)
- settings.ASYNC_DATABASE_URL is automatically derived for async engine
- Alembic uses settings.DATABASE_URL directly (sync)
- Both point to the same underlying database
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings
from app.core.base import Base
import logging

logger = logging.getLogger(__name__)

# Use the derived ASYNC_DATABASE_URL from settings
# This ensures we're using the same database as Alembic migrations
database_url = settings.ASYNC_DATABASE_URL

# Log database connection (masked for security)
masked_db = settings.get_masked_db_url(database_url)
logger.info(f"Async SQLAlchemy engine connecting to: {masked_db}")

engine = create_async_engine(
    database_url,
    echo=settings.DATABASE_ECHO,
    future=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# Dependency to get database session
async def get_db() -> AsyncSession:
    """Get database session"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
