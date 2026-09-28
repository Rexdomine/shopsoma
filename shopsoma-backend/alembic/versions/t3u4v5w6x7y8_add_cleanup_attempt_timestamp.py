"""Track product-image cleanup retry scheduling."""

from alembic import op
import sqlalchemy as sa


revision = "t3u4v5w6x7y8"
down_revision = "s1t2u3v4w5x6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_image_storage_cleanups",
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_product_image_storage_cleanups_last_attempted_at",
        "product_image_storage_cleanups",
        ["last_attempted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_image_storage_cleanups_last_attempted_at",
        table_name="product_image_storage_cleanups",
    )
    op.drop_column("product_image_storage_cleanups", "last_attempted_at")
