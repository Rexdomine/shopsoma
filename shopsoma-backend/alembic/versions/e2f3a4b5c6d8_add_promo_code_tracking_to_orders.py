"""Add promo code tracking columns to orders

Revision ID: e2f3a4b5c6d8
Revises: d1e2f3a4b5c7
Create Date: 2026-11-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2f3a4b5c6d8"
down_revision: Union[str, None] = "d1e2f3a4b5c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE orders
            ADD COLUMN IF NOT EXISTS promo_code_id UUID,
            ADD COLUMN IF NOT EXISTS promo_code VARCHAR(50),
            ADD COLUMN IF NOT EXISTS promo_usage_counted BOOLEAN NOT NULL DEFAULT FALSE;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_orders_promo_code_id'
            ) THEN
                ALTER TABLE orders
                    ADD CONSTRAINT fk_orders_promo_code_id
                    FOREIGN KEY (promo_code_id) REFERENCES promo_codes(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_orders_promo_code_id
            ON orders (promo_code_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_orders_promo_code_id;")
    op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS fk_orders_promo_code_id;")
    op.execute(
        """
        ALTER TABLE orders
            DROP COLUMN IF EXISTS promo_usage_counted,
            DROP COLUMN IF EXISTS promo_code,
            DROP COLUMN IF EXISTS promo_code_id;
        """
    )
