# Shopsoma Render Deployment Checklist

Use this checklist to ensure smooth deployment to Render staging.

## Pre-Deployment Checklist

### Code Preparation
- [ ] All changes committed to `develop` branch
- [ ] Code builds successfully locally
  ```bash
  cd shopsoma-backend && python -m pytest
  cd shopsoma-frontend && npm run build
  ```
- [ ] No sensitive data in code (API keys, passwords)
- [ ] `.env` files added to `.gitignore`

### Configuration Files
- [ ] `render.yaml` in project root
- [ ] `requirements.txt` in `shopsoma-backend/`
- [ ] `build.sh` in `shopsoma-backend/` (executable)
- [ ] `.env.staging` in `shopsoma-frontend/`

### Database
- [ ] All migrations created: `alembic revision --autogenerate`
- [ ] Migrations tested locally: `alembic upgrade head`
- [ ] Seed data scripts ready (`seed_products.py`, etc.)

## Deployment Steps

### 1. Push to GitHub
```bash
# Ensure you're on develop branch
git checkout develop

# Add deployment files
git add render.yaml RENDER_DEPLOYMENT.md DEPLOYMENT_CHECKLIST.md
git add shopsoma-backend/requirements.txt shopsoma-backend/build.sh
git add shopsoma-frontend/.env.staging

# Commit
git commit -m "chore: add Render deployment configuration for staging"

# Push
git push origin develop
```

### 2. Create Render Account
- [ ] Go to https://render.com
- [ ] Sign up with GitHub
- [ ] Grant Render access to your repository

### 3. Deploy Using Blueprint
- [ ] Go to Render Dashboard → **New** → **Blueprint**
- [ ] Select `shopsoma` repository
- [ ] Choose `develop` branch
- [ ] Review services in `render.yaml`
- [ ] Click **Apply**
- [ ] Wait for deployment (~15 minutes)

### 4. Verify Services Created
- [ ] Database: `shopsoma-staging-db` (Status: Available)
- [ ] Backend: `shopsoma-staging-api` (Status: Live)
- [ ] Frontend: `shopsoma-staging` (Status: Live)

### 5. Check Environment Variables
Backend (`shopsoma-staging-api`):
- [ ] `DATABASE_URL` (auto-populated from database)
- [ ] `SECRET_KEY` (auto-generated)
- [ ] `ALGORITHM=HS256`
- [ ] `ACCESS_TOKEN_EXPIRE_MINUTES=30`
- [ ] `REFRESH_TOKEN_EXPIRE_DAYS=7`
- [ ] `ENVIRONMENT=staging`
- [ ] `ALLOWED_ORIGINS` includes frontend URL

Frontend (`shopsoma-staging`):
- [ ] `VITE_API_BASE_URL=https://shopsoma-staging-api.onrender.com/api/v1`

### 6. Run Database Migrations
```bash
# In Render Dashboard → shopsoma-staging-api → Shell
alembic upgrade head
```

### 7. Seed Demo Data
```bash
# In Render Dashboard → shopsoma-staging-api → Shell
python seed_products.py
python activate_products.py
python update_products_with_variations.py
```

## Post-Deployment Verification

### Backend API Tests
- [ ] Health check: `https://shopsoma-staging-api.onrender.com/api/v1/health`
- [ ] API docs: `https://shopsoma-staging-api.onrender.com/docs`
- [ ] Test endpoint: `GET /api/v1/products`
- [ ] Test authentication: `POST /api/v1/auth/login`

### Frontend Tests
- [ ] Homepage loads: `https://shopsoma-staging.onrender.com`
- [ ] Products display correctly
- [ ] Navigation works
- [ ] Product detail pages load
- [ ] Images display
- [ ] API calls work (check browser console)

### Database Verification
```bash
# In database shell or via external connection
SELECT COUNT(*) FROM products;  -- Should return 10
SELECT COUNT(*) FROM product_variants;  -- Should return 90 (10 products × 9 variants)
SELECT COUNT(*) FROM users WHERE role = 'vendor';  -- Should return 4
```

## Monitoring Setup

### Set Up Alerts
- [ ] Email notifications enabled in Render Dashboard
- [ ] Health check alerts configured
- [ ] Deploy notifications enabled

### Add Monitoring
- [ ] Check logs regularly: Service → Logs tab
- [ ] Monitor metrics: Service → Metrics tab
- [ ] Set up error tracking (e.g., Sentry) - optional

## Common Issues & Solutions

### Issue: Backend fails to start
**Solution**:
```bash
# Check logs for errors
# Common fix: Ensure DATABASE_URL is set correctly
# Run migrations manually via shell
```

### Issue: Frontend shows blank page
**Solution**:
```bash
# Check that VITE_API_BASE_URL is correct
# Verify rewrite rules are set: /* → /index.html
# Check browser console for errors
```

### Issue: Database connection timeout
**Solution**:
```bash
# Use INTERNAL database URL for backend
# Not the external URL
# Format: postgresql://user:pass@host/db
```

### Issue: 502 Bad Gateway
**Solution**:
```bash
# Wait for service to spin up (free tier)
# First request after inactivity takes 30-60s
# Check service logs for crashes
```

## Updating Staging

### Deploy New Changes
```bash
# On develop branch
git add .
git commit -m "Your changes"
git push origin develop

# Render auto-deploys in ~5-10 minutes
```

### Manual Redeploy
- [ ] Go to service in Render Dashboard
- [ ] Click **Manual Deploy** → **Deploy latest commit**

### Rollback if Needed
- [ ] Go to service → **Events**
- [ ] Find previous successful deploy
- [ ] Click **Rollback**

## Security Checklist

- [ ] All secrets in environment variables (not code)
- [ ] CORS configured correctly (ALLOWED_ORIGINS)
- [ ] Database not publicly accessible
- [ ] HTTPS enabled (automatic on Render)
- [ ] API rate limiting configured (if needed)

## Performance Optimization

- [ ] Enable compression in backend
- [ ] Optimize images (use CDN if available)
- [ ] Check database query performance
- [ ] Monitor response times in Metrics tab

## Documentation

- [ ] Update README with staging URL
- [ ] Document any staging-specific setup
- [ ] Share staging URL with team
- [ ] Create test accounts for QA

## Next Steps

After successful staging deployment:

1. **Testing Phase**
   - [ ] Perform full QA testing
   - [ ] Test all user flows
   - [ ] Check mobile responsiveness
   - [ ] Test payment integration (if applicable)

2. **Bug Fixes**
   - [ ] Create issues for bugs found
   - [ ] Fix on develop branch
   - [ ] Verify fixes on staging

3. **Production Deployment**
   - [ ] Merge develop → main
   - [ ] Create production Render services
   - [ ] Use production environment variables
   - [ ] Set up custom domain
   - [ ] Configure production database backups

## Team Communication

Share with your team:
```
🚀 Staging Environment Live!

Frontend: https://shopsoma-staging.onrender.com
Backend API: https://shopsoma-staging-api.onrender.com/docs

Test Accounts:
- Customer: customer@test.com / password123
- Vendor: vendor@test.com / password123

Auto-deploys from: develop branch
Deployment time: ~10 minutes after push
```

## Support Resources

- Render Status: https://status.render.com
- Render Docs: https://render.com/docs
- Community: https://community.render.com

## Success Criteria

Deployment is successful when:
- [ ] All three services show "Live" status
- [ ] Frontend loads without errors
- [ ] Backend API responds to requests
- [ ] Database contains seed data
- [ ] No console errors in browser
- [ ] All tests pass on staging environment

---

**Last Updated**: $(date)
**Deployed By**: Your Name
**Staging URL**: https://shopsoma-staging.onrender.com
