"""Promo code schemas"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal
from app.models.promo_code import DiscountType


def _normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class PromoCodeBase(BaseModel):
    """Base promo code schema"""
    code: str = Field(..., min_length=3, max_length=50, description="Promo code")
    description: Optional[str] = Field(None, max_length=500)
    discount_type: DiscountType
    discount_value: Decimal = Field(..., gt=0, description="Discount value")
    min_purchase_amount: Optional[Decimal] = Field(default=Decimal("0.00"), ge=0)
    max_discount_amount: Optional[Decimal] = Field(None, ge=0)
    usage_limit: Optional[int] = Field(None, ge=1, description="Total usage limit")
    usage_limit_per_user: int = Field(default=1, ge=1, description="Usage limit per user")
    valid_from: datetime
    valid_until: datetime
    is_active: bool = Field(default=True)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if len(cleaned) < 3:
            raise ValueError("Promo code must be at least 3 characters")
        return cleaned

    @model_validator(mode="after")
    def validate_dates_and_discount(self):
        if _normalize_dt(self.valid_until) <= _normalize_dt(self.valid_from):
            raise ValueError("valid_until must be after valid_from")
        if self.discount_type == DiscountType.PERCENTAGE and self.discount_value > Decimal("100"):
            raise ValueError("Percentage discount value cannot exceed 100")
        return self


class PromoCodeCreate(PromoCodeBase):
    """Schema for creating a promo code"""
    pass


class PromoCodeUpdate(BaseModel):
    """Schema for updating a promo code"""
    code: Optional[str] = Field(None, min_length=3, max_length=50)
    description: Optional[str] = Field(None, max_length=500)
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[Decimal] = Field(None, gt=0)
    min_purchase_amount: Optional[Decimal] = Field(None, ge=0)
    max_discount_amount: Optional[Decimal] = Field(None, ge=0)
    usage_limit: Optional[int] = Field(None, ge=1)
    usage_limit_per_user: Optional[int] = Field(None, ge=1)
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    is_active: Optional[bool] = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip().upper()
        if len(cleaned) < 3:
            raise ValueError("Promo code must be at least 3 characters")
        return cleaned

    @model_validator(mode="after")
    def validate_dates_and_discount(self):
        if self.valid_from is not None and self.valid_until is not None:
            if _normalize_dt(self.valid_until) <= _normalize_dt(self.valid_from):
                raise ValueError("valid_until must be after valid_from")
        if (
            self.discount_type == DiscountType.PERCENTAGE
            and self.discount_value is not None
            and self.discount_value > Decimal("100")
        ):
            raise ValueError("Percentage discount value cannot exceed 100")
        return self


class PromoCodeResponse(PromoCodeBase):
    """Schema for promo code response"""
    id: UUID
    usage_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PromoCodeListResponse(BaseModel):
    """Schema for list of promo codes"""
    promo_codes: list[PromoCodeResponse]
    total: int


class PromoCodeValidateRequest(BaseModel):
    """Request schema for validating a promo code"""
    code: str = Field(..., min_length=1, max_length=50)
    order_subtotal: Decimal = Field(..., gt=0, description="Order subtotal")
    currency: str = Field(default="NGN", max_length=3, description="Checkout currency")
    customer_email: Optional[str] = Field(None, max_length=255)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Promo code is required")
        return cleaned

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, v: str) -> str:
        return (v or "NGN").strip().upper()


class PromoCodeValidateResponse(BaseModel):
    """Response schema for promo code validation"""
    valid: bool
    code: Optional[str] = None
    discount_type: Optional[DiscountType] = None
    discount_value: Optional[Decimal] = None
    discount_amount: Optional[Decimal] = None  # Calculated discount
    currency: Optional[str] = "NGN"
    message: Optional[str] = None  # Error message if invalid
