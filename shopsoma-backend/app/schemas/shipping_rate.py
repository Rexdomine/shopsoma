"""Shipping rate schemas"""
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal


class ShippingRateBase(BaseModel):
    """Base shipping rate schema"""
    name: str = Field(..., min_length=1, max_length=100, description="Rate name")
    description: Optional[str] = Field(None, max_length=500, description="Rate description")
    base_rate: Decimal = Field(..., gt=0, description="Base shipping cost")
    country: str = Field(default="Nigeria", max_length=100)
    state: Optional[str] = Field(None, max_length=100, description="Specific state (null = all states)")
    min_order_value: Optional[Decimal] = Field(default=Decimal("0.00"), ge=0, description="Minimum order value")
    max_order_value: Optional[Decimal] = Field(None, ge=0, description="Maximum order value")
    min_delivery_days: int = Field(default=2, ge=1, description="Minimum delivery days")
    max_delivery_days: int = Field(default=5, ge=1, description="Maximum delivery days")
    is_active: bool = Field(default=True, description="Active status")
    is_default: bool = Field(default=False, description="Default rate")
    priority: int = Field(default=0, description="Priority (lower = higher priority)")


class ShippingRateCreate(ShippingRateBase):
    """Schema for creating a shipping rate"""
    pass


class ShippingRateUpdate(BaseModel):
    """Schema for updating a shipping rate"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    base_rate: Optional[Decimal] = Field(None, gt=0)
    country: Optional[str] = Field(None, max_length=100)
    state: Optional[str] = Field(None, max_length=100)
    min_order_value: Optional[Decimal] = Field(None, ge=0)
    max_order_value: Optional[Decimal] = Field(None, ge=0)
    min_delivery_days: Optional[int] = Field(None, ge=1)
    max_delivery_days: Optional[int] = Field(None, ge=1)
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
    priority: Optional[int] = None


class ShippingRateResponse(ShippingRateBase):
    """Schema for shipping rate response"""
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ShippingRateListResponse(BaseModel):
    """Schema for list of shipping rates"""
    shipping_rates: list[ShippingRateResponse]
    total: int


class ShippingCalculationRequest(BaseModel):
    """Request schema for calculating shipping cost"""
    country: str = Field(default="Nigeria", description="Delivery country")
    state: str = Field(..., description="Delivery state")
    order_value: Decimal = Field(..., gt=0, description="Order subtotal")


class ShippingCalculationResponse(BaseModel):
    """Response schema for shipping calculation"""
    available_rates: list[ShippingRateResponse]
    recommended_rate: Optional[ShippingRateResponse] = None
