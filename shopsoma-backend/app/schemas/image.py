"""Image upload and response schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ImageUploadResponse(BaseModel):
    """Response schema for image upload"""
    original: str = Field(..., description="Original image URL")
    thumbnail: Optional[str] = Field(None, description="Thumbnail URL (300x300)")
    medium: Optional[str] = Field(None, description="Medium size URL (800x800)")
    large: Optional[str] = Field(None, description="Large size URL (1600x1600)")
    s3_key: str = Field(..., description="S3 storage key")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "original": "https://cdn.shopsoma.com/products/2025/11/20251111_abc123.jpg",
                "thumbnail": "https://cdn.shopsoma.com/products/2025/11/20251111_abc123_thumbnail.jpg",
                "medium": "https://cdn.shopsoma.com/products/2025/11/20251111_abc123_medium.jpg",
                "large": "https://cdn.shopsoma.com/products/2025/11/20251111_abc123_large.jpg",
                "s3_key": "products/2025/11/20251111_abc123.jpg",
                "uploaded_at": "2025-11-11T10:30:00Z"
            }
        }


class ImageBatchUploadResponse(BaseModel):
    """Response schema for batch image uploads"""
    images: List[ImageUploadResponse]
    total: int
    success: int
    failed: int


class SignedUrlRequest(BaseModel):
    """Request schema for generating signed URL"""
    s3_key: str = Field(..., description="S3 object key")
    expiration: int = Field(
        default=3600,
        ge=60,
        le=86400,
        description="URL expiration in seconds (1 min to 24 hours)"
    )


class SignedUrlResponse(BaseModel):
    """Response schema for signed URL"""
    url: str = Field(..., description="Presigned URL")
    expires_in: int = Field(..., description="Expiration time in seconds")
    expires_at: datetime


class ImageDeleteResponse(BaseModel):
    """Response schema for image deletion"""
    success: bool
    message: str
    s3_key: str


class ImageBatchDeleteResponse(BaseModel):
    """Response schema for batch image deletion"""
    deleted: int
    failed: int
    total: int
    message: str


class ImageInfoResponse(BaseModel):
    """Response schema for image information"""
    s3_key: str
    size: int = Field(..., description="File size in bytes")
    content_type: str
    last_modified: datetime
    url: str
    metadata: dict = Field(default_factory=dict)
