"""Alembic environment configuration

IMPORTANT: Alembic uses DATABASE_URL environment variable (sync PostgreSQL connection).
The FastAPI app uses the same DATABASE_URL but converts it to async format.
Both MUST point to the same underlying database.
"""
from logging.config import fileConfig
import sys
from pathlib import Path
import logging
import os

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Import Base directly without initializing async engine
from app.core.base import Base

# Import all models to ensure they're registered with SQLAlchemy
# This must happen AFTER Base is defined
import app.models  # noqa

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Get DATABASE_URL from environment variable
# This is the single source of truth for database connection
app_db_url = os.environ.get("DATABASE_URL")

if app_db_url is None:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Please set it in your Render environment or .env file."
    )

# Alembic needs a sync driver, so convert async URL if necessary
# Example: postgresql+asyncpg://... -> postgresql://...
sync_db_url = app_db_url.replace("postgresql+asyncpg://", "postgresql://")

# Override sqlalchemy.url with the sync version
config.set_main_option("sqlalchemy.url", sync_db_url)

# Log database connection (masked for security)
logger = logging.getLogger('alembic.env')
try:
    from urllib.parse import urlparse
    parsed = urlparse(sync_db_url)
    host = parsed.hostname or "unknown"
    db_name = parsed.path.lstrip("/") or "unknown"
    masked_db = f"host={host} db={db_name}"
except Exception:
    masked_db = "host=unknown db=unknown"

# Print to console for immediate visibility during migrations
print(f"Alembic using database URL: postgresql://{masked_db.replace('host=', '').replace(' db=', '@')}")
logger.info(f"Alembic using database: {masked_db}")

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
