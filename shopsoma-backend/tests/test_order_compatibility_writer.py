"""Gate-off order compatibility-writer persistence contracts."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.order import Order
from app.models.order_guest_capability import OrderCurrentOwner
from app.models.user import User, UserRole


def _order(customer_id, **overrides) -> Order:
    values = {
        "id": uuid.uuid4(),
        "order_number": f"COMPAT-{uuid.uuid4().hex[:12]}",
        "customer_id": customer_id,
        "currency": "NGN",
        "subtotal": Decimal("100.00"),
        "shipping_cost": Decimal("0.00"),
        "tax_amount": Decimal("0.00"),
        "discount_amount": Decimal("0.00"),
        "total_amount": Decimal("100.00"),
    }
    values.update(overrides)
    return Order(**values)


@pytest.mark.asyncio
async def test_authenticated_order_write_adds_legacy_truth_and_owner(
    db_session, customer_user
) -> None:
    order = _order(customer_user["user"].id)
    db_session.add(order)

    await db_session.flush()

    assert (
        order.workflow_cohort,
        order.workflow_policy_version,
        order.checkout_access_mode,
    ) == ("legacy_pre_bridge", "legacy_pre_bridge_v1", "authenticated")
    owner = await db_session.get(OrderCurrentOwner, order.id)
    assert owner is not None
    assert owner.original_customer_id == order.customer_id
    assert owner.current_authenticated_user_id is None


@pytest.mark.asyncio
async def test_guest_order_write_preserves_guest_ownership_in_legacy_truth(
    db_session, customer_user
) -> None:
    order = _order(
        customer_user["user"].id,
        checkout_access_mode="guest_capability",
    )
    db_session.add(order)

    await db_session.flush()

    assert order.workflow_cohort == "legacy_pre_bridge"
    assert order.workflow_policy_version == "legacy_pre_bridge_v1"
    assert order.checkout_access_mode == "guest_capability"
    owner = await db_session.get(OrderCurrentOwner, order.id)
    assert owner is not None
    assert owner.original_customer_id == order.customer_id


@pytest.mark.asyncio
async def test_bulk_order_flush_inserts_generated_owners_after_pending_orders(
    db_session, customer_user
) -> None:
    pending_customer = User(
        id=uuid.uuid4(),
        email=f"compat-{uuid.uuid4().hex}@test.com",
        full_name="Compatibility Customer",
        role=UserRole.CUSTOMER,
        email_verified=True,
        is_active=True,
    )
    orders = [
        _order(customer_user["user"].id),
        _order(pending_customer.id),
        _order(customer_user["user"].id),
    ]
    db_session.add_all([pending_customer, *orders])

    await db_session.flush()

    owners = (
        await db_session.scalars(
            select(OrderCurrentOwner).where(
                OrderCurrentOwner.order_id.in_([order.id for order in orders])
            )
        )
    ).all()
    assert {owner.order_id for owner in owners} == {order.id for order in orders}


@pytest.mark.asyncio
async def test_repeated_flush_is_idempotent_and_rollback_removes_both_rows(
    db_session, customer_user
) -> None:
    order = _order(customer_user["user"].id)
    db_session.add(order)

    await db_session.flush()
    await db_session.flush()
    owner_count = await db_session.scalar(
        select(func.count())
        .select_from(OrderCurrentOwner)
        .where(OrderCurrentOwner.order_id == order.id)
    )
    assert owner_count == 1

    await db_session.rollback()

    assert await db_session.get(Order, order.id) is None
    assert await db_session.get(OrderCurrentOwner, order.id) is None

    db_session.add(order)
    await db_session.flush()

    assert await db_session.get(Order, order.id) is order
    assert await db_session.get(OrderCurrentOwner, order.id) is not None


@pytest.mark.asyncio
async def test_explicit_domestic_truth_is_never_overwritten(
    db_session, customer_user
) -> None:
    order = _order(
        customer_user["user"].id,
        workflow_cohort="domestic_checkout_v1",
        workflow_policy_version="domestic_checkout_v1",
        checkout_access_mode="authenticated",
    )
    db_session.add(order)

    await db_session.flush()

    assert (
        order.workflow_cohort,
        order.workflow_policy_version,
        order.checkout_access_mode,
    ) == ("domestic_checkout_v1", "domestic_checkout_v1", "authenticated")
    assert await db_session.get(OrderCurrentOwner, order.id) is not None
