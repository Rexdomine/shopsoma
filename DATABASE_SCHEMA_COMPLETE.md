# Database Schema & Migrations Complete ✅

**Date:** November 11, 2025
**Status:** Schema Designed, Models Created, Alembic Configured

---

## What Has Been Completed

### 1. Comprehensive Database Schema ✅

Created a complete Entity Relationship Diagram (ERD) with **14 core tables**:

1. **users** - Customer, vendor, and admin accounts
2. **vendors** - Vendor-specific information and KYC
3. **categories** - Product categories (hierarchical)
4. **products** - Core product information
5. **product_variants** - Size/color variations
6. **product_images** - Product photos with ordering
7. **addresses** - Customer shipping/billing addresses
8. **orders** - Customer orders
9. **order_items** - Individual items in orders
10. **payments** - Payment transactions (Stripe/Paystack)
11. **payouts** - Vendor payout tracking
12. **reviews** - Product reviews and ratings
13. **returns** - Product returns/RMA workflow
14. **audit_logs** - System audit trail

**Documentation:** [docs/database_schema.md](docs/database_schema.md)

---

### 2. SQLAlchemy Models ✅

Created complete async SQLAlchemy 2.0 models for all entities:

**Core Models:**
- `app/models/user.py` - User model with roles (customer/vendor/admin)
- `app/models/vendor.py` - Vendor model with KYC workflow
- `app/models/category.py` - Category model with hierarchical support
- `app/models/product.py` - Product, ProductVariant, ProductImage models
- `app/models/address.py` - Address model for shipping/billing
- `app/models/order.py` - Order and OrderItem models
- `app/models/payment.py` - Payment and Payout models
- `app/models/review.py` - Review model with ratings
- `app/models/returns.py` - Return/RMA model
- `app/models/audit_log.py` - Audit log model

**Features Implemented:**
- UUID primary keys for all tables
- Enum types for status fields
- Proper foreign key relationships
- Cascade delete rules
- Indexes on frequently queried columns
- Timestamps (created_at, updated_at)
- JSONB fields for flexible data
- Check constraints for data validation

---

### 3. Alembic Configuration ✅

**Files Created:**
- `alembic/` - Migration directory structure
- `alembic.ini` - Alembic configuration
- `alembic/env.py` - Environment configuration
- `app/core/database.py` - Database session management
- `app/core/config.py` - Application settings

**Configuration:**
- Automatic model import
- Settings from environment variables
- Support for both sync (migrations) and async (application) drivers
- Proper isolation between environments

---

### 4. Documentation ✅

Created comprehensive documentation:

1. **[database_schema.md](docs/database_schema.md)**
   - Complete ERD with relationships
   - Table definitions with all columns
   - Indexes and constraints
   - Data integrity rules
   - Performance considerations

2. **[database_migrations.md](docs/database_migrations.md)**
   - Migration workflow
   - Common scenarios and examples
   - Troubleshooting guide
   - Best practices
   - CI/CD integration examples

---

## Database Schema Highlights

### Key Relationships

```
User (1) ─── (1) Vendor
Vendor (1) ─── (N) Products
Product (1) ─── (N) ProductVariants
Product (1) ─── (N) ProductImages
User (1) ─── (N) Orders
Order (1) ─── (N) OrderItems
Order (1) ─── (N) Payments
Vendor (1) ─── (N) Payouts
Product (1) ─── (N) Reviews
Order (1) ─── (N) Returns
```

### Status Management

**Products:**
- `status`: draft, active, inactive, archived
- `moderation_status`: pending, approved, rejected

**Orders:**
- `payment_status`: pending, paid, failed, refunded
- `fulfillment_status`: pending, processing, shipped, delivered, cancelled

**Vendors:**
- `kyc_status`: pending, submitted, approved, rejected
- `approved`: boolean flag

**Payments:**
- `status`: pending, processing, completed, failed, refunded

**Payouts:**
- `status`: pending, processing, completed, failed

**Returns:**
- `status`: requested, approved, rejected, received, refunded

---

## Next Steps

### Immediate Actions

**1. Create PostgreSQL Database**

```bash
# Method 1: Using createdb
createdb shopsoma_db

# Method 2: Using psql
psql -U postgres
CREATE DATABASE shopsoma_db;
\q
```

**2. Generate Initial Migration**

```bash
cd shopsoma-backend
source venv/bin/activate
alembic revision --autogenerate -m "initial database schema"
```

**3. Apply Migration**

```bash
alembic upgrade head
```

**4. Verify Migration**

```bash
# Check current version
alembic current

# View tables
psql -U postgres -d shopsoma_db
\dt
\q
```

---

## File Structure

```
shopsoma-backend/
├── alembic/
│   ├── versions/           # Migration files (will be generated)
│   ├── env.py              # Environment configuration
│   ├── script.py.mako      # Migration template
│   └── README              # Alembic readme
├── app/
│   ├── core/
│   │   ├── config.py       # Application settings
│   │   ├── database.py     # Database session management
│   │   └── __init__.py
│   ├── models/
│   │   ├── __init__.py     # Model exports
│   │   ├── user.py         # User model
│   │   ├── vendor.py       # Vendor model
│   │   ├── category.py     # Category model
│   │   ├── product.py      # Product models
│   │   ├── address.py      # Address model
│   │   ├── order.py        # Order models
│   │   ├── payment.py      # Payment & Payout models
│   │   ├── review.py       # Review model
│   │   ├── returns.py      # Return model
│   │   └── audit_log.py    # Audit log model
│   └── main.py             # FastAPI application
├── alembic.ini             # Alembic configuration
├── requirements.txt        # Python dependencies (updated)
└── .env                    # Environment variables (created)
```

---

## Environment Configuration

### Development (.env)

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/shopsoma_db
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=dev-secret-key-change-in-production
ALGORITHM=HS256
ENVIRONMENT=development
DEBUG=true
```

### Production

```env
DATABASE_URL=postgresql://user:pass@host:5432/shopsoma_db
REDIS_URL=redis://host:6379/0
SECRET_KEY=<strong-random-key>
ALGORITHM=HS256
ENVIRONMENT=production
DEBUG=false
```

---

## Migration Workflow

### Creating Migrations

```bash
# 1. Modify models in app/models/
# 2. Generate migration
alembic revision --autogenerate -m "description"

# 3. Review migration file in alembic/versions/
# 4. Test upgrade
alembic upgrade head

# 5. Test downgrade
alembic downgrade -1

# 6. Re-upgrade
alembic upgrade head
```

### Team Workflow

```bash
# When pulling new code
git pull origin develop
alembic upgrade head

# When creating new features
git checkout -b feature/add-wishlist
# ... modify models ...
alembic revision --autogenerate -m "add wishlist table"
# ... commit migration file ...
git add alembic/versions/*.py
git commit -m "feat: add wishlist functionality"
```

---

## Database Features

### Performance Optimizations

1. **Indexes:**
   - Foreign keys
   - Status columns
   - Frequently filtered columns
   - Timestamp columns for date ranges

2. **Relationships:**
   - Lazy loading by default
   - Eager loading options available
   - Proper cascade rules

3. **Data Integrity:**
   - Foreign key constraints
   - Check constraints (e.g., rating 1-5)
   - Unique constraints
   - NOT NULL constraints

### Scalability Considerations

1. **Partitioning (Future):**
   - Orders table by date
   - Audit logs by date

2. **Caching Strategy:**
   - Product listings (Redis, 5 min TTL)
   - Category tree (Redis, 1 hour TTL)
   - Vendor stats (Redis, 15 min TTL)

3. **Read Replicas:**
   - Product catalog queries
   - Analytics queries
   - Reporting queries

---

## Testing the Schema

### 1. Verify All Tables Created

```sql
\dt

Expected tables:
- users
- vendors
- categories
- products
- product_variants
- product_images
- addresses
- orders
- order_items
- payments
- payouts
- reviews
- returns
- audit_logs
- alembic_version
```

### 2. Verify Foreign Keys

```sql
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name AS foreign_table_name,
    ccu.column_name AS foreign_column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage AS ccu
  ON ccu.constraint_name = tc.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY';
```

### 3. Verify Indexes

```sql
SELECT
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

---

## Common Operations

### Seed Data

Create `app/db/seed.py` for initial data:

```python
# Example: Seed categories
async def seed_categories():
    categories = [
        {"name": "Clothes", "slug": "clothes"},
        {"name": "Shoes", "slug": "shoes"},
        {"name": "Accessories", "slug": "accessories"},
    ]
    # ... insert logic ...
```

### Database Backup

```bash
# Backup
pg_dump -U postgres shopsoma_db > backup_$(date +%Y%m%d).sql

# Restore
psql -U postgres -d shopsoma_db < backup_20251111.sql
```

### Database Reset (Development Only!)

```bash
# Drop and recreate
dropdb shopsoma_db
createdb shopsoma_db
alembic upgrade head
```

---

## Security Considerations

1. **Passwords:**
   - Stored as bcrypt hashes
   - Never log or expose

2. **Sensitive Data:**
   - KYC documents stored as S3 URLs
   - Bank details encrypted at rest

3. **Audit Trail:**
   - All critical actions logged
   - Includes user, timestamp, changes

4. **Data Access:**
   - Row-level security (to be implemented)
   - API-level authorization checks

---

## Integration with FastAPI

### Using Database Session

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db

@app.get("/products")
async def list_products(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Product))
    products = result.scalars().all()
    return products
```

### Transaction Management

```python
async with db.begin():
    # All operations in transaction
    db.add(new_product)
    await db.flush()
    # Automatically commits or rolls back
```

---

## Troubleshooting

### Issue: Cannot connect to database

```bash
# Check PostgreSQL is running
pg_isready

# Check connection
psql -U postgres -d shopsoma_db
```

### Issue: Migration fails

```bash
# Check current state
alembic current

# View pending migrations
alembic upgrade head --sql

# Rollback if needed
alembic downgrade -1
```

### Issue: Model not detected

```bash
# Ensure model is imported in app/models/__init__.py
# Regenerate migration
alembic revision --autogenerate -m "fix model import"
```

---

## Resources

- **Documentation:**
  - [Database Schema](docs/database_schema.md)
  - [Migrations Guide](docs/database_migrations.md)
  - [Technical Guide](docs/shopsoma_technical_guide.md)

- **External Resources:**
  - [SQLAlchemy 2.0 Docs](https://docs.sqlalchemy.org/en/20/)
  - [Alembic Docs](https://alembic.sqlalchemy.org/)
  - [PostgreSQL Docs](https://www.postgresql.org/docs/)
  - [FastAPI + SQLAlchemy](https://fastapi.tiangolo.com/tutorial/sql-databases/)

---

## Summary

✅ **Schema Designed** - 14 tables with complete relationships
✅ **Models Created** - All SQLAlchemy models implemented
✅ **Alembic Configured** - Migration system ready
✅ **Documentation Complete** - Comprehensive guides created

**Next:** Generate and apply initial migration, then start implementing API endpoints!

---

**Status:** Ready for Migration Generation
**Timeline:** On track for December 12, 2025 launch
**Team:** Rex, Chisom, Maryam Sulaiman
