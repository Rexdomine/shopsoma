"""App settings schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class AppSettingBase(BaseModel):
    """Base app setting schema"""
    key: str = Field(..., min_length=1, max_length=100)
    value: Optional[str] = None
    value_type: str = Field(default="string", pattern="^(string|boolean|json)$")
    description: Optional[str] = None
    is_public: bool = False


class AppSettingCreate(AppSettingBase):
    """Create app setting"""
    pass


class AppSettingUpdate(BaseModel):
    """Update app setting"""
    value: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None


class AppSettingResponse(AppSettingBase):
    """App setting response"""
    id: UUID

    class Config:
        from_attributes = True


class ShippingProviderSettings(BaseModel):
    """Shipping provider settings"""
    use_shipbubble: bool = Field(default=False, description="Use ShipBubble for shipping rates")


class ShippingProviderSettingsUpdate(BaseModel):
    """Update shipping provider settings"""
    use_shipbubble: bool


class PayoutHoldSettings(BaseModel):
    """Payout hold settings"""
    hold_days: int = Field(default=14, ge=0, le=3650)
    updated_at: Optional[datetime] = None


class PayoutHoldSettingsUpdate(BaseModel):
    """Update payout hold settings"""
    hold_days: int = Field(..., ge=0, le=3650)


class DatabaseSyncResponse(BaseModel):
    """Database sync response"""
    status: str = Field(..., pattern="^(success|error)$")
    message: str
    duration_seconds: Optional[float] = None
