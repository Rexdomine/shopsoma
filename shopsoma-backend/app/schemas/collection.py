"""
Collection Pydantic schemas
"""
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import Optional, List
from uuid import UUID


class CollectionBase(BaseModel):
    """Base collection schema"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    banner_image_url: Optional[str] = None
    is_active: bool = Field(default=True)


class CollectionCreate(BaseModel):
    """Schema for creating a collection"""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    banner_image_url: Optional[str] = None


class CollectionUpdate(BaseModel):
    """Schema for updating a collection"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    banner_image_url: Optional[str] = None
    is_active: Optional[bool] = None


class CollectionResponse(CollectionBase):
    """Schema for collection response"""
    id: UUID
    vendor_id: UUID
    slug: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CollectionSummaryResponse(CollectionResponse):
    """Collection summary with product data"""
    products_available: int = 0
    thumbnails: List[str] = Field(default_factory=list)


class CollectionProductSummary(BaseModel):
    """Collection product summary"""
    id: UUID
    title: str
    status: str
    base_price: float
    total_stock: int
    made_to_order: bool = False
    made_to_order_timeline: Optional[str] = None
    created_at: datetime
    image_url: Optional[str] = None
    collection_name: Optional[str] = None


class CollectionProductsResponse(BaseModel):
    """Paginated collection products response"""
    items: List[CollectionProductSummary]
    total: int
    page: int
    page_size: int
    total_pages: int


class CollectionDetailResponse(CollectionSummaryResponse):
    """Collection detail response"""
    description: Optional[str] = None


class CollectionProductAssignRequest(BaseModel):
    """Assign products to a collection"""
    product_ids: List[UUID]
