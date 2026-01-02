from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.schemas.product import ProductResponse, ProductVariantResponse


class CartItemBase(BaseModel):
    product_id: str
    variant_id: Optional[str] = None
    quantity: int = Field(ge=1, description="Quantity must be at least 1")


class CartItemCreate(CartItemBase):
    session_id: Optional[str] = None


class CartItemUpdate(BaseModel):
    quantity: int = Field(ge=1, description="Quantity must be at least 1")


class CartItemResponse(CartItemBase):
    id: str
    user_id: Optional[str]
    session_id: Optional[str]
    price: float
    subtotal: float
    created_at: datetime
    updated_at: datetime
    product: Optional[ProductResponse] = None
    variant: Optional[ProductVariantResponse] = None

    class Config:
        from_attributes = True


class CartSummary(BaseModel):
    subtotal: float
    shipping: float
    tax: float
    discount: float
    total: float
    item_count: int


class CartResponse(BaseModel):
    items: List[CartItemResponse]
    summary: CartSummary
    last_updated: datetime


class ApplyCouponRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50)


class CouponBase(BaseModel):
    code: str
    discount_type: str  # 'percentage' or 'fixed'
    discount_value: float
    min_purchase: Optional[float] = None
    max_discount: Optional[float] = None
    usage_limit: Optional[int] = None
    valid_from: datetime
    valid_until: datetime
    is_active: bool = True


class CouponCreate(CouponBase):
    pass


class CouponResponse(CouponBase):
    id: str
    used_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ApplyCouponResponse(BaseModel):
    is_valid: bool
    discount_amount: float
    discount_type: str
    message: str
    cart: Optional[CartResponse] = None
