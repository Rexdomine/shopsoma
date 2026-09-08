"""Application configuration and settings.

This module defines the Settings class using Pydantic BaseSettings for loading
configuration from environment variables.
"""

import re
from typing import List, Literal, Optional
from uuid import UUID
from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
    )

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
    RENDER_DATABASE_URL: str = ""

    # Redis Settings
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("REDIS_URL", "redis_url")
    )

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
    STRIPE_WEBHOOK_SECRET: str = ""
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

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 5
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    TRUSTED_PROXY_IPS: str = ""

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

    # DHL Express MyDHL API
    # Docs: https://developer.dhl.com/api-reference/dhl-express-mydhl-api
    DHL_ENABLED: bool = False
    DHL_ENVIRONMENT: Literal["sandbox", "production"] = "sandbox"
    DHL_API_USERNAME: SecretStr = SecretStr("")
    DHL_API_PASSWORD: SecretStr = SecretStr("")
    DHL_EXPORT_ACCOUNT_NUMBER: SecretStr = SecretStr("")
    DHL_IMPORT_ACCOUNT_NUMBER: SecretStr = SecretStr("")
    DHL_REQUEST_TIMEOUT_SECONDS: float = Field(default=30.0, ge=1, le=60)

    # Domestic DHL workflow safety gates
    DHL_DOMESTIC_WORKFLOW_ENABLED: bool = False
    DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED: bool = False
    DHL_DOMESTIC_PROVIDER_CALLS_ENABLED: bool = False
    DHL_DOMESTIC_SANDBOX_COHORT_IDS: str = ""
    DHL_DOMESTIC_QUOTE_TTL_SECONDS: int = Field(default=1800, ge=300, le=3600)
    DHL_DOMESTIC_PAYMENT_WINDOW_SECONDS: int = Field(default=1800, ge=300, le=3600)
    DHL_DOMESTIC_AUTH_GRACE_SECONDS: int = Field(default=900, ge=60, le=1800)

    # Checkout prerequisites remain inert until a separately approved rollout.
    DOMESTIC_CHECKOUT_PREREQUISITES_ENABLED: bool = False
    DOMESTIC_CHECKOUT_COHORT_ALLOWLIST: str = ""
    DOMESTIC_CHECKOUT_COHORT_PERCENTAGE: int = Field(default=0, ge=0, le=100)
    CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION: Optional[int] = None
    CHECKOUT_CAPABILITY_ACTIVE_PEPPER: SecretStr = SecretStr("")
    CHECKOUT_CAPABILITY_PREVIOUS_PEPPER_VERSION: Optional[int] = None
    CHECKOUT_CAPABILITY_PREVIOUS_PEPPER: SecretStr = SecretStr("")

    @property
    def domestic_checkout_cohort_ids(self) -> frozenset[UUID]:
        raw = self.DOMESTIC_CHECKOUT_COHORT_ALLOWLIST
        if not raw:
            return frozenset()
        values = raw.split(",")
        if any(value != value.strip() or not value for value in values):
            return frozenset()
        try:
            parsed = tuple(UUID(value) for value in values)
        except ValueError:
            return frozenset()
        if len(set(parsed)) != len(parsed) or any(
            str(item) != raw_item for item, raw_item in zip(parsed, values)
        ):
            return frozenset()
        return frozenset(parsed)

    @property
    def checkout_capability_configured(self) -> bool:
        return bool(
            self.CHECKOUT_CAPABILITY_ACTIVE_PEPPER_VERSION
            and self.CHECKOUT_CAPABILITY_ACTIVE_PEPPER.get_secret_value()
        )

    @property
    def dhl_base_url(self) -> str:
        """Return the fixed official MyDHL API URL for the selected environment."""
        if self.DHL_ENVIRONMENT == "production":
            return "https://express.api.dhl.com/mydhlapi"
        return "https://express.api.dhl.com/mydhlapi/test"

    @property
    def dhl_configured(self) -> bool:
        """Return whether DHL is enabled with the minimum required configuration."""
        return self.DHL_ENABLED and all(
            secret.get_secret_value()
            for secret in (
                self.DHL_API_USERNAME,
                self.DHL_API_PASSWORD,
                self.DHL_EXPORT_ACCOUNT_NUMBER,
            )
        )

    @property
    def dhl_domestic_sandbox_cohort_ids(self) -> frozenset[UUID]:
        """Return a strict allowlist; malformed or duplicate values fail closed."""
        raw_values = self.DHL_DOMESTIC_SANDBOX_COHORT_IDS.split(",")
        if not raw_values or any(
            value != value.strip() or not value for value in raw_values
        ):
            return frozenset()
        try:
            cohort_ids = tuple(UUID(value) for value in raw_values)
        except ValueError:
            return frozenset()
        if any(str(cohort_id) != raw for cohort_id, raw in zip(cohort_ids, raw_values)):
            return frozenset()
        if len(set(cohort_ids)) != len(cohort_ids):
            return frozenset()
        return frozenset(cohort_ids)

    @property
    def FRONTEND_URL(self) -> str:
        """Alias for FRONTEND_BASE_URL for backward compatibility"""
        return self.FRONTEND_BASE_URL

    @property
    def allowed_origins_list(self) -> List[str]:
        return [
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def trusted_proxy_ips_list(self) -> List[str]:
        return [
            proxy_ip.strip()
            for proxy_ip in self.TRUSTED_PROXY_IPS.split(",")
            if proxy_ip.strip()
        ]

    # S3/Object Storage
    USE_LOCAL_STORAGE: Optional[bool] = None  # Defaults to local only in development
    ALLOW_LOCAL_STORAGE_IN_NON_DEV: bool = False
    LOCAL_UPLOAD_DIR: str = "uploads"  # Directory for local uploads
    S3_BUCKET_NAME: str = ""
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

    @model_validator(mode="after")
    def _validate_settings(self):
        environment = self.ENVIRONMENT.lower()

        if self.DHL_ENABLED:
            required_dhl_fields = {
                "DHL_API_USERNAME": self.DHL_API_USERNAME,
                "DHL_API_PASSWORD": self.DHL_API_PASSWORD,
                "DHL_EXPORT_ACCOUNT_NUMBER": self.DHL_EXPORT_ACCOUNT_NUMBER,
            }
            missing_dhl_fields = [
                field_name
                for field_name, secret in required_dhl_fields.items()
                if not secret.get_secret_value()
            ]
            if missing_dhl_fields:
                missing = ", ".join(missing_dhl_fields)
                raise ValueError(
                    "DHL is enabled but required settings are missing: " + missing
                )

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
        if self.USE_LOCAL_STORAGE is None:
            self.USE_LOCAL_STORAGE = environment == "development"
        if (
            environment != "development"
            and self.USE_LOCAL_STORAGE
            and not self.ALLOW_LOCAL_STORAGE_IN_NON_DEV
        ):
            raise ValueError(
                "USE_LOCAL_STORAGE cannot default to true outside development. "
                "Set USE_LOCAL_STORAGE=false with object storage credentials, or "
                "explicitly set ALLOW_LOCAL_STORAGE_IN_NON_DEV=true for a temporary non-production fallback."
            )
        if not self.USE_LOCAL_STORAGE:
            missing_storage_fields = [
                field_name
                for field_name, value in {
                    "AWS_ACCESS_KEY_ID": self.AWS_ACCESS_KEY_ID,
                    "AWS_SECRET_ACCESS_KEY": self.AWS_SECRET_ACCESS_KEY,
                    "AWS_REGION": self.AWS_REGION,
                    "S3_BUCKET_NAME": self.S3_BUCKET_NAME,
                }.items()
                if not value
            ]
            if missing_storage_fields:
                missing = ", ".join(missing_storage_fields)
                raise ValueError(
                    f"Object storage is enabled but required settings are missing: {missing}"
                )
        return self

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
