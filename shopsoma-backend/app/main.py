import logging
from pathlib import Path
import os
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
logger = logging.getLogger(__name__)

# Import routers
from app.api.v1 import auth, products, images, admin, seed, cart, addresses, shipping_rates, orders, promo_codes, payments, users, wishlist, newsletter, preferences, payment_portals, vendors, vendor_activation, vendor_applications, vendor_payment_methods, categories, collections, designers, settings as settings_router, admin_orders, admin_returns, admin_payouts, websocket
from app.core.config import settings

# Import middleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Shopsoma API starting")
    logger.info(
        "Storage backend: %s",
        f"local ({Path(settings.LOCAL_UPLOAD_DIR).resolve()})" if settings.USE_LOCAL_STORAGE else f"object ({settings.S3_BUCKET_NAME})"
    )
    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    yield
    # Shutdown
    logger.info("Shopsoma API shutting down")
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_origin_regex=settings.ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Session-ID"],
)

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

if settings.RATE_LIMIT_ENABLED:
    app.add_middleware(
        RateLimitMiddleware,
        rate_limit=settings.RATE_LIMIT_REQUESTS,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        trusted_proxy_ips=settings.trusted_proxy_ips_list,
    )

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
    return {
        "status": "healthy",
        "version": "1.0.0",
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
app.include_router(settings_router.router, prefix="/api/v1")
app.include_router(websocket.router, prefix="/api/v1")

# Mount static files for local image uploads (development only)
if settings.USE_LOCAL_STORAGE:
    uploads_dir = Path(settings.LOCAL_UPLOAD_DIR)
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")
    logger.info("Serving uploaded files from %s", uploads_dir.resolve())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
