"""Persist server-issued product image upload identities.

No backfill: pre-migration unassociated uploads must be uploaded again.
Existing product images, including legacy images, remain valid.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v5w6x7y8z9a0"
down_revision = "u4v5w6x7y8z9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_image_uploads",
        sa.Column("image_url", sa.Text(), primary_key=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("storage_keys", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("product_image_uploads")
