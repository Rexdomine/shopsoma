"""add One/Size to sizeenum

Revision ID: x7y8z9a0b1c2
Revises: w6x7y8z9a0b1
Create Date: 2026-10-01 12:00:00.000000
"""

from alembic import op

revision = "x7y8z9a0b1c2"
down_revision = "w6x7y8z9a0b1"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE sizeenum ADD VALUE IF NOT EXISTS 'One/Size'")


def downgrade():
    # PostgreSQL does not support removing values from an enum type directly
    pass
