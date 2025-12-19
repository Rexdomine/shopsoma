"""add_date_of_birth_to_users

Revision ID: 4faacd854049
Revises: 66739681d75e
Create Date: 2025-11-26 13:10:27.888350

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4faacd854049'
down_revision: Union[str, None] = '66739681d75e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add date_of_birth column to users table
    op.add_column('users', sa.Column('date_of_birth', sa.Date(), nullable=True))


def downgrade() -> None:
    # Remove date_of_birth column from users table
    op.drop_column('users', 'date_of_birth')
