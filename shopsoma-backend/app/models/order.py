"""Order models"""

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Session, relationship
from sqlalchemy.sql import func
import uuid
import enum

from app.core.base import Base


class PaymentStatus(str, enum.Enum):
    """Payment status enum"""

    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class FulfillmentStatus(str, enum.Enum):
    """Fulfillment status enum - unified order lifecycle"""

    ORDER_RECEIVED = "order_received"
    PREPARING_FOR_PICKUP = "preparing_for_pickup"
    PICKUP_SCHEDULED = "pickup_scheduled"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    RETURNED = "returned"
    CANCELLED = "cancelled"


class Order(Base):
    """Customer order model"""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "workflow_cohort",
            "workflow_policy_version",
            "checkout_access_mode",
            name="uq_orders_workflow_truth",
        ),
        CheckConstraint(
            "workflow_cohort IN ('legacy_pre_bridge','legacy_ambiguous_quarantined','domestic_checkout_v1')",
            name="ck_orders_workflow_cohort",
        ),
        CheckConstraint(
            "workflow_policy_version ~ '^[!-~]{1,40}$'",
            name="ck_orders_workflow_policy_version",
        ),
        CheckConstraint(
            "checkout_access_mode IN ('authenticated','guest_capability','legacy_quarantined') AND ((workflow_cohort='legacy_ambiguous_quarantined' AND workflow_policy_version='legacy_quarantine_v1' AND checkout_access_mode='legacy_quarantined') OR (workflow_cohort<>'legacy_ambiguous_quarantined' AND checkout_access_mode<>'legacy_quarantined'))",
            name="ck_orders_checkout_access_mode",
        ),
        ForeignKeyConstraint(
            ["checkout_estimate_selection_id", "id"],
            [
                "checkout_shipping_estimate_selections.id",
                "checkout_shipping_estimate_selections.order_id",
            ],
            name="fk_orders_checkout_estimate_selection",
            ondelete="RESTRICT",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        Index("ix_orders_workflow_cohort_created_at", "workflow_cohort", "created_at"),
        Index(
            "ix_orders_domestic_prerequisite_pending",
            "id",
            postgresql_where=text(
                "workflow_cohort='domestic_checkout_v1' AND checkout_prerequisites_completed_at IS NULL"
            ),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_number = Column(String(50), unique=True, nullable=False, index=True)
    customer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    workflow_cohort = Column(String(40), nullable=False)
    workflow_policy_version = Column(String(40), nullable=False)
    checkout_access_mode = Column(String(20), nullable=False)
    checkout_estimate_selection_id = Column(UUID(as_uuid=True), nullable=True)
    checkout_prerequisites_completed_at = Column(DateTime(timezone=True), nullable=True)

    # Address Information
    shipping_address_id = Column(
        UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=True
    )
    billing_address_id = Column(
        UUID(as_uuid=True), ForeignKey("addresses.id"), nullable=True
    )

    # Pricing
    currency = Column(String(3), nullable=False, default="NGN", server_default="NGN")
    subtotal = Column(Numeric(10, 2), nullable=False)
    shipping_cost = Column(Numeric(10, 2), default=0.00, nullable=False)
    tax_amount = Column(Numeric(10, 2), default=0.00, nullable=False)
    discount_amount = Column(Numeric(10, 2), default=0.00, nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)

    # Status
    payment_status = Column(
        SQLEnum(PaymentStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=PaymentStatus.PENDING,
        nullable=False,
        index=True,
    )
    fulfillment_status = Column(
        SQLEnum(FulfillmentStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=FulfillmentStatus.ORDER_RECEIVED,
        nullable=False,
        index=True,
    )

    # Delivery
    delivery_provider = Column(String(50), nullable=True)
    tracking_number = Column(String(100), nullable=True)
    estimated_delivery_date = Column(Date, nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    # Notes
    customer_notes = Column(Text, nullable=True)
    admin_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Relationships
    customer = relationship("User", back_populates="orders", foreign_keys=[customer_id])
    shipping_address = relationship("Address", foreign_keys=[shipping_address_id])
    billing_address = relationship("Address", foreign_keys=[billing_address_id])
    items = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    payments = relationship("Payment", back_populates="order")
    returns = relationship("Return", back_populates="order")
    pickups = relationship("VendorPickup", back_populates="order")

    def __repr__(self):
        return f"<Order {self.order_number}>"


class OrderItem(Base):
    """Order item model"""

    __tablename__ = "order_items"
    __table_args__ = (
        UniqueConstraint(
            "id", "order_id", "vendor_id", name="uq_order_items_id_order_vendor"
        ),
        UniqueConstraint("id", "order_id", name="uq_order_items_id_order"),
        UniqueConstraint(
            "id",
            "order_id",
            "inventory_policy",
            name="uq_order_items_id_order_inventory_policy",
        ),
        CheckConstraint(
            "inventory_policy IS NULL OR inventory_policy IN ('stock_managed','made_to_order')",
            name="ck_order_items_inventory_policy",
        ),
        CheckConstraint(
            "(inventory_policy IS NULL AND inventory_subject_kind IS NULL AND inventory_subject_id IS NULL) OR (inventory_policy='made_to_order' AND inventory_subject_kind IS NULL AND inventory_subject_id IS NULL) OR (inventory_policy='stock_managed' AND inventory_subject_kind IN ('product','product_variant','size_stock') AND inventory_subject_id IS NOT NULL)",
            name="ck_order_items_inventory_subject",
        ),
        CheckConstraint(
            "(inventory_source_product_id IS NULL AND inventory_source_catalogue_version IS NULL AND inventory_source_evidence_hash IS NULL AND inventory_policy_snapshot_at IS NULL) OR (inventory_source_product_id IS NOT NULL AND inventory_source_catalogue_version ~ '^[!-~]{1,100}$' AND inventory_source_evidence_hash ~ '^[0-9a-f]{64}$' AND inventory_policy_snapshot_at IS NOT NULL)",
            name="ck_order_items_inventory_source",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    variant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=True,
    )
    vendor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    inventory_policy = Column(String(30), nullable=True)
    inventory_subject_kind = Column(String(20), nullable=True)
    inventory_subject_id = Column(UUID(as_uuid=True), nullable=True)
    inventory_source_product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=True,
    )
    inventory_source_catalogue_version = Column(String(100), nullable=True)
    inventory_source_evidence_hash = Column(CHAR(64), nullable=True)
    inventory_policy_snapshot_at = Column(DateTime(timezone=True), nullable=True)

    # Product Snapshot (at time of order)
    product_title = Column(String(255), nullable=False)
    variant_details = Column(JSONB, nullable=True)  # {size: "M", color: "Blue"}

    # Pricing
    unit_price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="NGN", server_default="NGN")
    quantity = Column(Integer, default=1, nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)

    # Vendor Commission
    commission_rate = Column(Numeric(5, 2), nullable=False)
    commission_amount = Column(Numeric(10, 2), nullable=False)
    vendor_payout = Column(Numeric(10, 2), nullable=False)

    # Fulfillment
    fulfillment_status = Column(
        SQLEnum(FulfillmentStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=FulfillmentStatus.ORDER_RECEIVED,
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    order = relationship("Order", back_populates="items")
    product = relationship(
        "Product", back_populates="order_items", foreign_keys=[product_id]
    )
    variant = relationship("ProductVariant", back_populates="order_items")
    vendor = relationship("Vendor", back_populates="order_items")
    pickup = relationship("VendorPickup", back_populates="order_item", uselist=False)

    def __repr__(self):
        return f"<OrderItem {self.product_title} x{self.quantity}>"


@event.listens_for(Session, "before_flush")
def _write_gate_off_order_compatibility(session, _flush_context, _instances) -> None:
    """Classify new ordinary orders and project ownership in one transaction."""
    from app.models.order_guest_capability import OrderCurrentOwner

    new_orders = [row for row in session.new if isinstance(row, Order)]
    pending_owner_ids = {
        row.order_id for row in session.new if isinstance(row, OrderCurrentOwner)
    }

    for order in new_orders:
        if order.id is None:
            order.id = uuid.uuid4()
        if order.workflow_cohort is None and order.workflow_policy_version is None:
            order.workflow_cohort = "legacy_pre_bridge"
            order.workflow_policy_version = "legacy_pre_bridge_v1"
        if (
            order.checkout_access_mode is None
            and order.workflow_cohort == "legacy_pre_bridge"
        ):
            order.checkout_access_mode = "authenticated"
        if order.id not in pending_owner_ids:
            session.add(
                OrderCurrentOwner(
                    order_id=order.id,
                    original_customer_id=order.customer_id,
                )
            )
            pending_owner_ids.add(order.id)
