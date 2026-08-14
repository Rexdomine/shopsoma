"""Inert pre-payment shipping-estimate and inventory-coverage persistence."""

import uuid

from sqlalchemy import (
    BigInteger,
    CHAR,
    CheckConstraint,
    Column,
    DDL,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.base import Base
from app.models.checkout_prerequisite_ddl import (
    M2_CHECKOUT_DROP_DDL,
    M2_CHECKOUT_TRIGGER_DDL,
)

_UUID = UUID(as_uuid=True)
_NOW = func.statement_timestamp()


class CheckoutShippingEstimate(Base):
    __tablename__ = "checkout_shipping_estimates"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    order_id = Column(
        _UUID, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    customer_id = Column(
        _UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    destination_snapshot_hash = Column(CHAR(64), nullable=False)
    order_snapshot_hash = Column(CHAR(64), nullable=False)
    currency = Column(CHAR(3), nullable=False)
    ttl_seconds = Column(Integer, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    supersedes_estimate_id = Column(
        _UUID, ForeignKey("checkout_shipping_estimates.id", ondelete="RESTRICT")
    )
    source_kind = Column(String(30), nullable=False)
    source_reference = Column(String(200))
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    request_fingerprint = Column(CHAR(64), nullable=False)
    schema_version = Column(String(40), nullable=False)
    created_by_actor_type = Column(String(20), nullable=False)
    created_by_actor_id = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)
    creation_txid = Column(
        BigInteger, nullable=False, server_default=func.txid_current()
    )
    row_version = Column(Integer, nullable=False, server_default="1")

    __table_args__ = (
        CheckConstraint(
            "destination_snapshot_hash ~ '^[0-9a-f]{64}$' AND order_snapshot_hash ~ '^[0-9a-f]{64}$' AND request_fingerprint ~ '^[0-9a-f]{64}$' AND currency ~ '^[A-Z]{3}$'",
            name="ck_checkout_shipping_estimates_canonical",
        ),
        CheckConstraint(
            "ttl_seconds BETWEEN 300 AND 3600 AND expires_at > created_at AND row_version = 1",
            name="ck_checkout_shipping_estimates_lifecycle",
        ),
        CheckConstraint(
            "source_kind IN ('static_domestic_rate','sandbox_normalized') AND created_by_actor_type IN ('customer','guest_capability','staff')",
            name="ck_checkout_shipping_estimates_kinds",
        ),
        CheckConstraint(
            "source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$' AND idempotency_key ~ '^[!-~]{1,200}$' AND schema_version ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,39}$' AND created_by_actor_id ~ '^[!-~]{1,200}$'",
            name="ck_checkout_shipping_estimates_identifiers",
        ),
        UniqueConstraint(
            "customer_id",
            "source_command",
            "idempotency_key",
            name="uq_checkout_shipping_estimates_replay",
        ),
        UniqueConstraint(
            "supersedes_estimate_id", name="uq_checkout_shipping_estimates_successor"
        ),
        UniqueConstraint("id", "order_id", name="uq_checkout_shipping_estimates_order"),
        UniqueConstraint(
            "id", "customer_id", name="uq_checkout_shipping_estimates_customer"
        ),
        Index("ix_checkout_shipping_estimates_order_created", "order_id", "created_at"),
        Index("ix_checkout_shipping_estimates_expires", "expires_at"),
        Index("ix_checkout_shipping_estimates_snapshot", "order_snapshot_hash"),
    )


class CheckoutShippingEstimateOption(Base):
    __tablename__ = "checkout_shipping_estimate_options"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    estimate_id = Column(
        _UUID,
        ForeignKey("checkout_shipping_estimates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    option_key = Column(String(100), nullable=False)
    service_code = Column(String(100), nullable=False)
    service_label = Column(String(200), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(CHAR(3), nullable=False)
    min_delivery_days = Column(Integer)
    max_delivery_days = Column(Integer)
    source_rate_id = Column(_UUID, ForeignKey("shipping_rates.id", ondelete="RESTRICT"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        CheckConstraint(
            "amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric) AND amount > 0 AND amount <= 99999999.99 AND currency ~ '^[A-Z]{3}$'",
            name="ck_checkout_estimate_options_money",
        ),
        CheckConstraint(
            "option_key ~ '^[!-~]{1,100}$' AND service_code ~ '^[!-~]{1,100}$' AND service_label = btrim(service_label) AND length(service_label) BETWEEN 1 AND 200",
            name="ck_checkout_estimate_options_identifiers",
        ),
        CheckConstraint(
            "(min_delivery_days IS NULL AND max_delivery_days IS NULL) OR (min_delivery_days >= 0 AND min_delivery_days <= max_delivery_days AND max_delivery_days <= 365)",
            name="ck_checkout_estimate_options_delivery",
        ),
        UniqueConstraint(
            "estimate_id", "option_key", name="uq_checkout_estimate_options_key"
        ),
        UniqueConstraint(
            "id", "estimate_id", name="uq_checkout_estimate_options_estimate"
        ),
        UniqueConstraint(
            "estimate_id", "source_rate_id", name="uq_checkout_estimate_options_rate"
        ),
        Index("ix_checkout_estimate_options_estimate", "estimate_id"),
    )


class CheckoutShippingEstimateSelection(Base):
    __tablename__ = "checkout_shipping_estimate_selections"

    id = Column(_UUID, primary_key=True, default=uuid.uuid4)
    estimate_id = Column(_UUID, nullable=False)
    option_id = Column(_UUID, nullable=False)
    order_id = Column(_UUID, nullable=False)
    customer_id = Column(_UUID, nullable=False)
    selected_by_actor_type = Column(String(20), nullable=False)
    selected_by_actor_id = Column(String(200), nullable=False)
    shipping_amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(CHAR(3), nullable=False)
    source_command = Column(String(100), nullable=False)
    idempotency_key = Column(String(200), nullable=False)
    selected_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        ForeignKeyConstraint(
            ["estimate_id", "order_id"],
            ["checkout_shipping_estimates.id", "checkout_shipping_estimates.order_id"],
            name="fk_checkout_estimate_selections_order",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["estimate_id", "customer_id"],
            [
                "checkout_shipping_estimates.id",
                "checkout_shipping_estimates.customer_id",
            ],
            name="fk_checkout_estimate_selections_customer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["option_id", "estimate_id"],
            [
                "checkout_shipping_estimate_options.id",
                "checkout_shipping_estimate_options.estimate_id",
            ],
            name="fk_checkout_estimate_selections_option",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "shipping_amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric) AND shipping_amount > 0 AND shipping_amount <= 99999999.99 AND currency ~ '^[A-Z]{3}$'",
            name="ck_checkout_estimate_selections_money",
        ),
        CheckConstraint(
            "selected_by_actor_type IN ('customer','guest_capability') AND selected_by_actor_id ~ '^[!-~]{1,200}$' AND source_command ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$' AND idempotency_key ~ '^[!-~]{1,200}$'",
            name="ck_checkout_estimate_selections_identifiers",
        ),
        UniqueConstraint(
            "estimate_id", name="uq_checkout_estimate_selections_estimate"
        ),
        UniqueConstraint("order_id", name="uq_checkout_estimate_selections_order"),
        UniqueConstraint(
            "customer_id",
            "source_command",
            "idempotency_key",
            name="uq_checkout_estimate_selections_replay",
        ),
        UniqueConstraint(
            "id", "order_id", name="uq_checkout_estimate_selections_id_order"
        ),
    )


class OrderInventoryCoverage(Base):
    __tablename__ = "order_inventory_coverage"

    order_item_id = Column(_UUID, primary_key=True)
    order_id = Column(_UUID, nullable=False)
    checkout_estimate_selection_id = Column(_UUID, nullable=False)
    inventory_policy = Column(String(30), nullable=False)
    reservation_id = Column(_UUID)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        ForeignKeyConstraint(
            ["order_item_id", "order_id", "inventory_policy"],
            ["order_items.id", "order_items.order_id", "order_items.inventory_policy"],
            name="fk_order_inventory_coverage_item",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["checkout_estimate_selection_id", "order_id"],
            [
                "checkout_shipping_estimate_selections.id",
                "checkout_shipping_estimate_selections.order_id",
            ],
            name="fk_order_inventory_coverage_selection",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            [
                "reservation_id",
                "order_id",
                "order_item_id",
                "checkout_estimate_selection_id",
            ],
            [
                "stock_reservations.id",
                "stock_reservations.order_id",
                "stock_reservations.order_item_id",
                "stock_reservations.checkout_estimate_selection_id",
            ],
            name="fk_order_inventory_coverage_reservation",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "inventory_policy IN ('stock_managed','made_to_order') AND ((inventory_policy='stock_managed' AND reservation_id IS NOT NULL) OR (inventory_policy='made_to_order' AND reservation_id IS NULL))",
            name="ck_order_inventory_coverage_binding",
        ),
        UniqueConstraint(
            "order_id", "order_item_id", name="uq_order_inventory_coverage_order_item"
        ),
        Index("ix_order_inventory_coverage_policy", "order_id", "inventory_policy"),
    )


event.listen(Base.metadata, "after_create", DDL(M2_CHECKOUT_TRIGGER_DDL))
event.listen(Base.metadata, "before_drop", DDL(M2_CHECKOUT_DROP_DDL))
