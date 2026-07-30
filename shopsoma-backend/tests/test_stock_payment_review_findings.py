"""Regressions for exact-head review findings on PR 117."""

import asyncio
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.product import ProductVariant, SizeEnum, SizeStock, Variation
from app.models.stock_payment_persistence import (
    PaymentAttemptEvidence,
    PaymentAttemptReservation,
)


def _lane_helpers():
    path = Path(__file__).with_name("test_stock_payment_persistence.py")
    spec = importlib.util.spec_from_file_location("stock_payment_review_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _present_payment_lease(session, lease_token: uuid.UUID) -> None:
    await session.execute(
        text("SELECT set_config('shopsoma.payment_lease_token', :token, true)"),
        {"token": str(lease_token)},
    )


@pytest.mark.asyncio
async def test_verified_linked_reservation_remains_inventory_effective_after_ttl(
    db_session, vendor_user, customer_user
) -> None:
    """A paid unit cannot age out before its reservation is consumed."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph, intent, quote, option, selection, customer_user["user"].id
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))

    lease_token = uuid.uuid4()
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='call_started', lease_token=:lease_token, "
            "row_version=2 WHERE id=:attempt_id"
        ),
        {"lease_token": lease_token, "attempt_id": attempt.id},
    )
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="gateway_webhook",
        event_id=f"verified-{uuid.uuid4().hex}",
        evidence_type="authorization_result",
        evidence_hash=uuid.uuid4().hex * 2,
        observed_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    await db_session.flush()
    await _present_payment_lease(db_session, lease_token)
    await db_session.execute(
        text(
            "UPDATE payment_attempts SET state='verified', "
            "terminal_evidence_id=:evidence_id, row_version=3 WHERE id=:attempt_id"
        ),
        {"evidence_id": evidence.id, "attempt_id": attempt.id},
    )

    # Model a crashed consumer after payment verification without sleeping in real time.
    await db_session.execute(text("SET LOCAL session_replication_role = replica"))
    await db_session.execute(
        text(
            "UPDATE stock_reservations "
            "SET created_at=statement_timestamp() - interval '2 seconds', "
            "expires_at=statement_timestamp() - interval '1 second' WHERE id=:id"
        ),
        {"id": reservation.id},
    )
    await db_session.execute(text("SET LOCAL session_replication_role = origin"))

    competing = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    with pytest.raises(
        DBAPIError, match="stock reservation exceeds available inventory"
    ):
        async with db_session.begin_nested():
            db_session.add(competing)
            await db_session.flush()


@pytest.mark.asyncio
async def test_size_stock_is_the_locked_inventory_subject(
    db_session, vendor_user, customer_user
) -> None:
    """Vendor size stock is reserved independently of products.total_stock."""

    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    variation = Variation(
        product_id=graph["item"].product_id,
        title="Black",
        type="color",
        price=graph["item"].unit_price,
    )
    db_session.add(variation)
    await db_session.flush()
    size_stock = SizeStock(variation_id=variation.id, size=SizeEnum.M, stock=1)
    db_session.add(size_stock)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE order_items SET variant_details=CAST(:details AS jsonb) "
            "WHERE id=:order_item_id"
        ),
        {
            "details": json.dumps(
                {
                    "size": "M",
                    "color": "Black",
                    "size_stock_id": str(size_stock.id),
                    "variation_id": str(variation.id),
                }
            ),
            "order_item_id": graph["item"].id,
        },
    )
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        None,
        size_stock_id=size_stock.id,
    )
    db_session.add(reservation)
    await db_session.flush()

    competing = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        None,
        size_stock_id=size_stock.id,
    )
    with pytest.raises(
        DBAPIError, match="stock reservation exceeds available inventory"
    ):
        async with db_session.begin_nested():
            db_session.add(competing)
            await db_session.flush()
    with pytest.raises(
        DBAPIError, match="inventory cannot be reduced below active reservations"
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text("UPDATE size_stocks SET stock=0 WHERE id=:id"),
                {"id": size_stock.id},
            )


@pytest.mark.asyncio
async def test_made_to_order_reservation_does_not_require_finite_stock(
    db_session, vendor_user, customer_user
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    await db_session.execute(
        text("UPDATE products SET made_to_order=true WHERE id=:id"),
        {"id": graph["item"].product_id},
    )
    reservation = lane._reservation(
        graph, intent, quote, option, selection, customer_user["user"].id, sku
    )
    db_session.add(reservation)
    await db_session.flush()
    assert reservation.state == "active"


@pytest.mark.asyncio
@pytest.mark.parametrize("subject_kind", ["product", "variant"])
async def test_null_sku_uses_collision_free_inventory_subject_identity(
    db_session, vendor_user, customer_user, subject_kind
) -> None:
    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    variant_id = None
    if subject_kind == "variant":
        variant = ProductVariant(
            product_id=graph["item"].product_id,
            size="M",
            color=f"null-sku-{uuid.uuid4().hex[:8]}",
            price=graph["item"].unit_price,
            stock=1,
            sku=None,
        )
        db_session.add(variant)
        await db_session.flush()
        variant_id = variant.id
        await db_session.execute(
            text(
                "UPDATE order_items SET variant_id=:variant_id WHERE id=:order_item_id"
            ),
            {"variant_id": variant.id, "order_item_id": graph["item"].id},
        )
    else:
        await db_session.execute(
            text("UPDATE products SET sku=NULL WHERE id=:id"),
            {"id": graph["item"].product_id},
        )

    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        None,
        variant_id=variant_id,
    )
    db_session.add(reservation)
    await db_session.flush()
    assert reservation.sku is None


@pytest.mark.asyncio
async def test_size_stock_binding_rejects_mismatched_order_size(
    db_session, vendor_user, customer_user
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=10
    )
    variation = Variation(
        product_id=graph["item"].product_id,
        title="Blue",
        type="color",
        price=graph["item"].unit_price,
    )
    db_session.add(variation)
    await db_session.flush()
    size_stock = SizeStock(variation_id=variation.id, size=SizeEnum.M, stock=1)
    db_session.add(size_stock)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE order_items SET variant_details=CAST(:details AS jsonb) "
            "WHERE id=:order_item_id"
        ),
        {
            "details": json.dumps(
                {
                    "size": "L",
                    "color": "Blue",
                    "variation_id": str(variation.id),
                    "size_stock_id": str(size_stock.id),
                    "stock_source": "legacy_variation",
                }
            ),
            "order_item_id": graph["item"].id,
        },
    )
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        None,
        size_stock_id=size_stock.id,
    )
    db_session.add(reservation)
    with pytest.raises(
        DBAPIError, match="stock reservation subject binding is invalid"
    ):
        await db_session.flush()


@pytest.mark.asyncio
async def test_size_stock_parent_cannot_move_during_reservation(
    db_session, vendor_user, customer_user
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    other_graph, *_ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    variation = Variation(
        product_id=graph["item"].product_id,
        title="Black",
        type="color",
        price=graph["item"].unit_price,
    )
    db_session.add(variation)
    await db_session.flush()
    size_stock = SizeStock(variation_id=variation.id, size=SizeEnum.M, stock=1)
    db_session.add(size_stock)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE order_items SET variant_details=CAST(:details AS jsonb) "
            "WHERE id=:order_item_id"
        ),
        {
            "details": json.dumps(
                {
                    "size": "M",
                    "color": "Black",
                    "variation_id": str(variation.id),
                    "size_stock_id": str(size_stock.id),
                }
            ),
            "order_item_id": graph["item"].id,
        },
    )
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    mover = factory()
    reserver = factory()
    try:
        await mover.execute(
            text("UPDATE variations SET product_id=:product_id WHERE id=:id"),
            {"product_id": other_graph["item"].product_id, "id": variation.id},
        )

        async def reserve_after_parent_move():
            candidate = lane._reservation(
                graph,
                intent,
                quote,
                option,
                selection,
                customer_user["user"].id,
                None,
                size_stock_id=size_stock.id,
            )
            reserver.add(candidate)
            try:
                await reserver.flush()
                await reserver.commit()
                return None
            except DBAPIError as exc:
                await reserver.rollback()
                return str(exc)

        result_task = asyncio.create_task(reserve_after_parent_move())
        await asyncio.sleep(0.2)
        await mover.commit()
        result = await asyncio.wait_for(result_task, timeout=5)
        assert result is not None
        assert "stock reservation subject binding is invalid" in result
    finally:
        await mover.close()
        await reserver.close()


@pytest.mark.asyncio
async def test_size_stock_reservation_prevents_parent_move_after_binding(
    db_session, vendor_user, customer_user
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, _ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    other_graph, *_ = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=0
    )
    variation = Variation(
        product_id=graph["item"].product_id,
        title="Black",
        type="color",
        price=graph["item"].unit_price,
    )
    db_session.add(variation)
    await db_session.flush()
    size_stock = SizeStock(variation_id=variation.id, size=SizeEnum.M, stock=1)
    db_session.add(size_stock)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE order_items SET variant_details=CAST(:details AS jsonb) "
            "WHERE id=:order_item_id"
        ),
        {
            "details": json.dumps(
                {
                    "size": "M",
                    "color": "Black",
                    "variation_id": str(variation.id),
                    "size_stock_id": str(size_stock.id),
                }
            ),
            "order_item_id": graph["item"].id,
        },
    )
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    reserver = factory()
    mover = factory()
    try:
        candidate = lane._reservation(
            graph,
            intent,
            quote,
            option,
            selection,
            customer_user["user"].id,
            None,
            size_stock_id=size_stock.id,
        )
        reserver.add(candidate)
        await reserver.flush()

        async def move_parent_after_binding():
            try:
                await mover.execute(
                    text("UPDATE variations SET product_id=:product_id WHERE id=:id"),
                    {
                        "product_id": other_graph["item"].product_id,
                        "id": variation.id,
                    },
                )
                await mover.commit()
                return None
            except DBAPIError as exc:
                await mover.rollback()
                return str(exc)

        result_task = asyncio.create_task(move_parent_after_binding())
        await asyncio.sleep(0.2)
        await reserver.commit()
        result = await asyncio.wait_for(result_task, timeout=5)
        assert result is not None
        assert "reserved product identity is immutable" in result
    finally:
        await reserver.close()
        await mover.close()


@pytest.mark.asyncio
async def test_verification_serializes_with_reservation_after_ttl(
    db_session, vendor_user, customer_user
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    second_graph, second_intent, second_quote, second_option, second_selection, _ = (
        await lane._checkout_subject(db_session, vendor_user, customer_user, stock=1)
    )
    second_graph["item"].product_id = graph["item"].product_id
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        ttl_seconds=2,
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    lease_token = uuid.uuid4()
    attempt.state = "call_started"
    attempt.lease_token = lease_token
    attempt.row_version += 1
    await db_session.flush()
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    verifier = factory()
    competitor = factory()
    try:
        evidence_id = uuid.uuid4()
        verifier.add(
            PaymentAttemptEvidence(
                id=evidence_id,
                attempt_id=attempt.id,
                source="provider_webhook",
                event_id=f"verify-race-{uuid.uuid4().hex}",
                evidence_type="payment_verified",
                evidence_hash="6" * 64,
                observed_at=datetime.now(timezone.utc),
            )
        )
        await verifier.flush()
        await _present_payment_lease(verifier, lease_token)
        await verifier.execute(
            text(
                "UPDATE payment_attempts SET state='verified', terminal_evidence_id=:evidence_id, "
                "row_version=row_version+1 WHERE id=:attempt_id"
            ),
            {"evidence_id": evidence_id, "attempt_id": attempt.id},
        )
        await asyncio.sleep(2.1)

        async def reserve_competing_unit():
            candidate = lane._reservation(
                second_graph,
                second_intent,
                second_quote,
                second_option,
                second_selection,
                customer_user["user"].id,
                sku,
            )
            competitor.add(candidate)
            try:
                await competitor.flush()
                await competitor.commit()
                return None
            except DBAPIError as exc:
                await competitor.rollback()
                return str(exc)

        result_task = asyncio.create_task(reserve_competing_unit())
        await asyncio.sleep(0.2)
        await verifier.commit()
        result = await asyncio.wait_for(result_task, timeout=5)
        assert result is not None
        assert "stock reservation exceeds available inventory" in result
    finally:
        await verifier.close()
        await competitor.close()


@pytest.mark.asyncio
async def test_verification_serializes_with_stock_reduction_after_ttl(
    db_session, vendor_user, customer_user
):
    lane = _lane_helpers()
    graph, intent, quote, option, selection, sku = await lane._checkout_subject(
        db_session, vendor_user, customer_user, stock=1
    )
    reservation = lane._reservation(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
        sku,
        ttl_seconds=2,
    )
    db_session.add(reservation)
    await db_session.flush()
    attempt = lane._payment_attempt(
        graph,
        intent,
        quote,
        option,
        selection,
        customer_user["user"].id,
    )
    db_session.add(attempt)
    await db_session.flush()
    db_session.add(
        PaymentAttemptReservation(attempt_id=attempt.id, reservation_id=reservation.id)
    )
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    lease_token = uuid.uuid4()
    attempt.state = "call_started"
    attempt.lease_token = lease_token
    attempt.row_version += 1
    await db_session.flush()
    await db_session.commit()

    factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    verifier = factory()
    reducer = factory()
    try:
        evidence_id = uuid.uuid4()
        verifier.add(
            PaymentAttemptEvidence(
                id=evidence_id,
                attempt_id=attempt.id,
                source="provider_webhook",
                event_id=f"verify-stock-race-{uuid.uuid4().hex}",
                evidence_type="payment_verified",
                evidence_hash="7" * 64,
                observed_at=datetime.now(timezone.utc),
            )
        )
        await verifier.flush()
        await _present_payment_lease(verifier, lease_token)
        await verifier.execute(
            text(
                "UPDATE payment_attempts SET state='verified', terminal_evidence_id=:evidence_id, "
                "row_version=row_version+1 WHERE id=:attempt_id"
            ),
            {"evidence_id": evidence_id, "attempt_id": attempt.id},
        )
        await asyncio.sleep(2.1)

        async def reduce_paid_inventory():
            try:
                await reducer.execute(
                    text("UPDATE products SET total_stock=0 WHERE id=:product_id"),
                    {"product_id": graph["item"].product_id},
                )
                await reducer.commit()
                return None
            except DBAPIError as exc:
                await reducer.rollback()
                return str(exc)

        result_task = asyncio.create_task(reduce_paid_inventory())
        await asyncio.sleep(0.2)
        await verifier.commit()
        result = await asyncio.wait_for(result_task, timeout=5)
        assert result is not None
        assert "inventory cannot be reduced below active reservations" in result
    finally:
        await verifier.close()
        await reducer.close()
