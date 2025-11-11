"""Review model"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.core.database import Base


class Review(Base):
    """Product review model"""
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint('product_id', 'customer_id', 'order_id', name='uq_product_customer_order_review'),
        CheckConstraint('rating >= 1 AND rating <= 5', name='check_rating_range'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True)

    # Review Content
    rating = Column(Integer, nullable=False)
    title = Column(String(255), nullable=True)
    comment = Column(Text, nullable=True)

    # Images
    review_images = Column(JSONB, nullable=True)  # Array of image URLs

    # Status
    is_verified_purchase = Column(Boolean, default=False, nullable=False)
    is_approved = Column(Boolean, default=False, nullable=False, index=True)
    moderated_at = Column(DateTime(timezone=True), nullable=True)
    moderated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    product = relationship("Product", back_populates="reviews")
    customer = relationship("User", back_populates="reviews", foreign_keys=[customer_id])
    moderator = relationship("User", foreign_keys=[moderated_by])

    def __repr__(self):
        return f"<Review {self.product_id} - {self.rating} stars>"
