"""add return admin notes

Revision ID: c1d2e3f4g5h6
Revises: b9f1c2d3e4f5
Create Date: 2026-01-26 14:15:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c1d2e3f4g5h6'
down_revision = 'b9f1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('returns', sa.Column('admin_notes', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('returns', 'admin_notes')
