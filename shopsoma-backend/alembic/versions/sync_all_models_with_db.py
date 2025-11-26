"""sync all models with database

This migration synchronizes the database schema with SQLAlchemy models.
It creates missing tables and adds missing columns without modifying existing ones.

Revision ID: sync_all_models_with_db
Revises: 4faacd854049
Create Date: 2025-11-26 13:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, MetaData
from sqlalchemy.dialects import postgresql

# Import Base to get all registered models
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.core.base import Base
import app.models  # noqa - This ensures all models are registered


# revision identifiers, used by Alembic.
revision: str = 'sync_all_models_with_db'
down_revision: Union[str, None] = '4faacd854049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Synchronize database schema with SQLAlchemy models.

    For each model:
    - Create table if it doesn't exist
    - Add missing columns if table exists

    This is idempotent and safe - won't fail if tables/columns already exist.
    """
    # Get database connection and inspector
    bind = op.get_bind()
    inspector = inspect(bind)

    # Get existing tables in database
    existing_tables = inspector.get_table_names()

    print(f"Starting schema sync...")
    print(f"Found {len(Base.metadata.tables)} models to sync")
    print(f"Existing tables in database: {len(existing_tables)}")

    # Iterate over all tables defined in models
    for table_name, table in Base.metadata.tables.items():
        print(f"\nProcessing table: {table_name}")

        if table_name not in existing_tables:
            # Table doesn't exist - create it with all columns and constraints
            print(f"  ⚠️  Table '{table_name}' does not exist - creating...")

            try:
                # Create the table using Alembic's create_table operation
                # We'll build column list from the SQLAlchemy table object
                columns = []
                for col in table.columns:
                    # Create a copy of the column for the migration
                    col_copy = col.copy()
                    columns.append(col_copy)

                # Create table with all columns
                op.create_table(
                    table_name,
                    *columns
                )

                # Create indexes
                for index in table.indexes:
                    op.create_index(
                        index.name,
                        table_name,
                        [col.name for col in index.columns],
                        unique=index.unique
                    )

                print(f"  ✅ Created table '{table_name}' with {len(columns)} columns")

            except Exception as e:
                print(f"  ❌ Error creating table '{table_name}': {e}")
                # Continue with other tables even if one fails
                continue

        else:
            # Table exists - check for missing columns
            print(f"  ✓ Table '{table_name}' exists - checking columns...")

            # Get existing column names
            existing_columns = {col['name']: col for col in inspector.get_columns(table_name)}

            # Check each model column
            for col in table.columns:
                col_name = col.name

                if col_name not in existing_columns:
                    # Column is missing - add it
                    print(f"    ⚠️  Column '{col_name}' missing - adding...")

                    try:
                        # Create column copy with proper type
                        col_copy = col.copy()

                        # Add the column
                        op.add_column(table_name, col_copy)
                        print(f"    ✅ Added column '{table_name}.{col_name}'")

                    except Exception as e:
                        print(f"    ❌ Error adding column '{table_name}.{col_name}': {e}")
                        # Continue with other columns even if one fails
                        continue
                else:
                    print(f"    ✓ Column '{col_name}' exists")

    print(f"\n✅ Schema synchronization complete!")


def downgrade() -> None:
    """
    Downgrade is intentionally left as no-op for safety.

    This migration is designed to be additive only (create tables/columns).
    Dropping tables or columns automatically could be dangerous on a live database.

    If you need to remove tables/columns, create specific migration files for that.
    """
    print("Note: This migration does not support automatic downgrade.")
    print("Tables and columns added by this migration will remain in the database.")
    print("Create specific migrations to drop tables/columns if needed.")
    pass
