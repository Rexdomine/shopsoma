"""create_app_settings_table

Revision ID: 1ccbab26fbcd
Revises: b6ad33a51bb1
Create Date: 2025-12-17 13:52:43.753582

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ccbab26fbcd'
down_revision: Union[str, None] = 'b6ad33a51bb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create app_settings table
    op.create_table(
        'app_settings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('value_type', sa.String(length=20), nullable=False, server_default='string'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_app_settings_key'), 'app_settings', ['key'], unique=True)

    # Insert default ShipBubble setting (disabled by default)
    op.execute(
        """
        INSERT INTO app_settings (id, key, value, value_type, description, is_public)
        VALUES (
            gen_random_uuid(),
            'shipping_use_shipbubble',
            'false',
            'boolean',
            'Use ShipBubble API for shipping rates',
            false
        )
        """
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_app_settings_key'), table_name='app_settings')
    op.drop_table('app_settings')
