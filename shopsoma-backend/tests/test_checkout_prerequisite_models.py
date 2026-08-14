"""Milestone 2 ORM persistence and authorization metadata contracts."""

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint


def _constraint_names(table):
    return {constraint.name for constraint in table.constraints if constraint.name}


def test_checkout_prerequisite_tables_are_distinct_and_complete() -> None:
    from app.models.checkout_shipping_estimate import (
        CheckoutShippingEstimate,
        CheckoutShippingEstimateOption,
        CheckoutShippingEstimateSelection,
        OrderInventoryCoverage,
    )
    from app.models.customer_shipping_quote import CustomerShippingQuote

    assert CheckoutShippingEstimate.__tablename__ != CustomerShippingQuote.__tablename__
    assert (
        CheckoutShippingEstimateOption.__tablename__
        == "checkout_shipping_estimate_options"
    )
    assert (
        CheckoutShippingEstimateSelection.__tablename__
        == "checkout_shipping_estimate_selections"
    )
    assert OrderInventoryCoverage.__tablename__ == "order_inventory_coverage"


def test_order_and_item_install_immutable_workflow_snapshot_contract() -> None:
    from app.models.order import Order, OrderItem

    assert {
        "workflow_cohort",
        "workflow_policy_version",
        "checkout_access_mode",
        "checkout_estimate_selection_id",
        "checkout_prerequisites_completed_at",
    } <= set(Order.__table__.columns.keys())
    assert {
        "inventory_policy",
        "inventory_subject_kind",
        "inventory_subject_id",
        "inventory_source_product_id",
        "inventory_source_catalogue_version",
        "inventory_source_evidence_hash",
        "inventory_policy_snapshot_at",
    } <= set(OrderItem.__table__.columns.keys())
    assert "uq_order_items_id_order_inventory_policy" in _constraint_names(
        OrderItem.__table__
    )


def test_guest_capability_persists_only_versioned_hmac_metadata() -> None:
    from app.models.order_guest_capability import OrderGuestCapability

    columns = set(OrderGuestCapability.__table__.columns.keys())
    assert {"id", "token_digest", "pepper_key_version", "scope", "order_id"} <= columns
    assert not ({"token", "plaintext_token", "secret"} & columns)
    digest_type = str(OrderGuestCapability.__table__.c.token_digest.type).upper()
    assert "BYTEA" in digest_type


def test_composite_topology_contains_exact_membership_targets() -> None:
    from app.models.stock_payment_persistence import (
        PaymentAttempt,
        PaymentAttemptReservation,
        StockReservation,
    )

    membership = PaymentAttemptReservation.__table__
    assert {"order_id", "order_item_id", "checkout_estimate_selection_id"} <= set(
        membership.columns.keys()
    )
    assert "uq_payment_attempts_checkout_membership_target" in _constraint_names(
        PaymentAttempt.__table__
    )
    assert "uq_stock_reservations_checkout_membership_target" in _constraint_names(
        StockReservation.__table__
    )
    fks = [c for c in membership.constraints if isinstance(c, ForeignKeyConstraint)]
    tuples = {
        (
            tuple(element.parent.name for element in fk.elements),
            tuple(element.target_fullname for element in fk.elements),
        )
        for fk in fks
    }
    assert (
        ("attempt_id", "order_id", "checkout_estimate_selection_id"),
        (
            "payment_attempts.id",
            "payment_attempts.order_id",
            "payment_attempts.checkout_estimate_selection_id",
        ),
    ) in tuples
    assert (
        (
            "reservation_id",
            "order_id",
            "order_item_id",
            "checkout_estimate_selection_id",
        ),
        (
            "stock_reservations.id",
            "stock_reservations.order_id",
            "stock_reservations.order_item_id",
            "stock_reservations.checkout_estimate_selection_id",
        ),
    ) in tuples


def test_schema_models_name_every_check_unique_and_composite_fk() -> None:
    from app.models.checkout_shipping_estimate import (
        CheckoutShippingEstimate,
        CheckoutShippingEstimateOption,
        CheckoutShippingEstimateSelection,
        OrderInventoryCoverage,
    )
    from app.models.order_guest_capability import (
        OrderCurrentOwner,
        OrderGuestCapability,
        OrderWorkflowClassification,
        OrderWorkflowMigrationRun,
    )

    for model in (
        CheckoutShippingEstimate,
        CheckoutShippingEstimateOption,
        CheckoutShippingEstimateSelection,
        OrderInventoryCoverage,
        OrderCurrentOwner,
        OrderGuestCapability,
        OrderWorkflowClassification,
        OrderWorkflowMigrationRun,
    ):
        for constraint in model.__table__.constraints:
            if isinstance(constraint, (CheckConstraint, UniqueConstraint)) or (
                isinstance(constraint, ForeignKeyConstraint)
                and len(constraint.elements) > 1
            ):
                assert (
                    constraint.name
                    or constraint.__class__.__name__ == "PrimaryKeyConstraint"
                )
