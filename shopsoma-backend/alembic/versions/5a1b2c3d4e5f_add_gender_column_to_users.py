"""add gender column to users

Revision ID: 5a1b2c3d4e5f
Revises: 4faacd854049
Create Date: 2025-11-26 14:22:55.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a1b2c3d4e5f'
down_revision: Union[str, None] = '4faacd854049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add gender column to users table"""
    # Add gender column as nullable String(50)
    # Matches the User model definition: gender = Column(String(50), nullable=True)
    op.add_column('users', sa.Column('gender', sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Remove gender column from users table"""
    op.drop_column('users', 'gender')
