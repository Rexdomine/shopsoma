# Shopsoma - African Fashion Marketplace

Multi-vendor marketplace connecting African fashion designers with global buyers.

**Launch Target:** December 12, 2025
**Tech Stack:** React + TypeScript (Frontend) | FastAPI + Python (Backend)

## Repository Structure

This is a monorepo containing both frontend and backend applications:

```
shopsoma/
├── shopsoma-frontend/    # React + Vite + TypeScript
├── shopsoma-backend/     # FastAPI + Python
├── docs/                 # Project documentation
└── PROJECT_SETUP_SUMMARY.md
```

## Quick Start

### Frontend Setup
```bash
cd shopsoma-frontend
npm install
npm run dev
```
Visit `http://localhost:5173`

See [Frontend README](shopsoma-frontend/README.md) for detailed instructions.

### Backend Setup
```bash
cd shopsoma-backend
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Visit `http://localhost:8000/api/docs`

See [Backend README](shopsoma-backend/README.md) for detailed instructions.

## Documentation

- [Technical Guide](docs/shopsoma_technical_guide.md) - Architecture & system design
- [Project Setup Summary](PROJECT_SETUP_SUMMARY.md) - Development workflow & next steps
- [Frontend Documentation](shopsoma-frontend/README.md)
- [Backend Documentation](shopsoma-backend/README.md)

## Development Workflow

### Branch Strategy
- `main` - Production-ready code
- `develop` - Integration branch for features
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `hotfix/*` - Urgent production fixes

### Making Changes
1. Create feature branch from `develop`
2. Make changes and commit with conventional commits
3. Push and create PR to `develop`
4. Get approval from code owners
5. Merge to `develop`

### Commit Convention
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation
- `style:` - Code formatting
- `refactor:` - Code restructuring
- `test:` - Tests
- `chore:` - Maintenance

## Technology Stack

### Frontend
- React 18+ with TypeScript
- Vite for build tooling
- TailwindCSS (to be added)
- Redux Toolkit / Zustand (to be decided)

### Backend
- FastAPI (Python 3.11+)
- PostgreSQL 14+
- Redis 7+
- Celery for background tasks
- SQLAlchemy 2.0 (async)

### Infrastructure
- Docker & Docker Compose
- Render (deployment)
- GitHub Actions (CI/CD)

## Key Features (Phase 1)

### Customer Experience
- Product browsing & search
- Shopping cart & checkout
- Order tracking
- Secure payments (Stripe/Paystack)

### Vendor Dashboard
- Product inventory management
- CSV bulk upload
- Order management
- Sales analytics

### Admin Panel
- Vendor approval
- Product moderation
- Payout management
- Platform analytics

## Team

- **Project Manager:** Rex
- **Design Lead:** Chisom
- **Vendor Operations:** Maryam Sulaiman

## Contributing

1. Review the [technical guide](docs/shopsoma_technical_guide.md)
2. Follow the PR templates
3. Ensure tests pass
4. Get code owner approval

## License

Proprietary - Shopsoma 2025

---

**Shopsoma** - Connecting African Fashion with the World
