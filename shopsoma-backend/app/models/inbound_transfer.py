"""Independent-provider inbound transfer persistence."""

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
    Index,
    Integer,
    String,
    text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.core.base import Base
from app.services.fulfillment.transitions import InboundState
from app.models.fulfillment_cohort import _enum_values


class InboundTransfer(Base):
    """Sanitized operational metadata for one cohort moving to one ShopSoma hub."""

    __tablename__ = "inbound_transfers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cohort_id = Column(UUID(as_uuid=True), nullable=False)
    order_id = Column(UUID(as_uuid=True), nullable=False)
    vendor_id = Column(UUID(as_uuid=True), nullable=False)
    target_hub_id = Column(
        UUID(as_uuid=True),
        ForeignKey("fulfillment_hubs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    provider_name = Column(String(100), nullable=False)
    provider_reference = Column(String(200), nullable=False)
    replaces_transfer_id = Column(UUID(as_uuid=True), nullable=True)
    state = Column(
        SQLEnum(
            InboundState,
            values_callable=_enum_values,
            name="inbound_transfer_state",
        ),
        nullable=False,
        default=InboundState.NOT_REQUESTED,
        server_default=InboundState.NOT_REQUESTED.value,
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
        ForeignKeyConstraint(
            ["cohort_id", "order_id", "vendor_id"],
            [
                "fulfillment_cohorts.id",
                "fulfillment_cohorts.order_id",
                "fulfillment_cohorts.vendor_id",
            ],
            name="fk_inbound_transfers_cohort_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["replaces_transfer_id", "cohort_id", "order_id", "vendor_id"],
            [
                "inbound_transfers.id",
                "inbound_transfers.cohort_id",
                "inbound_transfers.order_id",
                "inbound_transfers.vendor_id",
            ],
            name="fk_inbound_transfers_replacement_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "provider_name = btrim(provider_name) AND "
            "provider_name ~ '^[A-Za-z0-9][A-Za-z0-9 ._:/-]*$'",
            name="ck_inbound_transfers_provider_name_sanitized",
        ),
        CheckConstraint(
            "provider_reference = btrim(provider_reference) AND "
            "provider_reference ~ '^[A-Za-z0-9][A-Za-z0-9 ._:/-]*$'",
            name="ck_inbound_transfers_provider_reference_sanitized",
        ),
        CheckConstraint("version >= 1", name="ck_inbound_transfers_version_positive"),
        UniqueConstraint(
            "id",
            "cohort_id",
            "order_id",
            "vendor_id",
            name="uq_inbound_transfers_identity",
        ),
        UniqueConstraint(
            "replaces_transfer_id",
            name="uq_inbound_transfers_replaces_transfer_id",
        ),
        Index(
            "uq_inbound_transfers_active_cohort",
            "cohort_id",
            unique=True,
            postgresql_where=text(
                "state NOT IN ('received_complete', 'lost', 'damaged', 'cancelled')"
            ),
        ),
    )
    __mapper_args__ = {"version_id_col": version, "version_id_generator": False}


class InboundTransferItemAllocation(Base):
    """Quantity from a cohort allocation assigned to an inbound transfer."""

    __tablename__ = "inbound_transfer_item_allocations"

    transfer_id = Column(UUID(as_uuid=True), primary_key=True)
    order_item_id = Column(UUID(as_uuid=True), primary_key=True)
    cohort_id = Column(UUID(as_uuid=True), nullable=False)
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
            ["transfer_id", "cohort_id", "order_id", "vendor_id"],
            [
                "inbound_transfers.id",
                "inbound_transfers.cohort_id",
                "inbound_transfers.order_id",
                "inbound_transfers.vendor_id",
            ],
            name="fk_inbound_transfer_items_transfer_identity",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["cohort_id", "order_item_id", "order_id", "vendor_id"],
            [
                "cohort_item_allocations.cohort_id",
                "cohort_item_allocations.order_item_id",
                "cohort_item_allocations.order_id",
                "cohort_item_allocations.vendor_id",
            ],
            name="fk_inbound_transfer_items_cohort_allocation",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "allocated_quantity > 0",
            name="ck_inbound_transfer_items_quantity_positive",
        ),
    )


@event.listens_for(InboundTransfer, "before_update")
def _increment_inbound_transfer_version(_mapper, _connection, target) -> None:
    target.version += 1


_TRANSFER_QUANTITY_FUNCTION = DDL(
    """
    CREATE FUNCTION validate_inbound_transfer_item_quantity()
    RETURNS trigger AS $$
    DECLARE cohort_quantity integer;
    BEGIN
        SELECT allocated_quantity INTO cohort_quantity
        FROM cohort_item_allocations
        WHERE cohort_id = NEW.cohort_id AND order_item_id = NEW.order_item_id
        FOR UPDATE;
        IF NEW.allocated_quantity > cohort_quantity THEN
            RAISE EXCEPTION USING
                ERRCODE = '23514',
                MESSAGE = 'inbound transfer allocation exceeds cohort allocation';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """
)
_TRANSFER_QUANTITY_TRIGGER = DDL(
    """
    CREATE TRIGGER tr_inbound_transfer_items_quantity_safe
    BEFORE INSERT ON inbound_transfer_item_allocations
    FOR EACH ROW EXECUTE FUNCTION validate_inbound_transfer_item_quantity()
    """
)
_TRANSFER_LINEAGE_FUNCTION = DDL(
    """
    CREATE FUNCTION validate_inbound_transfer_lineage()
    RETURNS trigger AS $$
    DECLARE existing_count integer; replaced_state inbound_transfer_state;
    BEGIN
        IF TG_OP = 'UPDATE' AND (
            NEW.cohort_id IS DISTINCT FROM OLD.cohort_id
            OR NEW.order_id IS DISTINCT FROM OLD.order_id
            OR NEW.vendor_id IS DISTINCT FROM OLD.vendor_id
            OR NEW.target_hub_id IS DISTINCT FROM OLD.target_hub_id
            OR NEW.replaces_transfer_id IS DISTINCT FROM OLD.replaces_transfer_id
        ) THEN
            RAISE EXCEPTION USING
                ERRCODE = '23503',
                MESSAGE = 'inbound transfer identity is immutable';
        END IF;
        IF TG_OP = 'INSERT' THEN
            PERFORM id FROM fulfillment_cohorts
            WHERE id = NEW.cohort_id FOR UPDATE;
            SELECT COUNT(*) INTO existing_count
            FROM inbound_transfers WHERE cohort_id = NEW.cohort_id;
            IF existing_count = 0 AND NEW.replaces_transfer_id IS NOT NULL THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'initial inbound transfer cannot replace another transfer';
            ELSIF existing_count > 0 THEN
                IF NEW.replaces_transfer_id IS NULL THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        MESSAGE = 'replacement inbound transfer requires lineage';
                END IF;
                SELECT state INTO replaced_state
                FROM inbound_transfers
                WHERE id = NEW.replaces_transfer_id
                  AND cohort_id = NEW.cohort_id
                  AND order_id = NEW.order_id
                  AND vendor_id = NEW.vendor_id;
                IF replaced_state IS NULL OR replaced_state NOT IN (
                    'cancelled', 'lost', 'damaged'
                ) THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23514',
                        MESSAGE = 'only cancelled, lost, or damaged transfers may be replaced';
                END IF;
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """
)
_TRANSFER_LINEAGE_TRIGGER = DDL(
    """
    CREATE TRIGGER tr_inbound_transfers_lineage_safe
    BEFORE INSERT OR UPDATE ON inbound_transfers
    FOR EACH ROW EXECUTE FUNCTION validate_inbound_transfer_lineage()
    """
)
_TRANSFER_DELETE_FUNCTION = DDL(
    """
    CREATE FUNCTION reject_inbound_transfer_delete()
    RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING
            ERRCODE = '23503',
            MESSAGE = 'inbound transfers are audit records and cannot be deleted';
    END;
    $$ LANGUAGE plpgsql
    """
)
_TRANSFER_DELETE_TRIGGER = DDL(
    """
    CREATE TRIGGER tr_inbound_transfers_delete_restricted
    BEFORE DELETE ON inbound_transfers
    FOR EACH ROW EXECUTE FUNCTION reject_inbound_transfer_delete()
    """
)
_TRANSFER_ALLOCATION_AUDIT_FUNCTION = DDL(
    """
    CREATE FUNCTION reject_inbound_transfer_item_allocation_mutation()
    RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION USING
            ERRCODE = '23503',
            MESSAGE = 'inbound transfer item allocations are immutable audit records';
    END;
    $$ LANGUAGE plpgsql
    """
)
_TRANSFER_ALLOCATION_AUDIT_TRIGGER = DDL(
    """
    CREATE TRIGGER tr_inbound_transfer_item_allocations_immutable
    BEFORE UPDATE OR DELETE ON inbound_transfer_item_allocations
    FOR EACH ROW
    EXECUTE FUNCTION reject_inbound_transfer_item_allocation_mutation()
    """
)

event.listen(InboundTransfer.__table__, "after_create", _TRANSFER_LINEAGE_FUNCTION)
event.listen(InboundTransfer.__table__, "after_create", _TRANSFER_LINEAGE_TRIGGER)
event.listen(InboundTransfer.__table__, "after_create", _TRANSFER_DELETE_FUNCTION)
event.listen(InboundTransfer.__table__, "after_create", _TRANSFER_DELETE_TRIGGER)
event.listen(
    InboundTransfer.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_inbound_transfer_lineage()"),
)
event.listen(
    InboundTransfer.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS reject_inbound_transfer_delete()"),
)
event.listen(
    InboundTransferItemAllocation.__table__, "after_create", _TRANSFER_QUANTITY_FUNCTION
)
event.listen(
    InboundTransferItemAllocation.__table__, "after_create", _TRANSFER_QUANTITY_TRIGGER
)
event.listen(
    InboundTransferItemAllocation.__table__,
    "after_create",
    _TRANSFER_ALLOCATION_AUDIT_FUNCTION,
)
event.listen(
    InboundTransferItemAllocation.__table__,
    "after_create",
    _TRANSFER_ALLOCATION_AUDIT_TRIGGER,
)
event.listen(
    InboundTransferItemAllocation.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS validate_inbound_transfer_item_quantity()"),
)
event.listen(
    InboundTransferItemAllocation.__table__,
    "after_drop",
    DDL("DROP FUNCTION IF EXISTS reject_inbound_transfer_item_allocation_mutation()"),
)
