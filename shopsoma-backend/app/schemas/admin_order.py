"""Admin order schemas with enhanced fields for super user management"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID

from app.models.order import PaymentStatus, FulfillmentStatus
from app.models.vendor_pickup import PickupStatus


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class OrderStatusUpdate(BaseModel):
    """Update order fulfillment status"""
    fulfillment_status: FulfillmentStatus
    admin_notes: Optional[str] = None

    # Pickup window fields (for PICKUP_SCHEDULED status)
    pickup_window_start: Optional[str] = None
    pickup_window_end: Optional[str] = None
    courier_name: Optional[str] = None
    rider_id: Optional[str] = None


class ShippingInfoUpdate(BaseModel):
    """Update shipping information"""
    delivery_provider: Optional[str] = None
    tracking_number: Optional[str] = None
    estimated_delivery_date: Optional[date] = None
    admin_notes: Optional[str] = None


class PickupStatusUpdate(BaseModel):
    """Update pickup status"""
    pickup_status: Optional[PickupStatus] = None
    scheduled_pickup_date: Optional[datetime] = None
    actual_pickup_date: Optional[datetime] = None
    pickup_window_start: Optional[datetime] = None
    pickup_window_end: Optional[datetime] = None
    logistics_partner: Optional[str] = None
    courier_name: Optional[str] = None
    rider_id: Optional[str] = None
    tracking_number: Optional[str] = None
    qc_notes: Optional[str] = None
    admin_notes: Optional[str] = None


class BulkStatusUpdate(BaseModel):
    """Bulk update order statuses"""
    order_ids: List[UUID] = Field(..., min_length=1)
    fulfillment_status: FulfillmentStatus
    admin_notes: Optional[str] = None


class RefundRequest(BaseModel):
    """Process order refund"""
    reason: str = Field(..., min_length=10, max_length=500)
    refund_amount: Optional[Decimal] = Field(None, gt=0)
    refund_type: str = Field(default="full", pattern="^(full|partial)$")
    admin_notes: Optional[str] = None

    @field_validator('refund_amount')
    @classmethod
    def validate_refund_amount(cls, v, info):
        if info.data.get('refund_type') == 'partial' and v is None:
            raise ValueError('Refund amount is required for partial refunds')
        return v


class CancelOrderRequest(BaseModel):
    """Cancel order"""
    cancellation_reason: str = Field(..., min_length=10, max_length=500)
    refund: bool = Field(default=True, description="Whether to process refund")
    admin_notes: Optional[str] = None


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class CustomerInfo(BaseModel):
    """Customer information for admin view"""
    id: UUID
    first_name: Optional[str]
    last_name: Optional[str]
    email: str
    phone: Optional[str]

    class Config:
        from_attributes = True


class VendorInfo(BaseModel):
    """Vendor information for admin view"""
    id: UUID
    business_name: str
    contact_email: Optional[str]
    contact_phone: Optional[str]

    class Config:
        from_attributes = True


class AddressInfo(BaseModel):
    """Address information"""
    id: UUID
    full_name: str
    phone: str
    street_address: str
    city: str
    state: str
    country: str
    postal_code: str

    class Config:
        from_attributes = True


class OrderItemDetail(BaseModel):
    """Order item with vendor information"""
    id: UUID
    product_id: UUID
    product_title: str
    product_image_url: Optional[str] = None
    variant_details: Optional[dict]
    unit_price: Decimal
    currency: str
    quantity: int
    subtotal: Decimal
    commission_rate: Decimal
    commission_amount: Decimal
    vendor_payout: Decimal
    fulfillment_status: FulfillmentStatus
    vendor: VendorInfo

    class Config:
        from_attributes = True


class PickupInfo(BaseModel):
    """Pickup information"""
    id: UUID
    status: PickupStatus
    scheduled_pickup_date: Optional[datetime]
    actual_pickup_date: Optional[datetime]
    pickup_window_start: Optional[datetime]
    pickup_window_end: Optional[datetime]
    logistics_partner: Optional[str]
    courier_name: Optional[str]
    rider_id: Optional[str]
    tracking_number: Optional[str]
    qc_center_arrival_date: Optional[datetime]
    qc_approved_date: Optional[datetime]
    qc_rejected_date: Optional[datetime]
    qc_notes: Optional[str]
    vendor_notes: Optional[str]
    admin_notes: Optional[str]

    class Config:
        from_attributes = True


class ReadyPackageInfo(BaseModel):
    """Minimal ready-package metadata for admin shadow-quote selection."""
    id: UUID
    current_version: int
    hub_id: UUID
    ready_at: datetime

    class Config:
        from_attributes = True


class OrderListItem(BaseModel):
    """Order in list view"""
    id: UUID
    order_number: str
    customer: CustomerInfo
    total_amount: Decimal
    currency: str
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus
    created_at: datetime
    vendor_count: int = 0
    item_count: int = 0

    class Config:
        from_attributes = True


class OrderDetail(BaseModel):
    """Complete order detail for admin"""
    id: UUID
    order_number: str
    customer: CustomerInfo

    # Address Information
    shipping_address: Optional[AddressInfo]
    billing_address: Optional[AddressInfo]

    # Pricing
    currency: str
    subtotal: Decimal
    shipping_cost: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal

    # Status
    payment_status: PaymentStatus
    fulfillment_status: FulfillmentStatus

    # Delivery
    delivery_provider: Optional[str]
    tracking_number: Optional[str]
    estimated_delivery_date: Optional[date]
    delivered_at: Optional[datetime]

    # Notes
    customer_notes: Optional[str]
    admin_notes: Optional[str]

    # Timestamps
    created_at: datetime
    updated_at: datetime
    confirmed_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    cancellation_reason: Optional[str]

    # Items and Pickups
    items: List[OrderItemDetail]
    pickups: List[PickupInfo]
    ready_packages: List[ReadyPackageInfo] = Field(default_factory=list)

    class Config:
        from_attributes = True


class OrderStats(BaseModel):
    """Order statistics for admin dashboard"""
    total_orders: int
    total_revenue: Decimal
    pending_orders: int
    processing_orders: int
    shipped_orders: int
    delivered_orders: int
    cancelled_orders: int
    pending_payment: int
    failed_payment: int
    average_order_value: Decimal
    orders_today: int
    revenue_today: Decimal


class ShadowQuoteResult(BaseModel):
    """Redacted operator-safe shadow quote evidence summary (no credentials, no raw payload)."""
    order_id: UUID
    shadow_quote_id: UUID
    result_kind: str = Field(..., pattern="^(success|no_service|failed)$")
    environment: str
    adapter_version: str
    provider: str = "dhl"
    offers_count: int = 0
    offers_redacted: List[dict] = Field(default_factory=list)
    gate_status: dict = Field(default_factory=dict)
    quoted_at: datetime
    note: Optional[str] = None

    class Config:
        from_attributes = True


class PaginatedOrders(BaseModel):
    """Paginated order list response"""
    orders: List[OrderListItem]
    total: int
    page: int
    page_size: int
    total_pages: int
