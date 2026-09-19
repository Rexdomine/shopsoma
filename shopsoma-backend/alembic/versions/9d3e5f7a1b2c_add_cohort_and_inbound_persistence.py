"""add cohort and independent inbound persistence

Revision ID: 9d3e5f7a1b2c
Revises: 8c2d4e6f7a9b
Create Date: 2026-07-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "9d3e5f7a1b2c"
down_revision: Union[str, Sequence[str], None] = "8c2d4e6f7a9b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


readiness_type = postgresql.ENUM(
    "ready_to_wear",
    "made_to_order",
    name="fulfillment_readiness_type",
    create_type=False,
)
vendor_preparation_state = postgresql.ENUM(
    "not_started",
    "vendor_notified",
    "preparing",
    "ready_for_inbound",
    "blocked",
    "cancelled",
    name="vendor_preparation_state",
    create_type=False,
)
inbound_transfer_state = postgresql.ENUM(
    "not_requested",
    "planned",
    "accepted_by_provider",
    "handed_over",
    "in_transit",
    "received_partial",
    "received_complete",
    "delayed",
    "lost",
    "damaged",
    "cancelled",
    name="inbound_transfer_state",
    create_type=False,
)


def upgrade() -> None:
    readiness_type.create(op.get_bind(), checkfirst=False)
    vendor_preparation_state.create(op.get_bind(), checkfirst=False)
    inbound_transfer_state.create(op.get_bind(), checkfirst=False)

    op.create_unique_constraint(
        "uq_order_items_id_order_vendor",
        "order_items",
        ["id", "order_id", "vendor_id"],
    )

    op.create_table(
        "fulfillment_cohorts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("readiness_type", readiness_type, nullable=False),
        sa.Column("ready_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ready_through", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "state",
            vendor_preparation_state,
            server_default="not_started",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "ready_through >= ready_from",
            name="ck_fulfillment_cohorts_ready_window",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_fulfillment_cohorts_version_positive"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "order_id",
            "vendor_id",
            "readiness_type",
            "ready_from",
            "ready_through",
            name="uq_fulfillment_cohorts_canonical_window",
        ),
        sa.UniqueConstraint(
            "id",
            "order_id",
            "vendor_id",
            name="uq_fulfillment_cohorts_identity",
        ),
    )

    op.create_table(
        "cohort_item_allocations",
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allocated_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "allocated_quantity > 0",
            name="ck_cohort_item_allocations_quantity_positive",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id", "order_id", "vendor_id"],
            [
                "fulfillment_cohorts.id",
                "fulfillment_cohorts.order_id",
                "fulfillment_cohorts.vendor_id",
            ],
            name="fk_cohort_item_allocations_cohort_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["order_item_id", "order_id", "vendor_id"],
            ["order_items.id", "order_items.order_id", "order_items.vendor_id"],
            name="fk_cohort_item_allocations_order_item_identity",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("cohort_id", "order_item_id"),
        sa.UniqueConstraint(
            "cohort_id",
            "order_item_id",
            "order_id",
            "vendor_id",
            name="uq_cohort_item_allocations_identity",
        ),
    )

    op.create_table(
        "inbound_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_hub_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_name", sa.String(length=100), nullable=False),
        sa.Column("provider_reference", sa.String(length=200), nullable=False),
        sa.Column("replaces_transfer_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "state",
            inbound_transfer_state,
            server_default="not_requested",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider_name = btrim(provider_name) AND "
            "provider_name ~ '^[A-Za-z0-9][A-Za-z0-9 ._:/-]*$'",
            name="ck_inbound_transfers_provider_name_sanitized",
        ),
        sa.CheckConstraint(
            "provider_reference = btrim(provider_reference) AND "
            "provider_reference ~ '^[A-Za-z0-9][A-Za-z0-9 ._:/-]*$'",
            name="ck_inbound_transfers_provider_reference_sanitized",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_inbound_transfers_version_positive"
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id", "order_id", "vendor_id"],
            [
                "fulfillment_cohorts.id",
                "fulfillment_cohorts.order_id",
                "fulfillment_cohorts.vendor_id",
            ],
            name="fk_inbound_transfers_cohort_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
            ["target_hub_id"], ["fulfillment_hubs.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id",
            "cohort_id",
            "order_id",
            "vendor_id",
            name="uq_inbound_transfers_identity",
        ),
        sa.UniqueConstraint(
            "replaces_transfer_id",
            name="uq_inbound_transfers_replaces_transfer_id",
        ),
    )
    op.create_index(
        "uq_inbound_transfers_active_cohort",
        "inbound_transfers",
        ["cohort_id"],
        unique=True,
        postgresql_where=sa.text(
            "state NOT IN ('received_complete', 'lost', 'damaged', 'cancelled')"
        ),
    )

    op.create_table(
        "inbound_transfer_item_allocations",
        sa.Column("transfer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vendor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allocated_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "allocated_quantity > 0",
            name="ck_inbound_transfer_items_quantity_positive",
        ),
        sa.ForeignKeyConstraint(
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
        sa.ForeignKeyConstraint(
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
        sa.PrimaryKeyConstraint("transfer_id", "order_item_id"),
    )

    op.execute(
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
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_cohort_item_allocations_quantity_safe
        BEFORE INSERT ON cohort_item_allocations
        FOR EACH ROW
        EXECUTE FUNCTION validate_cohort_item_allocation_quantity();

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
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_order_items_cohort_quantity_safe
        BEFORE UPDATE OF quantity ON order_items
        FOR EACH ROW
        EXECUTE FUNCTION validate_order_item_quantity_against_cohorts();

        CREATE FUNCTION reject_fulfillment_cohort_delete()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION USING
                ERRCODE = '23503',
                MESSAGE = 'fulfillment cohorts are audit records and cannot be deleted';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_fulfillment_cohorts_delete_restricted
        BEFORE DELETE ON fulfillment_cohorts
        FOR EACH ROW EXECUTE FUNCTION reject_fulfillment_cohort_delete();

        CREATE FUNCTION reject_cohort_item_allocation_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION USING
                ERRCODE = '23503',
                MESSAGE = 'cohort item allocations are immutable audit records';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_cohort_item_allocations_immutable
        BEFORE UPDATE OR DELETE ON cohort_item_allocations
        FOR EACH ROW EXECUTE FUNCTION reject_cohort_item_allocation_mutation();

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
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_inbound_transfers_lineage_safe
        BEFORE INSERT OR UPDATE ON inbound_transfers
        FOR EACH ROW EXECUTE FUNCTION validate_inbound_transfer_lineage();

        CREATE FUNCTION reject_inbound_transfer_delete()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION USING
                ERRCODE = '23503',
                MESSAGE = 'inbound transfers are audit records and cannot be deleted';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_inbound_transfers_delete_restricted
        BEFORE DELETE ON inbound_transfers
        FOR EACH ROW EXECUTE FUNCTION reject_inbound_transfer_delete();

        CREATE FUNCTION validate_inbound_transfer_item_quantity()
        RETURNS trigger AS $$
        DECLARE cohort_quantity integer;
        BEGIN
            SELECT allocated_quantity INTO cohort_quantity
            FROM cohort_item_allocations
            WHERE cohort_id = NEW.cohort_id
              AND order_item_id = NEW.order_item_id
            FOR UPDATE;
            IF NEW.allocated_quantity > cohort_quantity THEN
                RAISE EXCEPTION USING
                    ERRCODE = '23514',
                    MESSAGE = 'inbound transfer allocation exceeds cohort allocation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_inbound_transfer_items_quantity_safe
        BEFORE INSERT ON inbound_transfer_item_allocations
        FOR EACH ROW
        EXECUTE FUNCTION validate_inbound_transfer_item_quantity();

        CREATE FUNCTION reject_inbound_transfer_item_allocation_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION USING
                ERRCODE = '23503',
                MESSAGE = 'inbound transfer item allocations are immutable audit records';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_inbound_transfer_item_allocations_immutable
        BEFORE UPDATE OR DELETE ON inbound_transfer_item_allocations
        FOR EACH ROW
        EXECUTE FUNCTION reject_inbound_transfer_item_allocation_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS tr_order_items_cohort_quantity_safe ON order_items"
    )
    op.drop_table("inbound_transfer_item_allocations")
    op.drop_index("uq_inbound_transfers_active_cohort", table_name="inbound_transfers")
    op.drop_table("inbound_transfers")
    op.drop_table("cohort_item_allocations")
    op.drop_table("fulfillment_cohorts")
    for function_name in (
        "reject_inbound_transfer_item_allocation_mutation",
        "validate_inbound_transfer_item_quantity",
        "reject_inbound_transfer_delete",
        "validate_inbound_transfer_lineage",
        "reject_cohort_item_allocation_mutation",
        "reject_fulfillment_cohort_delete",
        "validate_order_item_quantity_against_cohorts",
        "validate_cohort_item_allocation_quantity",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function_name}()")
    op.drop_constraint("uq_order_items_id_order_vendor", "order_items", type_="unique")
    inbound_transfer_state.drop(op.get_bind(), checkfirst=False)
    vendor_preparation_state.drop(op.get_bind(), checkfirst=False)
    readiness_type.drop(op.get_bind(), checkfirst=False)
