"""Add a durable lease for external product-image cleanup calls."""

from alembic import op
import sqlalchemy as sa


revision = "u4v5w6x7y8z9"
down_revision = "t3u4v5w6x7y8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_image_storage_cleanups",
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_product_image_storage_cleanups_claimed_at",
        "product_image_storage_cleanups",
        ["claimed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_image_storage_cleanups_claimed_at",
        table_name="product_image_storage_cleanups",
    )
    op.drop_column("product_image_storage_cleanups", "claimed_at")
