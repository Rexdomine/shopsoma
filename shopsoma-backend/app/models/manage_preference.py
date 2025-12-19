"""User manage preference model"""
from datetime import datetime
import uuid

from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.core.base import Base


class ManagePreference(Base):
    __tablename__ = "manage_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    interest = Column(String(50), nullable=True)
    preferred_language = Column(String(100), nullable=True)
    preferred_currency = Column(String(10), nullable=True)
    favorite_designers = Column(JSONB, nullable=False, default=list)
    favorite_categories = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="preference")
