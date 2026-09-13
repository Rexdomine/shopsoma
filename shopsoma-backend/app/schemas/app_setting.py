"""App settings schemas"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Literal
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
    """Effective selection and readiness; legacy response field is retained."""
    provider: Literal["manual", "shipbubble", "dhl"] = "manual"
    use_shipbubble: bool = False
    checkout_estimates_required: bool = False
    readiness: dict[str, bool] = Field(default_factory=lambda: {
        "manual": True, "shipbubble": False, "dhl": False,
    })


class ShippingProviderSettingsUpdate(BaseModel):
    provider: Optional[Literal["manual", "shipbubble", "dhl"]] = None
    use_shipbubble: Optional[bool] = None

    @model_validator(mode="after")
    def resolve_legacy_selection(self):
        if self.provider is None:
            if self.use_shipbubble is None:
                raise ValueError("A shipping provider selection is required")
            self.provider = "shipbubble" if self.use_shipbubble else "manual"
        elif self.use_shipbubble is not None and self.use_shipbubble != (self.provider == "shipbubble"):
            raise ValueError("Conflicting shipping provider selections")
        return self


class PayoutHoldSettings(BaseModel):
    """Payout hold settings"""
    hold_days: int = Field(default=14, ge=0, le=3650)
    updated_at: Optional[datetime] = None


class PayoutHoldSettingsUpdate(BaseModel):
    """Update payout hold settings"""
    hold_days: int = Field(..., ge=0, le=3650)


class CommissionSettings(BaseModel):
    """Platform commission settings"""
    commission_rate: float = Field(default=12.5, ge=0, le=100)
    updated_at: Optional[datetime] = None


class CommissionSettingsUpdate(BaseModel):
    """Update platform commission settings"""
    commission_rate: float = Field(..., ge=0, le=100)
    apply_to_existing_vendors: bool = False


class FeaturedRotationSettings(BaseModel):
    """Featured product rotation settings"""
    rotation_minutes: int = Field(default=10, ge=1, le=1440)
    updated_at: Optional[datetime] = None


class FeaturedRotationSettingsUpdate(BaseModel):
    """Update featured rotation settings"""
    rotation_minutes: int = Field(..., ge=1, le=1440)


class DatabaseSyncResponse(BaseModel):
    """Database sync response"""
    status: str = Field(..., pattern="^(success|error)$")
    message: str
    duration_seconds: Optional[float] = None
