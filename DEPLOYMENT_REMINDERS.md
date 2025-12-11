# Deployment Reminders for Render

## Date: December 7, 2025

---

## ⚠️ CRITICAL: Before Deploying to Render

### 1. Update CDN URL to Custom Domain

**Current Setup (Development)**:
```env
CDN_BASE_URL=https://pub-810c54dd4bfe4c4bba08d8cf059bade9.r2.dev
```

**Required for Production (Render)**:
```env
CDN_BASE_URL=https://cdn.shopsoma.com
```

**Steps to Set Up Custom Domain**:

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/) → **R2** → **Buckets** → **shopsoma-uploads**
2. Click **Settings** → **Custom Domains**
3. Click **Connect Domain**
4. Enter your custom domain: `cdn.shopsoma.com` (or `uploads.shopsoma.com`)
5. CloudFlare will automatically configure DNS (CNAME record)
6. Wait for DNS propagation (~5-10 minutes)
7. Update Render environment variables:
   - Variable: `CDN_BASE_URL`
   - Value: `https://cdn.shopsoma.com`

**Why Custom Domain is Important for Production**:
- ✅ Professional image URLs
- ✅ Automatic CloudFlare CDN caching (faster image loads worldwide)
- ✅ DDoS protection
- ✅ Better SEO (avoids `pub-xxxxx.r2.dev` in image URLs)
- ✅ SSL/HTTPS enabled automatically
- ✅ **Zero egress fees** (CloudFlare R2 bandwidth is always free!)

---

## 2. Environment Variables Checklist for Render

Make sure all these are set in Render dashboard:

### Database
```
DATABASE_URL=<render-postgresql-url>
```

### Security
```
SECRET_KEY=<production-secret-key-long-random-string>
ALGORITHM=HS256
ENVIRONMENT=production
DEBUG=false
```

### Payment Gateways
```
# Paystack
PAYSTACK_SECRET_KEY=<production-key>
PAYSTACK_PUBLIC_KEY=<production-key>

# Stripe
STRIPE_SECRET_KEY=<production-key>
STRIPE_PUBLISHABLE_KEY=<production-key>
```

### Email Service (Brevo)
```
BREVO_API_KEY=<your-brevo-key>
BREVO_SENDER_EMAIL=noreply@shopsoma.com
BREVO_SENDER_NAME=Shopsoma
```

### CloudFlare R2 Object Storage
```
USE_LOCAL_STORAGE=false
AWS_ACCESS_KEY_ID=01482f6255c71fac299f2c4d5f29f12d
AWS_SECRET_ACCESS_KEY=06e848b699dca56cbd2baddaaca730430ca913ea72d785d7dd706170d48acf7e
AWS_REGION=auto
S3_BUCKET_NAME=shopsoma-uploads
S3_ENDPOINT_URL=https://2ff0f98e15ecb3042837357b4502f1b5.r2.cloudflarestorage.com
CDN_BASE_URL=https://cdn.shopsoma.com  # ⚠️ MUST USE CUSTOM DOMAIN IN PRODUCTION
```

---

## 3. Security Checklist

### Before Deploying:
- [ ] Generate new `SECRET_KEY` for production (never use dev key in production!)
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(64))"
  ```
- [ ] Set `DEBUG=false`
- [ ] Set `ENVIRONMENT=production`
- [ ] Switch to production payment gateway keys (Paystack & Stripe)
- [ ] Verify all API keys are production-ready
- [ ] Set up custom domain for R2 CDN
- [ ] Configure CORS for production domain

### After Deploying:
- [ ] Test image uploads in production
- [ ] Verify images load from custom CDN domain
- [ ] Test payment processing
- [ ] Test email notifications
- [ ] Check CloudFlare R2 usage dashboard

---

## 4. Quick Reference: R2 Custom Domain Setup

### Option 1: Using CloudFlare Dashboard (Recommended)
1. R2 → Buckets → shopsoma-uploads → Settings → Custom Domains
2. Connect `cdn.shopsoma.com`
3. Wait for DNS propagation
4. Update `CDN_BASE_URL` in Render environment variables

### Option 2: Using CloudFlare DNS Manually
1. Go to CloudFlare DNS settings for `shopsoma.com`
2. Add CNAME record:
   - **Name**: `cdn`
   - **Target**: `shopsoma-uploads.2ff0f98e15ecb3042837357b4502f1b5.r2.cloudflarestorage.com`
   - **Proxy status**: Proxied (orange cloud) ✅
3. Wait for DNS propagation
4. Update `CDN_BASE_URL` in Render environment variables

---

## 5. Testing Checklist After Deployment

### Image Upload & Display
- [ ] Upload product image through vendor portal
- [ ] Verify image appears in product list
- [ ] Check image URL uses custom domain (`cdn.shopsoma.com`)
- [ ] Open image URL directly in browser
- [ ] Verify all 4 image variants load (thumbnail, medium, large, original)

### Payment Processing
- [ ] Test Paystack payment
- [ ] Test Stripe payment
- [ ] Verify payment confirmations
- [ ] Check email notifications

### Email Notifications
- [ ] Test order confirmation emails
- [ ] Test vendor application emails
- [ ] Test password reset emails

### General Functionality
- [ ] Test user registration
- [ ] Test vendor onboarding
- [ ] Test product creation
- [ ] Test order placement
- [ ] Test admin dashboard

---

## 6. Rollback Plan

If issues occur after deployment:

### Quick Rollback (Revert CDN URL)
1. Go to Render dashboard
2. Update `CDN_BASE_URL` back to public R2 URL:
   ```
   CDN_BASE_URL=https://pub-810c54dd4bfe4c4bba08d8cf059bade9.r2.dev
   ```
3. Restart Render service

### Full Rollback (Revert Deployment)
1. Go to Render dashboard → Deployments
2. Click on previous working deployment
3. Click "Redeploy"

---

## 7. Cost Monitoring

After deployment, monitor CloudFlare R2 usage:

### CloudFlare R2 Dashboard
- Storage usage (should stay under 10 GB for free tier)
- Class A operations (writes - free up to 1M/month)
- Class B operations (reads - free up to 10M/month)
- Egress (always free!)

### Set Up Alerts
1. Go to CloudFlare Dashboard → R2
2. Set up usage alerts:
   - Storage: Alert at 8 GB (80% of free tier)
   - Class A operations: Alert at 800K/month (80% of free tier)
   - Class B operations: Alert at 8M/month (80% of free tier)

---

## 8. Performance Optimization

### After Custom Domain Setup:

**CloudFlare CDN Benefits**:
- Images cached at CloudFlare edge locations worldwide
- Faster image loads for users globally
- Reduced origin requests (saves R2 operations)
- Automatic SSL/HTTPS
- DDoS protection

**Monitor Performance**:
- CloudFlare Analytics → CDN → Cache Hit Rate (should be >80%)
- CloudFlare Analytics → Performance → Bandwidth Saved
- Page load times (images should load <1s)

---

## Summary: Pre-Deployment Checklist

### Critical (Must Do):
- [ ] Set up custom domain for R2 CDN (`cdn.shopsoma.com`)
- [ ] Update `CDN_BASE_URL` in Render environment variables
- [ ] Generate new production `SECRET_KEY`
- [ ] Set `DEBUG=false` and `ENVIRONMENT=production`
- [ ] Switch to production payment gateway keys

### Recommended (Should Do):
- [ ] Set up CloudFlare R2 usage alerts
- [ ] Configure CORS for production domain
- [ ] Test all functionality in staging first
- [ ] Document rollback procedures

### Optional (Nice to Have):
- [ ] Enable CloudFlare analytics
- [ ] Set up monitoring/alerting
- [ ] Configure CDN cache rules
- [ ] Enable image optimization features

---

**Last Updated**: December 7, 2025
**Status**: Development environment configured with public R2 URL
**Next**: Set up custom domain before deploying to Render
