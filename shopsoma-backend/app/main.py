"""
Shopsoma Backend API
Main application entry point
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

# Load environment variables from .env file
load_dotenv()

# Basic logging configuration for app logs
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

# Import routers
from app.api.v1 import auth, products, images, admin, seed, cart, addresses, shipping_rates, orders, promo_codes, payments, users, wishlist, newsletter, preferences, payment_portals, vendors, vendor_activation, vendor_applications, vendor_payment_methods, categories, collections, designers, settings, admin_orders, admin_returns, admin_payouts, websocket

# Import middleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    print("🚀 Shopsoma API starting...")
    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    yield
    # Shutdown
    print("👋 Shopsoma API shutting down...")
    # TODO: Close database connections
    # TODO: Close Redis connections

app = FastAPI(
    title="Shopsoma API",
    description="Multi-vendor marketplace for African fashion",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan
)

# CORS Configuration
default_local_origins = [
    "http://localhost",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
    "http://127.0.0.1",
]
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS")
if allowed_origins_raw:
    allowed_origins = [
        origin.strip()
        for origin in allowed_origins_raw.split(",")
        if origin.strip()
    ]
else:
    allowed_origins = default_local_origins
allowed_origin_regex = os.getenv("ALLOWED_ORIGIN_REGEX", r"https?://localhost(:\d+)?")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_origin_regex=None,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Session-ID"],
)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add rate limiting middleware (5 requests per minute for auth endpoints)
# Temporarily disabled due to blocking issues - will fix and re-enable
# app.add_middleware(RateLimitMiddleware, rate_limit=5, window_seconds=60)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Welcome to Shopsoma API",
        "version": "1.0.0",
        "status": "operational"
    }

@app.get("/healthz")
async def health_check():
    """Health check endpoint for Render"""
    return {"status": "healthy"}

@app.get("/api/v1/health")
async def api_health_check():
    """API v1 health check endpoint"""
    from app.core.config import settings
    return {
        "status": "healthy",
        "version": "1.0.0",
        "paystack_configured": bool(settings.PAYSTACK_SECRET_KEY),
        "paystack_key_preview": settings.PAYSTACK_SECRET_KEY[:15] + "..." if settings.PAYSTACK_SECRET_KEY else "NOT SET"
    }

# Include routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(products.router, prefix="/api/v1")
app.include_router(images.router, prefix="/api/v1")
app.include_router(categories.router, prefix="/api/v1")
app.include_router(collections.router, prefix="/api/v1")
app.include_router(designers.router, prefix="/api/v1")
app.include_router(admin_orders.router, prefix="/api/v1")
app.include_router(admin_returns.router, prefix="/api/v1")
app.include_router(admin_payouts.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(seed.router, prefix="/api/v1")
app.include_router(cart.router, prefix="/api/v1")
app.include_router(addresses.router, prefix="/api/v1")
app.include_router(shipping_rates.router, prefix="/api/v1")
app.include_router(promo_codes.router, prefix="/api/v1")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(payments.router, prefix="/api/v1")
app.include_router(payment_portals.router, prefix="/api/v1/payments", tags=["Payment Portals"])
app.include_router(wishlist.router, prefix="/api/v1")
app.include_router(newsletter.router, prefix="/api/v1")
app.include_router(preferences.router, prefix="/api/v1")
app.include_router(vendors.router, prefix="/api/v1")
app.include_router(vendor_activation.router, prefix="/api/v1")
app.include_router(vendor_applications.router, prefix="/api/v1/vendor-applications", tags=["Vendor Applications"])
app.include_router(vendor_payment_methods.router, prefix="/api/v1")
app.include_router(settings.router, prefix="/api/v1")
app.include_router(websocket.router, prefix="/api/v1")

# Mount static files for local image uploads (development only)
from app.core.config import settings
if settings.USE_LOCAL_STORAGE:
    uploads_dir = Path(settings.LOCAL_UPLOAD_DIR)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")
    print(f"📁 Serving uploaded files from: {uploads_dir.absolute()}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
