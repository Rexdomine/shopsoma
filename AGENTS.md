# Repository Guidelines

## Project Structure & Module Organization
Monorepo with two apps:
- `shopsoma-frontend/` for the React + Vite + TypeScript client. Source in `shopsoma-frontend/src/` (components, pages, hooks, api, store, styles); static assets in `shopsoma-frontend/public/`.
- `shopsoma-backend/` for the FastAPI service. Core code in `shopsoma-backend/app/`, tests in `shopsoma-backend/tests/`, and migrations in `shopsoma-backend/alembic/`.
Docs live in `docs/` and top-level `*.md` guides; shared assets in `Assets/`.

## Build, Test, and Development Commands
Frontend (`shopsoma-frontend/`):
- `npm install` installs dependencies.
- `npm run dev` starts the Vite dev server.
- `npm run build` builds production assets.
- `npm run lint` runs ESLint.
- `npm run preview` serves the production build locally.

Backend (`shopsoma-backend/`):
- `python3 -m venv venv && source venv/bin/activate` creates/activates the venv.
- `pip install -r requirements.txt` installs dependencies.
- `uvicorn app.main:app --reload` runs the API locally.
- `pytest` or `pytest --cov=app tests/` runs tests.
- `black app/ tests/` and `ruff check app/ tests/` format/lint.
- `alembic upgrade head` applies migrations.
- `celery -A app.celery_app worker --loglevel=info` runs workers.

## Coding Style & Naming Conventions
Frontend:
- TypeScript + ESLint; follow existing formatting (2-space indents, single quotes).
- Components use `PascalCase` file names (e.g., `ProductCard.tsx`), hooks use `useX` naming, and variables use `camelCase`.

Backend:
- PEP 8 with 4-space indents; format with Black and lint with Ruff.
- Use `snake_case` for modules/functions, `PascalCase` for classes, and add type hints for public functions.

## Testing Guidelines
- Backend: `pytest` tests in `shopsoma-backend/tests/` with `test_*.py`; no explicit coverage threshold.
- Frontend: no test runner in `shopsoma-frontend/package.json`; if you add one, document the command and use consistent naming (for example, `*.test.tsx`).
- Root `test_*.sh` and `verify_*.sh` scripts are ad-hoc feature checks.

## Commit & Pull Request Guidelines
- Use conventional commits. History shows prefixes like `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`, `perf:`, and `debug:`.
- Branches follow `feature/*`, `bugfix/*`, and `hotfix/*` off `develop`; PRs target `develop`.
- PRs should include a summary, testing steps, linked issues, and screenshots for UI changes. Call out migrations or new environment variables and request code owner review.

## Configuration & Secrets
- Use `.env` files from `.env.example` in both apps; never commit real secrets.
- Backend expects PostgreSQL and Redis locally; ensure those services are running before testing.
