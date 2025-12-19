"""Audit log model"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.core.base import Base


class AuditLog(Base):
    """Audit log model for tracking critical actions"""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Action Details
    action = Column(String(100), nullable=False)  # vendor_approved, product_moderated, payout_processed
    entity_type = Column(String(50), nullable=True, index=True)  # vendor, product, order, payout
    entity_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Changes
    old_values = Column(JSONB, nullable=True)
    new_values = Column(JSONB, nullable=True)

    # Metadata
    ip_address = Column(INET, nullable=True)
    user_agent = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<AuditLog {self.action} - {self.entity_type}>"
