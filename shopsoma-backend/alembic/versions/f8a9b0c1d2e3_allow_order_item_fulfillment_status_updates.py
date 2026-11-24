"""Allow order_items.fulfillment_status updates on domestic_checkout_v1 orders.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-11-23 20:45:00.000000

Scopes ``trg_order_items_checkout_completion`` to checkout-prerequisite and
item-identity/inventory columns (matching ``trg_orders_checkout_completion``)
so post-payment ``order_items.fulfillment_status`` updates no longer re-run
the pre-payment ``active`` stock reservation check against ``consumed``
reservations, then backfills stale ``order_items.fulfillment_status`` values on
``domestic_checkout_v1`` orders.
"""

from typing import Union

from alembic import op


revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_order_items_checkout_completion ON order_items;

        CREATE CONSTRAINT TRIGGER trg_order_items_checkout_completion
        AFTER INSERT OR DELETE OR UPDATE OF id,order_id,product_id,variant_id,vendor_id,inventory_policy,inventory_subject_kind,inventory_subject_id,inventory_source_product_id,inventory_source_catalogue_version,inventory_source_evidence_hash,inventory_policy_snapshot_at,quantity,unit_price,subtotal,currency
        ON order_items
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION validate_checkout_prerequisite_completion();

        UPDATE order_items AS oi
        SET fulfillment_status = o.fulfillment_status
        FROM orders AS o
        WHERE oi.order_id = o.id
          AND o.workflow_cohort = 'domestic_checkout_v1'
          AND oi.fulfillment_status <> 'cancelled'
          AND oi.fulfillment_status IS DISTINCT FROM o.fulfillment_status
          AND (
              o.fulfillment_status IN (
                  'delivered',
                  'delivery_failed',
                  'returned',
                  'cancelled',
                  'in_transit',
                  'out_for_delivery'
              )
              OR (
                  o.fulfillment_status IN (
                      'preparing_for_pickup',
                      'pickup_scheduled',
                      'picked_up'
                  )
                  AND NOT (
                      oi.inventory_policy = 'made_to_order'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM vendor_pickups AS vp
                          WHERE vp.order_item_id = oi.id
                            AND (
                                vp.ready_for_pickup_at IS NOT NULL
                                OR vp.actual_pickup_date IS NOT NULL
                            )
                      )
                  )
              )
          );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_order_items_checkout_completion ON order_items;

        CREATE CONSTRAINT TRIGGER trg_order_items_checkout_completion
        AFTER INSERT OR UPDATE OR DELETE ON order_items
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
        EXECUTE FUNCTION validate_checkout_prerequisite_completion();
        """
    )
