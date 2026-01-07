"""
Core application configuration
"""
from pydantic_settings import BaseSettings
from typing import List, Optional
import os
from urllib.parse import urlparse


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = "Shopsoma API"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    # IMPORTANT: DATABASE_URL is the single source of truth for database connection
    # Both Alembic (sync) and FastAPI async engine MUST point to the same database
    DATABASE_URL: str
    DATABASE_ECHO: bool = False
    RENDER_DATABASE_URL: str = ""

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        """
        Derive async database URL from DATABASE_URL
        Converts postgresql:// to postgresql+asyncpg:// for async engine
        """
        if self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif self.DATABASE_URL.startswith("postgresql+asyncpg://"):
            return self.DATABASE_URL
        return self.DATABASE_URL

    def get_masked_db_url(self, url: str) -> str:
        """
        Return safe database URL for logging (password masked)
        Example output: "host=localhost db=shopsoma_db"
        """
        try:
            parsed = urlparse(url)
            host = parsed.hostname or "unknown"
            db_name = parsed.path.lstrip("/") or "unknown"
            return f"host={host} db={db_name}"
        except Exception:
            return "host=unknown db=unknown"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT Authentication
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    CUSTOMER_ACCESS_TOKEN_EXPIRE_DAYS: int = 3650
    CUSTOMER_REFRESH_TOKEN_EXPIRE_DAYS: int = 3650

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    ALLOWED_ORIGINS: Optional[str] = None
    ALLOWED_ORIGIN_REGEX: Optional[str] = None

    # Stripe
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Paystack
    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_PUBLIC_KEY: str = ""

    # Email
    SENDGRID_API_KEY: str = ""
    FROM_EMAIL: str = "noreply@shopsoma.com"

    # Brevo Email Service
    BREVO_API_KEY: str = ""
    BREVO_SENDER_EMAIL: str = "noreply@shopsoma.com"
    BREVO_SENDER_NAME: str = "Shopsoma"
    BRAND_LOGO_URL: str = "https://shopsoma.com/assets/email/logo-mark.png"
    FRONTEND_BASE_URL: str = "https://shopsoma.com"
    BREVO_NEWSLETTER_LIST_ID: Optional[int] = None

    # ShipBubble Shipping Service
    # Docs: https://docs.shipbubble.com
    SHIPBUBBLE_API_KEY: str = ""
    SHIPBUBBLE_WEBHOOK_SECRET: str = ""  # For webhook signature verification

    @property
    def FRONTEND_URL(self) -> str:
        """Alias for FRONTEND_BASE_URL for backward compatibility"""
        return self.FRONTEND_BASE_URL

    # S3/Object Storage
    USE_LOCAL_STORAGE: bool = True  # Use local file storage for development
    LOCAL_UPLOAD_DIR: str = "uploads"  # Directory for local uploads
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "shopsoma-uploads"
    S3_ENDPOINT_URL: str = ""  # For CloudFlare R2 or MinIO
    CDN_BASE_URL: str = ""  # CloudFront or CloudFlare CDN

    # Image Processing
    MAX_IMAGE_SIZE_MB: int = 10
    ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/webp,image/gif"
    IMAGE_QUALITY: int = 85
    THUMBNAIL_SIZE: str = "300,300"
    MEDIUM_SIZE: str = "800,800"
    LARGE_SIZE: str = "1600,1600"

    # Business Settings
    DEFAULT_COMMISSION_RATE: float = 12.5
    PAYOUT_HOLD_DAYS: int = 14

    # Admin Settings
    ADMIN_EMAIL: str = "admin@shopsoma.com"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
