"""Public contracts for pre-payment server shipping estimates."""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class CheckoutEstimateOptionResponse(BaseModel):
    id: UUID
    option_key: str
    service_code: str
    service_label: str
    amount: Decimal
    currency: str
    min_delivery_days: Optional[int] = None
    max_delivery_days: Optional[int] = None

    class Config:
        from_attributes = True


class CheckoutEstimateResponse(BaseModel):
    id: UUID
    order_id: UUID
    currency: str
    expires_at: datetime
    options: list[CheckoutEstimateOptionResponse]
    selected_option: Optional[CheckoutEstimateOptionResponse] = None
    server_payable_total: Decimal
