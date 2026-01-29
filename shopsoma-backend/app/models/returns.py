"""Returns model"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.base import Base


class ReturnStatus(str, enum.Enum):
    """Return status enum"""
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    RECEIVED = "received"
    REFUNDED = "refunded"


class Return(Base):
    """Product return/RMA model"""
    __tablename__ = "returns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    return_number = Column(String(50), unique=True, nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Return Details
    reason = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    request_details = Column(MutableDict.as_mutable(JSONB), nullable=True)
    return_images = Column(JSONB, nullable=True)  # Array of image URLs
    order_item_id = Column(UUID(as_uuid=True), ForeignKey("order_items.id", ondelete="RESTRICT"), nullable=True, index=True)

    # Status
    status = Column(SQLEnum(ReturnStatus), default=ReturnStatus.REQUESTED, nullable=False, index=True)

    # Refund
    refund_amount = Column(Numeric(10, 2), nullable=True)
    refund_method = Column(String(50), nullable=True)
    admin_notes = Column(Text, nullable=True)

    # Processing
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejection_reason = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    order = relationship("Order", back_populates="returns")
    order_item = relationship("OrderItem")
    customer = relationship("User", back_populates="returns", foreign_keys=[customer_id])
    approver = relationship("User", foreign_keys=[approved_by])

    def __repr__(self):
        return f"<Return {self.return_number}>"
