"""Vendor asset models for logos, banners, and size charts"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.core.base import Base


class VendorAsset(Base):
    """Vendor assets like logos, banners, size charts"""
    __tablename__ = "vendor_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False, index=True)

    # Asset Type
    asset_type = Column(String(50), nullable=False, index=True)  # logo, banner, size_chart

    # File Information
    file_url = Column(Text, nullable=False)
    file_name = Column(String(255), nullable=True)
    file_size = Column(Integer, nullable=True)  # in bytes
    mime_type = Column(String(100), nullable=True)

    # Display
    display_order = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    # Metadata
    alt_text = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    vendor = relationship("Vendor", back_populates="assets")

    def __repr__(self):
        return f"<VendorAsset {self.vendor_id} - {self.asset_type}>"
