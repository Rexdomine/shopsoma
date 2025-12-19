"""create_settings_table

Revision ID: h4i5j6k7l8m9
Revises: 94cb1a1d069d
Create Date: 2025-12-12 14:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = 'h4i5j6k7l8m9'
down_revision = '94cb1a1d069d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create settings table and seed initial data"""
    # Create settings table
    op.create_table(
        'settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('key', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Seed initial exchange rate setting
    op.execute(
        """
        INSERT INTO settings (id, key, value, description, created_at, updated_at)
        VALUES (
            gen_random_uuid(),
            'exchange_rate_usd_to_ngn',
            '833',
            'Exchange rate from USD to NGN (1 USD = X NGN)',
            NOW(),
            NOW()
        )
        """
    )


def downgrade() -> None:
    """Drop settings table"""
    op.drop_table('settings')
