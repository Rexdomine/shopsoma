"""Make checkout estimate idempotency independent of leaf command.

Revision ID: l9m0n1o2p3q4
Revises: k7l8m9n0p1q2
"""

from alembic import op

revision = "l9m0n1o2p3q4"
down_revision = "k7l8m9n0p1q2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_checkout_shipping_estimates_replay",
        "checkout_shipping_estimates",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_checkout_shipping_estimates_replay",
        "checkout_shipping_estimates",
        ["customer_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_checkout_shipping_estimates_replay",
        "checkout_shipping_estimates",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_checkout_shipping_estimates_replay",
        "checkout_shipping_estimates",
        ["customer_id", "source_command", "idempotency_key"],
    )
