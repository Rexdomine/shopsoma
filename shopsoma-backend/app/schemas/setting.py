"""Settings schemas"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class SettingBase(BaseModel):
    """Base setting schema"""
    key: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1)
    description: Optional[str] = None


class SettingCreate(SettingBase):
    """Schema for creating a new setting"""
    pass


class SettingUpdate(BaseModel):
    """Schema for updating a setting value"""
    value: str = Field(..., min_length=1)

    @field_validator('value')
    @classmethod
    def validate_value(cls, v: str, info) -> str:
        """Validate that value is not empty or only whitespace"""
        if not v or not v.strip():
            raise ValueError('Value cannot be empty or only whitespace')
        return v.strip()


class SettingResponse(SettingBase):
    """Schema for setting response"""
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExchangeRateUpdate(BaseModel):
    """Schema specifically for updating exchange rate"""
    rate: float = Field(..., gt=0, description="Exchange rate (1 USD = X NGN)")

    @field_validator('rate')
    @classmethod
    def validate_rate(cls, v: float) -> float:
        """Validate exchange rate is within reasonable bounds"""
        if v <= 0:
            raise ValueError('Exchange rate must be greater than 0')
        if v < 100 or v > 10000:
            raise ValueError('Exchange rate must be between 100 and 10,000 NGN per USD')
        return v


class ExchangeRateResponse(BaseModel):
    """Public exchange rate response"""
    rate: float
    updated_at: datetime
