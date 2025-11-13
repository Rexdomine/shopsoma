# Deployment Quick Reference Guide

## Development Workflow

### 1. Local Development
```bash
# Start backend
cd shopsoma-backend
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
uvicorn app.main:app --reload

# Start frontend (in new terminal)
cd shopsoma-frontend
npm run dev
```

### 2. Create Feature Branch
```bash
git checkout develop
git pull origin develop
git checkout -b feature/your-feature-name
```

### 3. Make Changes and Test
```bash
# Make your changes
git add .
git commit -m "feat: description of feature"
```

### 4. Push and Create PR
```bash
git push origin feature/your-feature-name
# Go to GitHub and create Pull Request to develop
```

### 5. After PR Approval
```bash
# Merge to develop (via GitHub UI)
# Staging deploys automatically! 🚀
```

## Staging Deployment

**Trigger**: Push to `develop` branch

**Automatic Steps**:
1. GitHub Actions runs CI tests
2. Render detects push to develop
3. Builds and deploys backend + frontend
4. Runs database migrations
5. Health checks confirm deployment

**URLs**:
- Frontend: https://shopsoma-staging.onrender.com
- API: https://shopsoma-staging-api.onrender.com
- Docs: https://shopsoma-staging-api.onrender.com/api/docs

**Time**: ~5-10 minutes

## Production Release

### Step 1: Prepare Release
```bash
# Ensure develop is stable
git checkout develop
git pull origin develop

# Test thoroughly on staging
# https://shopsoma-staging.onrender.com
```

### Step 2: Create Version Tag
```bash
# Create semantic version tag
git tag -a v1.0.0 -m "Release v1.0.0: Initial production release"
git push origin v1.0.0
```

### Step 3: GitHub Actions Creates Release
- Automatically generates changelog
- Creates GitHub Release
- Tags commit for production

### Step 4: Deploy to Production
```bash
# Merge to main branch
git checkout main
git merge v1.0.0
git push origin main

# Render deploys from main branch
```

**Time**: ~10-15 minutes

## Database Management

### Run Migrations (Staging)
```bash
# Migrations run automatically on deploy
# Check logs in Render dashboard

# Manual migration (if needed)
# Connect via Render shell:
alembic upgrade head
```

### Seed Database
```bash
# Reset and seed staging database
curl -X DELETE https://shopsoma-staging-api.onrender.com/api/v1/seed/reset
curl -X POST https://shopsoma-staging-api.onrender.com/api/v1/seed/initialize

# Response: {"status":"success","message":"Created 5 products with variants",...}
```

### Rollback Migration
```bash
# In Render shell:
alembic downgrade -1  # Go back one version
alembic downgrade <revision>  # Go to specific version
```

## Environment Variables

### Required for Backend
```env
DATABASE_URL=<auto-provided-by-render>
SECRET_KEY=<generate-strong-secret>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
ENVIRONMENT=staging|production
ALLOWED_ORIGINS=<comma-separated-urls>
```

### Required for Frontend
```env
VITE_API_BASE_URL=<backend-api-url>
VITE_APP_NAME=Shopsoma
VITE_ENVIRONMENT=staging|production
```

### Set Variables in Render
1. Go to service dashboard
2. Click "Environment" tab
3. Add/edit variables
4. Click "Save Changes"
5. Service redeploys automatically

## Troubleshooting

### Deployment Stuck
1. Check Render dashboard logs
2. Look for build errors
3. Verify environment variables
4. Check render.yaml syntax

### Health Check Failing
```bash
# Test health endpoint
curl https://shopsoma-staging-api.onrender.com/api/v1/health

# Should return: {"status":"healthy","version":"1.0.0"}
```

### Database Connection Issues
1. Check DATABASE_URL is set correctly
2. Verify database is running (Render dashboard)
3. Check connection string format
4. Review migration logs

### Build Failures
**Backend**:
- Check requirements.txt
- Verify Python version (3.9)
- Check build logs for missing dependencies

**Frontend**:
- Check package.json
- Verify Node version (18)
- Check for TypeScript errors
- Verify environment variables

## Rollback Procedures

### Rollback Staging
```bash
git checkout develop
git revert <bad-commit-hash>
git push origin develop
# Render redeploys previous version
```

### Rollback Production
```bash
# Option 1: Revert commit
git checkout main
git revert <bad-commit-hash>
git push origin main

# Option 2: Deploy previous tag
git checkout main
git reset --hard v1.0.0  # Previous working version
git push origin main --force
```

## Monitoring

### Check Service Status
- Render Dashboard: https://dashboard.render.com
- GitHub Actions: Repository > Actions tab

### View Logs
**Real-time logs**:
1. Go to Render dashboard
2. Select service
3. Click "Logs" tab

**Historical logs**:
- Available in Render dashboard
- Can export for analysis

### Health Checks
```bash
# Staging
curl https://shopsoma-staging-api.onrender.com/api/v1/health

# Production (when configured)
curl https://api.shopsoma.com/api/v1/health
```

## Common Commands

### Git Operations
```bash
# Check current branch
git branch

# Update from remote
git pull origin develop

# Create new branch
git checkout -b feature/name

# View recent commits
git log --oneline -10

# View tags
git tag -l
```

### Database Commands
```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1

# Check current version
alembic current
```

### API Testing
```bash
# Test endpoints
curl https://shopsoma-staging-api.onrender.com/api/v1/products

# Test with authentication
curl -H "Authorization: Bearer <token>" \
  https://shopsoma-staging-api.onrender.com/api/v1/products
```

## Version Management

### Semantic Versioning
- **Major** (v2.0.0): Breaking changes
- **Minor** (v1.1.0): New features, backward compatible
- **Patch** (v1.0.1): Bug fixes

### Creating Tags
```bash
# Patch release (bug fixes)
git tag -a v1.0.1 -m "Fix critical bug"

# Minor release (new features)
git tag -a v1.1.0 -m "Add new feature"

# Major release (breaking changes)
git tag -a v2.0.0 -m "Major redesign"

# Push tag
git push origin v1.0.1
```

## Emergency Procedures

### Site Down
1. Check Render status page
2. Review recent deployments
3. Check service logs
4. Rollback if needed
5. Contact support if service issue

### Database Issues
1. Check database status (Render dashboard)
2. Verify connection string
3. Review migration logs
4. Restore from backup if needed

### Security Incident
1. Rotate all secrets immediately
2. Review access logs
3. Deploy emergency fix
4. Notify users if data breach
5. Document incident

## Support Resources

- **Documentation**: `/docs/` folder
- **Render Docs**: https://render.com/docs
- **GitHub Actions**: https://docs.github.com/actions
- **FastAPI Docs**: https://fastapi.tiangolo.com
- **React Docs**: https://react.dev

## Contacts

- **DevOps**: [Add contact]
- **Backend Lead**: [Add contact]
- **Frontend Lead**: [Add contact]
- **Database Admin**: [Add contact]
