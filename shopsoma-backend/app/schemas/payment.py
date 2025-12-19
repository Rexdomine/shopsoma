"""Payment schemas"""
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Dict, Any, Literal
from uuid import UUID
from datetime import datetime
from decimal import Decimal


class PaymentInitializeRequest(BaseModel):
    """Request schema for initializing a payment"""
    order_id: UUID = Field(..., description="Order ID to pay for")
    email: EmailStr = Field(..., description="Customer email")
    payment_gateway: Literal["paystack", "stripe"] = Field("paystack", description="Payment gateway to use")
    currency: Literal["NGN", "USD"] = Field("NGN", description="Currency for payment")
    callback_url: Optional[str] = Field(None, description="URL to redirect after payment")


class PaymentInitializeResponse(BaseModel):
    """Response schema for payment initialization"""
    status: bool
    message: str
    authorization_url: Optional[str] = None  # For Paystack
    access_code: Optional[str] = None  # For Paystack
    reference: Optional[str] = None  # For Paystack
    client_secret: Optional[str] = None  # For Stripe
    payment_intent_id: Optional[str] = None  # For Stripe
    payment_gateway: str


class PaymentVerifyRequest(BaseModel):
    """Request schema for verifying a payment"""
    reference: Optional[str] = Field(None, description="Payment reference (for Paystack)")
    payment_intent_id: Optional[str] = Field(None, description="Payment Intent ID (for Stripe)")
    payment_gateway: Literal["paystack", "stripe"] = Field("paystack", description="Payment gateway used")


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


class CustomerPortalResponse(BaseModel):
    """Response schema for customer portal URL generation"""
    url: str
    provider: Literal["paystack", "stripe"]

    class Config:
        from_attributes = True
