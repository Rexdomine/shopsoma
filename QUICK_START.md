# Shopsoma Quick Start Guide

## Running Commands from Terminal

### Important: Always Navigate to the Backend Directory First

```bash
# Navigate to backend directory
cd /Users/rex/Documents/Shopsoma/shopsoma-backend

# Activate virtual environment
source venv/bin/activate

# Now you can run alembic commands
alembic current
alembic history
```

---

## Quick Verification Script

We've created a verification script that runs all checks automatically:

```bash
# Navigate to backend directory
cd /Users/rex/Documents/Shopsoma/shopsoma-backend

# Run verification script
./verify_db.sh
```

This will check:
- ✅ Migration status
- ✅ All database tables
- ✅ Table structures
- ✅ Foreign keys
- ✅ Indexes

---

## Common Commands

### Alembic (Database Migrations)

```bash
cd shopsoma-backend
source venv/bin/activate

# Check current migration
alembic current

# View migration history
alembic history

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Create new migration
alembic revision --autogenerate -m "description"
```

### Database Operations

```bash
# Connect to database
docker exec orula-postgres psql -U postgres -d shopsoma_db

# Inside psql:
\dt                    # List tables
\d users              # Describe users table
\q                    # Quit

# One-line queries
docker exec orula-postgres psql -U postgres -d shopsoma_db -c "\dt"
docker exec orula-postgres psql -U postgres -d shopsoma_db -c "SELECT * FROM users;"
```

### Backend Server

```bash
cd shopsoma-backend
source venv/bin/activate

# Run development server
uvicorn app.main:app --reload

# Visit API docs
# http://localhost:8000/api/docs
```

---

## Project Structure

```
Shopsoma/
├── shopsoma-backend/       # FastAPI backend (YOU NEED TO BE HERE)
│   ├── venv/              # Virtual environment
│   ├── alembic/           # Database migrations
│   ├── app/               # Application code
│   ├── .env               # Environment variables
│   └── verify_db.sh       # Verification script
├── shopsoma-frontend/     # React frontend
└── docs/                  # Documentation
```

---

## Why "command not found: alembic"?

**Problem:** You're running commands from the wrong directory or without activating the virtual environment.

**Solution:**
```bash
# Step 1: Navigate to backend directory
cd /Users/rex/Documents/Shopsoma/shopsoma-backend

# Step 2: Activate virtual environment
source venv/bin/activate

# Step 3: Now alembic works!
alembic current
```

**Or use the shortcut:**
```bash
# From anywhere in the Shopsoma project
cd shopsoma-backend && source venv/bin/activate && alembic current
```

---

## Visual Guide

### ❌ Wrong (Will Fail)
```bash
rex@MacBookPro Shopsoma % alembic current
zsh: command not found: alembic
```

### ✅ Correct
```bash
rex@MacBookPro Shopsoma % cd shopsoma-backend
rex@MacBookPro shopsoma-backend % source venv/bin/activate
(venv) rex@MacBookPro shopsoma-backend % alembic current
3a9bcaf3fd5f (head)
```

---

## Quick Start Checklist

### First Time Setup

```bash
# 1. Navigate to backend
cd /Users/rex/Documents/Shopsoma/shopsoma-backend

# 2. Create virtual environment (if not exists)
python3 -m venv venv

# 3. Activate virtual environment
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Verify database
./verify_db.sh
```

### Daily Development

```bash
# 1. Navigate and activate
cd /Users/rex/Documents/Shopsoma/shopsoma-backend
source venv/bin/activate

# 2. Check migrations
alembic current

# 3. Start server
uvicorn app.main:app --reload
```

---

## Environment Indicator

When virtual environment is active, you'll see `(venv)` in your prompt:

```bash
# Before activation
rex@MacBookPro shopsoma-backend %

# After activation
(venv) rex@MacBookPro shopsoma-backend %
```

---

## Useful Aliases (Optional)

Add to your `~/.zshrc`:

```bash
# Shopsoma shortcuts
alias shop='cd /Users/rex/Documents/Shopsoma'
alias shopback='cd /Users/rex/Documents/Shopsoma/shopsoma-backend && source venv/bin/activate'
alias shopfront='cd /Users/rex/Documents/Shopsoma/shopsoma-frontend'
alias shopdb='cd /Users/rex/Documents/Shopsoma/shopsoma-backend && source venv/bin/activate && ./verify_db.sh'
```

Then reload:
```bash
source ~/.zshrc
```

Now you can use:
```bash
shopback          # Navigate to backend & activate venv
alembic current   # Now this works!
```

---

## Summary

**Golden Rule:** Always be in `shopsoma-backend/` directory with virtual environment activated!

```bash
# The magic command that makes everything work:
cd /Users/rex/Documents/Shopsoma/shopsoma-backend && source venv/bin/activate
```

---

## Verification Results

Your database is working perfectly! ✅

- **Migration:** 3a9bcaf3fd5f (head)
- **Tables:** 15 (all present)
- **Foreign Keys:** 28 (excellent)
- **Indexes:** 58 (optimized)

Ready for API development! 🚀
