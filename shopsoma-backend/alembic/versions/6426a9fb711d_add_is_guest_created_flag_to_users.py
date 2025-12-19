"""add is_guest_created flag to users

Revision ID: 6426a9fb711d
Revises: 9748af8bb105
Create Date: 2025-11-22 17:39:59.630632

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6426a9fb711d'
down_revision: Union[str, None] = '9748af8bb105'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_guest_created flag to users."""
    op.add_column(
        'users',
        sa.Column(
            'is_guest_created',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false')
        ),
    )
    # Backfill existing rows to false then drop default so application controls value
    op.execute("UPDATE users SET is_guest_created = FALSE WHERE is_guest_created IS NULL")
    op.alter_column('users', 'is_guest_created', server_default=None)


def downgrade() -> None:
    """Remove is_guest_created flag from users."""
    op.drop_column('users', 'is_guest_created')
