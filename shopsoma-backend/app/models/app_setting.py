"""Application settings model for admin configuration"""
from sqlalchemy import Column, String, Boolean, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
import uuid

from app.core.base import Base


class AppSetting(Base):
    """Application settings table"""
    __tablename__ = "app_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(20), nullable=False, default="string")  # string, boolean, json
    description = Column(Text, nullable=True)
    is_public = Column(Boolean, default=False)  # Whether setting is visible to public API

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<AppSetting(key='{self.key}', value='{self.value}')>"
