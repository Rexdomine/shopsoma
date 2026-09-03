"""Vendor/order readiness cohorts and quantity-safe item allocations."""

import enum
import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    DDL,
    Enum as SQLEnum,
    event,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.base import Base
from app.models.order import OrderItem
from app.services.fulfillment.transitions import VendorPreparationState


class FulfillmentReadinessType(str, enum.Enum):
    """The snapshotted preparation class shared by a cohort."""

    READY_TO_WEAR = "ready_to_wear"
    MADE_TO_ORDER = "made_to_order"


def _enum_values(enum_class):
    return [member.value for member in enum_class]


class FulfillmentCohort(Base):
    """One vendor's order items sharing a compatible readiness window."""

    __tablename__ = "fulfillment_cohorts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
    )
    vendor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    readiness_type = Column(
        SQLEnum(
            FulfillmentReadinessType,
            values_callable=_enum_values,
            name="fulfillment_readiness_type",
        ),
        nullable=False,
    )
    ready_from = Column(DateTime(timezone=True), nullable=False)
    ready_through = Column(DateTime(timezone=True), nullable=False)
    state = Column(
        SQLEnum(
            VendorPreparationState,
            values_callable=_enum_values,
            name="vendor_preparation_state",
        ),
        nullable=False,
        default=VendorPreparationState.NOT_STARTED,
        server_default=VendorPreparationState.NOT_STARTED.value,
    )
    version = Column(Integer, nullable=False, default=1, server_default="1")
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
        CheckConstraint(
            "ready_through >= ready_from", name="ck_fulfillment_cohorts_ready_window"
        ),
        CheckConstraint("version >= 1", name="ck_fulfillment_cohorts_version_positive"),
        UniqueConstraint(
            "order_id",
            "vendor_id",
            "readiness_type",
            "ready_from",
            "ready_through",
            name="uq_fulfillment_cohorts_canonical_window",
        ),
        UniqueConstraint(
            "id", "order_id", "vendor_id", name="uq_fulfillment_cohorts_identity"
        ),
    )
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}


class CohortItemAllocation(Base):
    """Auditable quantity of an order item assigned once to a cohort."""

    __tablename__ = "cohort_item_allocations"

    cohort_id = Column(UUID(as_uuid=True), primary_key=True)
    order_item_id = Column(UUID(as_uuid=True), primary_key=True)
    order_id = Column(UUID(as_uuid=True), nullable=False)
    vendor_id = Column(UUID(as_uuid=True), nullable=False)
    allocated_quantity = Column(Integer, nullable=False)
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
        ForeignKeyConstraint(
            ["cohort_id", "order_id", "vendor_id"],
            [
                "fulfillment_cohorts.id",
                "fulfillment_cohorts.order_id",
                "fulfillment_cohorts.vendor_id",
            ],
            name="fk_cohort_item_allocations_cohort_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["order_item_id", "order_id", "vendor_id"],
            ["order_items.id", "order_items.order_id", "order_items.vendor_id"],
            name="fk_cohort_item_allocations_order_item_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "allocated_quantity > 0",
            name="ck_cohort_item_allocations_quantity_positive",
        ),
        UniqueConstraint(
            "cohort_id",
            "order_item_id",
            "order_id",
            "vendor_id",
            name="uq_cohort_item_allocations_identity",
        ),
    )


@event.listens_for(FulfillmentCohort, "before_update")
def _increment_cohort_version(_mapper, _connection, target) -> None:
    target.version += 1


_COHORT_QUANTITY_FUNCTION = DDL(
    """
    CREATE FUNCTION validate_cohort_item_allocation_quantity()
    RETURNS trigger AS $$
    DECLARE item_quantity integer; assigned_quantity bigint;
    BEGIN
        SELECT quantity INTO item_quantity FROM order_items
        WHERE id = NEW.order_item_id FOR UPDATE;
        SELECT COALESCE(SUM(allocated_quantity), 0) INTO assigned_quantity
        FROM cohort_item_allocations
        WHERE order_item_id = NEW.order_item_id;
        IF assigned_quantity + NEW.allocated_quantity > item_quantity THEN
            RAISE EXCEPTION USING
                ERRCODE = '23514',
                MESSAGE = 'cohort allocations exceed order item quantity';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """
)
_COHORT_QUANTITY_TRIGGER = DDL(
    """
    CREATE TRIGGER tr_cohort_item_allocations_quantity_safe
    BEFORE INSERT ON cohort_item_allocations
    FOR EACH ROW EXECUTE FUNCTION validate_cohort_item_allocation_quantity()
    """
)
_ORDER_ITEM_QUANTITY_FUNCTION = DDL(
    """
    CREATE FUNCTION validate_order_item_quantity_against_cohorts()
    RETURNS trigger AS $$
    DECLARE assigned_quantity bigint;
    BEGIN
        SELECT COALESCE(SUM(allocated_quantity), 0) INTO assigned_quantity
        FROM cohort_item_allocations
        WHERE order_item_id = NEW.id;
        IF NEW.quantity < assigned_quantity THEN
            RAISE EXCEPTION USING
                ERRCODE = '23514',
                MESSAGE = 'order item quantity is below cohort allocations';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """
)
_ORDER_ITEM_QUANTITY_TRIGGER = DDL(
    """
    CREATE TRIGGER tr_order_items_cohort_quantity_safe
    BEFORE UPDATE OF quantity ON order_items
    FOR EACH ROW EXECUTE FUNCTION validate_order_item_quantity_against_cohorts()
    """
)
_COHORT_DELETE_FUNCTION = DDL(
    """
    CREATE FUNCTION reject_fulfillment_cohort_delete()
    RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING
            ERRCODE = '23503',
            MESSAGE = 'fulfillment cohorts are audit records and cannot be deleted';
    END;
    $$ LANGUAGE plpgsql
    """
)
_COHORT_DELETE_TRIGGER = DDL(
    """
    CREATE TRIGGER tr_fulfillment_cohorts_delete_restricted
    BEFORE DELETE ON fulfillment_cohorts
    FOR EACH ROW EXECUTE FUNCTION reject_fulfillment_cohort_delete()
    """
)
_COHORT_ALLOCATION_AUDIT_FUNCTION = DDL(
    """
    CREATE FUNCTION reject_cohort_item_allocation_mutation()
    RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING
            ERRCODE = '23503',
            MESSAGE = 'cohort item allocations are immutable audit records';
    END;
    $$ LANGUAGE plpgsql
    """
)
_COHORT_ALLOCATION_AUDIT_TRIGGER = DDL(
    """
    CREATE TRIGGER tr_cohort_item_allocations_immutable
    BEFORE UPDATE OR DELETE ON cohort_item_allocations
    FOR EACH ROW EXECUTE FUNCTION reject_cohort_item_allocation_mutation()
    """
)

event.listen(OrderItem.__table__, "after_create", _ORDER_ITEM_QUANTITY_FUNCTION)
event.listen(OrderItem.__table__, "after_create", _ORDER_ITEM_QUANTITY_TRIGGER)
event.listen(
    OrderItem.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_order_item_quantity_against_cohorts()"),
)
event.listen(FulfillmentCohort.__table__, "after_create", _COHORT_DELETE_FUNCTION)
event.listen(FulfillmentCohort.__table__, "after_create", _COHORT_DELETE_TRIGGER)
event.listen(
    FulfillmentCohort.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS reject_fulfillment_cohort_delete()"),
)
event.listen(CohortItemAllocation.__table__, "after_create", _COHORT_QUANTITY_FUNCTION)
event.listen(CohortItemAllocation.__table__, "after_create", _COHORT_QUANTITY_TRIGGER)
event.listen(
    CohortItemAllocation.__table__, "after_create", _COHORT_ALLOCATION_AUDIT_FUNCTION
)
event.listen(
    CohortItemAllocation.__table__, "after_create", _COHORT_ALLOCATION_AUDIT_TRIGGER
)
event.listen(
    CohortItemAllocation.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_cohort_item_allocation_quantity()"),
)
event.listen(
    CohortItemAllocation.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS reject_cohort_item_allocation_mutation()"),
)
