"""add admin-curated shop edits associations

Revision ID: q3r4s5t6u7v8
Revises: c9d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa

revision = "q3r4s5t6u7v8"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "product_shop_edit_categories",
        sa.Column("product_id", sa.UUID(), nullable=False),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "category_id"),
    )
    op.create_index("ix_product_shop_edit_categories_category_id", "product_shop_edit_categories", ["category_id"])


def downgrade():
    op.drop_index("ix_product_shop_edit_categories_category_id", table_name="product_shop_edit_categories")
    op.drop_table("product_shop_edit_categories")
