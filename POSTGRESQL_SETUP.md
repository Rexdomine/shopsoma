# PostgreSQL Setup Guide

## Option 1: Install PostgreSQL with Homebrew (Recommended for macOS)

### Install PostgreSQL

```bash
# Install PostgreSQL
brew install postgresql@15

# Start PostgreSQL service
brew services start postgresql@15

# Add to PATH
echo 'export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc

# Or for bash
echo 'export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"' >> ~/.bash_profile
source ~/.bash_profile
```

### Create Database

```bash
# Create database
createdb shopsoma_db

# Or using psql
psql postgres
CREATE DATABASE shopsoma_db;
\q
```

### Verify Installation

```bash
# Check version
psql --version

# Connect to database
psql -U $USER -d shopsoma_db

# List databases
\l

# Quit
\q
```

---

## Option 2: Use Docker (Fastest Setup)

### Using Docker Compose

The backend already has a `docker-compose.yml` file configured!

```bash
cd shopsoma-backend

# Start PostgreSQL (and Redis)
docker-compose up -d db redis

# View logs
docker-compose logs -f db

# Check status
docker-compose ps
```

**Connection Details:**
- Host: `localhost`
- Port: `5432`
- Database: `shopsoma_db`
- Username: `shopsoma`
- Password: `shopsoma_dev_password`

**Update .env file:**
```env
DATABASE_URL=postgresql://shopsoma:shopsoma_dev_password@localhost:5432/shopsoma_db
```

### Verify Docker Database

```bash
# Connect to database
docker-compose exec db psql -U shopsoma -d shopsoma_db

# List databases
\l

# Quit
\q
```

---

## Option 3: PostgreSQL.app (macOS GUI)

1. Download from https://postgresapp.com/
2. Install and launch Postgres.app
3. Click "Initialize" to create a server
4. Add to PATH:
   ```bash
   echo 'export PATH="/Applications/Postgres.app/Contents/Versions/latest/bin:$PATH"' >> ~/.zshrc
   source ~/.zshrc
   ```
5. Create database:
   ```bash
   createdb shopsoma_db
   ```

---

## After Installation: Generate & Apply Migrations

Once PostgreSQL is running:

### 1. Generate Initial Migration

```bash
cd shopsoma-backend
source venv/bin/activate

# Generate migration
alembic revision --autogenerate -m "initial database schema"
```

### 2. Apply Migration

```bash
alembic upgrade head
```

### 3. Verify

```bash
# Check migration status
alembic current

# Connect to database
psql -U postgres -d shopsoma_db  # Or use docker: docker-compose exec db psql -U shopsoma -d shopsoma_db

# List tables
\dt

# Expected tables:
# - users
# - vendors
# - categories
# - products
# - product_variants
# - product_images
# - addresses
# - orders
# - order_items
# - payments
# - payouts
# - reviews
# - returns
# - audit_logs
# - alembic_version

# View table structure
\d users

# Quit
\q
```

---

## Recommended: Use Docker Compose

**For development, Docker Compose is the fastest and most consistent option:**

```bash
cd shopsoma-backend

# Start all services (PostgreSQL, Redis, Celery)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

**Update your .env:**
```env
DATABASE_URL=postgresql://shopsoma:shopsoma_dev_password@localhost:5432/shopsoma_db
REDIS_URL=redis://localhost:6379/0
```

Then run migrations:
```bash
source venv/bin/activate
alembic upgrade head
```

---

## Troubleshooting

### Issue: Port 5432 already in use

```bash
# Check what's using the port
lsof -i :5432

# Kill the process if needed
kill -9 <PID>

# Or change the port in docker-compose.yml
ports:
  - "5433:5432"  # Map to different host port
```

### Issue: Permission denied

```bash
# Using Homebrew installation
sudo chown -R $USER /opt/homebrew/var/postgres

# Restart PostgreSQL
brew services restart postgresql@15
```

### Issue: Cannot connect to database

```bash
# Check if PostgreSQL is running
brew services list  # For Homebrew
docker-compose ps   # For Docker

# Check connection
psql -U postgres -h localhost -p 5432
```

---

## Next Steps

1. Choose installation method (Docker recommended)
2. Start PostgreSQL
3. Generate initial migration
4. Apply migration
5. Verify tables created
6. Start building API endpoints!

---

**Recommended:** Start with Docker Compose for fastest setup and consistency across team members.
