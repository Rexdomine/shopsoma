"""Durably retain product-image storage keys that need cleanup retry."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "s1t2u3v4w5x6"
down_revision = "r7s8t9u0v1w2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_image_storage_cleanups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("storage_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_product_image_storage_cleanups_product_id", "product_image_storage_cleanups", ["product_id"])
    op.create_index("ix_product_image_storage_cleanups_image_id", "product_image_storage_cleanups", ["image_id"])


def downgrade() -> None:
    op.drop_index("ix_product_image_storage_cleanups_image_id", table_name="product_image_storage_cleanups")
    op.drop_index("ix_product_image_storage_cleanups_product_id", table_name="product_image_storage_cleanups")
    op.drop_table("product_image_storage_cleanups")