"""Phase 2A-4A immutable customer quote persistence contracts."""

import asyncio
import importlib.util
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker


QUOTE_COLUMNS = {
    "id",
    "order_id",
    "customer_id",
    "intent_id",
    "package_id",
    "package_version",
    "seal_id",
    "origin_hub_id",
    "destination_snapshot_hash",
    "source_rate_response_id",
    "supersedes_quote_id",
    "currency",
    "ttl_seconds",
    "expires_at",
    "initiating_actor_type",
    "initiating_actor_id",
    "source_command",
    "idempotency_key",
    "request_fingerprint",
    "schema_version",
    "row_version",
    "creation_txid",
    "created_at",
}
OPTION_COLUMNS = {
    "id",
    "quote_id",
    "source_rate_offer_id",
    "option_key",
    "provider",
    "product_code",
    "service_code",
    "service_label",
    "source_amount",
    "adjustment_amount",
    "total_amount",
    "currency",
    "transit_days",
    "delivery_date",
    "created_at",
}
SELECTION_COLUMNS = {
    "id",
    "quote_id",
    "intent_id",
    "option_id",
    "customer_id",
    "selected_by_id",
    "source_command",
    "idempotency_key",
    "selected_at",
    "created_at",
}


def _column_names(model) -> set[str]:
    return {column.name for column in inspect(model).columns}


def test_quote_models_are_separate_from_provider_evidence_and_normalized() -> None:
    from app.models.customer_shipping_quote import (
        CustomerShippingQuote,
        CustomerShippingQuoteOption,
        CustomerShippingQuoteSelection,
    )
    from app.models.domestic_rate_quote import DomesticRateOffer, DomesticRateResponse

    assert CustomerShippingQuote.__tablename__ == "customer_shipping_quotes"
    assert (
        CustomerShippingQuoteOption.__tablename__ == "customer_shipping_quote_options"
    )
    assert (
        CustomerShippingQuoteSelection.__tablename__
        == "customer_shipping_quote_selections"
    )
    assert _column_names(CustomerShippingQuote) == QUOTE_COLUMNS
    assert _column_names(CustomerShippingQuoteOption) == OPTION_COLUMNS
    assert _column_names(CustomerShippingQuoteSelection) == SELECTION_COLUMNS
    assert CustomerShippingQuote.__table__ is not DomesticRateResponse.__table__
    assert CustomerShippingQuoteOption.__table__ is not DomesticRateOffer.__table__

    forbidden = {
        "payload",
        "request_json",
        "response_json",
        "credentials",
        "account_number",
        "destination_name",
        "destination_phone",
        "destination_address_line1",
        "seal_value",
    }
    for model in (
        CustomerShippingQuote,
        CustomerShippingQuoteOption,
        CustomerShippingQuoteSelection,
    ):
        assert forbidden.isdisjoint(_column_names(model))


def test_quote_models_expose_database_enforced_immutable_contracts() -> None:
    from app.models.customer_shipping_quote import (
        CUSTOMER_SHIPPING_QUOTE_TRIGGER_DDLS,
        CustomerShippingQuote,
        CustomerShippingQuoteOption,
        CustomerShippingQuoteSelection,
    )

    ddl = "\n".join(CUSTOMER_SHIPPING_QUOTE_TRIGGER_DDLS)
    for table in (
        "customer_shipping_quotes",
        "customer_shipping_quote_options",
        "customer_shipping_quote_selections",
    ):
        assert table in ddl
    for invariant in (
        "quote ownership does not match order",
        "quote subject does not match outbound intent",
        "quote cannot use an invalidated outbound intent",
        "quote successor subject must match predecessor",
        "quote must supersede the current subject leaf",
        "selected quote cannot be superseded",
        "quote records are immutable audit",
        "quote option must match quote currency",
        "source rate offer does not match quote subject",
        "quote option records are immutable audit",
        "quote selection must identify an option from the quote",
        "quote selection owner does not match quote",
        "quote is expired or superseded",
        "quote selection records are immutable audit",
    ):
        assert invariant in ddl
    for model in (
        CustomerShippingQuote,
        CustomerShippingQuoteOption,
        CustomerShippingQuoteSelection,
    ):
        constraint_names = {
            constraint.name
            for constraint in model.__table__.constraints
            if constraint.name is not None
        }
        assert constraint_names


async def _rejects(session, statement: str, params: dict, match: str) -> None:
    with pytest.raises(DBAPIError, match=match):
        async with session.begin_nested():
            await session.execute(text(statement), params)


def _custody_helpers():
    path = Path(__file__).with_name("test_package_custody_persistence.py")
    spec = importlib.util.spec_from_file_location("quote_test_custody_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_quote_database_rejects_cross_customer_and_invalid_identifiers(
    db_session, vendor_user, customer_user
) -> None:
    """Direct SQL cannot bypass owner or bounded ASCII command identity."""
    custody = _custody_helpers()
    _passed_graph = custody._passed_graph
    _ready_package = custody._ready_package
    from app.models.package_custody import OutboundShipmentIntent

    graph = await _passed_graph(db_session, vendor_user, customer_user)
    package, _version, _item, seal = await _ready_package(db_session, graph)
    intent = OutboundShipmentIntent(
        package_id=package.id,
        package_version=1,
        seal_id=seal.id,
        order_id=graph["order"].id,
        origin_hub_id=graph["hub"].id,
        destination_name="Quote Customer",
        destination_phone="+2348000000000",
        destination_address_line1="1 Quote Street",
        destination_city="Lagos",
        destination_state="Lagos",
        destination_postal_code="100213",
        source_command="create_outbound_intent",
        idempotency_key=f"intent-{uuid.uuid4().hex}",
        created_by_id=graph["operator_id"],
    )
    db_session.add(intent)
    await db_session.flush()

    quote_params = {
        "id": uuid.uuid4(),
        "order_id": graph["order"].id,
        "customer_id": vendor_user["user"].id,
        "intent_id": intent.id,
        "package_id": package.id,
        "package_version": 1,
        "seal_id": seal.id,
        "origin_hub_id": graph["hub"].id,
        "destination_snapshot_hash": intent.destination_snapshot_hash,
        "currency": "NGN",
        "ttl_seconds": 1800,
        "initiating_actor_type": "customer",
        "initiating_actor_id": str(vendor_user["user"].id),
        "source_command": "create_quote",
        "idempotency_key": f"quote-{uuid.uuid4().hex}",
        "request_fingerprint": "a" * 64,
        "schema_version": "1",
    }
    columns = ", ".join(quote_params)
    values = ", ".join(f":{name}" for name in quote_params)
    await _rejects(
        db_session,
        f"INSERT INTO customer_shipping_quotes ({columns}) VALUES ({values})",
        quote_params,
        "quote ownership does not match order",
    )

    quote_params["customer_id"] = customer_user["user"].id
    quote_params["initiating_actor_id"] = str(vendor_user["user"].id)
    await _rejects(
        db_session,
        f"INSERT INTO customer_shipping_quotes ({columns}) VALUES ({values})",
        quote_params,
        "customer actor must match quote owner",
    )

    quote_params["initiating_actor_id"] = str(customer_user["user"].id)
    quote_params["source_command"] = "bad key\n"
    await _rejects(
        db_session,
        f"INSERT INTO customer_shipping_quotes ({columns}) VALUES ({values})",
        quote_params,
        "ck_customer_shipping_quotes_identifiers",
    )


def _domestic_helpers():
    path = Path(__file__).with_name("test_domestic_rate_persistence.py")
    spec = importlib.util.spec_from_file_location("quote_test_domestic_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _quote(graph, package, seal, intent, customer_id, **overrides):
    from app.models.customer_shipping_quote import CustomerShippingQuote

    values = {
        "order_id": graph["order"].id,
        "customer_id": customer_id,
        "intent_id": intent.id,
        "package_id": package.id,
        "package_version": 1,
        "seal_id": seal.id,
        "origin_hub_id": graph["hub"].id,
        "destination_snapshot_hash": intent.destination_snapshot_hash,
        "currency": "NGN",
        "ttl_seconds": 1800,
        "initiating_actor_type": "customer",
        "initiating_actor_id": str(customer_id),
        "source_command": "create_shipping_quote",
        "idempotency_key": f"quote-{uuid.uuid4().hex}",
        "request_fingerprint": uuid.uuid4().hex * 2,
        "schema_version": "customer-quote-v1",
    }
    values.update(overrides)
    return CustomerShippingQuote(**values)


def _option(quote_id, key, **overrides):
    from app.models.customer_shipping_quote import CustomerShippingQuoteOption

    values = {
        "quote_id": quote_id,
        "option_key": key,
        "provider": "carrier",
        "product_code": "DOMESTIC",
        "service_code": key.upper(),
        "service_label": f"{key.title()} service",
        "source_amount": Decimal("1000.0000"),
        "adjustment_amount": Decimal("50.0000"),
        "total_amount": Decimal("1050.0000"),
        "currency": "NGN",
        "transit_days": 2,
    }
    values.update(overrides)
    return CustomerShippingQuoteOption(**values)


async def _force_deferred_checks(session) -> None:
    await session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await session.execute(text("SET CONSTRAINTS ALL DEFERRED"))


async def _record_custody_release(session, graph, package, seal) -> None:
    from app.models.package_custody import CustodyEvent, CustodyStream

    stream = CustodyStream(
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        package_id=package.id,
        package_version=1,
    )
    session.add(stream)
    await session.flush()
    previous = None
    occurred = seal.applied_at
    for position, event_type in enumerate(
        ("packed", "sealed", "staged", "released"), 1
    ):
        if event_type != "packed":
            occurred += timedelta(microseconds=1)
        event = CustodyEvent(
            stream_id=stream.id,
            version=position,
            previous_event_id=None if previous is None else previous.id,
            cohort_id=graph["cohort"].id,
            order_id=graph["order"].id,
            vendor_id=graph["vendor_id"],
            hub_id=graph["hub"].id,
            event_type=event_type,
            actor_type="user",
            actor_id=str(graph["operator_id"]),
            source_system="shopsoma_hub",
            source_command="record_custody",
            idempotency_key=f"quote-handoff-{event_type}-{uuid.uuid4().hex}",
            occurred_at=occurred,
            location="Lagos Hub",
            package_id=package.id,
            package_version=1,
            seal_id=None if event_type == "packed" else seal.id,
        )
        session.add(event)
        await session.flush()
        previous = event


@pytest.mark.asyncio
async def test_quote_requires_at_least_one_option_at_transaction_boundary(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    quote = _quote(graph, package, seal, intent, customer_user["user"].id)
    with pytest.raises(DBAPIError, match="customer quote requires at least one option"):
        async with db_session.begin_nested():
            db_session.add(quote)
            await db_session.flush()
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


@pytest.mark.asyncio
async def test_quote_creation_serializes_against_order_owner_change(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async with sessions() as quoter, sessions() as owner_changer:
        quote = _quote(graph, package, seal, intent, customer_user["user"].id)
        quoter.add(quote)
        await quoter.flush()
        quoter.add(_option(quote.id, "owner-race"))
        await quoter.flush()
        owner_pid = await owner_changer.scalar(text("SELECT pg_backend_pid()"))

        async def change_owner() -> str:
            try:
                await owner_changer.execute(
                    text("UPDATE orders SET customer_id=:other WHERE id=:order_id"),
                    {
                        "other": vendor_user["user"].id,
                        "order_id": graph["order"].id,
                    },
                )
                await owner_changer.commit()
                return "changed"
            except DBAPIError as exc:
                await owner_changer.rollback()
                return str(exc.orig)

        task = asyncio.create_task(change_owner())
        for _ in range(100):
            blocked = await db_session.scalar(
                text(
                    "SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"
                ),
                {"pid": owner_pid},
            )
            if blocked:
                break
            if task.done():
                pytest.fail("order owner update bypassed the quote ownership lock")
            await asyncio.sleep(0.02)
        else:
            pytest.fail("order owner update did not block behind quote creation")
        await quoter.commit()
        result = await asyncio.wait_for(task, timeout=15)

    assert "order ownership is frozen by customer shipping quote" in result


@pytest.mark.asyncio
async def test_multi_option_quote_is_database_timestamped_selectable_and_immutable(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    quote = _quote(graph, package, seal, intent, customer_user["user"].id)
    db_session.add(quote)
    await db_session.flush()
    economy = _option(quote.id, "economy")
    express = _option(
        quote.id,
        "express",
        source_amount=Decimal("1500.0000"),
        adjustment_amount=Decimal("125.2500"),
        total_amount=Decimal("1625.2500"),
        transit_days=1,
    )
    db_session.add_all([economy, express])
    await db_session.flush()
    await _force_deferred_checks(db_session)

    assert quote.row_version == 1
    assert quote.expires_at - quote.created_at == timedelta(seconds=1800)
    assert {economy.option_key, express.option_key} == {"economy", "express"}
    assert express.total_amount == Decimal("1625.2500")

    await _rejects(
        db_session,
        "UPDATE orders SET customer_id=:other WHERE id=:order_id",
        {"other": vendor_user["user"].id, "order_id": graph["order"].id},
        "order ownership is frozen by customer shipping quote",
    )

    from app.models.customer_shipping_quote import CustomerShippingQuoteSelection

    selection = CustomerShippingQuoteSelection(
        quote_id=quote.id,
        intent_id=intent.id,
        option_id=economy.id,
        customer_id=customer_user["user"].id,
        selected_by_id=vendor_user["user"].id,
        source_command="select-rate",
        idempotency_key="selection-spoof",
    )
    with pytest.raises(DBAPIError, match="quote selection owner does not match quote"):
        async with db_session.begin_nested():
            db_session.add(selection)
            await db_session.flush()

    selection = CustomerShippingQuoteSelection(
        quote_id=quote.id,
        intent_id=intent.id,
        option_id=express.id,
        customer_id=customer_user["user"].id,
        selected_by_id=customer_user["user"].id,
        source_command="select_shipping_quote_option",
        idempotency_key=f"selection-{uuid.uuid4().hex}",
    )
    db_session.add(selection)
    await db_session.flush()
    assert selection.selected_at is not None

    for table, row_id, message in (
        ("customer_shipping_quotes", quote.id, "quote records are immutable audit"),
        (
            "customer_shipping_quote_options",
            economy.id,
            "quote option records are immutable audit",
        ),
        (
            "customer_shipping_quote_selections",
            selection.id,
            "quote selection records are immutable audit",
        ),
    ):
        await _rejects(
            db_session,
            f"DELETE FROM {table} WHERE id=:id",
            {"id": row_id},
            message,
        )


@pytest.mark.asyncio
async def test_committed_quote_rejects_later_option_append(
    db_session, vendor_user, customer_user
) -> None:
    """A quote's normalized option set is frozen at its creation transaction."""
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    quote = _quote(graph, package, seal, intent, customer_user["user"].id)
    db_session.add(quote)
    await db_session.flush()
    db_session.add(_option(quote.id, "initial"))
    await db_session.commit()

    with pytest.raises(DBAPIError, match="quote no longer accepts options"):
        async with db_session.begin_nested():
            db_session.add(_option(quote.id, "later"))
            await db_session.flush()


@pytest.mark.asyncio
async def test_quote_replay_shape_and_cross_quote_selection_fail_closed(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    replay_key = f"quote-{uuid.uuid4().hex}"
    first = _quote(
        graph,
        package,
        seal,
        intent,
        customer_user["user"].id,
        idempotency_key=replay_key,
    )
    db_session.add(first)
    await db_session.flush()
    first_option = _option(first.id, "first")
    db_session.add(first_option)
    await db_session.flush()
    await _force_deferred_checks(db_session)

    duplicate = _quote(
        graph,
        package,
        seal,
        intent,
        customer_user["user"].id,
        idempotency_key=replay_key,
        supersedes_quote_id=first.id,
    )
    with pytest.raises(
        IntegrityError, match="uq_customer_shipping_quotes_customer_replay"
    ):
        async with db_session.begin_nested():
            db_session.add(duplicate)
            await db_session.flush()

    second = _quote(
        graph,
        package,
        seal,
        intent,
        customer_user["user"].id,
        supersedes_quote_id=first.id,
    )
    db_session.add(second)
    await db_session.flush()
    second_option = _option(second.id, "second")
    db_session.add(second_option)
    await db_session.flush()
    await _force_deferred_checks(db_session)

    await _rejects(
        db_session,
        "INSERT INTO customer_shipping_quote_selections "
        "(id, quote_id, intent_id, option_id, customer_id, selected_by_id, "
        "source_command, idempotency_key) "
        "VALUES (:id, :quote, :intent, :option, :customer, :customer, 'select_quote', :key)",
        {
            "id": uuid.uuid4(),
            "quote": first.id,
            "intent": intent.id,
            "option": second_option.id,
            "customer": customer_user["user"].id,
            "key": f"selection-{uuid.uuid4().hex}",
        },
        "quote selection must identify an option from the quote|fk_customer_shipping_quote_selections_option",
    )


@pytest.mark.asyncio
async def test_quote_rejects_non_finite_money_and_post_handoff_creation(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    quote = _quote(graph, package, seal, intent, customer_user["user"].id)
    db_session.add(quote)
    await db_session.flush()
    with pytest.raises(
        IntegrityError, match="ck_customer_shipping_quote_options_amounts"
    ):
        async with db_session.begin_nested():
            db_session.add(
                _option(
                    quote.id,
                    "nan",
                    source_amount=Decimal("NaN"),
                    adjustment_amount=Decimal("NaN"),
                    total_amount=Decimal("NaN"),
                )
            )
            await db_session.flush()
    db_session.add(_option(quote.id, "finite"))
    await db_session.flush()
    await _force_deferred_checks(db_session)

    graph2, package2, seal2, intent2 = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    await _record_custody_release(db_session, graph2, package2, seal2)
    with pytest.raises(
        DBAPIError, match="quote cannot be created after custody handoff"
    ):
        async with db_session.begin_nested():
            db_session.add(
                _quote(
                    graph2,
                    package2,
                    seal2,
                    intent2,
                    customer_user["user"].id,
                )
            )
            await db_session.flush()


@pytest.mark.asyncio
async def test_invalidated_quote_cannot_be_selected(
    db_session, vendor_user, customer_user
) -> None:
    from app.models.package_custody import OutboundShipmentIntentInvalidation

    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    quote = _quote(graph, package, seal, intent, customer_user["user"].id)
    db_session.add(quote)
    await db_session.flush()
    option = _option(quote.id, "invalidated")
    db_session.add(option)
    await db_session.flush()
    await _force_deferred_checks(db_session)
    now = await db_session.scalar(text("SELECT clock_timestamp()"))
    db_session.add(
        OutboundShipmentIntentInvalidation(
            intent_id=intent.id,
            reason="authorized destination correction",
            actor_type="user",
            actor_id=str(graph["operator_id"]),
            source_command="invalidate_outbound",
            idempotency_key=f"selection-invalidate-{uuid.uuid4().hex}",
            invalidated_at=now,
        )
    )
    await db_session.flush()
    await _rejects(
        db_session,
        "INSERT INTO customer_shipping_quote_selections "
        "(id,quote_id,intent_id,option_id,customer_id,selected_by_id,source_command,idempotency_key) "
        "VALUES (:id,:quote,:intent,:option,:customer,:customer,'select_quote',:key)",
        {
            "id": uuid.uuid4(),
            "quote": quote.id,
            "intent": intent.id,
            "option": option.id,
            "customer": customer_user["user"].id,
            "key": f"invalid-selection-{uuid.uuid4().hex}",
        },
        "quote subject is no longer eligible for selection",
    )


@pytest.mark.asyncio
async def test_phase_2b_offer_provenance_is_reused_without_mutating_evidence(
    db_session, vendor_user, customer_user
) -> None:
    from app.models.domestic_rate_quote import DomesticRateOffer, DomesticRateResponse

    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = domestic._attempt(graph, package, seal, intent, claimed)
    received = await domestic._complete_attempt(db_session, attempt, "success")
    response = DomesticRateResponse(
        attempt_id=attempt.id,
        result_kind="success",
        received_at=received,
        expires_at=received + timedelta(minutes=15),
        ttl_seconds=900,
    )
    db_session.add(response)
    await db_session.flush()
    offer = DomesticRateOffer(
        response_id=response.id,
        provider_product_code="N",
        provider_service_code="DOM-N",
        service_label="Domestic Express",
        total_amount=Decimal("1234.5678"),
        currency="NGN",
        transit_days=1,
        delivery_date=attempt.planned_ship_date + timedelta(days=1),
    )
    db_session.add(offer)
    await db_session.flush()
    await _force_deferred_checks(db_session)

    too_long = _quote(
        graph,
        package,
        seal,
        intent,
        customer_user["user"].id,
        source_rate_response_id=response.id,
        ttl_seconds=1000,
    )
    with pytest.raises(
        DBAPIError, match="source rate response is not eligible quote evidence"
    ):
        async with db_session.begin_nested():
            db_session.add(too_long)
            await db_session.flush()

    quote = _quote(
        graph,
        package,
        seal,
        intent,
        customer_user["user"].id,
        source_rate_response_id=response.id,
        ttl_seconds=600,
    )
    db_session.add(quote)
    await db_session.flush()
    option = _option(
        quote.id,
        "dhl-dom-n",
        source_rate_offer_id=offer.id,
        provider="dhl",
        product_code="N",
        service_code="DOM-N",
        service_label="Domestic Express",
        source_amount=Decimal("1234.5678"),
        adjustment_amount=Decimal("65.4322"),
        total_amount=Decimal("1300.0000"),
        transit_days=1,
        delivery_date=offer.delivery_date,
    )
    db_session.add(option)
    await db_session.flush()
    await _force_deferred_checks(db_session)
    assert option.source_amount == offer.total_amount
    assert option.total_amount == Decimal("1300.0000")

    bad = _option(
        quote.id,
        "tampered",
        source_rate_offer_id=offer.id,
        provider="dhl",
        product_code="N",
        service_code="DOM-N",
        service_label="Domestic Express",
        source_amount=Decimal("1234.0000"),
        adjustment_amount=Decimal("66.0000"),
        total_amount=Decimal("1300.0000"),
        transit_days=1,
        delivery_date=offer.delivery_date,
    )
    with pytest.raises(
        DBAPIError, match="source rate offer does not match quote subject"
    ):
        async with db_session.begin_nested():
            db_session.add(bad)
            await db_session.flush()

    successor = _quote(
        graph,
        package,
        seal,
        intent,
        customer_user["user"].id,
        source_rate_response_id=response.id,
        supersedes_quote_id=quote.id,
        ttl_seconds=600,
    )
    db_session.add(successor)
    await db_session.flush()
    successor_option = _option(
        successor.id,
        "dhl-dom-n-refresh",
        source_rate_offer_id=offer.id,
        provider="dhl",
        product_code="N",
        service_code="DOM-N",
        service_label="Domestic Express",
        source_amount=Decimal("1234.5678"),
        adjustment_amount=Decimal("65.4322"),
        total_amount=Decimal("1300.0000"),
        transit_days=1,
        delivery_date=offer.delivery_date,
    )
    db_session.add(successor_option)
    await db_session.flush()
    await _force_deferred_checks(db_session)


@pytest.mark.asyncio
async def test_expired_or_superseded_quote_cannot_be_selected(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    expired = _quote(
        graph, package, seal, intent, customer_user["user"].id, ttl_seconds=1
    )
    db_session.add(expired)
    await db_session.flush()
    expired_option = _option(expired.id, "expires")
    db_session.add(expired_option)
    await db_session.flush()
    await _force_deferred_checks(db_session)
    await asyncio.sleep(1.05)

    late_option = _option(expired.id, "late")
    with pytest.raises(DBAPIError, match="quote no longer accepts options"):
        async with db_session.begin_nested():
            db_session.add(late_option)
            await db_session.flush()

    await _rejects(
        db_session,
        "INSERT INTO customer_shipping_quote_selections "
        "(id, quote_id, intent_id, option_id, customer_id, selected_by_id, "
        "source_command, idempotency_key) "
        "VALUES (:id, :quote, :intent, :option, :customer, :customer, 'select_quote', :key)",
        {
            "id": uuid.uuid4(),
            "quote": expired.id,
            "intent": intent.id,
            "option": expired_option.id,
            "customer": customer_user["user"].id,
            "key": f"expired-{uuid.uuid4().hex}",
        },
        "quote is expired or superseded",
    )

    current = _quote(
        graph,
        package,
        seal,
        intent,
        customer_user["user"].id,
        supersedes_quote_id=expired.id,
    )
    db_session.add(current)
    await db_session.flush()
    current_option = _option(current.id, "current")
    db_session.add(current_option)
    await db_session.flush()
    successor = _quote(
        graph,
        package,
        seal,
        intent,
        customer_user["user"].id,
        supersedes_quote_id=current.id,
    )
    db_session.add(successor)
    await db_session.flush()
    db_session.add(_option(successor.id, "successor"))
    await db_session.flush()
    await _force_deferred_checks(db_session)
    await _rejects(
        db_session,
        "INSERT INTO customer_shipping_quote_selections "
        "(id, quote_id, intent_id, option_id, customer_id, selected_by_id, "
        "source_command, idempotency_key) "
        "VALUES (:id, :quote, :intent, :option, :customer, :customer, 'select_quote', :key)",
        {
            "id": uuid.uuid4(),
            "quote": current.id,
            "intent": intent.id,
            "option": current_option.id,
            "customer": customer_user["user"].id,
            "key": f"superseded-{uuid.uuid4().hex}",
        },
        "quote is expired or superseded",
    )


@pytest.mark.asyncio
async def test_quote_creation_rechecks_invalidation_after_waiting_for_package_lock(
    db_session, vendor_user, customer_user
) -> None:
    """A concurrent invalidation that wins the package lock must reject the quote."""
    from app.models.package_custody import OutboundShipmentIntentInvalidation

    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    customer_id = customer_user["user"].id
    operator_id = graph["operator_id"]
    invalidated_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.commit()

    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def wait_until_lock_blocked(observer, pid: int) -> None:
        for _ in range(100):
            blocked = await observer.scalar(
                text(
                    "SELECT wait_event_type = 'Lock' FROM pg_stat_activity "
                    "WHERE pid=:pid"
                ),
                {"pid": pid},
            )
            if blocked:
                return
            await asyncio.sleep(0.02)
        pytest.fail(f"backend {pid} did not block on the package lock")

    async def invalidate(session) -> str:
        try:
            session.add(
                OutboundShipmentIntentInvalidation(
                    intent_id=intent.id,
                    reason="concurrent quote race",
                    actor_type="user",
                    actor_id=str(operator_id),
                    source_command="invalidate_outbound_intent",
                    idempotency_key=f"invalidate-{uuid.uuid4().hex}",
                    invalidated_at=invalidated_at,
                )
            )
            await session.commit()
            return "invalidated"
        except Exception:
            await session.rollback()
            raise

    async def create_quote(session) -> str:
        try:
            quote = _quote(graph, package, seal, intent, customer_id)
            session.add(quote)
            await session.flush()
            session.add(_option(quote.id, "racing"))
            await session.commit()
            return "committed"
        except DBAPIError as exc:
            await session.rollback()
            return str(exc.orig)

    async with sessions() as blocker, sessions() as invalidator, sessions() as quoter:
        await blocker.execute(
            text("SELECT 1 FROM hub_packages WHERE id=:id FOR UPDATE"),
            {"id": package.id},
        )
        invalidator_pid = await invalidator.scalar(text("SELECT pg_backend_pid()"))
        quoter_pid = await quoter.scalar(text("SELECT pg_backend_pid()"))

        invalidation_task = asyncio.create_task(invalidate(invalidator))
        await wait_until_lock_blocked(blocker, invalidator_pid)
        quote_task = asyncio.create_task(create_quote(quoter))
        await wait_until_lock_blocked(blocker, quoter_pid)

        await blocker.commit()
        results = await asyncio.wait_for(
            asyncio.gather(invalidation_task, quote_task), timeout=15
        )

    assert results[0] == "invalidated"
    assert "quote cannot use an invalidated outbound intent" in results[1]
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM customer_shipping_quotes WHERE intent_id=:intent"
            ),
            {"intent": intent.id},
        )
        == 0
    )


@pytest.mark.asyncio
async def test_selection_rechecks_expiry_after_waiting_for_subject_lock(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    quote = _quote(
        graph,
        package,
        seal,
        intent,
        customer_user["user"].id,
        ttl_seconds=1,
    )
    db_session.add(quote)
    await db_session.flush()
    option = _option(quote.id, "expiry-race")
    db_session.add(option)
    await db_session.flush()
    await _force_deferred_checks(db_session)
    await db_session.commit()

    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with sessions() as blocker, sessions() as selector:
        await blocker.execute(
            text("SELECT 1 FROM hub_package_seals WHERE id=:id FOR UPDATE"),
            {"id": seal.id},
        )
        selector_pid = await selector.scalar(text("SELECT pg_backend_pid()"))

        async def select_quote() -> str:
            try:
                await selector.execute(
                    text(
                        "INSERT INTO customer_shipping_quote_selections "
                        "(id,quote_id,intent_id,option_id,customer_id,selected_by_id,"
                        "source_command,idempotency_key) VALUES "
                        "(:id,:quote,:intent,:option,:customer,:customer,'select_quote',:key)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "quote": quote.id,
                        "intent": intent.id,
                        "option": option.id,
                        "customer": customer_user["user"].id,
                        "key": f"expiry-race-{uuid.uuid4().hex}",
                    },
                )
                await selector.commit()
                return "selected"
            except DBAPIError as exc:
                await selector.rollback()
                return str(exc.orig)

        task = asyncio.create_task(select_quote())
        for _ in range(100):
            blocked = await db_session.scalar(
                text(
                    "SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"
                ),
                {"pid": selector_pid},
            )
            if blocked:
                break
            await asyncio.sleep(0.02)
        else:
            pytest.fail("selection did not block on the sealed package subject")
        await asyncio.sleep(1.05)
        await blocker.commit()
        result = await asyncio.wait_for(task, timeout=15)

    assert "quote is expired or superseded" in result


@pytest.mark.asyncio
async def test_competing_quote_refreshes_allow_exactly_one_successor(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    original = _quote(graph, package, seal, intent, customer_user["user"].id)
    db_session.add(original)
    await db_session.flush()
    db_session.add(_option(original.id, "original"))
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def refresh(label: str) -> str:
        async with sessions() as session:
            try:
                successor = _quote(
                    graph,
                    package,
                    seal,
                    intent,
                    customer_user["user"].id,
                    supersedes_quote_id=original.id,
                    idempotency_key=f"refresh-{label}-{uuid.uuid4().hex}",
                )
                session.add(successor)
                await session.flush()
                session.add(_option(successor.id, label))
                await session.commit()
                return "committed"
            except IntegrityError:
                await session.rollback()
                return "rejected"

    results = await asyncio.wait_for(
        asyncio.gather(refresh("one"), refresh("two")), timeout=15
    )
    assert sorted(results) == ["committed", "rejected"]
    successor_count = await db_session.scalar(
        text(
            "SELECT count(*) FROM customer_shipping_quotes "
            "WHERE supersedes_quote_id=:quote"
        ),
        {"quote": original.id},
    )
    assert successor_count == 1


@pytest.mark.asyncio
async def test_same_subject_rejects_a_second_root_and_requires_leaf_supersession(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    customer_id = customer_user["user"].id
    root = _quote(graph, package, seal, intent, customer_id)
    db_session.add(root)
    await db_session.flush()
    db_session.add(_option(root.id, "root"))
    await db_session.flush()
    await _force_deferred_checks(db_session)

    independent_root = _quote(graph, package, seal, intent, customer_id)
    with pytest.raises(
        DBAPIError, match="quote must supersede the current subject leaf"
    ):
        async with db_session.begin_nested():
            db_session.add(independent_root)
            await db_session.flush()

    successor = _quote(
        graph, package, seal, intent, customer_id, supersedes_quote_id=root.id
    )
    db_session.add(successor)
    await db_session.flush()
    db_session.add(_option(successor.id, "successor"))
    await db_session.flush()
    await _force_deferred_checks(db_session)

    stale_branch = _quote(
        graph, package, seal, intent, customer_id, supersedes_quote_id=root.id
    )
    with pytest.raises(
        DBAPIError,
        match="quote must supersede the current subject leaf|uq_customer_shipping_quotes_single_successor",
    ):
        async with db_session.begin_nested():
            db_session.add(stale_branch)
            await db_session.flush()


@pytest.mark.asyncio
async def test_selection_intent_is_database_bound_to_its_quote(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    _graph2, _package2, _seal2, other_intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    customer_id = customer_user["user"].id
    quote = _quote(graph, package, seal, intent, customer_id)
    db_session.add(quote)
    await db_session.flush()
    option = _option(quote.id, "bound")
    db_session.add(option)
    await db_session.flush()
    await _force_deferred_checks(db_session)

    await _rejects(
        db_session,
        "INSERT INTO customer_shipping_quote_selections "
        "(id,quote_id,intent_id,option_id,customer_id,selected_by_id,source_command,idempotency_key) "
        "VALUES (:id,:quote,:wrong_intent,:option,:customer,:customer,'select_quote',:key)",
        {
            "id": uuid.uuid4(),
            "quote": quote.id,
            "wrong_intent": other_intent.id,
            "option": option.id,
            "customer": customer_id,
            "key": f"wrong-intent-{uuid.uuid4().hex}",
        },
        "quote selection owner does not match quote|fk_customer_shipping_quote_selections_intent",
    )


@pytest.mark.asyncio
async def test_concurrent_double_selection_commits_once_per_subject_intent(
    db_session, vendor_user, customer_user
) -> None:
    """The closest legal double-select shape is two options on one current quote."""
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    customer_id = customer_user["user"].id
    quote = _quote(graph, package, seal, intent, customer_id)
    db_session.add(quote)
    await db_session.flush()
    options = [_option(quote.id, "first"), _option(quote.id, "second")]
    db_session.add_all(options)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def select(option_id) -> str:
        async with sessions() as session:
            try:
                await session.execute(
                    text(
                        "INSERT INTO customer_shipping_quote_selections "
                        "(id,quote_id,intent_id,option_id,customer_id,selected_by_id,"
                        "source_command,idempotency_key) VALUES "
                        "(:id,:quote,:intent,:option,:customer,:customer,'select_quote',:key)"
                    ),
                    {
                        "id": uuid.uuid4(),
                        "quote": quote.id,
                        "intent": intent.id,
                        "option": option_id,
                        "customer": customer_id,
                        "key": f"concurrent-selection-{uuid.uuid4().hex}",
                    },
                )
                await session.commit()
                return "committed"
            except IntegrityError as exc:
                await session.rollback()
                assert "uq_customer_shipping_quote_selections_" in str(exc.orig)
                return "rejected"

    results = await asyncio.wait_for(
        asyncio.gather(*(select(option.id) for option in options)), timeout=15
    )
    assert sorted(results) == ["committed", "rejected"]
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM customer_shipping_quote_selections "
                "WHERE intent_id=:intent"
            ),
            {"intent": intent.id},
        )
        == 1
    )


@pytest.mark.asyncio
async def test_selection_winning_refresh_race_freezes_selected_predecessor(
    db_session, vendor_user, customer_user
) -> None:
    domestic = _domestic_helpers()
    graph, package, seal, intent = await domestic._subject(
        db_session, vendor_user, customer_user
    )
    customer_id = customer_user["user"].id
    quote = _quote(graph, package, seal, intent, customer_id)
    db_session.add(quote)
    await db_session.flush()
    option = _option(quote.id, "race")
    db_session.add(option)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def wait_for_lock(observer, pid: int) -> None:
        for _ in range(100):
            if await observer.scalar(
                text(
                    "SELECT wait_event_type='Lock' FROM pg_stat_activity WHERE pid=:pid"
                ),
                {"pid": pid},
            ):
                return
            await asyncio.sleep(0.02)
        pytest.fail(f"backend {pid} did not block in refresh-selection race")

    async def select(session) -> str:
        await session.execute(
            text(
                "INSERT INTO customer_shipping_quote_selections "
                "(id,quote_id,intent_id,option_id,customer_id,selected_by_id,"
                "source_command,idempotency_key) VALUES "
                "(:id,:quote,:intent,:option,:customer,:customer,'select_quote',:key)"
            ),
            {
                "id": uuid.uuid4(),
                "quote": quote.id,
                "intent": intent.id,
                "option": option.id,
                "customer": customer_id,
                "key": f"selection-wins-{uuid.uuid4().hex}",
            },
        )
        await session.commit()
        return "selected"

    async def refresh(session) -> str:
        try:
            successor = _quote(
                graph,
                package,
                seal,
                intent,
                customer_id,
                supersedes_quote_id=quote.id,
            )
            session.add(successor)
            await session.flush()
            session.add(_option(successor.id, "stale-refresh"))
            await session.commit()
            return "refreshed"
        except DBAPIError as exc:
            await session.rollback()
            return str(exc.orig)

    async with sessions() as blocker, sessions() as selector, sessions() as refresher:
        await blocker.execute(
            text("SELECT 1 FROM outbound_shipment_intents WHERE id=:id FOR UPDATE"),
            {"id": intent.id},
        )
        selector_pid = await selector.scalar(text("SELECT pg_backend_pid()"))
        refresher_pid = await refresher.scalar(text("SELECT pg_backend_pid()"))
        selection_task = asyncio.create_task(select(selector))
        await wait_for_lock(db_session, selector_pid)
        refresh_task = asyncio.create_task(refresh(refresher))
        await wait_for_lock(db_session, refresher_pid)
        await blocker.commit()
        results = await asyncio.wait_for(
            asyncio.gather(selection_task, refresh_task), timeout=15
        )

    assert results[0] == "selected"
    assert "selected quote cannot be superseded" in results[1]
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM customer_shipping_quotes "
                "WHERE supersedes_quote_id=:quote"
            ),
            {"quote": quote.id},
        )
        == 0
    )
