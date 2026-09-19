"""PostgreSQL contracts for fulfilment cohorts and independent inbound transfers."""

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.core.base import Base
from app.models import (
    CohortItemAllocation,
    FulfillmentCohort,
    FulfillmentReadinessType,
    InboundTransfer,
    InboundTransferItemAllocation,
)
from app.models.fulfillment_hub import FulfillmentHub
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.services.fulfillment.transitions import InboundState, VendorPreparationState


async def _rejects(session, instance, match: str | None = None) -> None:
    with pytest.raises(IntegrityError, match=match):
        async with session.begin_nested():
            session.add(instance)
            await session.flush()


async def _domain(db_session, vendor_user, customer_user):
    vendor_id = vendor_user["vendor"].id
    order = Order(
        order_number=f"COHORT-{uuid.uuid4().hex[:10]}",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("100.00"),
        total_amount=Decimal("100.00"),
    )
    product = Product(
        vendor_id=vendor_id, title="Cohort item", base_price=Decimal("10")
    )
    db_session.add_all([order, product])
    await db_session.flush()
    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor_id,
        product_title="Cohort item",
        unit_price=Decimal("10"),
        quantity=5,
        subtotal=Decimal("50"),
        commission_rate=Decimal("10"),
        commission_amount=Decimal("5"),
        vendor_payout=Decimal("45"),
    )
    hub = FulfillmentHub(
        code=f"lane3b-{uuid.uuid4().hex[:8]}",
        name="Lane 3B Hub",
        contact_name="Ops",
        contact_phone="+234****0000",
        address_line1="1 Test Street",
        city="Lagos",
        state="Lagos",
        cutoff_time=time(14),
    )
    db_session.add_all([item, hub])
    await db_session.flush()
    return order, item, hub


def _cohort(order, item, **overrides):
    now = datetime.now(timezone.utc)
    values = dict(
        order_id=order.id,
        vendor_id=item.vendor_id,
        readiness_type=FulfillmentReadinessType.READY_TO_WEAR,
        ready_from=now,
        ready_through=now + timedelta(days=2),
    )
    values.update(overrides)
    return FulfillmentCohort(**values)


def _allocation(cohort, item, quantity=1, **overrides):
    values = dict(
        cohort_id=cohort.id,
        order_item_id=item.id,
        order_id=cohort.order_id,
        vendor_id=cohort.vendor_id,
        allocated_quantity=quantity,
    )
    values.update(overrides)
    return CohortItemAllocation(**values)


def _transfer(cohort, hub, **overrides):
    values = dict(
        cohort_id=cohort.id,
        order_id=cohort.order_id,
        vendor_id=cohort.vendor_id,
        target_hub_id=hub.id,
        provider_name="Independent Provider",
        provider_reference=f"REF-{uuid.uuid4().hex[:12]}",
    )
    values.update(overrides)
    return InboundTransfer(**values)


def _transfer_allocation(transfer, allocation, quantity=1, **overrides):
    values = dict(
        transfer_id=transfer.id,
        cohort_id=allocation.cohort_id,
        order_item_id=allocation.order_item_id,
        order_id=allocation.order_id,
        vendor_id=allocation.vendor_id,
        allocated_quantity=quantity,
    )
    values.update(overrides)
    return InboundTransferItemAllocation(**values)


def test_models_are_public_and_use_transition_semantics() -> None:
    assert Base.metadata.tables["fulfillment_cohorts"] is FulfillmentCohort.__table__
    assert (
        Base.metadata.tables["cohort_item_allocations"]
        is CohortItemAllocation.__table__
    )
    assert Base.metadata.tables["inbound_transfers"] is InboundTransfer.__table__
    assert (
        Base.metadata.tables["inbound_transfer_item_allocations"]
        is InboundTransferItemAllocation.__table__
    )
    assert {
        state.value for state in FulfillmentCohort.__table__.c.state.type.enum_class
    } == {state.value for state in VendorPreparationState}
    assert {
        state.value for state in InboundTransfer.__table__.c.state.type.enum_class
    } == {state.value for state in InboundState}
    assert (
        inspect(FulfillmentCohort).version_id_col
        is FulfillmentCohort.__table__.c.version
    )
    assert (
        inspect(InboundTransfer).version_id_col is InboundTransfer.__table__.c.version
    )


def test_inbound_schema_is_independent_and_sanitized_only() -> None:
    columns = set(InboundTransfer.__table__.columns.keys())
    assert {
        "provider_name",
        "provider_reference",
        "target_hub_id",
        "replaces_transfer_id",
    } <= columns
    assert not columns.intersection(
        {
            "dhl",
            "carrier",
            "account_number",
            "credentials",
            "origin_address",
            "vendor_address",
            "tracking_url",
            "label",
        }
    )


@pytest.mark.asyncio
async def test_round_trip_defaults_windows_and_optimistic_versioning(
    db_session, vendor_user, customer_user
):
    order, item, hub = await _domain(db_session, vendor_user, customer_user)
    cohort = _cohort(order, item)
    db_session.add(cohort)
    await db_session.flush()
    allocation = _allocation(cohort, item, 3)
    transfer = _transfer(cohort, hub)
    db_session.add_all([allocation, transfer])
    await db_session.flush()
    transfer_allocation = _transfer_allocation(transfer, allocation, 2)
    db_session.add(transfer_allocation)
    await db_session.commit()

    assert cohort.state is VendorPreparationState.NOT_STARTED
    assert transfer.state is InboundState.NOT_REQUESTED
    assert cohort.version == transfer.version == 1
    assert cohort.created_at.tzinfo and transfer.created_at.tzinfo

    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    for model, row_id, attr, first_value, stale_value in (
        (
            FulfillmentCohort,
            cohort.id,
            "state",
            VendorPreparationState.VENDOR_NOTIFIED,
            VendorPreparationState.PREPARING,
        ),
        (
            InboundTransfer,
            transfer.id,
            "state",
            InboundState.PLANNED,
            InboundState.CANCELLED,
        ),
    ):
        async with sessions() as first, sessions() as stale:
            current = await first.get(model, row_id)
            outdated = await stale.get(model, row_id)
            setattr(current, attr, first_value)
            setattr(outdated, attr, stale_value)
            await first.commit()
            assert current.version == 2
            with pytest.raises(StaleDataError):
                await stale.commit()
            await stale.rollback()


@pytest.mark.asyncio
async def test_cohort_window_quantity_and_duplicate_constraints(
    db_session, vendor_user, customer_user
):
    order, item, _hub = await _domain(db_session, vendor_user, customer_user)
    now = datetime.now(timezone.utc)
    await _rejects(
        db_session,
        _cohort(order, item, ready_from=now, ready_through=now - timedelta(seconds=1)),
    )
    cohort = _cohort(order, item)
    db_session.add(cohort)
    await db_session.flush()
    await _rejects(
        db_session,
        _cohort(
            order,
            item,
            ready_from=cohort.ready_from,
            ready_through=cohort.ready_through,
        ),
    )
    await _rejects(db_session, _allocation(cohort, item, 0))
    db_session.add(_allocation(cohort, item, 3))
    await db_session.flush()
    await _rejects(db_session, _allocation(cohort, item, 1))


@pytest.mark.asyncio
async def test_cohort_allocation_rejects_cross_order_and_cross_vendor(
    db_session, vendor_user, customer_user
):
    order, item, _hub = await _domain(db_session, vendor_user, customer_user)
    other_order, other_item, _other_hub = await _domain(
        db_session, vendor_user, customer_user
    )
    cohort = _cohort(order, item)
    db_session.add(cohort)
    await db_session.flush()
    await _rejects(db_session, _allocation(cohort, other_item, 1))
    await _rejects(db_session, _allocation(cohort, item, 1, order_id=other_order.id))
    await _rejects(db_session, _allocation(cohort, item, 1, vendor_id=uuid.uuid4()))


@pytest.mark.asyncio
async def test_cohort_allocations_never_exceed_order_item_quantity_concurrently(
    db_session, vendor_user, customer_user
):
    order, item, _hub = await _domain(db_session, vendor_user, customer_user)
    first_cohort = _cohort(order, item)
    second_cohort = _cohort(
        order,
        item,
        readiness_type=FulfillmentReadinessType.MADE_TO_ORDER,
        ready_from=datetime.now(timezone.utc) + timedelta(days=3),
        ready_through=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db_session.add_all([first_cohort, second_cohort])
    await db_session.commit()

    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    async with sessions() as first, sessions() as second:
        first.add(_allocation(first_cohort, item, 3))
        await first.flush()  # holds the order-item row lock used by the trigger
        second.add(_allocation(second_cohort, item, 3))
        second_commit = __import__("asyncio").create_task(second.commit())
        await __import__("asyncio").sleep(0.1)
        assert not second_commit.done()
        await first.commit()
        with pytest.raises(IntegrityError):
            await second_commit
        await second.rollback()


@pytest.mark.asyncio
async def test_transfer_rejects_cross_cohort_hub_and_ambiguous_active_replacement(
    db_session, vendor_user, customer_user
):
    order, item, hub = await _domain(db_session, vendor_user, customer_user)
    other_order, other_item, _other_hub = await _domain(
        db_session, vendor_user, customer_user
    )
    cohort = _cohort(order, item)
    other = _cohort(
        other_order,
        other_item,
        readiness_type=FulfillmentReadinessType.MADE_TO_ORDER,
        ready_from=datetime.now(timezone.utc) + timedelta(days=3),
        ready_through=datetime.now(timezone.utc) + timedelta(days=4),
    )
    db_session.add_all([cohort, other])
    await db_session.flush()
    first = _transfer(cohort, hub)
    db_session.add(first)
    await db_session.flush()
    await _rejects(db_session, _transfer(cohort, hub))
    await _rejects(db_session, _transfer(cohort, hub, order_id=uuid.uuid4()))
    await _rejects(db_session, _transfer(cohort, hub, cohort_id=other.id))
    await _rejects(db_session, _transfer(cohort, hub, target_hub_id=uuid.uuid4()))

    first.state = InboundState.CANCELLED
    await db_session.flush()
    await _rejects(db_session, _transfer(cohort, hub))
    replacement = _transfer(cohort, hub, replaces_transfer_id=first.id)
    db_session.add(replacement)
    await db_session.flush()
    assert replacement.id is not None

    replacement.state = InboundState.RECEIVED_COMPLETE
    await db_session.flush()
    await _rejects(
        db_session,
        _transfer(cohort, hub, replaces_transfer_id=replacement.id),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"provider_name": " Independent Provider"},
        {"provider_name": "Independent Provider "},
        {"provider_name": ""},
        {"provider_name": "Independent\nProvider"},
        {"provider_name": "Prøvider"},
        {"provider_reference": " REF-1"},
        {"provider_reference": "REF-1 "},
        {"provider_reference": "REF\t1"},
    ],
)
async def test_transfer_rejects_noncanonical_provider_metadata(
    db_session, vendor_user, customer_user, overrides
):
    order, item, hub = await _domain(db_session, vendor_user, customer_user)
    cohort = _cohort(order, item)
    db_session.add(cohort)
    await db_session.flush()
    await _rejects(db_session, _transfer(cohort, hub, **overrides))


@pytest.mark.asyncio
async def test_transfer_item_rejects_cross_cohort_and_overallocation(
    db_session, vendor_user, customer_user
):
    order, item, hub = await _domain(db_session, vendor_user, customer_user)
    cohort = _cohort(order, item)
    other = _cohort(
        order,
        item,
        readiness_type=FulfillmentReadinessType.MADE_TO_ORDER,
        ready_from=datetime.now(timezone.utc) + timedelta(days=3),
        ready_through=datetime.now(timezone.utc) + timedelta(days=4),
    )
    db_session.add_all([cohort, other])
    await db_session.flush()
    allocation = _allocation(cohort, item, 3)
    other_allocation = _allocation(other, item, 2)
    transfer = _transfer(cohort, hub)
    db_session.add_all([allocation, other_allocation, transfer])
    await db_session.flush()
    await _rejects(db_session, _transfer_allocation(transfer, allocation, 0))
    await _rejects(db_session, _transfer_allocation(transfer, allocation, 4))
    await _rejects(db_session, _transfer_allocation(transfer, other_allocation, 1))
    db_session.add(_transfer_allocation(transfer, allocation, 3))
    await db_session.flush()


@pytest.mark.asyncio
async def test_explicit_delete_behaviour(db_session, vendor_user, customer_user):
    order, item, hub = await _domain(db_session, vendor_user, customer_user)
    cohort = _cohort(order, item)
    db_session.add(cohort)
    await db_session.flush()
    allocation = _allocation(cohort, item, 1)
    transfer = _transfer(cohort, hub)
    db_session.add_all([allocation, transfer])
    await db_session.flush()
    db_session.add(_transfer_allocation(transfer, allocation, 1))
    await db_session.commit()

    delete_attempts = (
        ("fulfillment_hubs", "id", hub.id),
        ("cohort_item_allocations", "cohort_id", cohort.id),
        ("inbound_transfer_item_allocations", "transfer_id", transfer.id),
        ("inbound_transfers", "id", transfer.id),
        ("fulfillment_cohorts", "id", cohort.id),
        ("order_items", "id", item.id),
    )
    for table, key, row_id in delete_attempts:
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await db_session.execute(
                    text(f"DELETE FROM {table} WHERE {key} = :id"),
                    {"id": row_id},
                )

    assert (
        await db_session.scalar(
            select(InboundTransfer).where(InboundTransfer.id == transfer.id)
        )
        is not None
    )
    assert (
        await db_session.scalar(
            select(CohortItemAllocation).where(
                CohortItemAllocation.cohort_id == cohort.id
            )
        )
        is not None
    )


@pytest.mark.asyncio
async def test_parent_quantities_and_allocation_audit_cannot_be_rewritten(
    db_session, vendor_user, customer_user
):
    order, item, hub = await _domain(db_session, vendor_user, customer_user)
    cohort = _cohort(order, item)
    db_session.add(cohort)
    await db_session.flush()
    allocation = _allocation(cohort, item, 3)
    transfer = _transfer(cohort, hub)
    db_session.add_all([allocation, transfer])
    await db_session.flush()
    db_session.add(_transfer_allocation(transfer, allocation, 2))
    await db_session.flush()

    statements = (
        ("UPDATE order_items SET quantity = 2 WHERE id = :id", item.id),
        (
            "UPDATE cohort_item_allocations SET allocated_quantity = 2 "
            "WHERE cohort_id = :id",
            cohort.id,
        ),
        (
            "UPDATE inbound_transfer_item_allocations SET allocated_quantity = 1 "
            "WHERE transfer_id = :id",
            transfer.id,
        ),
    )
    for statement, row_id in statements:
        with pytest.raises(IntegrityError):
            async with db_session.begin_nested():
                await db_session.execute(text(statement), {"id": row_id})
