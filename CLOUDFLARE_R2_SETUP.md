# CloudFlare R2 Setup Guide

## Date: December 7, 2025

## Overview
Complete guide to set up CloudFlare R2 object storage for Shopsoma image uploads.

---

## Your R2 Account Details

**Account ID**: `2ff0f98e15ecb3042837357b4502f1b5`
**S3 API Endpoint**: `https://2ff0f98e15ecb3042837357b4502f1b5.r2.cloudflarestorage.com`

---

## Step 1: Create R2 API Token

1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. Navigate to **R2** → **Overview**
3. Click **Manage R2 API Tokens** (right side)
4. Click **Create API Token**
5. Configure the token:
   - **Token Name**: `Shopsoma Upload Token`
   - **Permissions**: **Object Read & Write**
   - **TTL**: Never expire (or set custom expiry)
6. Click **Create API Token**

You'll receive:
- ✅ **Access Key ID** (starts with alphanumeric characters)
- ✅ **Secret Access Key** (long random string - **SAVE THIS NOW, it's only shown once!**)

**Important**: Copy both keys immediately and save them securely!

---

## Step 2: Create R2 Bucket

1. In Cloudflare Dashboard, go to **R2** → **Overview**
2. Click **Create bucket**
3. Configure bucket:
   - **Bucket name**: `shopsoma-uploads`
   - **Location**: Choose closest to your users (e.g., Automatic, WNAM for North America, ENAM for Europe)
4. Click **Create bucket**

**Note**: R2 bucket names must be unique across your account.

---

## Step 3: Configure Backend Environment Variables

Once you have the credentials, update your `.env` file:

### Current Configuration (Development - Local Storage)
```env
USE_LOCAL_STORAGE=true
LOCAL_UPLOAD_DIR=uploads
```

### Production Configuration (CloudFlare R2)
```env
# Switch to R2
USE_LOCAL_STORAGE=false

# R2 Credentials (from Step 1)
AWS_ACCESS_KEY_ID=<YOUR_R2_ACCESS_KEY_ID>
AWS_SECRET_ACCESS_KEY=<YOUR_R2_SECRET_ACCESS_KEY>

# R2 Configuration
AWS_REGION=auto
S3_BUCKET_NAME=shopsoma-uploads
S3_ENDPOINT_URL=https://2ff0f98e15ecb3042837357b4502f1b5.r2.cloudflarestorage.com

# Optional: CloudFlare CDN (if you set up a custom domain)
CDN_BASE_URL=
```

**File location**: `/Users/rex/Documents/Shopsoma/shopsoma-backend/.env`

---

## Step 4: Enable Public Access (Optional but Recommended)

For product images to be publicly accessible:

### Option A: R2 Public Buckets (Simple)
1. Go to **R2** → **Buckets** → **shopsoma-uploads**
2. Click **Settings**
3. Under **Public access**, click **Allow Access**
4. Confirm by typing the bucket name
5. Note the public bucket URL (e.g., `https://pub-xxxxx.r2.dev`)
6. Update `.env`:
   ```env
   CDN_BASE_URL=https://pub-xxxxx.r2.dev
   ```

### Option B: Custom Domain with CloudFlare CDN (Professional)
1. Go to **R2** → **Buckets** → **shopsoma-uploads**
2. Click **Settings** → **Custom Domains**
3. Click **Connect Domain**
4. Choose or add domain (e.g., `cdn.shopsoma.com` or `uploads.shopsoma.com`)
5. CloudFlare will automatically configure DNS
6. Update `.env`:
   ```env
   CDN_BASE_URL=https://cdn.shopsoma.com
   ```

**Benefits of Custom Domain**:
- ✅ Professional URLs (cdn.shopsoma.com vs pub-xxxxx.r2.dev)
- ✅ Automatic CloudFlare CDN caching
- ✅ DDoS protection
- ✅ Better SEO
- ✅ No bandwidth charges (CloudFlare R2 has zero egress fees!)

---

## Step 5: Test the Configuration

### 5.1 Update .env with Your Credentials
```bash
# Edit the .env file
nano /Users/rex/Documents/Shopsoma/shopsoma-backend/.env
```

Replace:
```env
AWS_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID_HERE
AWS_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY_HERE
```

With your actual R2 credentials.

### 5.2 Switch to R2
```env
USE_LOCAL_STORAGE=false
```

### 5.3 Restart Backend Server
The server will automatically reload and use R2.

### 5.4 Test Upload
1. Go to vendor product creation page
2. Upload an image
3. Check R2 bucket for uploaded files
4. Verify image URLs work

---

## How It Works

### Image Upload Flow with R2

1. **User uploads image** → Frontend sends to `/api/v1/images/upload`
2. **Backend validates** → Checks file type and size
3. **Backend processes** → Compresses and resizes image
4. **Backend uploads to R2**:
   - Original: `products/2025/12/abc123_original.jpg`
   - Thumbnail: `products/2025/12/abc123_thumbnail.jpg`
   - Medium: `products/2025/12/abc123_medium.jpg`
   - Large: `products/2025/12/abc123_large.jpg`
5. **Backend returns URLs**:
   ```json
   {
     "original": "https://cdn.shopsoma.com/products/2025/12/abc123_original.jpg",
     "thumbnail": "https://cdn.shopsoma.com/products/2025/12/abc123_thumbnail.jpg",
     "medium": "https://cdn.shopsoma.com/products/2025/12/abc123_medium.jpg",
     "large": "https://cdn.shopsoma.com/products/2025/12/abc123_large.jpg",
     "s3_key": "products/2025/12/abc123_original.jpg"
   }
   ```
6. **Frontend stores URLs** → Saves to product data
7. **Product displays** → Shows images from R2 CDN

---

## File Structure in R2 Bucket

```
shopsoma-uploads/
├── products/
│   └── 2025/
│       └── 12/
│           ├── abc123_original.jpg       (Full size, compressed)
│           ├── abc123_thumbnail.jpg      (300x300)
│           ├── abc123_medium.jpg         (800x800)
│           └── abc123_large.jpg          (1600x1600)
├── avatars/
│   └── 2025/
│       └── 12/
│           └── user-avatar.jpg
└── ... (other folders)
```

**Organization**:
- Folder by purpose (`products`, `avatars`, etc.)
- Year/Month subfolders for organization
- Unique filenames to prevent collisions

---

## Cost Analysis

### CloudFlare R2 Pricing (as of Dec 2025)
- **Storage**: $0.015/GB/month (first 10 GB free)
- **Class A Operations** (writes): $4.50/million (first 1 million free/month)
- **Class B Operations** (reads): $0.36/million (first 10 million free/month)
- **Egress**: **$0** (FREE - unlimited bandwidth!)

### Example Cost for Shopsoma:
**Assumptions**:
- 1,000 products
- 4 images per product (original + 3 variants)
- Average 500 KB per image
- 10,000 views per month

**Storage**:
- Total images: 4,000
- Total storage: ~2 GB
- Cost: **$0** (under 10 GB free tier)

**Operations**:
- Uploads per month: ~500 (new products)
- Reads per month: ~50,000 (views × variants)
- Cost: **$0** (under free tier)

**Egress**: **$0** (always free on R2!)

**Total Monthly Cost**: **~$0** 🎉

**Comparison to AWS S3**:
- AWS S3 would charge $4.50/month for egress on 50 GB bandwidth
- R2 saves you money from day one!

---

## Security Best Practices

### 1. API Token Security
- ✅ Never commit API tokens to git
- ✅ Use environment variables (`.env`)
- ✅ Add `.env` to `.gitignore`
- ✅ Rotate tokens periodically

### 2. Bucket Permissions
- ✅ Use Object Read & Write (not Admin)
- ✅ Don't enable public writes
- ✅ Only allow reads if using public bucket

### 3. CORS Configuration
If using custom domain, configure CORS in R2:
```json
[
  {
    "AllowedOrigins": ["https://shopsoma.com", "https://www.shopsoma.com"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }
]
```

---

## Troubleshooting

### Error: "Access Denied"
**Cause**: Incorrect credentials or insufficient permissions
**Fix**: Verify `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are correct

### Error: "Bucket not found"
**Cause**: Bucket name mismatch
**Fix**: Ensure `S3_BUCKET_NAME=shopsoma-uploads` matches actual bucket name

### Error: "Invalid endpoint"
**Cause**: Wrong endpoint URL
**Fix**: Use `https://2ff0f98e15ecb3042837357b4502f1b5.r2.cloudflarestorage.com`

### Images not loading in browser
**Cause**: Bucket not public or CORS not configured
**Fix**: Enable public access in R2 bucket settings

---

## Migration from Local to R2

### Option 1: Fresh Start (Recommended for New Projects)
1. Update `.env` to use R2
2. Restart backend
3. Upload new images (old local images stay in `uploads/`)
4. No data migration needed

### Option 2: Migrate Existing Images
If you have existing images in `uploads/`:
1. Install AWS CLI or R2 CLI
2. Upload existing images:
   ```bash
   aws s3 sync uploads/ s3://shopsoma-uploads/ \
     --endpoint-url https://2ff0f98e15ecb3042837357b4502f1b5.r2.cloudflarestorage.com
   ```
3. Update database to use R2 URLs (if needed)

---

## Summary Checklist

### Initial Setup
- [ ] Create R2 API token (get Access Key ID and Secret Key)
- [ ] Create R2 bucket (`shopsoma-uploads`)
- [ ] Update `.env` with R2 credentials
- [ ] Set `USE_LOCAL_STORAGE=false`
- [ ] Restart backend server
- [ ] Test image upload

### Optional (Recommended for Production)
- [ ] Enable public access on R2 bucket
- [ ] Set up custom domain (cdn.shopsoma.com)
- [ ] Configure CORS for your domain
- [ ] Update `CDN_BASE_URL` in `.env`
- [ ] Test CDN URLs work

### Security
- [ ] Verify `.env` is in `.gitignore`
- [ ] Use Object Read & Write permissions only
- [ ] Consider token rotation schedule

---

## Quick Start Commands

```bash
# 1. Navigate to backend directory
cd /Users/rex/Documents/Shopsoma/shopsoma-backend

# 2. Edit .env file
nano .env

# 3. Update these values:
#    - AWS_ACCESS_KEY_ID=<your-access-key>
#    - AWS_SECRET_ACCESS_KEY=<your-secret-key>
#    - USE_LOCAL_STORAGE=false

# 4. Save and exit (Ctrl+X, Y, Enter)

# 5. Server will auto-reload or restart manually:
# (Server should already be running with --reload flag)

# 6. Test upload through frontend
```

---

## What You Need to Provide

Please share these with me once you have them:

1. **R2 Access Key ID** - From API token creation
2. **R2 Secret Access Key** - From API token creation
3. **Bucket Name** - Confirm it's `shopsoma-uploads` or let me know if different
4. **(Optional) Public Bucket URL or Custom Domain** - For CDN configuration

Once I have these, I'll update your `.env` file with the correct values and we can test the R2 integration!

---

**Status**: ✅ R2 Configured - ⚠️ Public Access Setup Required
**Next Steps**: Enable public access on R2 bucket → Update CDN_BASE_URL → Test upload

**Date**: December 7, 2025
**Last Updated**: December 7, 2025 (R2 credentials configured)
