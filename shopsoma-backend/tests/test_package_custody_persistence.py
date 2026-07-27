"""Package/custody metadata and PostgreSQL DDL contracts."""

from pathlib import Path
import asyncio
import importlib.util
import uuid

import pytest
from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker


_HELPERS_SPEC = importlib.util.spec_from_file_location(
    "lane_3c_helpers", Path(__file__).with_name("test_hub_quality_persistence.py")
)
assert _HELPERS_SPEC is not None and _HELPERS_SPEC.loader is not None
_HUB = importlib.util.module_from_spec(_HELPERS_SPEC)
_HELPERS_SPEC.loader.exec_module(_HUB)


def test_package_custody_models_have_required_tables_and_constraints():
    from app.models.package_custody import (
        CustodyEvent,
        CustodyStream,
        HubPackage,
        HubPackageItem,
        HubPackageSeal,
        HubPackageVersion,
        OutboundShipmentIntent,
        OutboundShipmentIntentInvalidation,
    )

    models = (
        HubPackage,
        HubPackageVersion,
        HubPackageItem,
        HubPackageSeal,
        CustodyStream,
        CustodyEvent,
        OutboundShipmentIntent,
        OutboundShipmentIntentInvalidation,
    )
    assert [m.__tablename__ for m in models] == [
        "hub_packages",
        "hub_package_versions",
        "hub_package_items",
        "hub_package_seals",
        "custody_streams",
        "custody_events",
        "outbound_shipment_intents",
        "outbound_shipment_intent_invalidations",
    ]
    assert all(
        any(
            isinstance(c, (CheckConstraint, UniqueConstraint))
            for c in m.__table__.constraints
        )
        for m in models
    )


def test_outbound_intent_is_provider_agnostic_and_structured():
    from app.models.package_custody import OutboundShipmentIntent

    names = set(OutboundShipmentIntent.__table__.c.keys())
    assert not names & {
        "provider",
        "carrier",
        "dhl_account",
        "tracking_number",
        "label_url",
        "booking_id",
    }
    assert {
        "package_id",
        "package_version",
        "seal_id",
        "order_id",
        "origin_hub_id",
        "destination_name",
        "destination_address_line1",
        "destination_city",
        "destination_state",
        "destination_postal_code",
        "destination_country_code",
    } <= names
    assert "destination_snapshot" not in names


def test_measurements_are_fixed_precision():
    from app.models.package_custody import HubPackageVersion

    for name in ("weight_kg", "length_cm", "width_cm", "height_cm"):
        column = HubPackageVersion.__table__.c[name]
        assert (column.type.precision, column.type.scale) == (10, 3)


def test_approved_aggregate_identity_and_evidence_contract():
    from app.models.package_custody import CustodyEvent, CustodyStream, HubPackageItem

    identity = {"cohort_id", "order_id", "vendor_id", "hub_id"}
    assert identity <= set(CustodyStream.__table__.c.keys())
    event_names = set(CustodyEvent.__table__.c.keys())
    assert (
        identity
        | {
            "actor_type",
            "actor_id",
            "source_system",
            "recorded_at",
            "location",
            "counterparty",
            "evidence_ref",
            "evidence_hash",
            "package_id",
            "package_version",
            "seal_id",
        }
        <= event_names
    )
    assert "evidence" not in event_names
    assert not CustodyEvent.__table__.c.location.nullable
    assert "correction_reason" in event_names
    allocation_fk = next(
        fk
        for fk in HubPackageItem.__table__.foreign_key_constraints
        if fk.referred_table.name == "cohort_item_allocations"
    )
    assert [c.name for c in allocation_fk.columns] == [
        "cohort_id",
        "order_item_id",
        "order_id",
        "vendor_id",
    ]


def test_active_partial_indexes_and_model_ddl_hooks_are_installed():
    from app.models.package_custody import (
        HubPackageSeal,
        OutboundShipmentIntent,
        OutboundShipmentIntentInvalidation,
    )

    seal_indexes = {index.name: index for index in HubPackageSeal.__table__.indexes}
    intent_indexes = {
        index.name: index for index in OutboundShipmentIntent.__table__.indexes
    }
    assert isinstance(seal_indexes["uq_hub_package_seals_active"], Index)
    assert (
        str(
            seal_indexes["uq_hub_package_seals_active"].dialect_options["postgresql"][
                "where"
            ]
        )
        == "retired_at IS NULL"
    )
    assert "uq_outbound_shipment_intents_active" in intent_indexes
    assert OutboundShipmentIntentInvalidation.__table__.dispatch.after_create


@pytest.mark.asyncio
async def test_model_created_postgresql_schema_installs_package_custody_triggers(
    db_session,
):
    functions = set(
        (
            await db_session.execute(
                text("SELECT proname FROM pg_proc WHERE proname = ANY(:names)"),
                {
                    "names": [
                        "validate_hub_package_write",
                        "validate_hub_package_version_insert",
                        "reject_package_immutable_mutation",
                        "validate_hub_package_item_insert",
                        "validate_hub_package_seal_insert",
                        "validate_hub_package_seal_mutation",
                        "validate_custody_stream_mutation",
                        "validate_custody_event_insert",
                        "validate_outbound_intent_insert",
                        "validate_outbound_intent_invalidation_insert",
                    ]
                },
            )
        ).scalars()
    )
    assert len(functions) == 10
    triggers = set(
        (
            await db_session.execute(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE NOT tgisinternal AND tgname LIKE ANY(:patterns)"
                ),
                {"patterns": ["tr_hub_package%", "tr_custody%", "tr_outbound%"]},
            )
        ).scalars()
    )
    assert {
        "tr_hub_packages_write",
        "tr_hub_package_versions_insert",
        "tr_hub_package_items_insert",
        "tr_hub_package_seals_insert",
        "tr_custody_events_insert",
        "tr_outbound_shipment_intents_insert",
    } <= triggers


async def _passed_graph(db_session, vendor_user, customer_user, *, quantity=3):
    from app.models import EvidencePurpose, QCDecision, QuarantineDisposition

    graph = await _HUB._graph(db_session, vendor_user, customer_user, quantity=quantity)
    receipt = _HUB._receipt(graph)
    db_session.add(receipt)
    await db_session.flush()
    receipt_item = _HUB._receipt_item(graph, receipt)
    db_session.add(receipt_item)
    await db_session.flush()
    await _HUB._complete_receipt(db_session, receipt)
    qc = await _HUB._start_qc(db_session, graph, receipt)
    inspection = _HUB._inspection(
        graph,
        receipt,
        receipt_item,
        qc,
        decision=QCDecision.PASS,
        inspected_quantity=quantity,
        reason_code=None,
        quarantine_disposition=QuarantineDisposition.NOT_APPLICABLE,
    )
    db_session.add(inspection)
    await db_session.flush()
    await _HUB._attach_evidence(
        db_session,
        graph,
        receipt,
        EvidencePurpose.QC_INSPECTION,
        inspection_id=inspection.id,
    )
    completed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.execute(
        text(
            "UPDATE hub_qc_sessions SET state='qc_passed', completed_at=:at "
            "WHERE id=:id"
        ),
        {"id": qc.id, "at": completed_at},
    )
    return graph


async def _packing_package(db_session, graph, *, quantity=1, add_item=True):
    from app.models.package_custody import (
        HubPackage,
        HubPackageItem,
        HubPackageVersion,
    )

    aggregate = HubPackage(
        order_id=graph["order"].id,
        hub_id=graph["hub"].id,
        source_command="pack_order",
        idempotency_key=f"pack-{uuid.uuid4().hex}",
        created_by_id=graph["operator_id"],
    )
    db_session.add(aggregate)
    await db_session.flush()
    packed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    version = HubPackageVersion(
        package_id=aggregate.id,
        version=1,
        order_id=graph["order"].id,
        hub_id=graph["hub"].id,
        weight_kg="1.250",
        length_cm="20.000",
        width_cm="15.000",
        height_cm="10.000",
        packed_by_id=graph["operator_id"],
        packed_at=packed_at,
    )
    db_session.add(version)
    await db_session.flush()
    item = None
    if add_item:
        item = HubPackageItem(
            package_id=aggregate.id,
            package_version=1,
            order_id=graph["order"].id,
            hub_id=graph["hub"].id,
            cohort_id=graph["cohort"].id,
            vendor_id=graph["vendor_id"],
            order_item_id=graph["item"].id,
            quantity=quantity,
        )
        db_session.add(item)
        await db_session.flush()
    return aggregate, version, item


async def _ready_package(db_session, graph, *, quantity=1):
    from app.models.package_custody import HubPackageSeal

    aggregate, version, item = await _packing_package(
        db_session, graph, quantity=quantity
    )
    applied_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    seal = HubPackageSeal(
        package_id=aggregate.id,
        package_version=1,
        opaque_value=f"seal-{uuid.uuid4().hex}",
        applied_by_id=graph["operator_id"],
        applied_at=applied_at,
    )
    db_session.add(seal)
    await db_session.flush()
    sealed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.execute(
        text(
            "UPDATE hub_packages SET state='sealed', sealed_at=:at, row_version=2 "
            "WHERE id=:id"
        ),
        {"id": aggregate.id, "at": sealed_at},
    )
    ready_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.execute(
        text(
            "UPDATE hub_packages SET state='ready', ready_at=:at, row_version=3 "
            "WHERE id=:id"
        ),
        {"id": aggregate.id, "at": ready_at},
    )
    return aggregate, version, item, seal


@pytest.mark.asyncio
async def test_package_lifecycle_caps_terminal_passed_quantity_and_freezes_truth(
    db_session, vendor_user, customer_user
):
    from app.models.package_custody import HubPackageItem

    graph = await _passed_graph(db_session, vendor_user, customer_user, quantity=2)
    aggregate, version, item = await _packing_package(db_session, graph, quantity=2)
    await _HUB._rejects(
        db_session,
        HubPackageItem(
            package_id=aggregate.id,
            package_version=1,
            order_id=graph["order"].id,
            hub_id=graph["hub"].id,
            cohort_id=graph["cohort"].id,
            vendor_id=graph["vendor_id"],
            order_item_id=graph["item"].id,
            quantity=1,
        ),
        match="quantity exceeds terminal passed",
    )
    await _HUB._rejects(
        db_session,
        statement="UPDATE hub_package_items SET quantity=1 WHERE id=:id",
        params={"id": item.id},
        match="immutable audit",
    )
    await _HUB._rejects(
        db_session,
        statement=(
            "UPDATE hub_package_versions SET weight_kg=2 WHERE package_id=:id "
            "AND version=1"
        ),
        params={"id": aggregate.id},
        match="immutable audit",
    )


@pytest.mark.asyncio
async def test_package_rejects_advanced_creation_future_clock_and_empty_sealing(
    db_session, vendor_user, customer_user
):
    from datetime import timedelta
    from app.models.package_custody import HubPackage, HubPackageVersion

    graph = await _passed_graph(db_session, vendor_user, customer_user)
    await _HUB._rejects(
        db_session,
        HubPackage(
            order_id=graph["order"].id,
            hub_id=graph["hub"].id,
            state="sealed",
            sealed_at=await db_session.scalar(text("SELECT clock_timestamp()")),
            source_command="pack_order",
            idempotency_key=f"pack-{uuid.uuid4().hex}",
            created_by_id=graph["operator_id"],
        ),
        match="must start packing",
    )
    aggregate = HubPackage(
        order_id=graph["order"].id,
        hub_id=graph["hub"].id,
        source_command="pack_order",
        idempotency_key=f"pack-{uuid.uuid4().hex}",
        created_by_id=graph["operator_id"],
    )
    db_session.add(aggregate)
    await db_session.flush()
    future = await db_session.scalar(text("SELECT clock_timestamp()")) + timedelta(
        days=1
    )
    await _HUB._rejects(
        db_session,
        HubPackageVersion(
            package_id=aggregate.id,
            version=1,
            order_id=graph["order"].id,
            hub_id=graph["hub"].id,
            weight_kg="1",
            length_cm="1",
            width_cm="1",
            height_cm="1",
            packed_by_id=graph["operator_id"],
            packed_at=future,
        ),
        match="timestamps violate subject chronology",
    )


@pytest.mark.asyncio
async def test_item_and_custody_stream_creation_cannot_be_future_dated(
    db_session, vendor_user, customer_user
):
    from datetime import timedelta
    from app.models.package_custody import CustodyStream, HubPackageItem

    graph = await _passed_graph(db_session, vendor_user, customer_user)
    aggregate, _version, _item = await _packing_package(
        db_session, graph, add_item=False
    )
    future = await db_session.scalar(text("SELECT clock_timestamp()")) + timedelta(
        days=1
    )
    await _HUB._rejects(
        db_session,
        HubPackageItem(
            package_id=aggregate.id,
            package_version=1,
            order_id=graph["order"].id,
            hub_id=graph["hub"].id,
            cohort_id=graph["cohort"].id,
            vendor_id=graph["vendor_id"],
            order_item_id=graph["item"].id,
            quantity=1,
            created_at=future,
        ),
        match="package item chronology",
    )
    await _HUB._rejects(
        db_session,
        CustodyStream(
            cohort_id=graph["cohort"].id,
            order_id=graph["order"].id,
            vendor_id=graph["vendor_id"],
            hub_id=graph["hub"].id,
            created_at=future,
        ),
        match="custody stream cannot be future-dated",
    )


@pytest.mark.asyncio
async def test_seal_intent_invalidation_and_repack_are_ordered_and_immutable(
    db_session, vendor_user, customer_user
):
    from app.models.package_custody import (
        OutboundShipmentIntent,
        OutboundShipmentIntentInvalidation,
    )

    graph = await _passed_graph(db_session, vendor_user, customer_user)
    aggregate, _version, _item, seal = await _ready_package(db_session, graph)
    intent = OutboundShipmentIntent(
        package_id=aggregate.id,
        package_version=1,
        seal_id=seal.id,
        order_id=graph["order"].id,
        origin_hub_id=graph["hub"].id,
        destination_name="Customer",
        destination_phone="+2348000000000",
        destination_address_line1="1 Destination Road",
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
    retirement_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await _HUB._rejects(
        db_session,
        statement=(
            "UPDATE hub_package_seals SET retired_at=:at, retired_by_id=:actor, "
            "retirement_reason='repack' WHERE id=:id"
        ),
        params={"id": seal.id, "at": retirement_at, "actor": graph["operator_id"]},
        match="must be invalidated",
    )
    await _HUB._rejects(
        db_session,
        statement="UPDATE outbound_shipment_intents SET destination_city='Abuja' WHERE id=:id",
        params={"id": intent.id},
        match="immutable audit",
    )
    invalidated_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    invalidation = OutboundShipmentIntentInvalidation(
        intent_id=intent.id,
        reason="authorized repack",
        actor_type="user",
        actor_id=str(graph["operator_id"]),
        source_command="invalidate_outbound_intent",
        idempotency_key=f"invalidate-{uuid.uuid4().hex}",
        invalidated_at=invalidated_at,
    )
    db_session.add(invalidation)
    await db_session.flush()
    await _HUB._rejects(
        db_session,
        statement=(
            "UPDATE hub_package_seals SET retired_at=applied_at, "
            "retired_by_id=:actor, retirement_reason='reverse dated' WHERE id=:id"
        ),
        params={"id": seal.id, "actor": graph["operator_id"]},
        match="seal retirement must follow outbound intent invalidation",
    )
    retirement_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.execute(
        text(
            "UPDATE hub_package_seals SET retired_at=:at, retired_by_id=:actor, "
            "retirement_reason='authorized repack' WHERE id=:id"
        ),
        {"id": seal.id, "at": retirement_at, "actor": graph["operator_id"]},
    )
    await db_session.execute(
        text(
            "UPDATE hub_packages SET state='packing', current_version=2, "
            "sealed_at=NULL, ready_at=NULL, row_version=4 WHERE id=:id"
        ),
        {"id": aggregate.id},
    )


@pytest.mark.asyncio
async def test_custody_events_form_immutable_exact_private_chain(
    db_session, vendor_user, customer_user
):
    from app.models.package_custody import CustodyEvent, CustodyStream

    graph = await _passed_graph(db_session, vendor_user, customer_user)
    aggregate, _version, _item, seal = await _ready_package(db_session, graph)
    stream = CustodyStream(
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
    )
    db_session.add(stream)
    await db_session.flush()
    occurred_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    first = CustodyEvent(
        stream_id=stream.id,
        version=1,
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        event_type="packed",
        actor_type="user",
        actor_id=str(graph["operator_id"]),
        source_system="shopsoma_hub",
        source_command="record_custody",
        idempotency_key=f"custody-{uuid.uuid4().hex}",
        occurred_at=occurred_at,
        location="Lagos Hub",
        evidence_ref="private/custody/proof.jpg",
        evidence_hash="a" * 64,
        package_id=aggregate.id,
        package_version=1,
    )
    db_session.add(first)
    await db_session.flush()
    await _HUB._rejects(
        db_session,
        CustodyEvent(
            stream_id=stream.id,
            version=2,
            previous_event_id=uuid.uuid4(),
            cohort_id=graph["cohort"].id,
            order_id=graph["order"].id,
            vendor_id=graph["vendor_id"],
            hub_id=graph["hub"].id,
            event_type="staged",
            actor_type="user",
            actor_id=str(graph["operator_id"]),
            source_system="shopsoma_hub",
            source_command="record_custody",
            idempotency_key=f"custody-{uuid.uuid4().hex}",
            occurred_at=await db_session.scalar(text("SELECT clock_timestamp()")),
            location="Lagos Hub",
            package_id=aggregate.id,
            package_version=1,
            seal_id=seal.id,
        ),
        match="custody chain fork",
    )
    await _HUB._rejects(
        db_session,
        statement="DELETE FROM custody_events WHERE id=:id",
        params={"id": first.id},
        match="immutable audit",
    )


@pytest.mark.asyncio
async def test_concurrent_package_writers_cannot_overpack_passed_quantity(
    db_session, vendor_user, customer_user
):
    from app.models.package_custody import (
        HubPackage,
        HubPackageItem,
        HubPackageVersion,
    )

    graph = await _passed_graph(db_session, vendor_user, customer_user, quantity=3)
    packages = []
    for position in range(2):
        aggregate = HubPackage(
            order_id=graph["order"].id,
            hub_id=graph["hub"].id,
            source_command="pack_order",
            idempotency_key=f"race-pack-{position}-{uuid.uuid4().hex}",
            created_by_id=graph["operator_id"],
        )
        db_session.add(aggregate)
        await db_session.flush()
        packed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
        db_session.add(
            HubPackageVersion(
                package_id=aggregate.id,
                version=1,
                order_id=graph["order"].id,
                hub_id=graph["hub"].id,
                weight_kg="1",
                length_cm="1",
                width_cm="1",
                height_cm="1",
                packed_by_id=graph["operator_id"],
                packed_at=packed_at,
            )
        )
        await db_session.flush()
        packages.append(aggregate.id)
    await db_session.commit()

    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def insert_quantity(package_id):
        async with sessions() as session:
            try:
                session.add(
                    HubPackageItem(
                        package_id=package_id,
                        package_version=1,
                        order_id=graph["order"].id,
                        hub_id=graph["hub"].id,
                        cohort_id=graph["cohort"].id,
                        vendor_id=graph["vendor_id"],
                        order_item_id=graph["item"].id,
                        quantity=2,
                    )
                )
                await session.commit()
                return "committed"
            except IntegrityError as error:
                await session.rollback()
                assert "quantity exceeds terminal passed" in str(error)
                return "rejected"

    results = await asyncio.wait_for(
        asyncio.gather(*(insert_quantity(package_id) for package_id in packages)),
        timeout=15,
    )
    assert sorted(results) == ["committed", "rejected"]
    total = await db_session.scalar(
        text(
            "SELECT COALESCE(sum(quantity),0) FROM hub_package_items "
            "WHERE order_item_id=:item"
        ),
        {"item": graph["item"].id},
    )
    assert total == 2


@pytest.mark.asyncio
async def test_concurrent_custody_writers_cannot_fork_chain(
    db_session, vendor_user, customer_user
):
    from app.models.package_custody import CustodyEvent, CustodyStream

    graph = await _passed_graph(db_session, vendor_user, customer_user)
    aggregate, _version, _item, seal = await _ready_package(db_session, graph)
    stream = CustodyStream(
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
    )
    db_session.add(stream)
    await db_session.flush()
    first = CustodyEvent(
        stream_id=stream.id,
        version=1,
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        event_type="packed",
        actor_type="user",
        actor_id=str(graph["operator_id"]),
        source_system="shopsoma_hub",
        source_command="record_custody",
        idempotency_key=f"custody-{uuid.uuid4().hex}",
        occurred_at=await db_session.scalar(text("SELECT clock_timestamp()")),
        location="Lagos Hub",
        package_id=aggregate.id,
        package_version=1,
    )
    db_session.add(first)
    await db_session.flush()
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def append(position):
        async with sessions() as session:
            try:
                session.add(
                    CustodyEvent(
                        stream_id=stream.id,
                        version=2,
                        previous_event_id=first.id,
                        cohort_id=graph["cohort"].id,
                        order_id=graph["order"].id,
                        vendor_id=graph["vendor_id"],
                        hub_id=graph["hub"].id,
                        event_type="sealed",
                        actor_type="user",
                        actor_id=str(graph["operator_id"]),
                        source_system="shopsoma_hub",
                        source_command="record_custody",
                        idempotency_key=f"fork-{position}-{uuid.uuid4().hex}",
                        occurred_at=await session.scalar(
                            text("SELECT clock_timestamp()")
                        ),
                        location="Lagos Hub",
                        package_id=aggregate.id,
                        package_version=1,
                        seal_id=seal.id,
                    )
                )
                await session.commit()
                return "committed"
            except IntegrityError as error:
                await session.rollback()
                assert "custody chain fork" in str(error)
                return "rejected"

    results = await asyncio.wait_for(asyncio.gather(append(1), append(2)), timeout=15)
    assert sorted(results) == ["committed", "rejected"]
    versions = list(
        (
            await db_session.execute(
                text(
                    "SELECT version FROM custody_events WHERE stream_id=:stream "
                    "ORDER BY version"
                ),
                {"stream": stream.id},
            )
        ).scalars()
    )
    assert versions == [1, 2]


@pytest.mark.asyncio
async def test_intent_creation_and_seal_retirement_share_deadlock_free_lock_order(
    db_session, vendor_user, customer_user
):
    from app.models.package_custody import OutboundShipmentIntent

    graph = await _passed_graph(db_session, vendor_user, customer_user)
    aggregate, _version, _item, seal = await _ready_package(db_session, graph)
    await db_session.commit()
    sessions = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def create_intent():
        async with sessions() as session:
            try:
                session.add(
                    OutboundShipmentIntent(
                        package_id=aggregate.id,
                        package_version=1,
                        seal_id=seal.id,
                        order_id=graph["order"].id,
                        origin_hub_id=graph["hub"].id,
                        destination_name="Customer",
                        destination_phone="+2348000000000",
                        destination_address_line1="1 Destination Road",
                        destination_city="Lagos",
                        destination_state="Lagos",
                        destination_postal_code="100001",
                        destination_country_code="NG",
                        source_command="prepare_outbound",
                        idempotency_key=f"race-intent-{uuid.uuid4().hex}",
                        created_by_id=graph["operator_id"],
                    )
                )
                await session.commit()
                return "intent-committed"
            except IntegrityError as error:
                await session.rollback()
                assert "requires exact current ready package" in str(error)
                return "intent-rejected"

    async def retire_seal():
        async with sessions() as session:
            try:
                retired_at = await session.scalar(text("SELECT clock_timestamp()"))
                await session.execute(
                    text(
                        "UPDATE hub_package_seals SET retired_at=:at, "
                        "retired_by_id=:actor, retirement_reason='authorized correction' "
                        "WHERE id=:id"
                    ),
                    {
                        "id": seal.id,
                        "at": retired_at,
                        "actor": graph["operator_id"],
                    },
                )
                await session.commit()
                return "seal-committed"
            except IntegrityError as error:
                await session.rollback()
                assert "active outbound intent must be invalidated" in str(
                    error
                ) or "terminal package requires exactly one active current seal" in str(
                    error
                )
                return "seal-rejected"

    results = await asyncio.wait_for(
        asyncio.gather(create_intent(), retire_seal()), timeout=15
    )
    assert sum(result.endswith("committed") for result in results) == 1
    intent_count = await db_session.scalar(
        text("SELECT count(*) FROM outbound_shipment_intents WHERE package_id=:id"),
        {"id": aggregate.id},
    )
    seal_retired = await db_session.scalar(
        text("SELECT retired_at IS NOT NULL FROM hub_package_seals WHERE id=:id"),
        {"id": seal.id},
    )
    assert (intent_count, seal_retired) == (1, False)


@pytest.mark.asyncio
async def test_sealing_must_follow_qc_version_item_and_seal_clocks(
    db_session, vendor_user, customer_user
):
    from datetime import timedelta
    from app.models.package_custody import HubPackageSeal

    graph = await _passed_graph(db_session, vendor_user, customer_user)
    aggregate, version, _item = await _packing_package(db_session, graph)
    applied_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    seal = HubPackageSeal(
        package_id=aggregate.id,
        package_version=1,
        opaque_value=f"seal-{uuid.uuid4().hex}",
        applied_by_id=graph["operator_id"],
        applied_at=applied_at,
    )
    db_session.add(seal)
    await db_session.flush()
    await _HUB._rejects(
        db_session,
        statement=(
            "UPDATE hub_packages SET state='sealed', sealed_at=:at, row_version=2 "
            "WHERE id=:id"
        ),
        params={
            "id": aggregate.id,
            "at": version.packed_at + timedelta(microseconds=1),
        },
        match="sealing must follow package version, composition, and seal",
    )


@pytest.mark.asyncio
async def test_custody_rejects_direct_terminal_lifecycle_and_seal_interval_violation(
    db_session, vendor_user, customer_user
):
    from datetime import timedelta
    from app.models.package_custody import CustodyEvent, CustodyStream

    graph = await _passed_graph(db_session, vendor_user, customer_user)
    aggregate, version, _item, seal = await _ready_package(db_session, graph)
    stream = CustodyStream(
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
    )
    db_session.add(stream)
    await db_session.flush()
    await _HUB._rejects(
        db_session,
        CustodyEvent(
            stream_id=stream.id,
            version=1,
            cohort_id=graph["cohort"].id,
            order_id=graph["order"].id,
            vendor_id=graph["vendor_id"],
            hub_id=graph["hub"].id,
            event_type="provider_accepted",
            actor_type="carrier",
            actor_id="carrier-1",
            source_system="carrier_feed",
            source_command="accept",
            idempotency_key=f"terminal-{uuid.uuid4().hex}",
            occurred_at=await db_session.scalar(text("SELECT clock_timestamp()")),
            location="Lagos Hub",
            package_id=aggregate.id,
            package_version=1,
            seal_id=seal.id,
        ),
        match="illegal custody lifecycle transition",
    )
    first = CustodyEvent(
        stream_id=stream.id,
        version=1,
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        event_type="packed",
        actor_type="user",
        actor_id=str(graph["operator_id"]),
        source_system="shopsoma_hub",
        source_command="record_custody",
        idempotency_key=f"packed-{uuid.uuid4().hex}",
        occurred_at=version.packed_at,
        location="Lagos Hub",
        package_id=aggregate.id,
        package_version=1,
    )
    db_session.add(first)
    await db_session.flush()
    await _HUB._rejects(
        db_session,
        CustodyEvent(
            stream_id=stream.id,
            version=2,
            previous_event_id=first.id,
            cohort_id=graph["cohort"].id,
            order_id=graph["order"].id,
            vendor_id=graph["vendor_id"],
            hub_id=graph["hub"].id,
            event_type="sealed",
            actor_type="user",
            actor_id=str(graph["operator_id"]),
            source_system="shopsoma_hub",
            source_command="record_custody",
            idempotency_key=f"sealed-{uuid.uuid4().hex}",
            occurred_at=seal.applied_at - timedelta(microseconds=1),
            location="Lagos Hub",
            package_id=aggregate.id,
            package_version=1,
            seal_id=seal.id,
        ),
        match="custody seal interval is invalid",
    )


@pytest.mark.asyncio
async def test_terminal_package_cannot_commit_without_active_current_seal(
    db_session, vendor_user, customer_user
):
    graph = await _passed_graph(db_session, vendor_user, customer_user)
    _aggregate, _version, _item, seal = await _ready_package(db_session, graph)
    retired_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    with pytest.raises(
        IntegrityError,
        match="terminal package requires exactly one active current seal",
    ):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    "UPDATE hub_package_seals SET retired_at=:at, retired_by_id=:actor, "
                    "retirement_reason='invalid standalone retirement' WHERE id=:id"
                ),
                {"id": seal.id, "at": retired_at, "actor": graph["operator_id"]},
            )
            await db_session.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
