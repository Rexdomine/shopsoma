"""SQLAlchemy models for ShipBubble shipment bookings and webhook audit."""

import uuid
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.core.base import Base


class ShipbubbleShipment(Base):
    """Authoritative booking and tracking state for an order fulfilled via ShipBubble."""

    __tablename__ = "shipbubble_shipments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    estimate_option_id = Column(
        UUID(as_uuid=True),
        ForeignKey("checkout_shipping_estimate_options.id", ondelete="SET NULL"),
        nullable=True,
    )
    request_token = Column(String(120), nullable=False)
    courier_id = Column(String(60), nullable=False)
    service_code = Column(String(60), nullable=False)
    courier_name = Column(String(100), nullable=False)
    shipbubble_order_id = Column(String(100), nullable=True)  # e.g. "SB-2CF48224272"
    status = Column(String(50), nullable=False, default="pending", server_default="pending")
    tracking_code = Column(String(100), nullable=True)
    tracking_url = Column(String(255), nullable=True)
    waybill_document_url = Column(String(255), nullable=True)
    shipping_fee = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(10), nullable=False, default="NGN", server_default="NGN")
    raw_response = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        Index("ix_shipbubble_shipments_order_id", "order_id"),
        Index("ix_shipbubble_shipments_status", "status"),
        Index("ix_shipbubble_shipments_sb_order_id", "shipbubble_order_id"),
    )


class ShipbubbleWebhookEvent(Base):
    """Immutable audit record for received ShipBubble webhook deliveries."""

    __tablename__ = "shipbubble_webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(100), nullable=True)
    event_type = Column(String(100), nullable=True)
    payload_sha256 = Column(String(64), nullable=False, unique=True)
    payload = Column(JSONB, nullable=False)
    status = Column(String(30), nullable=False, default="received", server_default="received")
    error_message = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_shipbubble_webhook_events_status", "status"),
        Index("ix_shipbubble_webhook_events_payload_sha256", "payload_sha256"),
    )
