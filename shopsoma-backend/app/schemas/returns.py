"""Return request schemas"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime


class ReturnCreateRequest(BaseModel):
    order_id: UUID
    order_item_id: UUID
    reason: str = Field(..., min_length=2, max_length=100)
    opened: Optional[str] = None
    return_action: Optional[str] = None
    description: Optional[str] = Field(None, max_length=2000)


class ReturnUpdateRequest(BaseModel):
    reason: Optional[str] = Field(None, min_length=2, max_length=100)
    opened: Optional[str] = None
    return_action: Optional[str] = None
    description: Optional[str] = Field(None, max_length=2000)


class ReturnResponse(BaseModel):
    id: UUID
    return_number: str
    status: str
    reason: str
    description: Optional[str]
    opened: Optional[str] = None
    return_action: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: datetime
    order_id: UUID
    order_number: Optional[str]
    order_date: Optional[datetime]
    product_title: Optional[str]
    quantity: Optional[int]
    amount: Optional[float]
    product_image_url: Optional[str]

    class Config:
        from_attributes = True
