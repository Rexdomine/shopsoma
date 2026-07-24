"""add domestic fulfillment persistence

Revision ID: 8c2d4e6f7a9b
Revises: 7b87484b1b1f
Create Date: 2026-07-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8c2d4e6f7a9b"
down_revision: Union[str, Sequence[str], None] = "7b87484b1b1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


profile_source = postgresql.ENUM(
    "manual",
    "measured",
    "imported",
    name="logistics_profile_source",
    create_type=False,
)
verification_status = postgresql.ENUM(
    "pending",
    "verified",
    "rejected",
    name="logistics_verification_status",
    create_type=False,
)


def upgrade() -> None:
    profile_source.create(op.get_bind(), checkfirst=False)
    verification_status.create(op.get_bind(), checkfirst=False)

    op.create_unique_constraint(
        "uq_product_variants_product_id_id",
        "product_variants",
        ["product_id", "id"],
    )
    op.create_table(
        "fulfillment_hubs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=False),
        sa.Column("contact_phone", sa.String(length=32), nullable=False),
        sa.Column("address_line1", sa.String(length=255), nullable=False),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=False),
        sa.Column("state", sa.String(length=100), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column(
            "country_code", sa.String(length=2), server_default="NG", nullable=False
        ),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default="Africa/Lagos",
            nullable=False,
        ),
        sa.Column("cutoff_time", sa.Time(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            "code ~ '^[a-z0-9]+(-[a-z0-9]+)*$'",
            name="ck_fulfillment_hubs_code_canonical",
        ),
        sa.CheckConstraint(
            "name ~ '[^[:space:]]'", name="ck_fulfillment_hubs_name_present"
        ),
        sa.CheckConstraint(
            "contact_name ~ '[^[:space:]]'",
            name="ck_fulfillment_hubs_contact_name_present",
        ),
        sa.CheckConstraint(
            "contact_phone ~ '[^[:space:]]'",
            name="ck_fulfillment_hubs_contact_phone_present",
        ),
        sa.CheckConstraint(
            "address_line1 ~ '[^[:space:]]'",
            name="ck_fulfillment_hubs_address_line1_present",
        ),
        sa.CheckConstraint(
            "city ~ '[^[:space:]]'", name="ck_fulfillment_hubs_city_present"
        ),
        sa.CheckConstraint(
            "state ~ '[^[:space:]]'", name="ck_fulfillment_hubs_state_present"
        ),
        sa.CheckConstraint(
            "country_code = 'NG'", name="ck_fulfillment_hubs_country_ng"
        ),
        sa.CheckConstraint(
            "timezone = 'Africa/Lagos'", name="ck_fulfillment_hubs_timezone_lagos"
        ),
        sa.CheckConstraint("version >= 1", name="ck_fulfillment_hubs_version_positive"),
        sa.CheckConstraint(
            "(activated_at IS NULL AND activated_by_id IS NULL) OR "
            "(activated_at IS NOT NULL AND activated_by_id IS NOT NULL)",
            name="ck_fulfillment_hubs_activation_audit_paired",
        ),
        sa.CheckConstraint(
            "NOT is_active OR (activated_at IS NOT NULL AND activated_by_id IS NOT NULL)",
            name="ck_fulfillment_hubs_active_has_audit",
        ),
        sa.ForeignKeyConstraint(["activated_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_fulfillment_hubs_code"),
    )
    op.execute(
        """
        CREATE FUNCTION prevent_fulfillment_hub_activation_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.activated_at IS NOT NULL AND (
                NEW.activated_at IS DISTINCT FROM OLD.activated_at
                OR NEW.activated_by_id IS DISTINCT FROM OLD.activated_by_id
            ) THEN
                RAISE EXCEPTION 'fulfillment hub activation audit is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER tr_fulfillment_hubs_activation_audit_immutable
        BEFORE UPDATE OF activated_at, activated_by_id ON fulfillment_hubs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_fulfillment_hub_activation_audit_mutation();
        """
    )
    op.create_table(
        "product_logistics_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("weight_kg", sa.Numeric(precision=7, scale=3), nullable=True),
        sa.Column("length_cm", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("width_cm", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("height_cm", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("preparation_min_days", sa.Integer(), nullable=True),
        sa.Column("preparation_max_days", sa.Integer(), nullable=True),
        sa.Column("source", profile_source, server_default="manual", nullable=False),
        sa.Column(
            "verification_status",
            verification_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            "(weight_kg IS NULL AND length_cm IS NULL AND width_cm IS NULL "
            "AND height_cm IS NULL) OR "
            "(weight_kg IS NOT NULL AND length_cm IS NOT NULL "
            "AND width_cm IS NOT NULL AND height_cm IS NOT NULL "
            "AND weight_kg > 0 AND weight_kg <= 1000 "
            "AND length_cm > 0 AND length_cm <= 1000 "
            "AND width_cm > 0 AND width_cm <= 1000 "
            "AND height_cm > 0 AND height_cm <= 1000)",
            name="ck_product_logistics_profiles_measurements",
        ),
        sa.CheckConstraint(
            "(preparation_min_days IS NULL AND preparation_max_days IS NULL) OR "
            "(preparation_min_days IS NOT NULL "
            "AND preparation_max_days IS NOT NULL "
            "AND preparation_min_days >= 0 AND preparation_max_days >= "
            "preparation_min_days AND preparation_max_days <= 365)",
            name="ck_product_logistics_profiles_preparation_days",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_product_logistics_profiles_version_positive"
        ),
        sa.CheckConstraint(
            "(verification_status = 'pending' AND verified_at IS NULL "
            "AND verified_by_id IS NULL) OR "
            "(verification_status IN ('verified', 'rejected') "
            "AND verified_at IS NOT NULL AND verified_by_id IS NOT NULL)",
            name="ck_product_logistics_profiles_verification_consistent",
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["product_id", "variant_id"],
            ["product_variants.product_id", "product_variants.id"],
            name="fk_product_logistics_profiles_variant",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_product_logistics_profiles_product",
        "product_logistics_profiles",
        ["product_id"],
        unique=True,
        postgresql_where=sa.text("variant_id IS NULL"),
    )
    op.create_index(
        "uq_product_logistics_profiles_variant",
        "product_logistics_profiles",
        ["product_id", "variant_id"],
        unique=True,
        postgresql_where=sa.text("variant_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS tr_fulfillment_hubs_activation_audit_immutable "
        "ON fulfillment_hubs"
    )
    op.drop_index(
        "uq_product_logistics_profiles_variant",
        table_name="product_logistics_profiles",
    )
    op.drop_index(
        "uq_product_logistics_profiles_product",
        table_name="product_logistics_profiles",
    )
    op.drop_table("product_logistics_profiles")
    op.drop_table("fulfillment_hubs")
    op.execute(
        "DROP FUNCTION IF EXISTS " "prevent_fulfillment_hub_activation_audit_mutation()"
    )
    op.drop_constraint(
        "uq_product_variants_product_id_id",
        "product_variants",
        type_="unique",
    )
    verification_status.drop(op.get_bind(), checkfirst=False)
    profile_source.drop(op.get_bind(), checkfirst=False)
