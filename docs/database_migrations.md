# Database Migrations Guide

## Overview

This project uses **Alembic** for database migrations. Alembic is a lightweight database migration tool for SQLAlchemy.

## Setup

### Prerequisites
1. PostgreSQL 14+ installed and running
2. Python virtual environment activated
3. Dependencies installed (`pip install -r requirements.txt`)

### Database Configuration

**Development:**
```bash
# Create database
createdb shopsoma_db

# Or using psql
psql -U postgres
CREATE DATABASE shopsoma_db;
```

**Production:**
- Database URL is configured via `DATABASE_URL` environment variable
- Use the PostgreSQL addon on Render

## Migration Commands

### Generate a New Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "description of changes"

# Create empty migration for manual SQL
alembic revision -m "description"
```

### Apply Migrations

```bash
# Upgrade to latest version
alembic upgrade head

# Upgrade one version
alembic upgrade +1

# Upgrade to specific revision
alembic upgrade <revision_id>
```

### Rollback Migrations

```bash
# Downgrade one version
alembic downgrade -1

# Downgrade to specific revision
alembic downgrade <revision_id>

# Downgrade to base (empty database)
alembic downgrade base
```

### View Migration History

```bash
# Show current version
alembic current

# Show migration history
alembic history

# Show migration history with verbose output
alembic history --verbose
```

## Migration Workflow

### 1. Making Schema Changes

1. Update SQLAlchemy models in `app/models/`
2. Generate migration:
   ```bash
   alembic revision --autogenerate -m "add column to users table"
   ```
3. Review the generated migration file in `alembic/versions/`
4. Edit if necessary (add data migrations, custom indexes, etc.)
5. Test the migration:
   ```bash
   alembic upgrade head
   ```
6. Test the rollback:
   ```bash
   alembic downgrade -1
   alembic upgrade head
   ```

### 2. Team Workflow

**When pulling new code:**
```bash
git pull origin develop
alembic upgrade head
```

**Before merging PR:**
- Ensure migration file is included
- Test migration locally
- Document any manual steps required

### 3. Production Deployment

**Pre-deployment checklist:**
- [ ] Migration tested locally
- [ ] Migration tested on staging
- [ ] Rollback plan documented
- [ ] Database backup created
- [ ] Downtime communicated (if needed)

**Deployment steps:**
```bash
# 1. Backup database
pg_dump -U postgres shopsoma_db > backup_$(date +%Y%m%d_%H%M%S).sql

# 2. Apply migrations
alembic upgrade head

# 3. Verify
alembic current
```

## Common Scenarios

### Adding a New Table

1. Create model in `app/models/`
2. Import model in `app/models/__init__.py`
3. Generate migration:
   ```bash
   alembic revision --autogenerate -m "add products table"
   ```

### Adding a Column

1. Add column to model
2. Generate migration:
   ```bash
   alembic revision --autogenerate -m "add status column to orders"
   ```
3. Review migration - add default value if needed:
   ```python
   op.add_column('orders', sa.Column('status', sa.String(20), nullable=False, server_default='pending'))
   ```

### Dropping a Column (Careful!)

1. Remove column from model
2. Generate migration:
   ```bash
   alembic revision --autogenerate -m "remove deprecated_column from users"
   ```
3. **Important:** Consider data migration before dropping:
   ```python
   # In upgrade()
   # First, migrate data if needed
   op.execute("UPDATE users SET new_column = deprecated_column")
   # Then drop
   op.drop_column('users', 'deprecated_column')

   # In downgrade()
   op.add_column('users', sa.Column('deprecated_column', sa.String()))
   ```

### Renaming a Column

```python
def upgrade():
    op.alter_column('users', 'old_name', new_column_name='new_name')

def downgrade():
    op.alter_column('users', 'new_name', new_column_name='old_name')
```

### Data Migration

```python
from alembic import op
import sqlalchemy as sa

def upgrade():
    # Add new column
    op.add_column('products', sa.Column('new_field', sa.String()))

    # Migrate data
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE products SET new_field = old_field || '_suffix'")
    )

    # Drop old column
    op.drop_column('products', 'old_field')

def downgrade():
    # Reverse process
    op.add_column('products', sa.Column('old_field', sa.String()))
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE products SET old_field = REPLACE(new_field, '_suffix', '')")
    )
    op.drop_column('products', 'new_field')
```

## Troubleshooting

### Migration Conflicts

If two developers create migrations simultaneously:

```bash
# Get both migration files
git pull origin develop

# Alembic will show "Multiple head revisions"
alembic heads

# Create a merge migration
alembic merge heads -m "merge migrations"

# Apply
alembic upgrade head
```

### Failed Migration

```bash
# Check current state
alembic current

# Mark migration as complete without running (use carefully!)
alembic stamp <revision_id>

# Or rollback and fix
alembic downgrade -1
# Fix the migration file
alembic upgrade head
```

### Database Out of Sync

```bash
# Generate SQL without applying
alembic upgrade head --sql > migration.sql

# Review and apply manually if needed
psql -U postgres -d shopsoma_db -f migration.sql
```

## Best Practices

1. **Always review auto-generated migrations** - Alembic might miss some changes
2. **Test migrations both ways** - Upgrade and downgrade
3. **Keep migrations small** - One logical change per migration
4. **Add comments** - Explain complex migrations
5. **Never edit applied migrations** - Create new ones instead
6. **Backup before production** - Always
7. **Use transactions** - Most DDL statements are atomic in PostgreSQL
8. **Consider downtime** - Large table alterations might lock tables

## Migration File Structure

```python
"""add user roles

Revision ID: abc123def456
Revises: previous_revision
Create Date: 2025-11-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'abc123def456'
down_revision = 'previous_revision'
branch_labels = None
depends_on = None

def upgrade():
    # Add your upgrade commands here
    pass

def downgrade():
    # Add your downgrade commands here
    pass
```

## Environment Variables

Alembic reads `DATABASE_URL` from `.env` file:

```env
# For migrations (synchronous)
DATABASE_URL=postgresql://postgres:password@localhost:5432/shopsoma_db

# For application (asynchronous)
# DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/shopsoma_db
```

Note: Alembic uses psycopg2 (synchronous), while FastAPI uses asyncpg (asynchronous).

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Run database migrations
  run: |
    alembic upgrade head
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

### Pre-commit Hook

Create `.git/hooks/pre-commit`:
```bash
#!/bin/bash
# Check for pending migrations
if [ -n "$(alembic check)" ]; then
    echo "Error: Pending model changes detected. Run 'alembic revision --autogenerate'"
    exit 1
fi
```

---

**For more information:**
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [Database Schema](./database_schema.md)
