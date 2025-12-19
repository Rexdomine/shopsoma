#!/bin/bash
# Database Verification Script for Shopsoma

echo "🔍 Verifying Shopsoma Database Setup..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "❌ Virtual environment not found. Run: python3 -m venv venv"
    exit 1
fi

# Activate virtual environment
source venv/bin/activate

echo "1️⃣  Checking Alembic Migration Status..."
alembic current
echo ""

echo "2️⃣  Listing All Database Tables..."
docker exec orula-postgres psql -U postgres -d shopsoma_db -c "\dt"
echo ""

echo "3️⃣  Counting Total Tables..."
docker exec orula-postgres psql -U postgres -d shopsoma_db -c "SELECT COUNT(*) as total_tables FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';"
echo ""

echo "4️⃣  Checking Users Table Structure..."
docker exec orula-postgres psql -U postgres -d shopsoma_db -c "\d users" | head -20
echo ""

echo "5️⃣  Checking Products Table Structure..."
docker exec orula-postgres psql -U postgres -d shopsoma_db -c "\d products" | head -25
echo ""

echo "6️⃣  Verifying Foreign Key Relationships..."
docker exec orula-postgres psql -U postgres -d shopsoma_db -c "SELECT COUNT(*) as total_foreign_keys FROM information_schema.table_constraints WHERE constraint_type = 'FOREIGN KEY' AND table_schema = 'public';"
echo ""

echo "7️⃣  Checking Indexes..."
docker exec orula-postgres psql -U postgres -d shopsoma_db -c "SELECT COUNT(*) as total_indexes FROM pg_indexes WHERE schemaname = 'public';"
echo ""

echo "8️⃣  Migration History..."
alembic history
echo ""

echo "✅ Database verification complete!"
echo ""
echo "📊 Summary:"
echo "  - Migration: 3a9bcaf3fd5f (initial database schema)"
echo "  - Expected Tables: 15 (14 core + alembic_version)"
echo "  - Expected Foreign Keys: 20+"
echo "  - Expected Indexes: 30+"
echo ""
echo "📚 Documentation:"
echo "  - Schema: docs/database_schema.md"
echo "  - Migrations: docs/database_migrations.md"
echo "  - Setup: POSTGRESQL_SETUP.md"
