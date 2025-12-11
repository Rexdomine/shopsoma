"""Vendor schemas"""
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, UUID4, EmailStr, Field, field_validator
from decimal import Decimal


# ==================== VENDOR ASSET SCHEMAS ====================

class VendorAssetBase(BaseModel):
    """Base vendor asset schema"""
    asset_type: str = Field(..., description="Asset type: logo, banner, size_chart")
    file_url: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    display_order: int = 0
    is_active: bool = True
    alt_text: Optional[str] = None
    description: Optional[str] = None


class VendorAssetCreate(VendorAssetBase):
    """Create vendor asset"""
    pass


class VendorAssetUpdate(BaseModel):
    """Update vendor asset"""
    asset_type: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None
    alt_text: Optional[str] = None
    description: Optional[str] = None


class VendorAssetResponse(VendorAssetBase):
    """Vendor asset response"""
    id: UUID4
    vendor_id: UUID4
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== VENDOR ONBOARDING SCHEMAS ====================

class VendorOnboardingRequest(BaseModel):
    """Vendor onboarding/registration request"""
    business_name: str = Field(..., min_length=2, max_length=255)
    business_description: Optional[str] = None
    business_address: Optional[str] = None
    business_phone: Optional[str] = None

    # Bank Information
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_account_name: Optional[str] = None


class VendorKYCSubmission(BaseModel):
    """Vendor KYC document submission"""
    kyc_document_type: str = Field(..., description="ID type: passport, drivers_license, etc")
    kyc_document_url: str = Field(..., description="URL to uploaded document")


class VendorProfileUpdate(BaseModel):
    """Vendor profile update"""
    business_name: Optional[str] = Field(None, min_length=2, max_length=255)
    business_description: Optional[str] = None
    business_address: Optional[str] = None
    business_phone: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account_number: Optional[str] = None
    bank_account_name: Optional[str] = None


class VendorBrandInfoUpdate(BaseModel):
    """Update vendor brand info during onboarding"""
    business_phone: str = Field(..., min_length=1)
    email: Optional[str] = None
    business_description: Optional[str] = None
    logo_url: Optional[str] = None
    shipping_country: Optional[str] = None
    shipping_address: str = Field(..., min_length=1)
    returning_country: Optional[str] = None
    returning_address: Optional[str] = None
    open_days: List[str] = Field(..., min_items=1)  # ["MON", "TUE", ...]
    open_hour: str = Field(..., pattern=r'^\d{2}:\d{2}$')  # "09:00"
    close_hour: str = Field(..., pattern=r'^\d{2}:\d{2}$')  # "17:00"


class VendorPayoutInfoUpdate(BaseModel):
    """Update vendor payout info during onboarding"""
    tin: Optional[str] = None  # Tax ID Number
    account_type: str = Field(..., min_length=1)  # "Checking", "Savings"
    bank_name: str = Field(..., min_length=1)
    account_number: str = Field(..., min_length=1)
    account_holder: str = Field(..., min_length=1)


class VendorResponse(BaseModel):
    """Vendor response schema"""
    id: UUID4
    user_id: UUID4
    business_name: str
    business_description: Optional[str]
    business_address: Optional[str]
    business_phone: Optional[str]
    logo_url: Optional[str]
    returning_address: Optional[str]
    open_days: Optional[List[str]]
    open_hour: Optional[str]
    close_hour: Optional[str]
    secondary_contacts: Optional[List[dict]]

    # KYC Status
    kyc_status: str
    kyc_submitted_at: Optional[datetime]

    # Bank Information
    bank_name: Optional[str]
    bank_account_number: Optional[str]
    bank_account_name: Optional[str]

    # Platform Settings
    commission_rate: Decimal
    approved: bool
    approved_at: Optional[datetime]

    # Store Status
    store_active: bool
    store_paused_at: Optional[datetime]
    store_deleted_at: Optional[datetime]

    # Onboarding State
    is_onboarding: bool
    brand_info_completed: bool
    payout_info_completed: bool
    onboarding_completed_at: Optional[datetime]

    # Metrics
    total_products: int
    total_orders: int
    total_revenue: Decimal

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ==================== VENDOR PICKUP SCHEMAS ====================

class VendorPickupBase(BaseModel):
    """Base vendor pickup schema"""
    order_type: str = Field(default="RTW", description="RTW, MADE_TO_ORDER, or CUSTOM")
    estimated_production_days: Optional[int] = None
    pickup_address: Optional[str] = None
    pickup_contact_name: Optional[str] = None
    pickup_contact_phone: Optional[str] = None
    vendor_notes: Optional[str] = None


class VendorPickupCreate(VendorPickupBase):
    """Create vendor pickup"""
    order_item_id: UUID4


class VendorPickupUpdate(BaseModel):
    """Update vendor pickup"""
    estimated_production_days: Optional[int] = None
    pickup_address: Optional[str] = None
    pickup_contact_name: Optional[str] = None
    pickup_contact_phone: Optional[str] = None
    vendor_notes: Optional[str] = None


class VendorPickupResponse(VendorPickupBase):
    """Vendor pickup response"""
    id: UUID4
    vendor_id: UUID4
    order_id: UUID4
    order_item_id: UUID4

    scheduled_pickup_date: Optional[datetime]
    actual_pickup_date: Optional[datetime]

    logistics_partner: Optional[str]
    tracking_number: Optional[str]
    driver_name: Optional[str]
    driver_phone: Optional[str]

    status: str

    qc_center_arrival_date: Optional[datetime]
    qc_approved_date: Optional[datetime]
    qc_rejected_date: Optional[datetime]
    qc_notes: Optional[str]

    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    cancellation_reason: Optional[str]

    class Config:
        from_attributes = True


# ==================== VENDOR NOTIFICATION SCHEMAS ====================

class VendorNotificationResponse(BaseModel):
    """Vendor notification response"""
    id: UUID4
    vendor_id: UUID4
    notification_type: str
    title: str
    message: str

    order_id: Optional[UUID4]
    pickup_id: Optional[UUID4]
    payout_id: Optional[UUID4]

    data: Optional[dict]

    is_read: bool
    read_at: Optional[datetime]

    created_at: datetime

    class Config:
        from_attributes = True


class VendorNotificationMarkRead(BaseModel):
    """Mark notification as read"""
    notification_ids: List[UUID4]


# ==================== VENDOR ORDER SCHEMAS ====================

class VendorOrderItemResponse(BaseModel):
    """Vendor-specific order item response"""
    id: UUID4
    order_id: UUID4
    product_id: UUID4
    product_title: str
    variant_details: Optional[dict]

    unit_price: Decimal
    quantity: int
    subtotal: Decimal

    commission_rate: Decimal
    commission_amount: Decimal
    vendor_payout: Decimal

    fulfillment_status: str

    created_at: datetime

    class Config:
        from_attributes = True


class VendorOrderResponse(BaseModel):
    """Vendor-specific order response"""
    id: UUID4
    order_number: str

    # Only vendor's items from this order
    items: List[VendorOrderItemResponse]

    # Customer info (limited)
    customer_name: str
    customer_email: str

    # Shipping address
    shipping_address: Optional[dict]

    # Order status
    payment_status: str
    fulfillment_status: str

    # Timestamps
    created_at: datetime
    confirmed_at: Optional[datetime]

    class Config:
        from_attributes = True


class VendorOrderItemUpdate(BaseModel):
    """Update order item fulfillment status"""
    fulfillment_status: str = Field(..., pattern="^(pending|processing|shipped|delivered|cancelled)$", description="New fulfillment status")


# ==================== VENDOR PAYOUT SCHEMAS ====================

class VendorPayoutResponse(BaseModel):
    """Vendor payout response"""
    id: UUID4
    vendor_id: UUID4

    payout_period_start: date
    payout_period_end: date

    total_sales: Decimal
    commission_amount: Decimal
    payout_amount: Decimal

    status: str
    processed_at: Optional[datetime]
    payment_reference: Optional[str]

    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class VendorPayoutSummary(BaseModel):
    """Vendor payout summary"""
    pending_amount: Decimal
    last_payout_amount: Decimal
    last_payout_date: Optional[date]
    total_earnings: Decimal
    current_month_sales: Decimal


# ==================== VENDOR DASHBOARD SCHEMAS ====================

class VendorDashboardMetrics(BaseModel):
    """Vendor dashboard metrics"""
    # Products
    total_products: int
    active_products: int
    pending_approval_products: int

    # Orders
    total_orders: int
    pending_orders: int
    in_progress_orders: int
    completed_orders: int

    # Revenue
    total_revenue: Decimal
    current_month_revenue: Decimal
    pending_payout: Decimal

    # Pickups
    scheduled_pickups: int
    pending_pickups: int

    # Notifications
    unread_notifications: int


class VendorProductPerformance(BaseModel):
    """Vendor product performance"""
    product_id: UUID4
    product_title: str
    total_sales: int
    total_revenue: Decimal
    views_count: int
    orders_count: int


class VendorDashboardResponse(BaseModel):
    """Vendor dashboard response"""
    vendor: VendorResponse
    metrics: VendorDashboardMetrics
    recent_orders: List[VendorOrderResponse]
    top_products: List[VendorProductPerformance]
    recent_notifications: List[VendorNotificationResponse]
    upcoming_pickups: List[VendorPickupResponse]


# ==================== VENDOR PRODUCT SCHEMAS ====================

class VendorProductListFilters(BaseModel):
    """Filters for vendor product listing"""
    status: Optional[str] = None  # draft, active, inactive
    moderation_status: Optional[str] = None  # pending, approved, rejected
    category_id: Optional[UUID4] = None
    search: Optional[str] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
