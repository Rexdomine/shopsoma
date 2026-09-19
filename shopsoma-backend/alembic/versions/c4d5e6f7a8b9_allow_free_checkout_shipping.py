"""Allow legitimate zero-cost checkout shipping options.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
"""

from alembic import op


revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None

_OPTION_NONNEGATIVE = "amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric) AND amount >= 0 AND amount <= 99999999.99 AND currency ~ '^[A-Z]{3}$'"
_OPTION_POSITIVE = _OPTION_NONNEGATIVE.replace("amount >= 0", "amount > 0")
_SELECTION_NONNEGATIVE = "shipping_amount NOT IN ('NaN'::numeric,'Infinity'::numeric,'-Infinity'::numeric) AND shipping_amount >= 0 AND shipping_amount <= 99999999.99 AND currency ~ '^[A-Z]{3}$'"
_SELECTION_POSITIVE = _SELECTION_NONNEGATIVE.replace(
    "shipping_amount >= 0", "shipping_amount > 0"
)


def _replace(name: str, table: str, expression: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, expression)


def upgrade() -> None:
    _replace(
        "ck_checkout_estimate_options_money",
        "checkout_shipping_estimate_options",
        _OPTION_NONNEGATIVE,
    )
    _replace(
        "ck_checkout_estimate_selections_money",
        "checkout_shipping_estimate_selections",
        _SELECTION_NONNEGATIVE,
    )


def downgrade() -> None:
    _replace(
        "ck_checkout_estimate_selections_money",
        "checkout_shipping_estimate_selections",
        _SELECTION_POSITIVE,
    )
    _replace(
        "ck_checkout_estimate_options_money",
        "checkout_shipping_estimate_options",
        _OPTION_POSITIVE,
    )
