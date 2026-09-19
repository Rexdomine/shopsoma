"""Add explicit test-account classification metadata.

Revision ID: 3d4e5f6a7b8c
Revises: n1o2p3q4r5s6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "3d4e5f6a7b8c"
down_revision: Union[str, None] = "n1o2p3q4r5s6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_test_account", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("test_account_tagged_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("test_account_tagged_by", sa.UUID(), nullable=True),
    )
    op.add_column("users", sa.Column("test_account_tag_reason", sa.String(length=255), nullable=True))
    op.create_index("ix_users_is_test_account", "users", ["is_test_account"], unique=False)
    op.create_foreign_key(
        "fk_users_test_account_tagged_by",
        "users",
        "users",
        ["test_account_tagged_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # Keep the database default: direct SQL/bootstrap writers may omit this column.


def downgrade() -> None:
    op.drop_constraint("fk_users_test_account_tagged_by", "users", type_="foreignkey")
    op.drop_index("ix_users_is_test_account", table_name="users")
    op.drop_column("users", "test_account_tag_reason")
    op.drop_column("users", "test_account_tagged_by")
    op.drop_column("users", "test_account_tagged_at")
    op.drop_column("users", "is_test_account")
