"""add_collection_banner_image

Revision ID: 8f7c9a1b2c3d
Revises: 17d4240dbb35
Create Date: 2025-12-24 11:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8f7c9a1b2c3d"
down_revision = "17d4240dbb35"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collections", sa.Column("banner_image_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("collections", "banner_image_url")
