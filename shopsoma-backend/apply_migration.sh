#!/bin/bash

# Complete migration script with proper error handling
# Run from shopsoma-backend directory

set -e  # Exit on any error

echo "=============================================="
echo "Shopsoma Settings Table Migration"
echo "=============================================="
echo ""

# Check we're in the right directory
if [ ! -f "alembic.ini" ]; then
    echo "❌ Error: alembic.ini not found!"
    echo "Please run this script from the shopsoma-backend directory"
    exit 1
fi

# Check .env file exists
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "Please create a .env file with DATABASE_URL"
    exit 1
fi

# Check DATABASE_URL is set in .env
if ! grep -q "DATABASE_URL" .env; then
    echo "❌ Error: DATABASE_URL not found in .env file!"
    echo "Please add DATABASE_URL to your .env file"
    exit 1
fi

echo "✓ Prerequisites checked"
echo ""

# Activate virtual environment
echo "1. Activating virtual environment..."
if [ ! -d "venv" ]; then
    echo "❌ Error: venv directory not found!"
    echo "Please create a virtual environment first: python3 -m venv venv"
    exit 1
fi

source venv/bin/activate
echo "✓ Virtual environment activated"
echo ""

# Check current migration state
echo "2. Checking current migration state..."
alembic current
echo ""

# Show pending migrations
echo "3. Checking for pending migrations..."
alembic history | head -5
echo ""

# Apply migrations
echo "4. Applying migrations..."
alembic upgrade head

if [ $? -eq 0 ]; then
    echo "✓ Migrations applied successfully!"
else
    echo "❌ Migration failed!"
    exit 1
fi
echo ""

# Verify settings table exists
echo "5. Verifying settings table..."
if command -v psql &> /dev/null; then
    echo "Running database verification..."

    # Extract database connection info from .env
    DB_URL=$(grep DATABASE_URL .env | cut -d '=' -f2- | tr -d '"' | tr -d "'")

    # Check if table exists
    if psql "$DB_URL" -c "\d settings" &> /dev/null; then
        echo "✓ Settings table exists"

        # Show table structure
        echo ""
        echo "Table structure:"
        psql "$DB_URL" -c "\d settings"

        # Show seed data
        echo ""
        echo "Seed data:"
        psql "$DB_URL" -c "SELECT key, value, description FROM settings;"
    else
        echo "⚠ Could not verify table (this might be OK if psql connection failed)"
    fi
else
    echo "⚠ psql not available - skipping database verification"
    echo "This is OK - the migration should still have succeeded"
fi

echo ""
echo "=============================================="
echo "✓ Migration Complete!"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Restart your backend server:"
echo "   uvicorn app.main:app --reload"
echo ""
echo "2. Test the API endpoint:"
echo "   curl http://localhost:8000/api/v1/settings/public/exchange-rate"
echo ""
echo "3. Test in frontend:"
echo "   Navigate to http://localhost:5173/admin/settings"
echo ""
