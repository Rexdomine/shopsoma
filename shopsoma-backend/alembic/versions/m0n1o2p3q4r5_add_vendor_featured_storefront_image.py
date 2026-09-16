"""add vendor featured storefront image

Revision ID: m0n1o2p3q4r5
Revises: l9m0n1o2p3q4
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa


revision = "m0n1o2p3q4r5"
down_revision = "l9m0n1o2p3q4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vendors",
        sa.Column("featured_storefront_image_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("vendors", "featured_storefront_image_url")
