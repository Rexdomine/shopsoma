"""add payment gateway customer ids to user

Revision ID: 9748af8bb105
Revises: 5ec6095c2c06
Create Date: 2025-11-21 22:58:48.358745

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9748af8bb105'
down_revision: Union[str, None] = '5ec6095c2c06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add payment gateway customer ID columns to users table
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('paystack_customer_code', sa.String(length=255), nullable=True))
    op.create_index(op.f('ix_users_stripe_customer_id'), 'users', ['stripe_customer_id'], unique=False)
    op.create_index(op.f('ix_users_paystack_customer_code'), 'users', ['paystack_customer_code'], unique=False)


def downgrade() -> None:
    # Remove payment gateway customer ID columns from users table
    op.drop_index(op.f('ix_users_paystack_customer_code'), table_name='users')
    op.drop_index(op.f('ix_users_stripe_customer_id'), table_name='users')
    op.drop_column('users', 'paystack_customer_code')
    op.drop_column('users', 'stripe_customer_id')
