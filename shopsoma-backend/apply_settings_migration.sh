#!/bin/bash

# Script to apply settings table migration
# Run this from the shopsoma-backend directory

set -e  # Exit on error

echo "=============================================="
echo "Applying Settings Table Migration"
echo "=============================================="
echo ""

# Activate virtual environment
echo "1. Activating virtual environment..."
source venv/bin/activate

# Check current migration state
echo ""
echo "2. Checking current migration state..."
alembic current

# Apply migrations
echo ""
echo "3. Applying pending migrations..."
alembic upgrade head

# Verify settings table was created
echo ""
echo "4. Verifying settings table exists..."
psql -U shopsoma -d shopsoma_db -c "\d settings" || {
    echo "ERROR: Settings table not found!"
    exit 1
}

# Check seed data
echo ""
echo "5. Checking seed data..."
psql -U shopsoma -d shopsoma_db -c "SELECT key, value, description FROM settings;" || {
    echo "ERROR: Could not query settings table!"
    exit 1
}

echo ""
echo "=============================================="
echo "✓ Migration applied successfully!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Restart your backend server: uvicorn app.main:app --reload"
echo "2. Test the API: curl http://localhost:8000/api/v1/settings/public/exchange-rate"
echo "3. Test frontend: Navigate to /admin/settings"
