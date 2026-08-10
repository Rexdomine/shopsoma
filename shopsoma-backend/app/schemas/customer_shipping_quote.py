"""Public, redacted schemas for customer shipping quotes."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CustomerShippingQuoteOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    service_label: str
    total_amount: Decimal
    currency: str
    transit_days: int | None = None
    delivery_date: date | None = None


class CustomerShippingQuoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    currency: str
    expires_at: datetime
    created_at: datetime
    status: Literal["available", "selected", "expired", "superseded"]
    selected_option_id: UUID | None = None
    options: list[CustomerShippingQuoteOptionResponse]
