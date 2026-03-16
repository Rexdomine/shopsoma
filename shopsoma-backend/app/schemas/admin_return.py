"""Admin return schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from decimal import Decimal
from app.models.returns import ReturnStatus


class ReturnCustomerInfo(BaseModel):
    id: UUID
    full_name: str
    email: str


class AdminReturnListItem(BaseModel):
    id: UUID
    return_number: str
    status: ReturnStatus
    reason: str
    created_at: datetime
    order_number: Optional[str]
    customer: Optional[ReturnCustomerInfo]
    product_title: Optional[str]
    quantity: Optional[int]
    amount: Optional[Decimal]

    class Config:
        from_attributes = True


class AdminReturnListResponse(BaseModel):
    returns: List[AdminReturnListItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminReturnDetail(BaseModel):
    id: UUID
    return_number: str
    status: ReturnStatus
    reason: str
    description: Optional[str]
    opened: Optional[str]
    return_action: Optional[str]
    admin_notes: Optional[str]
    rejection_reason: Optional[str]
    refund_amount: Optional[Decimal]
    refund_method: Optional[str]
    approved_by: Optional[UUID]
    approved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    order_id: UUID
    order_number: Optional[str]
    order_date: Optional[datetime]
    product_title: Optional[str]
    quantity: Optional[int]
    amount: Optional[Decimal]
    product_image_url: Optional[str]

    class Config:
        from_attributes = True


class AdminReturnStatusUpdate(BaseModel):
    status: ReturnStatus
    admin_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    refund_amount: Optional[Decimal] = None
    refund_method: Optional[str] = None


class AdminReturnNotesUpdate(BaseModel):
    admin_notes: Optional[str] = Field(None, max_length=2000)
