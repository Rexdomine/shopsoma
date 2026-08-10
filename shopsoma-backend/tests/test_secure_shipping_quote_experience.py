"""Lean authenticated customer shipping-quote orchestration and API contracts."""

import asyncio
import importlib.util
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker


def _domestic_helpers():
    path = Path(__file__).with_name("test_domestic_rate_persistence.py")
    spec = importlib.util.spec_from_file_location("secure_quote_domestic_helpers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _rated_subject(db_session, vendor_user, customer_user, *, currency="NGN"):
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
        expires_at=received + timedelta(hours=1),
        ttl_seconds=3600,
    )
    db_session.add(response)
    await db_session.flush()
    economy = DomesticRateOffer(
        response_id=response.id,
        provider_product_code="N",
        provider_service_code="DOM-N",
        service_label="DHL Domestic Express",
        total_amount=Decimal("1234.5600"),
        currency=currency,
        transit_days=2,
        delivery_date=attempt.planned_ship_date + timedelta(days=2),
    )
    priority = DomesticRateOffer(
        response_id=response.id,
        provider_product_code="N",
        provider_service_code="DOM-P",
        service_label="DHL Domestic Priority",
        total_amount=Decimal("2234.0000"),
        currency=currency,
        transit_days=1,
        delivery_date=attempt.planned_ship_date + timedelta(days=1),
    )
    db_session.add_all((economy, priority))
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    await db_session.commit()
    return graph, package, seal, intent, response, economy, priority


def _capabilities(*, workflow_enabled=True, provider_calls_enabled=False):
    from app.services.shipping.capabilities import DomesticShippingCapabilities

    return DomesticShippingCapabilities(
        workflow_enabled=workflow_enabled,
        quote_enforcement_enabled=False,
        provider_calls_enabled=provider_calls_enabled,
    )


@pytest.mark.parametrize(
    "value",
    ("", " key", "key ", "key with space", "café", "x" * 201, "line\nfeed"),
)
def test_idempotency_keys_are_bounded_canonical_ascii(value) -> None:
    from app.services.shipping.customer_quotes import validate_idempotency_key

    with pytest.raises(ValueError, match="idempotency key is invalid"):
        validate_idempotency_key(value)


def test_customer_quote_response_schema_redacts_provider_and_subject_internals() -> (
    None
):
    from app.schemas.customer_shipping_quote import CustomerShippingQuoteResponse

    exposed = set(CustomerShippingQuoteResponse.model_fields)
    assert {
        "package_id",
        "package_version",
        "seal_id",
        "intent_id",
        "origin_hub_id",
        "destination_snapshot_hash",
        "source_rate_response_id",
        "request_fingerprint",
        "provider",
        "product_code",
        "service_code",
        "source_rate_offer_id",
        "raw_payload",
        "account_alias",
    }.isdisjoint(exposed)


async def _case_create_quote_uses_authoritative_persisted_evidence_and_replays_exact_result(
    db_session, vendor_user, customer_user
) -> None:
    from app.services.shipping.customer_quotes import CustomerShippingQuoteService

    graph, _package, _seal, intent, response, economy, priority = await _rated_subject(
        db_session, vendor_user, customer_user
    )
    service = CustomerShippingQuoteService(
        db_session,
        capabilities=_capabilities(),
        quote_ttl_seconds=1800,
    )

    created = await service.create_quote(
        order_id=graph["order"].id,
        customer_id=customer_user["user"].id,
        idempotency_key="create-quote-1",
    )
    replayed = await service.create_quote(
        order_id=graph["order"].id,
        customer_id=customer_user["user"].id,
        idempotency_key="create-quote-1",
    )

    assert replayed == created
    assert created.intent_id == intent.id
    assert created.source_rate_response_id == response.id
    assert {option.source_rate_offer_id for option in created.options} == {
        economy.id,
        priority.id,
    }
    assert {option.total_amount for option in created.options} == {
        Decimal("1234.5600"),
        Decimal("2234.0000"),
    }
    assert {option.currency for option in created.options} == {"NGN"}
    assert created.status == "available"


async def _case_create_quote_fails_closed_for_gate_currency_and_stale_subject(
    db_session, vendor_user, customer_user
) -> None:
    from app.services.shipping.customer_quotes import (
        CustomerShippingQuoteService,
        ShippingQuoteUnavailable,
    )

    graph, _package, _seal, intent, _response, _economy, _priority = (
        await _rated_subject(db_session, vendor_user, customer_user, currency="USD")
    )
    disabled = CustomerShippingQuoteService(
        db_session,
        capabilities=_capabilities(workflow_enabled=False),
        quote_ttl_seconds=1800,
    )
    with pytest.raises(
        ShippingQuoteUnavailable, match="shipping quotes are unavailable"
    ):
        await disabled.create_quote(
            order_id=graph["order"].id,
            customer_id=customer_user["user"].id,
            idempotency_key="gate-off",
        )

    enabled = CustomerShippingQuoteService(
        db_session,
        capabilities=_capabilities(),
        quote_ttl_seconds=1800,
    )
    with pytest.raises(
        ShippingQuoteUnavailable, match="eligible shipping rates are unavailable"
    ):
        await enabled.create_quote(
            order_id=graph["order"].id,
            customer_id=customer_user["user"].id,
            idempotency_key="wrong-currency",
        )

    from app.models.package_custody import OutboundShipmentIntentInvalidation

    invalidated_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    db_session.add(
        OutboundShipmentIntentInvalidation(
            intent_id=intent.id,
            reason="Customer quote test invalidation",
            actor_type="system",
            actor_id="secure-quote-test",
            source_command="invalidate_outbound_intent",
            idempotency_key=f"invalidate-{uuid.uuid4().hex}",
            invalidated_at=invalidated_at,
        )
    )
    await db_session.commit()
    with pytest.raises(
        ShippingQuoteUnavailable, match="shipping quote subject is unavailable"
    ):
        await enabled.create_quote(
            order_id=graph["order"].id,
            customer_id=customer_user["user"].id,
            idempotency_key="stale-subject",
        )


async def _case_selection_revalidates_eligibility_and_replay_conflicts(
    db_session, vendor_user, customer_user
) -> None:
    from app.services.shipping.customer_quotes import (
        CustomerShippingQuoteService,
        ShippingQuoteConflict,
    )

    graph, *_rest = await _rated_subject(db_session, vendor_user, customer_user)
    service = CustomerShippingQuoteService(
        db_session,
        capabilities=_capabilities(),
        quote_ttl_seconds=1800,
    )
    quote = await service.create_quote(
        order_id=graph["order"].id,
        customer_id=customer_user["user"].id,
        idempotency_key="create-selectable",
    )
    first, second = quote.options
    selected = await service.select_option(
        order_id=graph["order"].id,
        quote_id=quote.id,
        option_id=first.id,
        customer_id=customer_user["user"].id,
        idempotency_key="select-1",
    )
    replayed = await service.select_option(
        order_id=graph["order"].id,
        quote_id=quote.id,
        option_id=first.id,
        customer_id=customer_user["user"].id,
        idempotency_key="select-1",
    )
    assert replayed == selected
    assert replayed.selected_option_id == first.id

    with pytest.raises(ShippingQuoteConflict, match="idempotency key was already used"):
        await service.select_option(
            order_id=graph["order"].id,
            quote_id=quote.id,
            option_id=second.id,
            customer_id=customer_user["user"].id,
            idempotency_key="select-1",
        )


async def _case_create_conflicts_when_selected_quote_blocks_requoting(
    db_session, vendor_user, customer_user
) -> None:
    from app.services.shipping.customer_quotes import (
        CustomerShippingQuoteService,
        ShippingQuoteConflict,
    )

    graph, *_rest = await _rated_subject(db_session, vendor_user, customer_user)
    service = CustomerShippingQuoteService(
        db_session,
        capabilities=_capabilities(),
        quote_ttl_seconds=1800,
    )
    quote = await service.create_quote(
        order_id=graph["order"].id,
        customer_id=customer_user["user"].id,
        idempotency_key="create-before-selection",
    )
    await service.select_option(
        order_id=graph["order"].id,
        quote_id=quote.id,
        option_id=quote.options[0].id,
        customer_id=customer_user["user"].id,
        idempotency_key="select-before-requote",
    )

    with pytest.raises(
        ShippingQuoteConflict, match="selected shipping quote cannot be replaced"
    ):
        await service.create_quote(
            order_id=graph["order"].id,
            customer_id=customer_user["user"].id,
            idempotency_key="requote-after-selection",
        )


async def _case_create_keys_serialize_across_customer_orders(
    db_session, vendor_user, customer_user
) -> None:
    from app.services.shipping.customer_quotes import (
        CustomerShippingQuoteService,
        ShippingQuoteConflict,
    )

    first_graph, *_ = await _rated_subject(db_session, vendor_user, customer_user)
    second_graph, *_ = await _rated_subject(db_session, vendor_user, customer_user)
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def create(order_id):
        async with sessions() as session:
            service = CustomerShippingQuoteService(
                session,
                capabilities=_capabilities(),
                quote_ttl_seconds=1800,
            )
            try:
                quote = await service.create_quote(
                    order_id=order_id,
                    customer_id=customer_user["user"].id,
                    idempotency_key="customer-wide-create-race",
                )
                await session.commit()
                return ("created", quote.order_id)
            except ShippingQuoteConflict:
                await session.rollback()
                return ("conflict", order_id)

    results = await asyncio.gather(
        create(first_graph["order"].id),
        create(second_graph["order"].id),
    )
    assert sorted(result[0] for result in results) == ["conflict", "created"]


async def _case_selection_is_serialized_across_two_postgresql_connections(
    db_session, vendor_user, customer_user
) -> None:
    from app.services.shipping.customer_quotes import (
        CustomerShippingQuoteService,
        ShippingQuoteConflict,
    )

    graph, *_rest = await _rated_subject(db_session, vendor_user, customer_user)
    seed_service = CustomerShippingQuoteService(
        db_session,
        capabilities=_capabilities(),
        quote_ttl_seconds=1800,
    )
    quote = await seed_service.create_quote(
        order_id=graph["order"].id,
        customer_id=customer_user["user"].id,
        idempotency_key="create-race",
    )
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def select(option_id, key):
        async with sessions() as session:
            service = CustomerShippingQuoteService(
                session,
                capabilities=_capabilities(),
                quote_ttl_seconds=1800,
            )
            try:
                result = await service.select_option(
                    order_id=graph["order"].id,
                    quote_id=quote.id,
                    option_id=option_id,
                    customer_id=customer_user["user"].id,
                    idempotency_key=key,
                )
                await session.commit()
                return result.selected_option_id
            except ShippingQuoteConflict:
                await session.rollback()
                return None

    results = await asyncio.gather(
        select(quote.options[0].id, "race-a"),
        select(quote.options[1].id, "race-b"),
    )
    assert sum(result is not None for result in results) == 1


async def _case_api_is_authenticated_idor_safe_and_redacted(
    client, db_session, vendor_user, customer_user, monkeypatch
) -> None:
    from app.core.config import settings

    graph, *_rest = await _rated_subject(db_session, vendor_user, customer_user)
    monkeypatch.setattr(settings, "DHL_DOMESTIC_WORKFLOW_ENABLED", True)
    path = f"/api/v1/orders/{graph['order'].id}/shipping-quotes"

    unauthenticated = await client.get(path)
    assert unauthenticated.status_code in {401, 403}

    hidden = await client.get(path, headers=vendor_user["headers"])
    missing = await client.get(
        f"/api/v1/orders/{uuid.uuid4()}/shipping-quotes",
        headers=vendor_user["headers"],
    )
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()

    created = await client.post(
        path,
        headers={**customer_user["headers"], "X-Idempotency-Key": "api-create-1"},
    )
    assert created.status_code == 201, created.text
    payload = created.json()
    assert payload["options"][0]["total_amount"] == "1234.5600"
    serialized = created.text.lower()
    for forbidden in (
        "destination_",
        "package_id",
        "seal_id",
        "intent_id",
        "source_rate",
        "request_fingerprint",
        "account_alias",
        "product_code",
        "service_code",
        '"provider"',
    ):
        assert forbidden not in serialized

    selected = await client.post(
        f"{path}/{payload['id']}/options/{payload['options'][0]['id']}/select",
        headers={**customer_user["headers"], "X-Idempotency-Key": "api-select-1"},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["status"] == "selected"

    requote = await client.post(
        path,
        headers={
            **customer_user["headers"],
            "X-Idempotency-Key": "api-requote-after-selection",
        },
    )
    assert requote.status_code == 409, requote.text
    assert requote.json() == {"detail": "selected shipping quote cannot be replaced"}


@pytest.mark.asyncio
async def test_secure_shipping_quote_experience_end_to_end(
    client, db_session, vendor_user, customer_user, monkeypatch
) -> None:
    """Exercise all PostgreSQL/API cases in one repository fixture lifecycle."""
    await _case_create_quote_uses_authoritative_persisted_evidence_and_replays_exact_result(
        db_session, vendor_user, customer_user
    )
    await _case_create_quote_fails_closed_for_gate_currency_and_stale_subject(
        db_session, vendor_user, customer_user
    )
    await _case_selection_revalidates_eligibility_and_replay_conflicts(
        db_session, vendor_user, customer_user
    )
    await _case_create_keys_serialize_across_customer_orders(
        db_session, vendor_user, customer_user
    )
    await _case_create_conflicts_when_selected_quote_blocks_requoting(
        db_session, vendor_user, customer_user
    )
    await _case_selection_is_serialized_across_two_postgresql_connections(
        db_session, vendor_user, customer_user
    )
    await _case_api_is_authenticated_idor_safe_and_redacted(
        client, db_session, vendor_user, customer_user, monkeypatch
    )
