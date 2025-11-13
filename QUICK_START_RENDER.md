# 🚀 Quick Start: Deploy to Render in 5 Steps

**Time to deploy**: ~20 minutes
**Cost**: Free tier (first 90 days)

## Step 1: Push to GitHub (2 minutes)

```bash
# Make sure you're on develop branch
git checkout develop

# Add all deployment files
git add .

# Commit
git commit -m "chore: add Render deployment configuration"

# Push
git push origin develop
```

## Step 2: Sign Up for Render (2 minutes)

1. Go to https://render.com
2. Click **"Get Started for Free"**
3. Choose **"Sign up with GitHub"**
4. Authorize Render to access your repositories

## Step 3: Deploy with Blueprint (1 minute)

1. In Render Dashboard, click **"New"** → **"Blueprint"**
2. Select your repository: `shopsoma`
3. Render detects `render.yaml` automatically
4. Click **"Apply"**
5. Wait while Render creates:
   - ✅ PostgreSQL database
   - ✅ Backend API
   - ✅ Frontend

**Estimated time**: 10-15 minutes

## Step 4: Seed Database (3 minutes)

Once backend shows "Live":

1. Go to `shopsoma-staging-api` service
2. Click **"Shell"** tab
3. Run these commands:

```bash
python seed_products.py
python activate_products.py
python update_products_with_variations.py
```

## Step 5: Test Your Site! (2 minutes)

1. **Frontend**: Click the URL for `shopsoma-staging`
   - Should look like: `https://shopsoma-staging.onrender.com`

2. **Backend API**: Click the URL for `shopsoma-staging-api`, add `/docs`
   - Should look like: `https://shopsoma-staging-api.onrender.com/docs`

3. **Verify**:
   - ✅ Homepage loads
   - ✅ Products display with images
   - ✅ Can navigate to product details
   - ✅ Size guide works

## 🎉 You're Done!

Your staging site is live and auto-deploys whenever you push to `develop`!

---

## URLs You'll Get

After deployment, you'll have:

- **Frontend (your main site)**:
  ```
  https://shopsoma-staging.onrender.com
  ```

- **Backend API**:
  ```
  https://shopsoma-staging-api.onrender.com
  ```

- **API Documentation**:
  ```
  https://shopsoma-staging-api.onrender.com/docs
  ```

- **Database**:
  ```
  Internal connection (used by backend automatically)
  ```

---

## Common Issues

### 🐌 Site is slow to load first time
**This is normal!** Free tier services "spin down" after 15 minutes of inactivity. First request takes 30-60 seconds to wake up.

### ❌ Backend shows error
Check logs: Service → Logs tab. Common fixes:
- Wait for database to finish provisioning
- Verify environment variables are set
- Check that migrations ran successfully

### 🖼️ Images not loading
This is expected if using Unsplash URLs. Some may fail. We'll add proper image upload later.

---

## Next Steps

1. **Share with your team**:
   ```
   Staging Site: https://shopsoma-staging.onrender.com
   Auto-deploys from: develop branch
   ```

2. **Start testing**: Create test orders, test checkout flow

3. **Keep developing**: Every push to `develop` auto-deploys

4. **When ready for production**: Merge `develop` → `main`

---

## Need Help?

- 📖 Full Guide: See `RENDER_DEPLOYMENT.md`
- ✅ Checklist: See `DEPLOYMENT_CHECKLIST.md`
- 💬 Community: https://community.render.com
- 📧 Support: support@render.com
