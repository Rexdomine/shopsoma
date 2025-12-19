# Environment Variable Loading Fix for Alembic

## Problem

**Error**:
```
RuntimeError: DATABASE_URL environment variable is not set.
Please set it in your Render environment or .env file.
```

**When**: Running `alembic upgrade head`

## Root Cause

The `alembic/env.py` file was trying to read `DATABASE_URL` from environment variables, but it wasn't loading the `.env` file first.

**Why this happened**:
- FastAPI's `main.py` loads `.env` using `load_dotenv()`
- Alembic runs separately and has its own `env.py` file
- The `env.py` file wasn't loading `.env`, so `DATABASE_URL` was undefined

## Solution

Added `python-dotenv` loading to `alembic/env.py`:

### Change Made

**File**: `shopsoma-backend/alembic/env.py`

**Lines 18-20** (added):
```python
# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()
```

This ensures Alembic loads environment variables from `.env` before trying to access `DATABASE_URL`.

## Why This Fix Works

### Before (Broken)
```python
# alembic/env.py
import os
from alembic import context

# ... other imports ...

# This fails because .env was never loaded!
app_db_url = os.environ.get("DATABASE_URL")  # ❌ Returns None
```

### After (Fixed)
```python
# alembic/env.py
import os
from dotenv import load_dotenv
from alembic import context

# Load .env file first
load_dotenv()  # ✅ Now environment variables are available

# ... other imports ...

# This now works!
app_db_url = os.environ.get("DATABASE_URL")  # ✅ Returns actual value
```

## How to Apply the Migration Now

### Method 1: Using the Script (Recommended)

```bash
cd /Users/rex/Documents/Shopsoma/shopsoma-backend
./apply_migration.sh
```

The script will:
- ✅ Check prerequisites (.env file, DATABASE_URL, venv)
- ✅ Activate virtual environment
- ✅ Show current migration state
- ✅ Apply pending migrations
- ✅ Verify settings table was created
- ✅ Show next steps

### Method 2: Manual Commands

```bash
cd /Users/rex/Documents/Shopsoma/shopsoma-backend
source venv/bin/activate
alembic upgrade head
```

## Verification

### 1. Check Migration Succeeded

```bash
alembic current
```

**Expected Output**:
```
h4i5j6k7l8m9 (head)
```

### 2. Check Settings Table Exists

```bash
psql -U shopsoma -d shopsoma_db -c "\d settings"
```

**Expected**: Shows table structure with columns: id, key, value, description, created_at, updated_at

### 3. Check Seed Data

```bash
psql -U shopsoma -d shopsoma_db -c "SELECT * FROM settings;"
```

**Expected**: Shows one row with `exchange_rate_usd_to_ngn = 833`

### 4. Test API Endpoint

```bash
# Start server
cd /Users/rex/Documents/Shopsoma/shopsoma-backend
source venv/bin/activate
uvicorn app.main:app --reload

# In new terminal, test endpoint
curl http://localhost:8000/api/v1/settings/public/exchange-rate
```

**Expected Response**:
```json
{
  "rate": 833.0,
  "updated_at": "2025-12-12T..."
}
```
**Status**: `200 OK` ✅

### 5. Test Frontend

1. Navigate to `http://localhost:5173/admin/settings`
2. Login as admin
3. Should see current exchange rate without errors

## What Gets Created

### Settings Table Schema

```sql
CREATE TABLE settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(255) NOT NULL UNIQUE,
    value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE UNIQUE INDEX ix_settings_key ON settings(key);
```

### Initial Data

```sql
INSERT INTO settings (key, value, description)
VALUES (
    'exchange_rate_usd_to_ngn',
    '833',
    'Exchange rate from USD to NGN (1 USD = X NGN)'
);
```

## Troubleshooting

### Error: "No module named 'dotenv'"

**Cause**: `python-dotenv` package not installed in virtual environment.

**Solution**:
```bash
source venv/bin/activate
pip install python-dotenv
```

### Error: ".env file not found"

**Cause**: Missing `.env` file or running from wrong directory.

**Solution**:
```bash
# Make sure you're in the backend directory
cd /Users/rex/Documents/Shopsoma/shopsoma-backend

# Check .env exists
ls -la .env

# If missing, create it with DATABASE_URL
cp .env.example .env
# Then edit .env and set DATABASE_URL
```

### Error: "Can't locate revision 'g3h4i5j6k7l8'"

**Cause**: Previous migrations haven't been applied.

**Solution**:
```bash
# Apply all pending migrations
alembic upgrade head
```

### Error: Still getting "relation does not exist" after migration

**Solutions**:

1. **Verify migration was applied**:
   ```bash
   alembic current
   ```
   Should show `h4i5j6k7l8m9 (head)`

2. **Check correct database**:
   ```bash
   # In .env file, verify DATABASE_URL points to correct database
   grep DATABASE_URL .env
   ```

3. **Restart backend server**:
   ```bash
   # Stop server (Ctrl+C)
   # Clear any cached connections
   uvicorn app.main:app --reload
   ```

4. **Verify table in correct database**:
   ```bash
   psql -U shopsoma -d shopsoma_db -c "\dt settings"
   ```

## Why load_dotenv() Is Safe

### Security Considerations

1. **Development Only**: `.env` files are for local development
2. **Production**: Uses actual environment variables (Render, Heroku, etc.)
3. **Gitignored**: `.env` is in `.gitignore` (never committed)
4. **No Override**: `load_dotenv()` doesn't override existing environment variables
5. **Standard Practice**: Widely used in Python projects

### How It Works

```python
from dotenv import load_dotenv

# Load .env file if it exists
# If DATABASE_URL already exists in environment, it won't be overridden
load_dotenv()

# Now you can access variables from .env
db_url = os.environ.get("DATABASE_URL")
```

## Related Files

**Modified**:
- `alembic/env.py` - Added `load_dotenv()` import and call

**Created**:
- `apply_migration.sh` - Complete migration script with verification
- `ENV_FILE_LOADING_FIX.md` - This documentation

**Existing** (unchanged):
- `alembic/versions/h4i5j6k7l8m9_create_settings_table.py` - Migration file
- `.env` - Environment variables (must exist)
- `requirements.txt` - Should already have `python-dotenv`

## Complete Test Flow

```bash
# 1. Navigate to backend
cd /Users/rex/Documents/Shopsoma/shopsoma-backend

# 2. Activate venv
source venv/bin/activate

# 3. Verify python-dotenv is installed
pip list | grep python-dotenv

# 4. Apply migration
alembic upgrade head

# 5. Verify table
psql -U shopsoma -d shopsoma_db -c "SELECT COUNT(*) FROM settings;"

# 6. Start server
uvicorn app.main:app --reload

# 7. Test API (in new terminal)
curl http://localhost:8000/api/v1/settings/public/exchange-rate

# 8. Test frontend
# Open browser: http://localhost:5173/admin/settings
```

## Summary of Fixes

1. ✅ **Import Error Fix**: Added `require_admin` alias in dependencies.py
2. ✅ **Environment Loading Fix**: Added `load_dotenv()` to alembic/env.py
3. ⏭️ **Next**: Apply migration to create settings table

## Expected Timeline

- **Fix Applied**: ~30 seconds (edit alembic/env.py)
- **Migration Run**: ~5 seconds (alembic upgrade head)
- **Verification**: ~2 minutes (check table, test API, test frontend)
- **Total**: ~3 minutes from fix to working system

## Implementation Date
December 12, 2025

## Related Documentation
- [Database Migration Required](./DATABASE_MIGRATION_REQUIRED.md) - Why migration is needed
- [Admin Exchange Rate Settings](./ADMIN_EXCHANGE_RATE_SETTINGS.md) - Full feature docs
- [Import Error Fix](./IMPORT_ERROR_FIX.md) - Previous fix
