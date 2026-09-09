"""add vendor supplied parcel dimensions to products

Revision ID: k7l8m9n0p1q2
Revises: f9d1b3e5a7c9
"""
from alembic import op
import sqlalchemy as sa

revision = "k7l8m9n0p1q2"
down_revision = "75427e964440"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("weight_kg", "length_cm", "width_cm", "height_cm"):
        op.add_column("products", sa.Column(name, sa.Numeric(10, 3), nullable=True))


def downgrade():
    for name in ("height_cm", "width_cm", "length_cm", "weight_kg"):
        op.drop_column("products", name)