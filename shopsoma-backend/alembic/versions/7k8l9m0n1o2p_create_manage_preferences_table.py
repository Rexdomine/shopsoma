"""create manage_preferences table

Revision ID: 7k8l9m0n1o2p
Revises: 6f7g8h9i0j1k
Create Date: 2025-11-26 16:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = '7k8l9m0n1o2p'
down_revision: Union[str, None] = '6f7g8h9i0j1k'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create manage_preferences table"""
    op.create_table(
        'manage_preferences',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('interest', sa.String(length=50), nullable=True),
        sa.Column('preferred_language', sa.String(length=100), nullable=True),
        sa.Column('preferred_currency', sa.String(length=10), nullable=True),
        sa.Column('favorite_designers', JSONB, nullable=False, server_default='[]'),
        sa.Column('favorite_categories', JSONB, nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    """Drop manage_preferences table"""
    op.drop_table('manage_preferences')
