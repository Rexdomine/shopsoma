"""Persist exact storage keys for product image lifecycle cleanup."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "r7s8t9u0v1w2"
down_revision = "q3r4s5t6u7v8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product_images",
        sa.Column("storage_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product_images", "storage_keys")
