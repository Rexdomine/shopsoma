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
    # Preserve legacy rows while making the new cross-command key unique.
    # Older releases allowed the same customer/key pair once per source
    # command, so rewrite later duplicates before creating the constraint.
    # Both the append-only guard and the truth-validation trigger reject this
    # intentional legacy-key rewrite. Disable only user triggers for the locked
    # table, then restore them before the migration returns.
    op.execute(
        "ALTER TABLE checkout_shipping_estimates DISABLE TRIGGER USER"
    )
    try:
        op.execute(
            """
            WITH duplicates AS (
                SELECT id,
                       idempotency_key,
                       ROW_NUMBER() OVER (
                           PARTITION BY customer_id, idempotency_key
                           ORDER BY created_at, id
                       ) AS duplicate_number
                FROM checkout_shipping_estimates
            )
            UPDATE checkout_shipping_estimates AS estimate
            SET idempotency_key = LEFT(duplicates.idempotency_key, 150)
                || ':legacy:' || duplicates.id::text
            FROM duplicates
            WHERE estimate.id = duplicates.id
              AND duplicates.duplicate_number > 1
            """
        )
    finally:
        op.execute(
            "ALTER TABLE checkout_shipping_estimates ENABLE TRIGGER USER"
        )
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
