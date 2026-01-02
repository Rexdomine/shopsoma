"""Admin payout schemas"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.payment import PayoutStatus


class AdminPayoutVendor(BaseModel):
    id: UUID
    business_name: str
    email: Optional[str]
    phone: Optional[str]

    class Config:
        from_attributes = True


class AdminPayoutResponse(BaseModel):
    id: UUID
    vendor: AdminPayoutVendor
    payout_period_start: date
    payout_period_end: date
    total_sales: Decimal
    commission_amount: Decimal
    payout_amount: Decimal
    status: PayoutStatus
    processed_at: Optional[datetime]
    payment_reference: Optional[str]
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AdminPayoutList(BaseModel):
    payouts: List[AdminPayoutResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminPayoutStatusUpdate(BaseModel):
    status: PayoutStatus
    payment_reference: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=500)


class AdminPayoutBulkStatusUpdate(BaseModel):
    payout_ids: List[UUID] = Field(..., min_length=1)
    status: PayoutStatus
    notes: Optional[str] = Field(None, max_length=500)


class AdminPayoutAccountDetails(BaseModel):
    payout_id: UUID
    vendor_id: UUID
    vendor_name: str
    bank_name: str
    account_number: str
    account_holder: str
    account_type: Optional[str]
    is_default: bool
    payment_method_id: Optional[UUID]
    source: str
