# Shopsoma Render Deployment Guide

This guide walks you through deploying Shopsoma to Render for staging.

## Overview

The staging environment deploys from the `develop` branch and includes:
- **Backend API** (FastAPI): `shopsoma-staging-api.onrender.com`
- **Frontend** (React): `shopsoma-staging.onrender.com`
- **Database** (PostgreSQL): Managed by Render

## Prerequisites

1. **GitHub Repository**: Ensure your code is pushed to GitHub
2. **Render Account**: Sign up at [render.com](https://render.com)
3. **Current Branch**: Make sure you're on the `develop` branch

## Deployment Steps

### Option 1: Using Render Blueprint (Recommended)

This method deploys everything at once using the `render.yaml` configuration.

1. **Push Configuration to GitHub**
   ```bash
   git add render.yaml
   git commit -m "Add Render deployment configuration"
   git push origin develop
   ```

2. **Create Blueprint on Render**
   - Go to [Render Dashboard](https://dashboard.render.com/)
   - Click **"New"** → **"Blueprint"**
   - Connect your GitHub repository
   - Select the `shopsoma` repository
   - Choose the `develop` branch
   - Render will detect `render.yaml` automatically
   - Review the services that will be created:
     - `shopsoma-staging-db` (PostgreSQL)
     - `shopsoma-staging-api` (Backend)
     - `shopsoma-staging` (Frontend)
   - Click **"Apply"**

3. **Wait for Deployment**
   - Render will create all three services
   - Database creation: ~2 minutes
   - Backend deployment: ~5-10 minutes
   - Frontend deployment: ~3-5 minutes
   - Total time: ~10-15 minutes

4. **Verify Deployment**
   - Backend API: `https://shopsoma-staging-api.onrender.com/api/v1/health`
   - Frontend: `https://shopsoma-staging.onrender.com`

### Option 2: Manual Setup (Alternative)

If you prefer to set up services individually:

#### Step 1: Create PostgreSQL Database

1. Go to Render Dashboard → **New** → **PostgreSQL**
2. Configure:
   - **Name**: `shopsoma-staging-db`
   - **Database**: `shopsoma_staging`
   - **User**: `shopsoma_user`
   - **Region**: Oregon (or closest to your users)
   - **Plan**: Free
3. Click **"Create Database"**
4. Wait for provisioning (~2 minutes)
5. Copy the **Internal Database URL** (starts with `postgresql://`)

#### Step 2: Deploy Backend API

1. Go to Render Dashboard → **New** → **Web Service**
2. Connect your GitHub repository
3. Configure:
   - **Name**: `shopsoma-staging-api`
   - **Region**: Oregon
   - **Branch**: `develop`
   - **Root Directory**: `shopsoma-backend`
   - **Runtime**: Python 3
   - **Build Command**:
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command**:
     ```bash
     alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
     ```
   - **Plan**: Free

4. **Environment Variables** (Add these):
   ```
   DATABASE_URL=<paste-internal-database-url>
   SECRET_KEY=<generate-random-key>
   ALGORITHM=HS256
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   REFRESH_TOKEN_EXPIRE_DAYS=7
   ENVIRONMENT=staging
   ALLOWED_ORIGINS=https://shopsoma-staging.onrender.com,http://localhost:5173
   DATABASE_ECHO=false
   ```

5. **Advanced Settings**:
   - Health Check Path: `/api/v1/health`
   - Auto-Deploy: Yes

6. Click **"Create Web Service"**

#### Step 3: Deploy Frontend

1. Go to Render Dashboard → **New** → **Static Site**
2. Connect your GitHub repository
3. Configure:
   - **Name**: `shopsoma-staging`
   - **Region**: Oregon
   - **Branch**: `develop`
   - **Root Directory**: `shopsoma-frontend`
   - **Build Command**:
     ```bash
     npm install && npm run build
     ```
   - **Publish Directory**: `dist`

4. **Environment Variables**:
   ```
   VITE_API_BASE_URL=https://shopsoma-staging-api.onrender.com/api/v1
   ```

5. **Rewrite Rules** (for React Router):
   - Source: `/*`
   - Destination: `/index.html`
   - Action: Rewrite

6. Click **"Create Static Site"**

## Post-Deployment Setup

### 1. Seed Demo Data

Once the backend is deployed, seed the database with demo products:

```bash
# SSH into the backend service (via Render shell)
# Or use a one-time job:

# In Render Dashboard → shopsoma-staging-api → Shell
python seed_products.py
python activate_products.py
python update_products_with_variations.py
```

### 2. Configure Custom Domains (Optional)

1. Go to service settings
2. Click **"Custom Domain"**
3. Add your domain:
   - Frontend: `staging.shopsoma.com`
   - Backend: `api-staging.shopsoma.com`
4. Update DNS records as instructed by Render

### 3. Set Up Environment Variables

Recommended additional environment variables:

**Backend**:
```env
# Email (if using email features)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=<your-sendgrid-key>

# File Storage (if using AWS S3)
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>
AWS_S3_BUCKET=shopsoma-staging
AWS_REGION=us-west-2

# Redis (if caching)
REDIS_URL=<redis-url>
```

**Frontend**:
```env
VITE_APP_NAME=Shopsoma Staging
VITE_ENVIRONMENT=staging
VITE_ANALYTICS_ID=<staging-analytics-id>
```

## Continuous Deployment

Render automatically redeploys when you push to the `develop` branch:

```bash
git add .
git commit -m "Your changes"
git push origin develop
```

- **Backend**: Redeploys in ~5-10 minutes
- **Frontend**: Redeploys in ~3-5 minutes

## Monitoring & Logs

### View Logs

1. Go to Render Dashboard
2. Select your service
3. Click **"Logs"** tab
4. View real-time logs or filter by date

### Health Checks

- Backend: `https://shopsoma-staging-api.onrender.com/api/v1/health`
- Check response time and status

### Metrics

Render provides:
- CPU usage
- Memory usage
- Request count
- Response times

Access via: Service → **Metrics** tab

## Database Management

### Access Database

1. Go to `shopsoma-staging-db` service
2. Click **"Connect"** tab
3. Choose connection method:
   - **Internal URL**: For backend service
   - **External URL**: For local tools (pgAdmin, TablePlus)

### Run Migrations

```bash
# Via Render shell
alembic upgrade head

# Or create a migration
alembic revision --autogenerate -m "migration message"
alembic upgrade head
```

### Backup Database

Render Free tier includes:
- Automatic daily backups (retained for 7 days)
- Manual backups via Dashboard

To create manual backup:
1. Go to database service
2. Click **"Backups"**
3. Click **"Create Backup"**

## Troubleshooting

### Backend Won't Start

**Check logs for common issues**:

1. **Database connection failed**
   - Verify `DATABASE_URL` is correct
   - Check database service is running

2. **Missing dependencies**
   - Ensure `requirements.txt` is up to date
   - Check build logs for pip install errors

3. **Migration errors**
   - Run `alembic upgrade head` manually via shell
   - Check migration files for issues

### Frontend 404 Errors

1. **Verify rewrite rules**:
   - Source: `/*`
   - Destination: `/index.html`

2. **Check environment variables**:
   - `VITE_API_BASE_URL` points to correct backend URL

### Slow Performance

Free tier limitations:
- Services spin down after 15 minutes of inactivity
- First request after spin-down takes 30-60 seconds
- Consider upgrading to paid tier for production

## Cost Optimization

### Free Tier Limits

- **Web Services**: 750 hours/month (one service always free)
- **Static Sites**: Unlimited
- **PostgreSQL**: 90 days free, then $7/month
- **Bandwidth**: 100 GB/month

### Tips

1. Use staging only for testing, not demos
2. Delete old preview deployments
3. Monitor usage in Dashboard
4. Consider pausing services when not in use

## Environment Comparison

| Feature | Local | Staging (Render) | Production |
|---------|-------|------------------|------------|
| Branch | `develop` | `develop` | `main` |
| Database | Local PostgreSQL | Render PostgreSQL | Managed DB |
| URL | localhost:5174 | *.onrender.com | shopsoma.com |
| Auto-deploy | No | Yes | Yes |
| SSL | No | Yes (automatic) | Yes |
| Backups | Manual | Automatic | Automatic |

## Next Steps

1. ✅ Deploy staging environment
2. 🧪 Test all features on staging
3. 🐛 Fix any bugs found
4. 🔄 Merge to `main` for production
5. 🚀 Deploy production environment

## Support

- **Render Docs**: https://render.com/docs
- **Render Community**: https://community.render.com
- **GitHub Issues**: Create issue in repository

## Additional Resources

- [Render Python Quickstart](https://render.com/docs/deploy-fastapi)
- [Render Static Sites](https://render.com/docs/static-sites)
- [Render Databases](https://render.com/docs/databases)
- [Environment Variables](https://render.com/docs/environment-variables)
