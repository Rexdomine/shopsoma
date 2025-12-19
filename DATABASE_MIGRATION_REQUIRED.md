# Database Migration Required: Settings Table

## Problem

**Error**: `relation "settings" does not exist`
**Status**: 500 Internal Server Error
**Endpoint**: `GET /api/v1/settings/public/exchange-rate`

## Root Cause

The settings table migration was created but not applied to your database. The application is trying to query a table that doesn't exist yet.

## Solution: Apply the Migration

### Option 1: Using the Migration Script (Recommended)

```bash
cd /Users/rex/Documents/Shopsoma/shopsoma-backend
python3 run_migration.py
```

This script will:
1. Check current migration state
2. Apply all pending migrations
3. Verify the settings table was created
4. Show next steps

### Option 2: Manual Migration (If Script Fails)

```bash
cd /Users/rex/Documents/Shopsoma/shopsoma-backend

# Activate virtual environment
source venv/bin/activate

# Check current migration
alembic current

# Apply migration
alembic upgrade head

# Verify table exists
psql -U shopsoma -d shopsoma_db -c "\d settings"
```

### Option 3: Using Shell Script

```bash
cd /Users/rex/Documents/Shopsoma/shopsoma-backend
./apply_settings_migration.sh
```

## What the Migration Creates

### Table: `settings`

```sql
CREATE TABLE settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key VARCHAR(255) NOT NULL UNIQUE,
    value TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX ix_settings_key ON settings(key);
```

### Initial Seed Data

```sql
INSERT INTO settings (id, key, value, description)
VALUES (
    gen_random_uuid(),
    'exchange_rate_usd_to_ngn',
    '833',
    'Exchange rate from USD to NGN (1 USD = X NGN)'
);
```

## Verification Steps

### 1. Check Table Exists

```bash
psql -U shopsoma -d shopsoma_db -c "\d settings"
```

**Expected Output**:
```
                          Table "public.settings"
   Column    |           Type           | Collation | Nullable | Default
-------------+--------------------------+-----------+----------+---------
 id          | uuid                     |           | not null |
 key         | character varying(255)   |           | not null |
 value       | text                     |           | not null |
 description | text                     |           |          |
 created_at  | timestamp with time zone |           | not null | now()
 updated_at  | timestamp with time zone |           | not null | now()
Indexes:
    "settings_pkey" PRIMARY KEY, btree (id)
    "ix_settings_key" UNIQUE, btree (key)
```

### 2. Check Seed Data

```bash
psql -U shopsoma -d shopsoma_db -c "SELECT * FROM settings;"
```

**Expected Output**:
```
                  id                  |           key           | value |              description
--------------------------------------+-------------------------+-------+---------------------------------------
 <uuid>                               | exchange_rate_usd_to_ngn| 833   | Exchange rate from USD to NGN (...)
```

### 3. Test API Endpoint

**Restart Backend** (if running):
```bash
cd /Users/rex/Documents/Shopsoma/shopsoma-backend
source venv/bin/activate
uvicorn app.main:app --reload
```

**Test Public Endpoint**:
```bash
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

### 4. Test Frontend

1. Navigate to: `http://localhost:5173/admin/settings`
2. Login as admin
3. Verify page loads without "Failed to load settings" error
4. Should see current exchange rate: **1 USD = ₦833.00**

## Migration File Details

**File**: `shopsoma-backend/alembic/versions/h4i5j6k7l8m9_create_settings_table.py`
**Revision**: `h4i5j6k7l8m9`
**Previous Revision**: `g3h4i5j6k7l8` (add_store_status_fields)
**Created**: December 12, 2025

## Troubleshooting

### Error: "Can't locate revision identified by 'g3h4i5j6k7l8'"

**Cause**: Previous migration is missing or hasn't been applied.

**Solution**:
```bash
# Check migration history
alembic history

# Apply all migrations from the beginning
alembic upgrade head
```

### Error: "duplicate key value violates unique constraint"

**Cause**: Settings table already exists with data.

**Solution**: Table already exists - no action needed! The error you saw was querying, not creating.

### Error: "relation 'settings' does not exist" persists after migration

**Solutions**:
1. **Verify migration was actually applied**:
   ```bash
   alembic current
   ```
   Should show: `h4i5j6k7l8m9 (head)`

2. **Check you're connected to the right database**:
   ```bash
   psql -U shopsoma -d shopsoma_db -c "SELECT current_database();"
   ```

3. **Restart backend server** (it may be caching connections):
   ```bash
   # Stop server (Ctrl+C)
   # Then restart
   uvicorn app.main:app --reload
   ```

### Error: "cannot import name 'Setting' from 'app.models'"

**Cause**: Python is caching old imports.

**Solution**:
```bash
# Restart server to clear import cache
# Or if using reload, save a file to trigger reload
```

## Post-Migration Checklist

- [ ] Migration applied successfully (`alembic upgrade head`)
- [ ] Settings table exists in database
- [ ] Seed data present (exchange_rate_usd_to_ngn = 833)
- [ ] Backend server restarted
- [ ] GET `/api/v1/settings/public/exchange-rate` returns 200 OK
- [ ] Frontend can fetch exchange rate on app load
- [ ] Admin settings page loads without errors
- [ ] Can view current exchange rate in admin settings
- [ ] Can update exchange rate (admin only)

## Expected Behavior After Fix

### Backend
- ✅ Server starts without errors
- ✅ Public exchange rate endpoint returns 200 OK
- ✅ Exchange rate value: 833 NGN per USD
- ✅ Admin endpoints protected (require admin auth)

### Frontend
- ✅ App loads and fetches exchange rate on initialization
- ✅ Currency conversions use fetched rate
- ✅ Admin settings page loads successfully
- ✅ Current rate displayed: **1 USD = ₦833.00**
- ✅ Admin can update rate
- ✅ Changes reflect immediately across platform

## Migration Timeline

1. ✅ Migration file created (h4i5j6k7l8m9_create_settings_table.py)
2. ⏳ **YOU ARE HERE** - Need to apply migration
3. ⏭️ Restart backend server
4. ⏭️ Test API endpoints
5. ⏭️ Test frontend functionality

## Quick Commands Reference

```bash
# Navigate to backend
cd /Users/rex/Documents/Shopsoma/shopsoma-backend

# Activate venv
source venv/bin/activate

# Apply migration
alembic upgrade head

# Verify
psql -U shopsoma -d shopsoma_db -c "SELECT * FROM settings;"

# Restart server
uvicorn app.main:app --reload

# Test API (in new terminal)
curl http://localhost:8000/api/v1/settings/public/exchange-rate
```

## Related Documentation

- [Admin Exchange Rate Settings](./ADMIN_EXCHANGE_RATE_SETTINGS.md) - Full feature documentation
- [Import Error Fix](./IMPORT_ERROR_FIX.md) - Previous fix for require_admin dependency

## Support

If you continue to see errors after following these steps:

1. Check the migration was applied:
   ```bash
   alembic current
   ```

2. Check the table exists:
   ```bash
   psql -U shopsoma -d shopsoma_db -c "\d settings"
   ```

3. Check server logs for any other errors

4. Verify you're using the correct database connection string in `.env`

## Implementation Date
December 12, 2025
