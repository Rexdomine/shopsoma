# Migration Branch Conflict Fix

## Problem

**Error**:
```
Multiple head revisions are present for given argument 'head';
please specify a specific target revision
```

**When**: Running `alembic upgrade head`

## Root Cause

The migration history had **two separate branches** (multiple heads) stemming from the same parent revision `g3h4i5j6k7l8`:

### Migration Chain Before Fix

```
Initial migrations...
    ↓
f2g3h4i5j6k7 (add_logo_to_vendors)
    ↓
g3h4i5j6k7l8 (add_store_status_fields) ← BRANCH POINT
    ↓                                  ↓
    ├─→ 9965ca7f294b                  ├─→ h4i5j6k7l8m9 (settings table)
    │   (add_variations)              │   ← HEAD 2 (CONFLICTING)
    │        ↓                         │
    └─→ 94cb1a1d069d                  └─→ (Nothing)
        (collections)
        ← HEAD 1 (ACTUAL LATEST)
```

**The Problem**:
- The settings migration (`h4i5j6k7l8m9`) pointed to `g3h4i5j6k7l8` as its parent
- But `9965ca7f294b` also pointed to `g3h4i5j6k7l8` as its parent
- This created two separate "heads" (latest migrations)
- Alembic couldn't determine which one to use as "head"

## Solution

Updated the settings migration to point to the actual latest migration (`94cb1a1d069d`) instead of the branching point.

### Migration Chain After Fix

```
Initial migrations...
    ↓
f2g3h4i5j6k7 (add_logo_to_vendors)
    ↓
g3h4i5j6k7l8 (add_store_status_fields)
    ↓
9965ca7f294b (add_variations)
    ↓
94cb1a1d069d (collections)
    ↓
h4i5j6k7l8m9 (settings table) ← SINGLE HEAD ✅
```

## Change Made

**File**: `alembic/versions/h4i5j6k7l8m9_create_settings_table.py`

**Line 4 & 15**: Changed `down_revision`

### Before (Broken)
```python
Revises: g3h4i5j6k7l8
...
down_revision = 'g3h4i5j6k7l8'  # ❌ Creates branch conflict
```

### After (Fixed)
```python
Revises: 94cb1a1d069d
...
down_revision = '94cb1a1d069d'  # ✅ Points to actual latest
```

## How to Apply the Migration Now

### Method 1: Standard Command

```bash
cd /Users/rex/Documents/Shopsoma/shopsoma-backend
source venv/bin/activate
alembic upgrade head
```

### Method 2: Using Script

```bash
cd /Users/rex/Documents/Shopsoma/shopsoma-backend
./apply_migration.sh
```

## Verification

### 1. Check There's Only One Head

```bash
alembic heads
```

**Expected Output** (should show only ONE head):
```
h4i5j6k7l8m9 (head)
```

**NOT** (multiple heads):
```
h4i5j6k7l8m9 (head)
94cb1a1d069d (head)  ← This would indicate still broken
```

### 2. Check Migration History

```bash
alembic history | head -20
```

**Expected**: Should show a single linear path from initial migration to `h4i5j6k7l8m9`

### 3. Apply Migration

```bash
alembic upgrade head
```

**Expected Output**:
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 94cb1a1d069d -> h4i5j6k7l8m9, create_settings_table
```

### 4. Verify Settings Table

```bash
psql -U shopsoma -d shopsoma_db -c "\d settings"
```

**Expected**: Shows table structure

```bash
psql -U shopsoma -d shopsoma_db -c "SELECT * FROM settings;"
```

**Expected**: Shows exchange_rate_usd_to_ngn = 833

### 5. Test API

```bash
curl http://localhost:8000/api/v1/settings/public/exchange-rate
```

**Expected**: `{"rate": 833.0, "updated_at": "..."}`

## Why This Happened

When I created the settings migration, I looked at the recent migrations and saw `g3h4i5j6k7l8` as a recent one, so I set it as the parent. However:

1. After `g3h4i5j6k7l8` was created, two more migrations were added:
   - `9965ca7f294b` (variations) on Dec 6
   - `94cb1a1d069d` (collections) on Dec 7

2. I created the settings migration on Dec 12 but didn't check what the actual latest migration was

3. This created a branch in the migration history

## Understanding Alembic Revisions

### Revision Chain Basics

```python
# Migration A
revision = 'aaa'
down_revision = None  # First migration

# Migration B
revision = 'bbb'
down_revision = 'aaa'  # Depends on A

# Migration C
revision = 'ccc'
down_revision = 'bbb'  # Depends on B
```

### Creating a Branch (Bad)

```python
# Migration D - WRONG!
revision = 'ddd'
down_revision = 'bbb'  # Also depends on B!
# Now both C and D claim B as parent → BRANCH!
```

### Correct Linear Chain

```python
# Migration D - CORRECT
revision = 'ddd'
down_revision = 'ccc'  # Depends on C (the latest)
```

## How to Avoid This in Future

### 1. Always Check Current Head Before Creating Migration

```bash
# Check what the current head is
alembic heads

# Output shows the latest revision
94cb1a1d069d (head)
```

### 2. Use Alembic's Auto-Generation

```bash
# This automatically sets down_revision to current head
alembic revision -m "create_settings_table"
```

### 3. Check History Before Manual Migration

```bash
# See the full chain
alembic history

# See just recent ones
alembic history | head -10
```

## Troubleshooting

### Still Getting "Multiple heads" Error

**Check heads**:
```bash
alembic heads
```

If you see multiple, you may have other conflicting migrations.

**Solution**: Identify the actual latest migration and update all conflicting ones to point to it.

### "Can't locate revision '94cb1a1d069d'"

**Cause**: The collections migration file is missing or corrupt.

**Solution**: Ensure `94cb1a1d069d_create_collections_table.py` exists in `alembic/versions/`

### Migration Applied But Table Doesn't Exist

**Causes**:
1. Wrong database connection
2. Migration partially failed
3. Rolled back due to error

**Solutions**:
1. Check `DATABASE_URL` in `.env`
2. Check migration logs for errors
3. Try running again with `--sql` to see what SQL would execute:
   ```bash
   alembic upgrade head --sql
   ```

## Migration Timeline

```
Dec 5:  f2g3h4i5j6k7 (add_logo_to_vendors)
        g3h4i5j6k7l8 (add_store_status_fields)

Dec 6:  9965ca7f294b (add_variations_and_size_stocks)
        ↑ Points to g3h4i5j6k7l8

Dec 7:  94cb1a1d069d (create_collections_table)
        ↑ Points to 9965ca7f294b

Dec 12: h4i5j6k7l8m9 (create_settings_table)
        ↑ Initially pointed to g3h4i5j6k7l8 (WRONG - created branch)
        ↑ Fixed to point to 94cb1a1d069d (CORRECT - linear chain)
```

## Complete Test Sequence

```bash
# 1. Navigate and activate venv
cd /Users/rex/Documents/Shopsoma/shopsoma-backend
source venv/bin/activate

# 2. Verify single head (should show h4i5j6k7l8m9 only)
alembic heads

# 3. Check current database state
alembic current

# 4. Apply migration
alembic upgrade head

# 5. Verify settings table exists
psql -U shopsoma -d shopsoma_db -c "SELECT COUNT(*) FROM settings;"

# 6. Start backend
uvicorn app.main:app --reload

# 7. Test API (in new terminal)
curl http://localhost:8000/api/v1/settings/public/exchange-rate

# 8. Test frontend
# Open browser: http://localhost:5173/admin/settings
```

## Summary of All Fixes

### Today's Issues and Solutions

1. ✅ **Import Error**: Added `require_admin` alias in dependencies.py
2. ✅ **Environment Loading**: Added `load_dotenv()` to alembic/env.py
3. ✅ **Branch Conflict**: Updated settings migration down_revision to '94cb1a1d069d'
4. ⏭️ **Next**: Apply migration to create settings table

### Files Modified

1. `app/api/dependencies.py` - Added require_admin alias (line 137)
2. `alembic/env.py` - Added load_dotenv() call (lines 18-20)
3. `alembic/versions/h4i5j6k7l8m9_create_settings_table.py` - Fixed down_revision (lines 4, 15)

## Implementation Date
December 12, 2025

## Related Documentation
- [Import Error Fix](./IMPORT_ERROR_FIX.md)
- [Environment Loading Fix](./ENV_FILE_LOADING_FIX.md)
- [Database Migration Required](./DATABASE_MIGRATION_REQUIRED.md)
- [Admin Exchange Rate Settings](./ADMIN_EXCHANGE_RATE_SETTINGS.md)
