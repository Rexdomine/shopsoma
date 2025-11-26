"""Wishlist schemas"""
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional


class WishlistItemBase(BaseModel):
    """Base wishlist item schema"""
    product_id: UUID


class WishlistItemCreate(WishlistItemBase):
    """Schema for adding item to wishlist"""
    pass


class WishlistItemResponse(BaseModel):
    """Wishlist item response schema"""
    id: UUID
    user_id: UUID
    product_id: UUID
    created_at: datetime

    # Product details (joined from product)
    product_title: str
    product_price: float
    product_sale_price: Optional[float] = None
    product_image: Optional[str] = None
    product_vendor_name: str
    product_slug: str
    is_active: bool

    class Config:
        from_attributes = True


class WishlistResponse(BaseModel):
    """Response schema for wishlist"""
    items: list[WishlistItemResponse]
    total: int

    class Config:
        from_attributes = True


class WishlistCheckResponse(BaseModel):
    """Response for checking if product is in wishlist"""
    in_wishlist: bool
    wishlist_item_id: Optional[UUID] = None

    class Config:
        from_attributes = True
