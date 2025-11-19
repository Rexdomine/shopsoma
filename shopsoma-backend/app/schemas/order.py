"""Order schemas"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, date
from decimal import Decimal
from app.models.order import PaymentStatus, FulfillmentStatus


# Order Item Schemas
class OrderItemBase(BaseModel):
    """Base order item schema"""
    product_id: UUID
    variant_id: Optional[UUID] = None
    quantity: int = Field(..., gt=0, description="Quantity")


class OrderItemCreate(OrderItemBase):
    """Schema for creating an order item"""
    pass


class OrderItemResponse(BaseModel):
    """Schema for order item response"""
    id: UUID
    order_id: UUID
    product_id: UUID
    variant_id: Optional[UUID]
    vendor_id: UUID
    product_title: str
    variant_details: Optional[Dict[str, Any]]
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    commission_rate: Decimal
    commission_amount: Decimal
    vendor_payout: Decimal
    fulfillment_status: FulfillmentStatus
    created_at: datetime
    product_image_url: Optional[str] = None

    class Config:
        from_attributes = True


# Guest Address Schema
class GuestAddressData(BaseModel):
    """Guest checkout address data"""
    full_name: str
    phone_number: str
    address_line1: str
    address_line2: Optional[str] = None
    city: str
    state: str
    postal_code: Optional[str] = None
    country: str = "Nigeria"


# Order Schemas
class OrderCreate(BaseModel):
    """Schema for creating an order"""
    items: list[OrderItemCreate] = Field(..., min_length=1, description="Order items")
    shipping_address_id: Optional[UUID] = Field(None, description="Shipping address ID")
    billing_address_id: Optional[UUID] = Field(None, description="Billing address ID (defaults to shipping)")
    guest_address: Optional[GuestAddressData] = Field(None, description="Guest checkout address data")
    customer_email: Optional[str] = Field(None, description="Customer email for guest checkout")
    customer_notes: Optional[str] = Field(None, max_length=1000, description="Customer notes")
    promo_code: Optional[str] = Field(None, description="Promo code to apply")


class OrderSummary(BaseModel):
    """Order summary for review before creation"""
    subtotal: Decimal
    shipping_cost: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    items_count: int
    estimated_delivery_days: Optional[int] = None


class OrderReviewRequest(BaseModel):
    """Request schema for order review/preview"""
    items: list[OrderItemCreate] = Field(..., min_length=1)
    shipping_address_id: Optional[UUID] = None
    guest_address: Optional[GuestAddressData] = None
    promo_code: Optional[str] = None


class OrderReviewResponse(BaseModel):
    """Response schema for order review"""
    summary: OrderSummary
    items: list[Dict[str, Any]]  # Product details with pricing
    shipping_rate: Optional[Dict[str, Any]]
    applied_promo: Optional[Dict[str, Any]]


class OrderUpdate(BaseModel):
    """Schema for updating an order (admin)"""
    payment_status: Optional[PaymentStatus] = None
    fulfillment_status: Optional[FulfillmentStatus] = None
    delivery_provider: Optional[str] = Field(None, max_length=50)
    tracking_number: Optional[str] = Field(None, max_length=100)
    estimated_delivery_date: Optional[date] = None
    admin_notes: Optional[str] = None


class OrderResponse(BaseModel):
    """Schema for order response"""
    id: UUID
    order_number: str
    customer_id: UUID
    shipping_address_id: Optional[UUID]
    billing_address_id: Optional[UUID]
    subtotal: Decimal
    shipping_cost: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus
    delivery_provider: Optional[str]
    tracking_number: Optional[str]
    estimated_delivery_date: Optional[date]
    delivered_at: Optional[datetime]
    customer_notes: Optional[str]
    admin_notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    confirmed_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    cancellation_reason: Optional[str]
    items: list[OrderItemResponse] = []

    class Config:
        from_attributes = True


class OrderListResponse(BaseModel):
    """Schema for list of orders"""
    orders: list[OrderResponse]
    total: int
    page: int
    page_size: int


class OrderCancelRequest(BaseModel):
    """Schema for cancelling an order"""
    cancellation_reason: str = Field(..., min_length=1, max_length=500, description="Reason for cancellation")
