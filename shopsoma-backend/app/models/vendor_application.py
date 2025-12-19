"""
Vendor Application Model
Represents a vendor signup application before approval
"""
from sqlalchemy import Column, String, DateTime, Boolean, Text, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
import uuid
from app.core.database import Base


class VendorApplication(Base):
    """Model for vendor application submissions"""
    __tablename__ = "vendor_applications"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Personal Information (Step 1)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone_country_code = Column(String(10), nullable=False)
    phone_number = Column(String(20), nullable=False)

    # Business Information (Step 2)
    business_name = Column(String(255), nullable=False)
    business_location = Column(Text, nullable=False)  # Detailed address
    is_business_registered = Column(Text, nullable=True)  # CAC details or "No"
    product_categories = Column(ARRAY(String), nullable=False)  # Array of categories
    local_production_level = Column(String(100), nullable=False)  # Production level
    years_in_business = Column(String(50), nullable=False)
    brand_story = Column(Text, nullable=True)  # What makes them special
    website_link = Column(String(500), nullable=True)
    social_media_handles = Column(JSON, nullable=True)  # {instagram: '', facebook: '', etc}

    # Application Status
    status = Column(
        String(50),
        nullable=False,
        default="pending_review",
        index=True
    )  # pending_review | approved | rejected

    # Admin notes
    admin_notes = Column(Text, nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), nullable=True)  # Admin user ID
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Related vendor ID (set after approval)
    vendor_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<VendorApplication {self.business_name} ({self.email}) - {self.status}>"
