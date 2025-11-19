"""Payment schemas"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from decimal import Decimal


class PaymentInitializeRequest(BaseModel):
    """Request schema for initializing a payment"""
    order_id: UUID = Field(..., description="Order ID to pay for")
    email: EmailStr = Field(..., description="Customer email")
    callback_url: Optional[str] = Field(None, description="URL to redirect after payment")


class PaymentInitializeResponse(BaseModel):
    """Response schema for payment initialization"""
    status: bool
    message: str
    authorization_url: str
    access_code: str
    reference: str


class PaymentVerifyRequest(BaseModel):
    """Request schema for verifying a payment"""
    reference: str = Field(..., description="Payment reference from Paystack")


class PaymentVerifyResponse(BaseModel):
    """Response schema for payment verification"""
    status: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class PaymentWebhookEvent(BaseModel):
    """Webhook event from Paystack"""
    event: str
    data: Dict[str, Any]


class PaymentResponse(BaseModel):
    """Payment record response"""
    id: UUID
    order_id: UUID
    transaction_id: Optional[str]
    payment_gateway: str
    payment_method: Optional[str]
    amount: Decimal
    currency: str
    status: str
    gateway_response: Optional[Dict[str, Any]]
    created_at: datetime
    completed_at: Optional[datetime]
    failed_at: Optional[datetime]
    failure_reason: Optional[str]

    class Config:
        from_attributes = True
