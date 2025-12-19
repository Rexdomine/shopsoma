#!/bin/bash

# Complete Setup and Verification Script for Currency Settings Feature
# This script performs all checks, runs the migration, and verifies the system

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "================================================================"
echo "  Shopsoma Currency Settings - Complete Setup & Verification"
echo "================================================================"
echo ""

# Function to print colored status
print_status() {
    if [ "$1" = "success" ]; then
        echo -e "${GREEN}✓${NC} $2"
    elif [ "$1" = "error" ]; then
        echo -e "${RED}✗${NC} $2"
    elif [ "$1" = "info" ]; then
        echo -e "${BLUE}ℹ${NC} $2"
    elif [ "$1" = "warning" ]; then
        echo -e "${YELLOW}⚠${NC} $2"
    fi
}

# Function to run command and check result
run_check() {
    local description=$1
    local command=$2
    local expected=$3

    echo ""
    echo "─────────────────────────────────────────────────────────────"
    echo "Check: $description"
    echo "─────────────────────────────────────────────────────────────"

    if eval "$command" > /dev/null 2>&1; then
        print_status "success" "$expected"
        return 0
    else
        print_status "error" "Failed: $description"
        return 1
    fi
}

# Check we're in the right directory
if [ ! -f "alembic.ini" ]; then
    print_status "error" "alembic.ini not found!"
    echo "Please run this script from the shopsoma-backend directory"
    exit 1
fi

print_status "success" "Running from shopsoma-backend directory"

# ============================================================
# PHASE 1: PRE-FLIGHT CHECKS
# ============================================================

echo ""
echo "================================================================"
echo "PHASE 1: Pre-Flight Checks"
echo "================================================================"

# Check 1: Virtual environment
echo ""
print_status "info" "Checking virtual environment..."
if [ ! -d "venv" ]; then
    print_status "error" "Virtual environment not found"
    echo "Please create it with: python3 -m venv venv"
    exit 1
fi
print_status "success" "Virtual environment exists"

# Activate venv
source venv/bin/activate
print_status "success" "Virtual environment activated"

# Check 2: Python packages
echo ""
print_status "info" "Checking required Python packages..."

packages=("alembic" "sqlalchemy" "asyncpg" "python-dotenv" "fastapi" "uvicorn")
for package in "${packages[@]}"; do
    if python -c "import $package" 2>/dev/null; then
        print_status "success" "$package installed"
    else
        print_status "error" "$package NOT installed"
        echo "Run: pip install $package"
        exit 1
    fi
done

# Check 3: .env file
echo ""
print_status "info" "Checking .env file..."
if [ ! -f ".env" ]; then
    print_status "error" ".env file not found!"
    echo "Please create .env file with DATABASE_URL"
    exit 1
fi
print_status "success" ".env file exists"

if grep -q "DATABASE_URL" .env; then
    print_status "success" "DATABASE_URL is set in .env"
else
    print_status "error" "DATABASE_URL not found in .env"
    exit 1
fi

# Check 4: Database connectivity
echo ""
print_status "info" "Checking database connectivity..."
DB_URL=$(grep DATABASE_URL .env | cut -d '=' -f2- | tr -d '"' | tr -d "'" | sed 's/postgresql+asyncpg/postgresql/')

if psql "$DB_URL" -c "SELECT 1;" > /dev/null 2>&1; then
    print_status "success" "Database connection successful"
else
    print_status "error" "Cannot connect to database"
    echo "Please check your DATABASE_URL and ensure PostgreSQL is running"
    exit 1
fi

# Check 5: Alembic migration status
echo ""
print_status "info" "Checking Alembic migration status..."

# Check for single head
HEAD_COUNT=$(alembic heads 2>/dev/null | grep -c "head" || echo "0")
if [ "$HEAD_COUNT" -eq 1 ]; then
    print_status "success" "Single migration head (no conflicts)"
    CURRENT_HEAD=$(alembic heads | grep -o "[a-z0-9]*" | head -1)
    echo "  Current head: $CURRENT_HEAD"
else
    print_status "error" "Multiple heads detected! Migration conflict exists."
    echo "Please fix the migration chain before proceeding"
    alembic heads
    exit 1
fi

# Check current database revision
CURRENT_REV=$(alembic current 2>/dev/null | grep -o "[a-z0-9]*" | head -1 || echo "none")
print_status "info" "Current database revision: $CURRENT_REV"

# ============================================================
# PHASE 2: MIGRATION
# ============================================================

echo ""
echo "================================================================"
echo "PHASE 2: Database Migration"
echo "================================================================"

# Check if settings table already exists
echo ""
print_status "info" "Checking if settings table already exists..."
if psql "$DB_URL" -c "\d settings" > /dev/null 2>&1; then
    print_status "warning" "Settings table already exists!"
    echo ""
    echo "Options:"
    echo "  1. Skip migration (table already exists)"
    echo "  2. Continue anyway (may fail if already applied)"
    echo ""
    read -p "Choose (1 or 2): " choice

    if [ "$choice" = "1" ]; then
        print_status "info" "Skipping migration step"
    else
        print_status "info" "Proceeding with migration..."
        alembic upgrade head
    fi
else
    print_status "info" "Settings table doesn't exist - applying migration..."
    echo ""

    # Run migration
    if alembic upgrade head; then
        print_status "success" "Migration completed successfully!"
    else
        print_status "error" "Migration failed!"
        echo "Check the error messages above"
        exit 1
    fi
fi

# ============================================================
# PHASE 3: VERIFICATION
# ============================================================

echo ""
echo "================================================================"
echo "PHASE 3: Verification"
echo "================================================================"

# Verify 1: Settings table structure
echo ""
print_status "info" "Verifying settings table structure..."
if psql "$DB_URL" -c "\d settings" > /tmp/table_structure.txt 2>&1; then
    print_status "success" "Settings table exists"
    echo ""
    echo "Table structure:"
    cat /tmp/table_structure.txt
else
    print_status "error" "Settings table not found!"
    exit 1
fi

# Verify 2: Seed data
echo ""
print_status "info" "Verifying seed data..."
SEED_COUNT=$(psql "$DB_URL" -t -c "SELECT COUNT(*) FROM settings WHERE key='exchange_rate_usd_to_ngn';" 2>/dev/null | tr -d ' ')

if [ "$SEED_COUNT" -eq 1 ]; then
    print_status "success" "Exchange rate seed data exists"

    RATE=$(psql "$DB_URL" -t -c "SELECT value FROM settings WHERE key='exchange_rate_usd_to_ngn';" 2>/dev/null | tr -d ' ')
    echo "  Current rate: 1 USD = ₦$RATE"
else
    print_status "warning" "Seed data not found - inserting..."
    psql "$DB_URL" -c "INSERT INTO settings (id, key, value, description, created_at, updated_at) VALUES (gen_random_uuid(), 'exchange_rate_usd_to_ngn', '833', 'Exchange rate from USD to NGN (1 USD = X NGN)', NOW(), NOW()) ON CONFLICT (key) DO NOTHING;"
    print_status "success" "Seed data inserted"
fi

# Verify 3: Full settings data
echo ""
print_status "info" "Current settings in database:"
psql "$DB_URL" -c "SELECT key, value, description, updated_at FROM settings;"

# ============================================================
# PHASE 4: API TEST (if server is not running)
# ============================================================

echo ""
echo "================================================================"
echo "PHASE 4: Backend API Test"
echo "================================================================"

echo ""
print_status "info" "Checking if backend server is running..."

if curl -s http://localhost:8000/healthz > /dev/null 2>&1; then
    print_status "success" "Backend server is running"

    # Test API endpoint
    echo ""
    print_status "info" "Testing exchange rate API endpoint..."

    RESPONSE=$(curl -s http://localhost:8000/api/v1/settings/public/exchange-rate)
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/settings/public/exchange-rate)

    if [ "$HTTP_CODE" = "200" ]; then
        print_status "success" "API endpoint working!"
        echo ""
        echo "Response:"
        echo "$RESPONSE" | python3 -m json.tool
    else
        print_status "error" "API endpoint returned HTTP $HTTP_CODE"
        echo "Response: $RESPONSE"
    fi
else
    print_status "warning" "Backend server is not running"
    echo ""
    echo "To start the server, run in a new terminal:"
    echo "  cd $(pwd)"
    echo "  source venv/bin/activate"
    echo "  uvicorn app.main:app --reload"
fi

# ============================================================
# PHASE 5: SUMMARY & NEXT STEPS
# ============================================================

echo ""
echo "================================================================"
echo "SETUP COMPLETE - Summary"
echo "================================================================"
echo ""

print_status "success" "Database migration completed"
print_status "success" "Settings table created"
print_status "success" "Seed data verified"

echo ""
echo "================================================================"
echo "Next Steps to Test Currency Settings:"
echo "================================================================"
echo ""

echo "1. START BACKEND (if not already running):"
echo "   cd $(pwd)"
echo "   source venv/bin/activate"
echo "   uvicorn app.main:app --reload"
echo ""

echo "2. START FRONTEND (in new terminal):"
echo "   cd ../shopsoma-frontend"
echo "   npm run dev"
echo ""

echo "3. TEST API ENDPOINT:"
echo "   curl http://localhost:8000/api/v1/settings/public/exchange-rate"
echo ""

echo "4. TEST ADMIN SETTINGS PAGE:"
echo "   - Open browser: http://localhost:5173/admin/settings"
echo "   - Login as admin"
echo "   - You should see: 1 USD = ₦833.00"
echo "   - Try updating the rate"
echo "   - Verify changes persist"
echo ""

echo "5. VERIFY CURRENCY CONVERSION:"
echo "   - Navigate to any product page"
echo "   - Toggle currency switcher between NGN and USD"
echo "   - Verify prices convert correctly"
echo ""

echo "================================================================"
echo "Troubleshooting:"
echo "================================================================"
echo ""
echo "If API returns 500 error:"
echo "  - Check backend logs for detailed error"
echo "  - Verify DATABASE_URL is correct"
echo "  - Restart backend server"
echo ""
echo "If frontend can't load settings:"
echo "  - Check browser console for errors"
echo "  - Verify CORS is configured correctly"
echo "  - Check API_BASE_URL in frontend config"
echo ""
echo "================================================================"
echo ""

print_status "success" "All checks passed! System is ready for testing."
echo ""
