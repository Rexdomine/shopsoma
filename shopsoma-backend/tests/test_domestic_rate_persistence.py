"""Immutable PostgreSQL contracts for normalized domestic rate evidence."""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import asyncio
import importlib.util
import uuid

import pytest
from sqlalchemy import CheckConstraint, UniqueConstraint, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_PACKAGE_SPEC = importlib.util.spec_from_file_location(
    "rate_package_helpers",
    Path(__file__).with_name("test_package_custody_persistence.py"),
)
assert _PACKAGE_SPEC is not None and _PACKAGE_SPEC.loader is not None
_PACKAGE = importlib.util.module_from_spec(_PACKAGE_SPEC)
_PACKAGE_SPEC.loader.exec_module(_PACKAGE)


async def _rejects(db_session, statement: str, params: dict, match: str) -> None:
    with pytest.raises(IntegrityError, match=match):
        async with db_session.begin_nested():
            await db_session.execute(text(statement), params)


def test_rate_models_are_bounded_normalized_and_private() -> None:
    from app.models.domestic_rate_quote import (
        DomesticRateAttempt,
        DomesticRateOffer,
        DomesticRateResponse,
    )

    assert [
        DomesticRateAttempt.__tablename__,
        DomesticRateResponse.__tablename__,
        DomesticRateOffer.__tablename__,
    ] == [
        "domestic_rate_attempts",
        "domestic_rate_responses",
        "domestic_rate_offers",
    ]
    attempt_names = set(DomesticRateAttempt.__table__.c.keys())
    response_names = set(DomesticRateResponse.__table__.c.keys())
    offer_names = set(DomesticRateOffer.__table__.c.keys())
    assert {
        "intent_id",
        "order_id",
        "package_id",
        "package_version",
        "seal_id",
        "origin_hub_id",
        "hub_version",
        "destination_country_code",
        "destination_snapshot_hash",
        "provider",
        "environment",
        "account_alias",
        "idempotency_key",
        "request_fingerprint",
        "fingerprint_key_version",
        "planned_ship_date",
        "adapter_version",
        "schema_version",
        "canonicalization_version",
        "claimed_at",
        "claim_ttl_seconds",
        "claim_expires_at",
        "call_started_at",
        "result_recorded_at",
        "classification",
        "failure_code",
    } <= attempt_names
    assert {
        "attempt_id",
        "result_kind",
        "received_at",
        "expires_at",
        "ttl_seconds",
    } <= response_names
    assert {
        "response_id",
        "provider_product_code",
        "provider_service_code",
        "service_label",
        "total_amount",
        "currency",
        "transit_days",
        "delivery_date",
    } <= offer_names
    forbidden = {
        "request",
        "response",
        "payload",
        "request_json",
        "response_json",
        "credentials",
        "username",
        "password",
        "api_key",
        "account_number",
        "account_value",
        "seal_value",
        "opaque_value",
        "destination_name",
        "destination_phone",
        "destination_address",
    }
    assert not (attempt_names | response_names | offer_names) & forbidden
    for table in (
        DomesticRateAttempt.__table__,
        DomesticRateResponse.__table__,
        DomesticRateOffer.__table__,
    ):
        assert all(fk.ondelete == "RESTRICT" for fk in table.foreign_key_constraints)
        assert any(isinstance(item, CheckConstraint) for item in table.constraints)
    assert (
        DomesticRateOffer.__table__.c.total_amount.type.precision,
        DomesticRateOffer.__table__.c.total_amount.type.scale,
    ) == (18, 4)
    assert DomesticRateAttempt.__table__.c.idempotency_key.type.length == 200
    assert DomesticRateAttempt.__table__.c.failure_code.type.length == 100
    assert DomesticRateAttempt.__table__.c.request_fingerprint.type.length == 64
    assert DomesticRateOffer.__table__.c.currency.type.length == 3
    assert any(
        isinstance(item, UniqueConstraint)
        and [column.name for column in item.columns] == ["attempt_id"]
        for item in DomesticRateResponse.__table__.constraints
    )


async def _subject(db_session, vendor_user, customer_user):
    from app.models.package_custody import OutboundShipmentIntent

    graph = await _PACKAGE._passed_graph(db_session, vendor_user, customer_user)
    await db_session.execute(
        text(
            "UPDATE fulfillment_hubs SET is_active=true, activated_at=clock_timestamp(), "
            "activated_by_id=:actor WHERE id=:hub"
        ),
        {"actor": graph["operator_id"], "hub": graph["hub"].id},
    )
    package, _version, _item, seal = await _PACKAGE._ready_package(db_session, graph)
    intent = OutboundShipmentIntent(
        package_id=package.id,
        package_version=1,
        seal_id=seal.id,
        order_id=graph["order"].id,
        origin_hub_id=graph["hub"].id,
        destination_name="Rate Test Customer",
        destination_phone="+234****0000",
        destination_address_line1="1 Private Destination Road",
        destination_city="Lagos",
        destination_state="Lagos",
        destination_postal_code="100001",
        destination_country_code="NG",
        source_command="prepare_outbound",
        idempotency_key=f"intent-{uuid.uuid4().hex}",
        created_by_id=graph["operator_id"],
    )
    db_session.add(intent)
    await db_session.flush()
    return graph, package, seal, intent


def _attempt(graph, package, seal, intent, claimed_at, **overrides):
    from app.models.domestic_rate_quote import DomesticRateAttempt

    values = {
        "intent_id": intent.id,
        "order_id": graph["order"].id,
        "package_id": package.id,
        "package_version": 1,
        "seal_id": seal.id,
        "origin_hub_id": graph["hub"].id,
        "hub_version": graph["hub"].version,
        "destination_country_code": "NG",
        "destination_snapshot_hash": intent.destination_snapshot_hash,
        "provider": "dhl",
        "environment": "sandbox",
        "account_alias": "dhl-ng-sandbox",
        "idempotency_key": f"rate-{uuid.uuid4().hex}",
        "request_fingerprint": "b" * 64,
        "fingerprint_key_version": "rate-fingerprint-v1",
        "planned_ship_date": date.today() + timedelta(days=1),
        "adapter_version": "mydhl-rates-v1",
        "schema_version": "domestic-rate-v1",
        "canonicalization_version": "rate-c14n-v1",
        "claimed_at": claimed_at,
        "classification": "pending",
    }
    values.update(overrides)
    return DomesticRateAttempt(**values)


async def _complete_attempt(db_session, attempt, classification: str):
    """Persist the mandatory pending claim, then record its terminal result."""
    db_session.add(attempt)
    await db_session.flush()
    called = await db_session.scalar(text("SELECT clock_timestamp()"))
    completed = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.execute(
        text(
            "UPDATE domestic_rate_attempts SET call_started_at=:called, "
            "result_recorded_at=:completed, classification=:classification "
            "WHERE id=:id"
        ),
        {
            "id": attempt.id,
            "called": called,
            "completed": completed,
            "classification": classification,
        },
    )
    return completed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    (
        {"call_started_at": "claimed"},
        {
            "call_started_at": "claimed",
            "result_recorded_at": "claimed",
            "classification": "success",
        },
        {
            "call_started_at": "claimed",
            "result_recorded_at": "claimed",
            "classification": "failure",
            "failure_code": "timeout",
        },
    ),
)
async def test_attempt_insert_must_be_a_pristine_pending_claim(
    db_session, vendor_user, customer_user, overrides
) -> None:
    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    resolved = {
        key: claimed if value == "claimed" else value
        for key, value in overrides.items()
    }
    attempt = _attempt(graph, package, seal, intent, claimed, **resolved)
    with pytest.raises(IntegrityError, match="rate attempt must begin pending"):
        async with db_session.begin_nested():
            db_session.add(attempt)
            await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ("rate-café", "rate\nkey", "rate key"))
async def test_idempotency_key_rejects_non_identifier_ascii(
    db_session, vendor_user, customer_user, value
) -> None:
    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(graph, package, seal, intent, claimed, idempotency_key=value)
    with pytest.raises(IntegrityError, match="ck_domestic_rate_attempts_identifiers"):
        async with db_session.begin_nested():
            db_session.add(attempt)
            await db_session.flush()


@pytest.mark.asyncio
async def test_attempt_rejects_destination_snapshot_not_derived_from_intent(
    db_session, vendor_user, customer_user
) -> None:
    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    assert intent.destination_snapshot_hash is not None
    assert len(intent.destination_snapshot_hash) == 64
    expected_hash = await db_session.scalar(
        text(
            "SELECT encode(sha256(convert_to(jsonb_build_array("
            "'destination-snapshot-v1', destination_name, destination_phone, "
            "destination_address_line1, destination_address_line2, destination_city, "
            "destination_state, destination_postal_code, destination_country_code"
            ")::text, 'UTF8')), 'hex') FROM outbound_shipment_intents WHERE id=:id"
        ),
        {"id": intent.id},
    )
    assert intent.destination_snapshot_hash == expected_hash
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(
        graph,
        package,
        seal,
        intent,
        claimed,
        destination_snapshot_hash="f" * 64,
    )
    with pytest.raises(IntegrityError, match="rate attempt subject binding is invalid"):
        async with db_session.begin_nested():
            db_session.add(attempt)
            await db_session.flush()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ("provider-café", "provider\tcode", "provider code"))
async def test_failure_code_rejects_non_identifier_ascii(
    db_session, vendor_user, customer_user, value
) -> None:
    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(graph, package, seal, intent, claimed)
    db_session.add(attempt)
    await db_session.flush()
    now = await db_session.scalar(text("SELECT clock_timestamp()"))
    await _rejects(
        db_session,
        "UPDATE domestic_rate_attempts SET call_started_at=:at, "
        "result_recorded_at=:at, classification='failure', failure_code=:code "
        "WHERE id=:id",
        {"id": attempt.id, "at": now, "code": value},
        "ck_domestic_rate_attempts_lifecycle",
    )


@pytest.mark.asyncio
async def test_attempt_lifecycle_is_one_way_and_identity_is_immutable(
    db_session, vendor_user, customer_user
) -> None:
    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(graph, package, seal, intent, claimed)
    db_session.add(attempt)
    await db_session.flush()

    await _rejects(
        db_session,
        "UPDATE domestic_rate_attempts SET account_alias='other-alias' WHERE id=:id",
        {"id": attempt.id},
        "rate attempt identity is immutable",
    )
    called = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.execute(
        text("UPDATE domestic_rate_attempts SET call_started_at=:at WHERE id=:id"),
        {"id": attempt.id, "at": called},
    )
    completed = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.execute(
        text(
            "UPDATE domestic_rate_attempts SET classification='success', "
            "result_recorded_at=:at WHERE id=:id"
        ),
        {"id": attempt.id, "at": completed},
    )
    await _rejects(
        db_session,
        "UPDATE domestic_rate_attempts SET classification='failure', failure_code='timeout' WHERE id=:id",
        {"id": attempt.id},
        "completed rate attempt is immutable",
    )
    await _rejects(
        db_session,
        "DELETE FROM domestic_rate_attempts WHERE id=:id",
        {"id": attempt.id},
        "rate evidence is append-only",
    )


@pytest.mark.asyncio
async def test_expired_pending_claim_can_be_truthfully_abandoned_and_reacquired(
    db_session, vendor_user, customer_user
) -> None:
    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(
        graph,
        package,
        seal,
        intent,
        claimed,
        claim_ttl_seconds=1,
        idempotency_key=f"recover-rate-{uuid.uuid4().hex}",
    )
    db_session.add(attempt)
    await db_session.flush()
    await db_session.refresh(attempt)
    assert attempt.claim_ttl_seconds == 1
    assert attempt.claim_expires_at == attempt.claimed_at + timedelta(seconds=1)

    await _rejects(
        db_session,
        "UPDATE domestic_rate_attempts SET classification='abandoned', "
        "failure_code='claim_expired' WHERE id=:id",
        {"id": attempt.id},
        "rate attempt claim has not expired",
    )
    await db_session.execute(
        text(
            "UPDATE domestic_rate_attempts SET call_started_at=clock_timestamp() "
            "WHERE id=:id"
        ),
        {"id": attempt.id},
    )
    await db_session.execute(text("SELECT pg_sleep(1.05)"))
    await db_session.execute(
        text(
            "UPDATE domestic_rate_attempts SET classification='abandoned', "
            "failure_code='claim_expired' WHERE id=:id"
        ),
        {"id": attempt.id},
    )
    await db_session.refresh(attempt)
    assert attempt.classification == "abandoned"
    assert attempt.result_recorded_at is not None
    assert attempt.completion_txid is not None
    active = await db_session.scalar(
        text(
            "SELECT active_attempt_id FROM outbound_intent_rate_guards WHERE intent_id=:id"
        ),
        {"id": intent.id},
    )
    assert active is None

    retry = _attempt(
        graph,
        package,
        seal,
        intent,
        claimed,
        idempotency_key=f"retry-rate-{uuid.uuid4().hex}",
    )
    db_session.add(retry)
    await db_session.flush()
    await db_session.refresh(retry)
    assert retry.claimed_at > attempt.claimed_at
    assert retry.claim_expires_at == retry.claimed_at + timedelta(seconds=300)
    active = await db_session.scalar(
        text(
            "SELECT active_attempt_id FROM outbound_intent_rate_guards WHERE intent_id=:id"
        ),
        {"id": intent.id},
    )
    assert active == retry.id
    await _rejects(
        db_session,
        "UPDATE domestic_rate_attempts SET classification='failure', "
        "failure_code='late_result' WHERE id=:id",
        {"id": attempt.id},
        "completed rate attempt is immutable",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", (0, 901))
async def test_claim_lease_duration_is_bounded_by_the_database(
    db_session, vendor_user, customer_user, ttl
) -> None:
    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(
        graph,
        package,
        seal,
        intent,
        claimed,
        claim_ttl_seconds=ttl,
    )
    with pytest.raises(IntegrityError, match="rate attempt claim duration is invalid"):
        async with db_session.begin_nested():
            db_session.add(attempt)
            await db_session.flush()


@pytest.mark.asyncio
async def test_expired_claim_rejects_late_call_and_terminal_results_until_abandoned(
    db_session, vendor_user, customer_user
) -> None:
    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(
        graph,
        package,
        seal,
        intent,
        claimed,
        claim_ttl_seconds=1,
    )
    db_session.add(attempt)
    await db_session.flush()
    await db_session.execute(text("SELECT pg_sleep(1.05)"))

    await _rejects(
        db_session,
        "UPDATE domestic_rate_attempts SET call_started_at=clock_timestamp() "
        "WHERE id=:id",
        {"id": attempt.id},
        "rate attempt claim has expired",
    )
    for classification, failure_code in (
        ("success", None),
        ("no_service", None),
        ("failure", "timeout"),
    ):
        await _rejects(
            db_session,
            "UPDATE domestic_rate_attempts SET classification=:classification, "
            "failure_code=:failure_code WHERE id=:id",
            {
                "id": attempt.id,
                "classification": classification,
                "failure_code": failure_code,
            },
            "rate attempt claim has expired",
        )
    active = await db_session.scalar(
        text(
            "SELECT active_attempt_id FROM outbound_intent_rate_guards WHERE intent_id=:id"
        ),
        {"id": intent.id},
    )
    assert active == attempt.id

    await db_session.execute(
        text(
            "UPDATE domestic_rate_attempts SET classification='abandoned', "
            "failure_code='claim_expired' WHERE id=:id"
        ),
        {"id": attempt.id},
    )
    await db_session.refresh(attempt)
    assert attempt.classification == "abandoned"


@pytest.mark.asyncio
async def test_terminal_attempt_cannot_commit_without_atomic_response(
    db_session, vendor_user, customer_user
) -> None:
    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(graph, package, seal, intent, claimed)
    await _complete_attempt(db_session, attempt, "success")

    with pytest.raises(
        IntegrityError, match="terminal rate attempt requires exactly one response"
    ):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_rate_evidence_recording_clocks_override_backdated_caller_values(
    db_session, vendor_user, customer_user
) -> None:
    from app.models.domestic_rate_quote import DomesticRateOffer, DomesticRateResponse

    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    backdated = await db_session.scalar(
        text("SELECT timestamptz '2000-01-01 00:00:00+00'")
    )
    attempt = _attempt(
        graph,
        package,
        seal,
        intent,
        backdated,
        created_at=backdated,
        idempotency_key=f"clock-rate-{uuid.uuid4().hex}",
        request_fingerprint="e" * 64,
    )
    db_session.add(attempt)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE domestic_rate_attempts SET call_started_at=:backdated "
            "WHERE id=:id"
        ),
        {"id": attempt.id, "backdated": backdated},
    )
    await db_session.execute(
        text(
            "UPDATE domestic_rate_attempts SET result_recorded_at=:backdated, "
            "classification='success' WHERE id=:id"
        ),
        {"id": attempt.id, "backdated": backdated},
    )
    response = DomesticRateResponse(
        attempt_id=attempt.id,
        result_kind="success",
        received_at=backdated,
        expires_at=backdated + timedelta(minutes=15),
        ttl_seconds=900,
        created_at=backdated,
    )
    db_session.add(response)
    await db_session.flush()
    offer = DomesticRateOffer(
        response_id=response.id,
        provider_product_code="N",
        provider_service_code="DOM-N",
        service_label="Domestic Express",
        total_amount=Decimal("100.0000"),
        currency="NGN",
        created_at=backdated,
    )
    db_session.add(offer)
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    clocks = (
        await db_session.execute(
            text(
                "SELECT a.claimed_at,a.call_started_at,a.result_recorded_at,a.created_at,"
                "r.received_at,r.expires_at,r.created_at,o.created_at "
                "FROM domestic_rate_attempts a "
                "JOIN domestic_rate_responses r ON r.attempt_id=a.id "
                "JOIN domestic_rate_offers o ON o.response_id=r.id "
                "WHERE a.id=:id"
            ),
            {"id": attempt.id},
        )
    ).one()
    assert all(value > backdated for value in clocks)
    assert clocks.expires_at == clocks.received_at + timedelta(seconds=900)


@pytest.mark.asyncio
async def test_rate_claim_and_intent_invalidation_have_one_bounded_winner(
    db_session, vendor_user, customer_user
) -> None:
    from app.models.package_custody import OutboundShipmentIntentInvalidation

    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    now = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(
        graph,
        package,
        seal,
        intent,
        now,
        idempotency_key=f"race-rate-{uuid.uuid4().hex}",
        request_fingerprint="d" * 64,
    )
    invalidation = OutboundShipmentIntentInvalidation(
        intent_id=intent.id,
        reason="authorized destination correction",
        actor_type="user",
        actor_id=str(graph["operator_id"]),
        source_command="invalidate_outbound",
        idempotency_key=f"race-invalidate-{uuid.uuid4().hex}",
        invalidated_at=now,
    )
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def claim() -> str:
        async with sessions() as session:
            try:
                session.add(attempt)
                await session.commit()
                return "claim-committed"
            except IntegrityError as error:
                await session.rollback()
                assert "rate attempt subject binding is invalid" in str(error)
                return "claim-rejected"

    async def invalidate() -> str:
        async with sessions() as session:
            try:
                session.add(invalidation)
                await session.commit()
                return "invalidation-committed"
            except IntegrityError as error:
                await session.rollback()
                assert "active rate attempt must complete" in str(error)
                return "invalidation-rejected"

    results = await asyncio.wait_for(asyncio.gather(claim(), invalidate()), timeout=15)
    assert sum(result.endswith("committed") for result in results) == 1
    attempt_count = await db_session.scalar(
        text("SELECT count(*) FROM domestic_rate_attempts WHERE intent_id=:intent"),
        {"intent": intent.id},
    )
    invalidation_count = await db_session.scalar(
        text(
            "SELECT count(*) FROM outbound_shipment_intent_invalidations "
            "WHERE intent_id=:intent"
        ),
        {"intent": intent.id},
    )
    guard = (
        await db_session.execute(
            text(
                "SELECT is_invalidated,active_attempt_id FROM outbound_intent_rate_guards "
                "WHERE intent_id=:intent"
            ),
            {"intent": intent.id},
        )
    ).one()
    assert (attempt_count, invalidation_count) in ((1, 0), (0, 1))
    assert guard == ((False, attempt.id) if attempt_count else (True, None))


@pytest.mark.asyncio
async def test_response_offer_shapes_money_ttl_and_append_only_guards(
    db_session, vendor_user, customer_user
) -> None:
    from app.models.domestic_rate_quote import DomesticRateOffer, DomesticRateResponse

    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(graph, package, seal, intent, claimed)
    received = await _complete_attempt(db_session, attempt, "success")
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
    bounded_slack_offer = DomesticRateOffer(
        response_id=response.id,
        provider_product_code="N",
        provider_service_code="SLACK",
        service_label="Bounded delivery slack",
        total_amount=Decimal("1235.0000"),
        currency="NGN",
        transit_days=1,
        delivery_date=attempt.planned_ship_date + timedelta(days=8),
    )
    db_session.add_all((offer, bounded_slack_offer))
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))

    amount = await db_session.scalar(
        text("SELECT total_amount FROM domestic_rate_offers WHERE id=:id"),
        {"id": offer.id},
    )
    assert amount == Decimal("1234.5678")
    await _rejects(
        db_session,
        "UPDATE domestic_rate_offers SET total_amount=1 WHERE id=:id",
        {"id": offer.id},
        "rate evidence is append-only",
    )
    await _rejects(
        db_session,
        "INSERT INTO domestic_rate_offers (id,response_id,provider_product_code,provider_service_code,service_label,total_amount,currency) VALUES (:id,:response,'X','BAD','Bad',0,'ngn')",
        {"id": uuid.uuid4(), "response": response.id},
        "ck_domestic_rate_offers",
    )
    await _rejects(
        db_session,
        "INSERT INTO domestic_rate_offers (id,response_id,provider_product_code,provider_service_code,service_label,total_amount,currency,transit_days,delivery_date) VALUES (:id,:response,'X','EARLY','Early delivery',1,'NGN',7,:delivery)",
        {
            "id": uuid.uuid4(),
            "response": response.id,
            "delivery": attempt.planned_ship_date + timedelta(days=1),
        },
        "rate offer delivery facts are invalid",
    )
    for service_code, transit_days, delivery_days in (
        ("SAME", None, 0),
        ("LATE", 1, 9),
    ):
        await _rejects(
            db_session,
            "INSERT INTO domestic_rate_offers (id,response_id,provider_product_code,provider_service_code,service_label,total_amount,currency,transit_days,delivery_date) VALUES (:id,:response,'X',:service,'Invalid delivery',1,'NGN',:transit,:delivery)",
            {
                "id": uuid.uuid4(),
                "response": response.id,
                "service": service_code,
                "transit": transit_days,
                "delivery": attempt.planned_ship_date + timedelta(days=delivery_days),
            },
            "rate offer delivery facts are invalid",
        )


@pytest.mark.asyncio
async def test_committed_success_response_rejects_late_offer_append(
    db_session, vendor_user, customer_user
) -> None:
    from app.models.domestic_rate_quote import DomesticRateOffer, DomesticRateResponse

    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    attempt = _attempt(graph, package, seal, intent, claimed)
    received = await _complete_attempt(db_session, attempt, "success")

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
        total_amount=Decimal("100.0000"),
        currency="NGN",
    )
    db_session.add(offer)
    await db_session.flush()
    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    response_created_at = await db_session.scalar(
        text("SELECT created_at FROM domestic_rate_responses WHERE id=:id"),
        {"id": response.id},
    )
    response_completion_txid = await db_session.scalar(
        text("SELECT completion_txid FROM domestic_rate_responses WHERE id=:id"),
        {"id": response.id},
    )
    offer_completion_txid = await db_session.scalar(
        text("SELECT completion_txid FROM domestic_rate_offers WHERE id=:id"),
        {"id": offer.id},
    )
    assert offer_completion_txid == response_completion_txid
    await db_session.commit()

    async with AsyncSession(
        bind=db_session.bind, expire_on_commit=False
    ) as later_session:
        later_transaction_at = await later_session.scalar(
            text("SELECT transaction_timestamp()")
        )
        assert later_transaction_at > response_created_at
        with pytest.raises(
            IntegrityError, match="rate response offer set is immutable"
        ):
            await later_session.execute(
                text(
                    "INSERT INTO domestic_rate_offers "
                    "(id,response_id,provider_product_code,provider_service_code,"
                    "service_label,total_amount,currency,created_at) VALUES "
                    "(:id,:response,'X','DOM-X','Late offer',10,'NGN',:created_at)"
                ),
                {
                    "id": uuid.uuid4(),
                    "response": response.id,
                    "created_at": response_created_at,
                },
            )


@pytest.mark.asyncio
async def test_no_service_has_no_offers_and_success_requires_one(
    db_session, vendor_user, customer_user
) -> None:
    from app.models.domestic_rate_quote import DomesticRateResponse

    graph, package, seal, intent = await _subject(
        db_session, vendor_user, customer_user
    )
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    no_service_attempt = _attempt(graph, package, seal, intent, claimed)
    received = await _complete_attempt(db_session, no_service_attempt, "no_service")
    no_service = DomesticRateResponse(
        attempt_id=no_service_attempt.id,
        result_kind="no_service",
        received_at=received,
        expires_at=received + timedelta(minutes=5),
        ttl_seconds=300,
    )
    db_session.add(no_service)
    await db_session.flush()
    await _rejects(
        db_session,
        "INSERT INTO domestic_rate_offers (id,response_id,provider_product_code,provider_service_code,service_label,total_amount,currency) VALUES (:id,:response,'N','DOM-N','Domestic',10,'NGN')",
        {"id": uuid.uuid4(), "response": no_service.id},
        "no-service response cannot contain offers",
    )

    await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    await db_session.commit()
    claimed = await db_session.scalar(text("SELECT clock_timestamp()"))
    success_attempt = _attempt(
        graph,
        package,
        seal,
        intent,
        claimed,
        idempotency_key=f"rate-{uuid.uuid4().hex}",
        request_fingerprint="c" * 64,
    )
    received = await _complete_attempt(db_session, success_attempt, "success")
    success = DomesticRateResponse(
        attempt_id=success_attempt.id,
        result_kind="success",
        received_at=received,
        expires_at=received + timedelta(minutes=5),
        ttl_seconds=300,
    )
    db_session.add(success)
    await db_session.flush()
    with pytest.raises(
        IntegrityError, match="success response requires at least one offer"
    ):
        async with db_session.begin_nested():
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
