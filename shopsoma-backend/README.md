# Shopsoma Backend API

Multi-vendor marketplace for African fashion - RESTful API

## Project Overview

Shopsoma Backend provides the core API infrastructure for the marketplace platform, handling:
- Authentication & authorization (JWT-based)
- Vendor management & KYC
- Product catalog & inventory
- Order processing & fulfillment
- Payment integration (Stripe & Paystack)
- Logistics & delivery management
- Admin operations & reporting

**Launch Target:** December 12, 2025
**Tech Stack:** Python 3.11+, FastAPI, PostgreSQL, Redis, Celery

## Prerequisites

- Python 3.11 or higher
- PostgreSQL 14+
- Redis 7+
- Git

## Getting Started

### 1. Clone the Repository

```bash
git clone <repository-url>
cd shopsoma-backend
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Setup

Create a `.env` file in the root directory:

```bash
cp .env.example .env
```

Configure your environment variables (see `.env.example` for all options).

### 5. Database Setup

```bash
# Create database
createdb shopsoma_db

# Run migrations
alembic upgrade head
```

### 6. Start Development Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`
- API Documentation: `http://localhost:8000/api/docs`
- ReDoc: `http://localhost:8000/api/redoc`

### 7. Start Celery Worker (Optional)

In a separate terminal:

```bash
celery -A app.celery_app worker --loglevel=info
```

## Available Commands

```bash
# Run development server
uvicorn app.main:app --reload

# Run tests
pytest

# Run tests with coverage
pytest --cov=app tests/

# Code formatting
black app/ tests/

# Linting
ruff check app/ tests/

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1

# Start Celery worker
celery -A app.celery_app worker --loglevel=info

# Start Celery beat (scheduled tasks)
celery -A app.celery_app beat --loglevel=info
```

## Project Structure

```
shopsoma-backend/
├── app/
│   ├── api/
│   │   └── v1/           # API version 1 endpoints
│   │       ├── auth.py        # Authentication endpoints
│   │       ├── products.py    # Product management
│   │       ├── vendors.py     # Vendor operations
│   │       ├── orders.py      # Order processing
│   │       ├── admin.py       # Admin operations
│   │       └── webhooks.py    # Payment webhooks
│   ├── models/          # SQLAlchemy models
│   │   ├── user.py
│   │   ├── vendor.py
│   │   ├── product.py
│   │   └── order.py
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # Business logic
│   │   ├── auth.py
│   │   ├── payment.py
│   │   ├── email.py
│   │   └── storage.py
│   ├── core/            # Core configuration
│   │   ├── config.py
│   │   ├── security.py
│   │   └── database.py
│   ├── tasks/           # Celery tasks
│   ├── utils/           # Helper functions
│   ├── middleware/      # Custom middleware
│   ├── main.py          # Application entry point
│   └── __init__.py
├── tests/               # Test suite
│   ├── test_auth.py
│   ├── test_products.py
│   ├── test_orders.py
│   └── conftest.py
├── alembic/             # Database migrations
│   ├── versions/
│   └── env.py
├── .github/             # GitHub workflows, PR templates
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variables template
├── Dockerfile           # Docker configuration
├── docker-compose.yml   # Local development setup
└── README.md
```

## API Endpoints

### Authentication
- `POST /api/v1/auth/signup` - Register new user
- `POST /api/v1/auth/login` - Login with email/password
- `POST /api/v1/auth/magic-link` - Send magic login link
- `GET /api/v1/auth/me` - Get current user profile

### Products
- `GET /api/v1/products` - List products (with filters)
- `GET /api/v1/products/{id}` - Get product details
- `POST /api/v1/vendor/products/upload` - Upload product CSV
- `PUT /api/v1/vendor/products/{id}` - Update product
- `DELETE /api/v1/vendor/products/{id}` - Delete product

### Orders
- `GET /api/v1/orders` - List user orders
- `GET /api/v1/orders/{id}` - Get order details
- `POST /api/v1/checkout` - Create order & initiate payment
- `POST /api/v1/orders/{id}/cancel` - Cancel order

### Vendor Management
- `POST /api/v1/vendor/register` - Register as vendor
- `GET /api/v1/vendor/dashboard` - Vendor analytics
- `GET /api/v1/vendor/orders` - Vendor orders

### Admin Operations
- `GET /api/v1/admin/vendors` - List all vendors
- `POST /api/v1/admin/approve/{vendor_id}` - Approve vendor
- `GET /api/v1/admin/payouts/export` - Export payout CSV

### Webhooks
- `POST /api/v1/webhooks/stripe` - Stripe payment webhook
- `POST /api/v1/webhooks/paystack` - Paystack payment webhook

## Development Workflow

### Branch Strategy

- `main` - Production-ready code
- `develop` - Integration branch for features
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `hotfix/*` - Urgent production fixes

### Making Changes

1. Create a feature branch from `develop`:
   ```bash
   git checkout develop
   git pull origin develop
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and commit:
   ```bash
   git add .
   git commit -m "feat: add vendor approval endpoint"
   ```

3. Push and create a Pull Request to `develop`:
   ```bash
   git push origin feature/your-feature-name
   ```

### Commit Message Convention

Follow conventional commits:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks
- `perf:` - Performance improvements

## Code Style

- Follow PEP 8 style guidelines
- Use Black for code formatting
- Use Ruff for linting
- Add type hints to function signatures
- Write docstrings for classes and functions
- Keep functions small and focused

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_auth.py

# Run with coverage report
pytest --cov=app --cov-report=html tests/

# Run tests in parallel
pytest -n auto
```

## Database Migrations

### Create a New Migration

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "add vendor kyc fields"

# Create empty migration
alembic revision -m "custom migration"
```

### Apply Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade to specific revision
alembic upgrade <revision_id>

# Downgrade one version
alembic downgrade -1
```

## Docker Setup

### Development with Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild containers
docker-compose up --build
```

### Production Docker Build

```bash
# Build image
docker build -t shopsoma-backend:latest .

# Run container
docker run -p 8000:8000 --env-file .env shopsoma-backend:latest
```

## Deployment

The backend is deployed on Render:
- **Production:** Deploys from `main` branch
- **Staging:** Deploys from `develop` branch

### Environment Variables

See `.env.example` for all required environment variables. Key variables include:

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `SECRET_KEY` | JWT secret key | Yes |
| `STRIPE_SECRET_KEY` | Stripe API key | Yes |
| `PAYSTACK_SECRET_KEY` | Paystack API key | Yes |
| `SENDGRID_API_KEY` | Email service key | Yes |
| `AWS_ACCESS_KEY_ID` | S3 access key | Yes |

### Deployment Checklist

- [ ] Environment variables configured
- [ ] Database migrations applied
- [ ] Redis connection verified
- [ ] Payment webhooks configured
- [ ] Email service configured
- [ ] S3 bucket created and configured
- [ ] Health check endpoint responding
- [ ] Monitoring and logging enabled

## Security Considerations

- All sensitive data encrypted at rest
- JWT tokens expire after 30 minutes
- Password hashing with bcrypt
- SQL injection protection via SQLAlchemy
- XSS protection via input validation
- CORS properly configured
- Rate limiting on authentication endpoints
- Payment webhooks verified with signatures

## Performance Optimization

- Database query optimization with indexes
- Redis caching for frequent queries
- Background tasks via Celery for:
  - Email sending
  - Image processing
  - Payout calculations
  - Report generation
- Connection pooling for database
- Async database operations with asyncpg

## Monitoring & Logging

- Health check endpoint: `/healthz`
- Structured logging with JSON format
- Error tracking and reporting
- Performance metrics collection
- Database query monitoring

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
pg_isready

# Test connection
psql -U postgres -d shopsoma_db
```

### Redis Connection Issues
```bash
# Check Redis is running
redis-cli ping

# Should return PONG
```

### Migration Issues
```bash
# Reset migrations (DEVELOPMENT ONLY)
alembic downgrade base
alembic upgrade head

# Check migration history
alembic history
alembic current
```

## Contributing

1. Follow the PR template when submitting changes
2. Ensure all tests pass
3. Add tests for new features
4. Update API documentation
5. Request review from code owners
6. Address review comments promptly

## Team

- **Project Manager:** Rex
- **Design Lead:** Chisom
- **Vendor Operations:** Maryam Sulaiman

## License

Proprietary - Shopsoma 2025

## Support

For questions or issues, contact the development team or create an issue in the repository.

---

**Shopsoma API** - Powering African Fashion Commerce
