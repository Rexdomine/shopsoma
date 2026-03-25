"""add currency to orders and order items

Revision ID: i5j6k7l8m9n0
Revises: c1d2e3f4g5h6
Create Date: 2026-03-25 13:55:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "i5j6k7l8m9n0"
down_revision = "c1d2e3f4g5h6"
branch_labels = None
depends_on = None

ORDERS_CURRENCY_MARKER = "created_by_migration_i5j6k7l8m9n0_orders_currency"
ORDER_ITEMS_CURRENCY_MARKER = "created_by_migration_i5j6k7l8m9n0_order_items_currency"


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _set_column_marker(table_name: str, column_name: str, marker: str) -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(f"COMMENT ON COLUMN {table_name}.{column_name} IS :marker"),
        {"marker": marker},
    )


def _get_column_marker(table_name: str, column_name: str):
    bind = op.get_bind()
    return bind.execute(
        sa.text(
            """
            SELECT pg_catalog.col_description(cls.oid, attr.attnum)
            FROM pg_catalog.pg_class AS cls
            JOIN pg_catalog.pg_attribute AS attr
              ON attr.attrelid = cls.oid
            WHERE cls.relname = :table_name
              AND attr.attname = :column_name
              AND attr.attnum > 0
              AND NOT attr.attisdropped
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    ).scalar_one_or_none()


def upgrade():
    if not _column_exists("orders", "currency"):
        op.add_column(
            "orders",
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="NGN"),
        )
        _set_column_marker("orders", "currency", ORDERS_CURRENCY_MARKER)
    if not _column_exists("order_items", "currency"):
        op.add_column(
            "order_items",
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="NGN"),
        )
        _set_column_marker("order_items", "currency", ORDER_ITEMS_CURRENCY_MARKER)


def downgrade():
    if _column_exists("order_items", "currency") and _get_column_marker("order_items", "currency") == ORDER_ITEMS_CURRENCY_MARKER:
        op.drop_column("order_items", "currency")
    if _column_exists("orders", "currency") and _get_column_marker("orders", "currency") == ORDERS_CURRENCY_MARKER:
        op.drop_column("orders", "currency")
