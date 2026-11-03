"""Address schemas"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from uuid import UUID
from datetime import datetime
from app.models.address import AddressType


class AddressBase(BaseModel):
    """Base address schema"""
    full_name: str = Field(..., min_length=1, max_length=255, description="Full name for delivery")
    phone_number: str = Field(..., min_length=10, max_length=20, description="Contact phone number")
    address_line1: str = Field(..., min_length=1, max_length=255, description="Street address")
    address_line2: Optional[str] = Field(None, max_length=255, description="Apartment, suite, etc.")
    house_number: Optional[str] = Field(None, max_length=255, description="House number")
    city: str = Field(..., min_length=1, max_length=100, description="City")
    state: str = Field(..., min_length=1, max_length=100, description="State/Province")
    postal_code: Optional[str] = Field(None, max_length=20, description="Postal/ZIP code")
    country: str = Field(default="Nigeria", max_length=100, description="Country")
    address_type: AddressType = Field(default=AddressType.SHIPPING, description="Address type")

    @model_validator(mode="after")
    def sync_house_number_and_address_line2(self) -> "AddressBase":
        hn = self.house_number.strip() if isinstance(self.house_number, str) else None
        l2 = self.address_line2.strip() if isinstance(self.address_line2, str) else None
        resolved = hn or l2 or None
        self.house_number = resolved
        self.address_line2 = resolved
        return self

    @field_validator('phone_number')
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validate phone number format"""
        # Remove all non-digit characters
        import re
        cleaned = re.sub(r'\D', '', v)
        if len(cleaned) < 10:
            raise ValueError('Phone number must contain at least 10 digits')
        return v


class AddressCreate(AddressBase):
    """Schema for creating a new address"""
    is_default: bool = Field(default=False, description="Set as default address")


class AddressUpdate(BaseModel):
    """Schema for updating an address"""
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    phone_number: Optional[str] = Field(None, min_length=10, max_length=20)
    address_line1: Optional[str] = Field(None, min_length=1, max_length=255)
    address_line2: Optional[str] = Field(None, max_length=255)
    house_number: Optional[str] = Field(None, max_length=255)
    city: Optional[str] = Field(None, min_length=1, max_length=100)
    state: Optional[str] = Field(None, min_length=1, max_length=100)
    postal_code: Optional[str] = Field(None, max_length=20)
    country: Optional[str] = Field(None, max_length=100)
    address_type: Optional[AddressType] = None
    is_default: Optional[bool] = None

    @model_validator(mode="after")
    def sync_house_number_and_address_line2(self) -> "AddressUpdate":
        has_hn = "house_number" in self.model_fields_set
        has_l2 = "address_line2" in self.model_fields_set
        if not has_hn and not has_l2:
            return self
        hn = self.house_number.strip() if isinstance(self.house_number, str) else None
        l2 = self.address_line2.strip() if isinstance(self.address_line2, str) else None
        if has_hn and has_l2:
            resolved = hn or l2 or None
        elif has_hn:
            resolved = hn or None
        else:
            resolved = l2 or None
        self.house_number = resolved
        self.address_line2 = resolved
        self.model_fields_set.add("address_line2")
        self.model_fields_set.add("house_number")
        return self

    @field_validator('phone_number')
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """Validate phone number format"""
        if v is None:
            return v
        # Remove all non-digit characters
        import re
        cleaned = re.sub(r'\D', '', v)
        if len(cleaned) < 10:
            raise ValueError('Phone number must contain at least 10 digits')
        return v


class AddressResponse(AddressBase):
    """Schema for address response"""
    id: UUID
    user_id: UUID
    is_default: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AddressListResponse(BaseModel):
    """Schema for list of addresses"""
    addresses: list[AddressResponse]
    total: int
