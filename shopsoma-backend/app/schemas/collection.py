"""
Collection Pydantic schemas
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional
from uuid import UUID


class CollectionBase(BaseModel):
    """Base collection schema"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: bool = Field(default=True)


class CollectionCreate(BaseModel):
    """Schema for creating a collection"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class CollectionUpdate(BaseModel):
    """Schema for updating a collection"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CollectionResponse(CollectionBase):
    """Schema for collection response"""
    id: UUID
    vendor_id: UUID
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
