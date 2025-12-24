# CI/CD Pipeline Documentation

## Overview

Shopsoma uses GitHub Actions for continuous integration and Render for continuous deployment. This document outlines the complete CI/CD pipeline setup.

## Pipeline Structure

### 1. Continuous Integration (CI)

**Workflow**: `.github/workflows/ci.yml`

Runs on every pull request and push to `develop` or `main` branches.

#### Backend CI
- **Python Setup**: Python 3.9
- **Database**: PostgreSQL 15 (test database)
- **Steps**:
  - Install dependencies from `requirements.txt`
  - Run linting with flake8
  - Run pytest with coverage reporting
  - Test database migrations

#### Frontend CI
- **Node.js Setup**: Node 18
- **Steps**:
  - Install dependencies with `npm ci`
  - Run ESLint for code quality
  - Run TypeScript type checking
  - Build production bundle
  - Upload build artifacts

#### Security Scanning
- **Tool**: Trivy vulnerability scanner
- Scans entire codebase for security issues
- Uploads results to GitHub Security tab

### 2. Staging Deployment

**Workflow**: `.github/workflows/deploy-staging.yml`

**Trigger**: Push to `develop` branch

**Process**:
1. Render auto-detects push to `develop` branch
2. Builds and deploys via render.yaml Blueprint
3. GitHub Actions performs health checks
4. Summary posted to GitHub Actions dashboard

**Staging URLs**:
- Frontend: https://shopsoma-staging.onrender.com
- API: https://shopsoma-staging-api.onrender.com

**Environment Variables** (Set in Render Dashboard):
```env
# Backend
DATABASE_URL=<Render provides this>
SECRET_KEY=<Generate 32+ character random string>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
ENVIRONMENT=staging
ALLOWED_ORIGINS=https://shopsoma-staging.onrender.com,http://localhost:5173
DATABASE_ECHO=false

# Frontend
VITE_API_BASE_URL=https://shopsoma-staging-api.onrender.com/api/v1
VITE_APP_NAME=Shopsoma Staging
VITE_ENVIRONMENT=staging
```

### 3. Production Deployment

**Workflow**: `.github/workflows/deploy-production.yml`

**Trigger**: Push version tags (e.g., `v1.0.0`, `v1.2.3`)

**Process**:
1. Create GitHub Release with changelog
2. Notify about production deployment
3. Requires manual merge to `main` branch
4. Render auto-deploys from `main` branch

**Creating a Production Release**:

```bash
# 1. Ensure develop is ready for production
git checkout develop
git pull origin develop

# 2. Create and push version tag
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# 3. GitHub Actions creates release automatically

# 4. Merge to main for deployment
git checkout main
git merge v1.0.0
git push origin main

# 5. Render deploys to production
```

**Production URLs** (when configured):
- Frontend: https://shopsoma.com
- API: https://api.shopsoma.com

**Environment Variables** (Set in Render Dashboard):
```env
# Backend
DATABASE_URL=<Production database URL>
SECRET_KEY=<Strong production secret>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
ENVIRONMENT=production
ALLOWED_ORIGINS=https://shopsoma.com
DATABASE_ECHO=false

# Frontend
VITE_API_BASE_URL=https://api.shopsoma.com/api/v1
VITE_APP_NAME=Shopsoma
VITE_ENVIRONMENT=production
```

## Environment Management

### Staging Environment
- **Purpose**: Testing and QA before production
- **Branch**: `develop`
- **Database**: Separate staging PostgreSQL instance
- **Deployment**: Automatic on push to develop
- **Access**: Team only (can add authentication)

### Production Environment
- **Purpose**: Live customer-facing application
- **Branch**: `main`
- **Database**: Production PostgreSQL with backups
- **Deployment**: Manual via version tags
- **Access**: Public

## Render Blueprint Configuration

The `render.yaml` file defines infrastructure as code:

```yaml
databases:
  - name: shopsoma-staging-db
    plan: free  # Upgrade to paid plan for production
    region: oregon
    databaseName: shopsoma_staging
    user: shopsoma_user

services:
  # Backend API
  - type: web
    name: shopsoma-staging-api
    env: python
    branch: develop
    buildCommand: "cd shopsoma-backend && pip install -r requirements.txt"
    startCommand: "cd shopsoma-backend && alembic upgrade heads && uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    healthCheckPath: /api/v1/health

  # Frontend
  - type: web
    name: shopsoma-staging
    env: static
    branch: develop
    buildCommand: "cd shopsoma-frontend && npm install && npm run build"
    staticPublishPath: shopsoma-frontend/dist
```

## Secrets Management

### GitHub Secrets
Navigate to: `Repository Settings > Secrets and variables > Actions`

**Required Secrets**: None currently (Render handles deployment)

**Optional Secrets** (for future integrations):
- `SLACK_WEBHOOK_URL`: For deployment notifications
- `SENTRY_DSN`: Error tracking
- `RENDER_API_KEY`: For API-based deployments

### Render Environment Variables
Set in Render Dashboard for each service:

1. Go to service settings
2. Navigate to "Environment" tab
3. Add environment variables
4. Click "Save Changes"

**Important**: Never commit secrets to git!

## Monitoring and Health Checks

### Health Check Endpoints

**Backend API**:
```bash
GET /api/v1/health
# Response: {"status": "healthy", "version": "1.0.0"}
```

**Frontend**:
```bash
GET /
# Response: 200 OK (HTML page)
```

### Deployment Monitoring

1. **GitHub Actions Dashboard**: Monitor CI/CD pipeline runs
2. **Render Dashboard**: View deployment logs and status
3. **Health Checks**: Automated checks after deployment

## Rollback Procedures

### Staging Rollback
```bash
# Revert commit on develop branch
git checkout develop
git revert <bad-commit-hash>
git push origin develop
# Render auto-deploys previous version
```

### Production Rollback
```bash
# Option 1: Revert on main branch
git checkout main
git revert <bad-commit-hash>
git push origin main

# Option 2: Deploy previous tag
git checkout main
git reset --hard v1.0.0  # Previous working version
git push origin main --force  # Use with caution!
```

## Troubleshooting

### CI Pipeline Failures

**Backend tests failing**:
- Check test database connection
- Verify environment variables in workflow
- Review pytest output in Actions logs

**Frontend build failing**:
- Check for TypeScript errors
- Verify npm dependencies
- Check build logs for specific errors

### Deployment Failures

**Render deployment stuck**:
1. Check Render dashboard logs
2. Verify render.yaml syntax
3. Check build command output
4. Review environment variables

**Health checks failing**:
1. Check service logs in Render
2. Verify database migrations ran
3. Check environment variables
4. Test endpoints manually

## Best Practices

### Development Workflow

1. **Feature Development**:
   ```bash
   git checkout -b feature/new-feature develop
   # Make changes
   git commit -m "feat: add new feature"
   git push origin feature/new-feature
   # Create PR to develop
   ```

2. **Code Review**: All changes require PR review before merge

3. **Testing**: CI pipeline must pass before merge

4. **Staging Deployment**: Merge to develop triggers auto-deploy

5. **Production Release**: Create version tag after staging validation

### Versioning Strategy

Follow [Semantic Versioning](https://semver.org/):

- **v1.0.0**: Major version (breaking changes)
- **v1.1.0**: Minor version (new features, backward compatible)
- **v1.1.1**: Patch version (bug fixes)

### Database Migrations

Always test migrations in staging first:

```bash
# Run migrations locally
cd shopsoma-backend
alembic upgrade head

# Test rollback
alembic downgrade -1

# Staging auto-runs migrations on deploy
# Monitor logs to ensure success
```

## Future Enhancements

- [ ] Add automated E2E tests with Playwright
- [ ] Implement blue-green deployments
- [ ] Add performance monitoring (Datadog/New Relic)
- [ ] Set up error tracking (Sentry)
- [ ] Add deployment notifications (Slack/Discord)
- [ ] Implement database backup automation
- [ ] Add load testing in staging
- [ ] Set up CDN for static assets

## Support

For CI/CD issues:
1. Check GitHub Actions logs
2. Review Render deployment logs
3. Consult this documentation
4. Contact DevOps team

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Render Documentation](https://render.com/docs)
- [Render Blueprint Reference](https://render.com/docs/blueprint-spec)
