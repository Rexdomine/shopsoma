"""
Pydantic schemas for Vendor Applications
"""
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from typing import Optional, List, Dict
from datetime import datetime
from uuid import UUID


class SocialMediaHandles(BaseModel):
    """Social media handles"""
    instagram: Optional[str] = None
    facebook: Optional[str] = None
    twitter: Optional[str] = None
    tiktok: Optional[str] = None
    pinterest: Optional[str] = None
    youtube: Optional[str] = None


class VendorApplicationCreate(BaseModel):
    """Schema for creating a vendor application"""
    # Personal Information (Step 1)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone_country_code: str = Field(..., min_length=1, max_length=10)
    phone_number: str = Field(..., min_length=1, max_length=20)

    # Business Information (Step 2)
    business_name: str = Field(..., min_length=1, max_length=255)
    business_location: str = Field(..., min_length=1)
    is_business_registered: Optional[str] = None
    product_categories: List[str] = Field(..., min_items=1)
    local_production_level: str = Field(..., min_length=1, max_length=100)
    years_in_business: str = Field(..., min_length=1, max_length=50)
    brand_story: Optional[str] = None
    website_link: Optional[str] = None
    social_media_handles: Optional[SocialMediaHandles] = None


class VendorApplicationResponse(BaseModel):
    """Schema for vendor application response"""
    id: UUID
    first_name: str
    last_name: str
    email: str
    phone_country_code: str
    phone_number: str
    business_name: str
    business_location: str
    is_business_registered: Optional[str]
    product_categories: List[str]
    local_production_level: str
    years_in_business: str
    brand_story: Optional[str]
    website_link: Optional[str]
    social_media_handles: Optional[Dict]
    status: str
    admin_notes: Optional[str]
    reviewed_by: Optional[UUID]
    reviewed_at: Optional[datetime]
    vendor_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VendorApplicationUpdate(BaseModel):
    """Schema for updating vendor application admin fields"""
    admin_notes: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(pending_review|approved|rejected)$")


class VendorApplicationApproval(BaseModel):
    """Schema for approving/rejecting vendor application"""
    status: str = Field(..., pattern="^(approved|rejected)$")
    admin_notes: Optional[str] = None
