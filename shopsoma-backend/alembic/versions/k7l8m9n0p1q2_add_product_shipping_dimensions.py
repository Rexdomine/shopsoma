"""add vendor supplied parcel dimensions to products

Revision ID: k7l8m9n0p1q2
Revises: 1c2b3d4e
"""
from alembic import op
import sqlalchemy as sa

revision = "k7l8m9n0p1q2"
down_revision = "1c2b3d4e"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("weight_kg", "length_cm", "width_cm", "height_cm"):
        op.add_column("products", sa.Column(name, sa.Numeric(10, 3), nullable=True))


def downgrade():
    for name in ("height_cm", "width_cm", "length_cm", "weight_kg"):
        op.drop_column("products", name)