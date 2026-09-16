"""add admin featured storefront vendor flag

Revision ID: n1o2p3q4r5s6
Revises: m0n1o2p3q4r5
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa

revision = "n1o2p3q4r5s6"
down_revision = "m0n1o2p3q4r5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vendors",
        sa.Column(
            "is_featured_storefront",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_vendors_is_featured_storefront",
        "vendors",
        ["is_featured_storefront"],
    )
    op.alter_column("vendors", "is_featured_storefront", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_vendors_is_featured_storefront", table_name="vendors")
    op.drop_column("vendors", "is_featured_storefront")
