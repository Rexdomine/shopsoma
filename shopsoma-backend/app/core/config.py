"""Application configuration and settings.

This module defines the Settings class using Pydantic BaseSettings for loading
configuration from environment variables.
"""

import re
from typing import List, Optional
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application Settings
    APP_NAME: str = "Shopsoma"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # Security Settings
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Database Settings
    DATABASE_URL: str
    DATABASE_ECHO: bool = False
    ASYNC_DATABASE_URL: Optional[str] = None

    # Redis Settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: Optional[str] = Field(default=None, validation_alias=AliasChoices("REDIS_URL", "redis_url"))

    # Email Settings
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_FROM_NAME: str = "Shopsoma"
    FRONTEND_BASE_URL: str = "http://localhost:5173"

    # Email Branding
    BRAND_LOGO_URL: str = "/assets/email/somalogoemail.png"

    # AWS Settings
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = ""
    AWS_S3_BUCKET: str = ""
    AWS_S3_ENDPOINT_URL: Optional[str] = None

    # Payment Settings
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_PUBLIC_KEY: str = ""

    # CORS Settings
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:5173,http://localhost:5174",
        validation_alias=AliasChoices("ALLOWED_ORIGINS", "allowed_origins"),
    )
    ALLOWED_ORIGIN_REGEX: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("ALLOWED_ORIGIN_REGEX", "allowed_origin_regex"),
    )

    # Celery Settings
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    # Brevo Email Service
    BREVO_API_KEY: str = ""
    BREVO_SENDER_EMAIL: str = "noreply@shopsoma.com"
    BREVO_SENDER_NAME: str = "Shopsoma"
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
    S3_BUCKET_NAME: str = "shopsoma-uploads"
    S3_ENDPOINT_URL: str = ""  # For CloudFlare R2 or MinIO
    CDN_BASE_URL: str = ""  # CloudFront or CloudFlare CDN

    # Image Processing
    MAX_IMAGE_SIZE_MB: int = 5
    ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/webp"
    IMAGE_QUALITY: int = 85
    THUMBNAIL_SIZE: str = "300,300"
    MEDIUM_SIZE: str = "800,800"
    LARGE_SIZE: str = "1600,1600"

    # Business Settings
    DEFAULT_COMMISSION_RATE: float = 12.5
    PAYOUT_HOLD_DAYS: int = 14
    PASSWORD_RESET_EXPIRE_MINUTES: int = 60

    # Admin Settings
    ADMIN_EMAIL: str = "admin@shopsoma.com"

    # Pagination Settings
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Security Headers
    SECURITY_HEADERS_ENABLED: bool = True

    # Default Currency
    DEFAULT_CURRENCY: str = "NGN"

    # DHL settings (legacy — referenced by .env but not used by Phase 4)
    DHL_ENABLED: bool = False
    DHL_ENVIRONMENT: str = "sandbox"
    DHL_API_USERNAME: str = ""
    DHL_API_PASSWORD: str = ""
    DHL_EXPORT_ACCOUNT_NUMBER: str = ""
    DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED: bool = False

    # DHL domestic Phase 4 workflow feature gates
    DHL_DOMESTIC_WORKFLOW_ENABLED: bool = False
    DHL_DOMESTIC_PROVIDER_CALLS_ENABLED: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "forbid"

    def model_post_init(self, __context) -> None:
        if not self.ASYNC_DATABASE_URL:
            self.ASYNC_DATABASE_URL = self._build_async_db_url(self.DATABASE_URL)
        if self.AWS_S3_BUCKET and not self.S3_BUCKET_NAME:
            self.S3_BUCKET_NAME = self.AWS_S3_BUCKET
        if self.AWS_S3_ENDPOINT_URL and not self.S3_ENDPOINT_URL:
            self.S3_ENDPOINT_URL = self.AWS_S3_ENDPOINT_URL
        if self.S3_BUCKET_NAME and not self.AWS_S3_BUCKET:
            self.AWS_S3_BUCKET = self.S3_BUCKET_NAME
        if self.S3_ENDPOINT_URL and not self.AWS_S3_ENDPOINT_URL:
            self.AWS_S3_ENDPOINT_URL = self.S3_ENDPOINT_URL

    @staticmethod
    def _build_async_db_url(database_url: str) -> str:
        if database_url.startswith("postgresql+asyncpg://"):
            return database_url
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)
        if database_url.startswith("postgresql://"):
            return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return database_url

    @staticmethod
    def get_masked_db_url(database_url: str) -> str:
        return re.sub(r"://([^:]+):([^@]+)@", r"://\\1:***@", database_url)


settings = Settings()
