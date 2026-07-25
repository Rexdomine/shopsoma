"""Adversarial PostgreSQL contracts for Lane 2A-3C hub quality persistence."""

import asyncio
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import uuid

import pytest
import app.models as models
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from app.models import (
    CohortItemAllocation,
    DiscrepancyType,
    EvidencePurpose,
    FulfillmentCohort,
    FulfillmentReadinessType,
    HubDiscrepancy,
    HubEvidence,
    HubQCInspection,
    HubQCSession,
    HubReceiptItem,
    HubReceiptSession,
    HubRemediation,
    InboundTransfer,
    InboundTransferItemAllocation,
    QCDecision,
    QuarantineDisposition,
    RemediationAction,
    RemediationState,
)
from app.models.fulfillment_hub import FulfillmentHub
from app.models.order import Order, OrderItem
from app.models.product import Product


NOW = datetime.now(timezone.utc)


async def _rejects(session, instance=None, statement=None, params=None, match=None):
    with pytest.raises(IntegrityError, match=match):
        async with session.begin_nested():
            if instance is not None:
                session.add(instance)
                await session.flush()
            else:
                await session.execute(text(statement), params or {})


async def _graph(db_session, vendor_user, customer_user, *, quantity=3):
    vendor_id = vendor_user["vendor"].id
    operator_id = vendor_user["user"].id
    order = Order(
        order_number=f"HUB-{uuid.uuid4().hex[:12]}",
        customer_id=customer_user["user"].id,
        subtotal=Decimal("30"),
        total_amount=Decimal("30"),
    )
    product = Product(vendor_id=vendor_id, title="Hub item", base_price=Decimal("10"))
    hub = FulfillmentHub(
        code=f"hub-{uuid.uuid4().hex[:10]}",
        name="Quality Hub",
        contact_name="Operator",
        contact_phone="+234****0000",
        address_line1="1 Test Street",
        city="Lagos",
        state="Lagos",
        cutoff_time=time(14),
    )
    db_session.add_all([order, product, hub])
    await db_session.flush()
    item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor_id,
        product_title="Hub item",
        unit_price=Decimal("10"),
        quantity=quantity,
        subtotal=Decimal(10 * quantity),
        commission_rate=Decimal("10"),
        commission_amount=Decimal("3"),
        vendor_payout=Decimal("27"),
    )
    cohort = FulfillmentCohort(
        order_id=order.id,
        vendor_id=vendor_id,
        readiness_type=FulfillmentReadinessType.READY_TO_WEAR,
        ready_from=NOW,
        ready_through=NOW + timedelta(days=2),
    )
    db_session.add_all([item, cohort])
    await db_session.flush()
    allocation = CohortItemAllocation(
        cohort_id=cohort.id,
        order_item_id=item.id,
        order_id=order.id,
        vendor_id=vendor_id,
        allocated_quantity=quantity,
    )
    transfer = InboundTransfer(
        cohort_id=cohort.id,
        order_id=order.id,
        vendor_id=vendor_id,
        target_hub_id=hub.id,
        provider_name="Independent Provider",
        provider_reference=f"REF-{uuid.uuid4().hex[:12]}",
    )
    db_session.add_all([allocation, transfer])
    await db_session.flush()
    transfer_item = InboundTransferItemAllocation(
        transfer_id=transfer.id,
        order_item_id=item.id,
        cohort_id=cohort.id,
        order_id=order.id,
        vendor_id=vendor_id,
        allocated_quantity=quantity,
    )
    db_session.add(transfer_item)
    await db_session.flush()
    return {
        "order": order,
        "item": item,
        "hub": hub,
        "cohort": cohort,
        "transfer": transfer,
        "operator_id": operator_id,
        "vendor_id": vendor_id,
        "quantity": quantity,
    }


def _receipt(graph, **overrides):
    values = dict(
        id=uuid.uuid4(),
        inbound_transfer_id=graph["transfer"].id,
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        operator_id=graph["operator_id"],
        idempotency_key=f"receipt-{uuid.uuid4().hex}",
        started_at=NOW,
    )
    values.update(overrides)
    return HubReceiptSession(**values)


def _receipt_item(graph, receipt, **overrides):
    values = dict(
        id=uuid.uuid4(),
        receipt_session_id=receipt.id,
        inbound_transfer_id=graph["transfer"].id,
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        order_item_id=graph["item"].id,
        expected_quantity=graph["quantity"],
        received_quantity=graph["quantity"],
        scan_identity=f"scan-{uuid.uuid4().hex}",
    )
    values.update(overrides)
    return HubReceiptItem(**values)


def _qc(graph, receipt, **overrides):
    values = dict(
        id=uuid.uuid4(),
        receipt_session_id=receipt.id,
        inbound_transfer_id=graph["transfer"].id,
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        operator_id=graph["operator_id"],
        sequence=1,
        state="qc_in_progress",
        started_at=NOW,
    )
    values.update(overrides)
    return HubQCSession(**values)


def _inspection(graph, receipt, receipt_item, qc, **overrides):
    values = dict(
        id=uuid.uuid4(),
        qc_session_id=qc.id,
        receipt_session_id=receipt.id,
        inbound_transfer_id=graph["transfer"].id,
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        receipt_item_id=receipt_item.id,
        order_item_id=graph["item"].id,
        decision=QCDecision.FAIL,
        inspected_quantity=1,
        reason_code="damage",
        quarantine_disposition=QuarantineDisposition.QUARANTINED,
    )
    values.update(overrides)
    return HubQCInspection(**values)


def _discrepancy(graph, receipt, receipt_item, kind, **overrides):
    values = dict(
        id=uuid.uuid4(),
        receipt_session_id=receipt.id,
        receipt_item_id=receipt_item.id,
        inbound_transfer_id=graph["transfer"].id,
        cohort_id=graph["cohort"].id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        order_item_id=graph["item"].id,
        type=kind,
        quantity=1,
        observed_item_identity=(
            "sku-observed" if kind is DiscrepancyType.WRONG_ITEM else None
        ),
        quarantine_disposition=(
            QuarantineDisposition.NOT_APPLICABLE
            if kind is DiscrepancyType.SHORTAGE
            else QuarantineDisposition.QUARANTINED
        ),
        recorded_by_id=graph["operator_id"],
    )
    values.update(overrides)
    return HubDiscrepancy(**values)


def _remediation(graph, receipt, qc, inspection, **overrides):
    values = dict(
        id=uuid.uuid4(),
        failed_inspection_id=inspection.id,
        qc_session_id=qc.id,
        receipt_session_id=receipt.id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        owner_id=graph["operator_id"],
        action=RemediationAction.REWORK,
        state=RemediationState.PENDING_APPROVAL,
        disposition=QuarantineDisposition.REWORK,
    )
    values.update(overrides)
    return HubRemediation(**values)


def _evidence(graph, receipt, purpose, **overrides):
    values = dict(
        receipt_session_id=receipt.id,
        order_id=graph["order"].id,
        vendor_id=graph["vendor_id"],
        hub_id=graph["hub"].id,
        purpose=purpose,
        access_scope="hub_quality_private",
        storage_reference=f"private/hub/{uuid.uuid4().hex}",
        integrity_hash="a" * 64,
        content_type="image/jpeg",
        byte_size=42,
        retention_until=NOW + timedelta(days=30),
        created_by_id=graph["operator_id"],
    )
    values.update(overrides)
    return HubEvidence(**values)


@pytest.mark.asyncio
async def test_receipt_idempotency_and_transfer_aggregate_binding(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    other = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph, idempotency_key="canonical-key")
    db_session.add(receipt)
    await db_session.flush()
    await _rejects(
        db_session,
        _receipt(graph, idempotency_key="canonical-key"),
        match="uq_hub_receipt_sessions_idempotency",
    )
    await _rejects(
        db_session,
        _receipt(graph, idempotency_key=" canonical-key"),
        match="idempotency_canonical",
    )
    for overrides in (
        {"order_id": other["order"].id},
        {"vendor_id": uuid.uuid4()},
        {"hub_id": other["hub"].id},
        {"cohort_id": other["cohort"].id},
        {"inbound_transfer_id": other["transfer"].id},
    ):
        await _rejects(
            db_session, _receipt(graph, **overrides), match="transfer_hub_identity"
        )


@pytest.mark.asyncio
async def test_receipt_item_allocation_quantity_identity_and_scan_invariants(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    db_session.add(receipt)
    await db_session.flush()
    for overrides, match in (
        ({"expected_quantity": graph["quantity"] - 1}, "expected quantity"),
        ({"received_quantity": -1}, "received_nonnegative"),
        ({"scan_identity": " scan"}, "scan_canonical"),
        ({"order_item_id": uuid.uuid4()}, "expected quantity"),
    ):
        await _rejects(
            db_session, _receipt_item(graph, receipt, **overrides), match=match
        )
    item = _receipt_item(
        graph, receipt, received_quantity=1, scan_identity="scan-canonical"
    )
    db_session.add(item)
    await db_session.flush()
    await _rejects(
        db_session,
        statement="UPDATE hub_receipt_items SET scan_identity='scan-renamed' WHERE id=:id",
        params={"id": item.id},
        match="aggregate identity is immutable",
    )
    receipt.completed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.flush()
    await _rejects(
        db_session,
        statement="UPDATE hub_receipt_items SET received_quantity=2 WHERE id=:id",
        params={"id": item.id},
        match="immutable",
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_receipt_sessions SET completed_at=NULL WHERE id=:id",
        params={"id": receipt.id},
        match="immutable",
    )
    await _rejects(
        db_session,
        _receipt_item(
            graph, receipt, received_quantity=1, scan_identity="scan-canonical"
        ),
        match="immutable",
    )
    second_receipt = _receipt(graph, idempotency_key="second-session")
    db_session.add(second_receipt)
    await db_session.flush()
    await _rejects(
        db_session,
        statement="UPDATE hub_receipt_items SET receipt_session_id=:target WHERE id=:id",
        params={"id": item.id, "target": second_receipt.id},
        match="aggregate identity is immutable",
    )
    second_item = _receipt_item(
        graph, second_receipt, received_quantity=2, scan_identity="scan-second"
    )
    db_session.add(second_item)
    await db_session.flush()
    assert item.received_quantity + second_item.received_quantity == graph["quantity"]
    third_receipt = _receipt(graph, idempotency_key="third-session")
    db_session.add(third_receipt)
    await db_session.flush()
    await _rejects(
        db_session,
        _receipt_item(
            graph, third_receipt, received_quantity=1, scan_identity="scan-third"
        ),
        match="cumulative received quantity",
    )
    await _rejects(
        db_session,
        _receipt_item(
            graph, third_receipt, received_quantity=0, scan_identity="scan-canonical"
        ),
        match="hub_receipt_items",
    )


@pytest.mark.asyncio
async def test_discrepancy_insert_rejects_completed_receipt(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    receipt.completed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.flush()
    await _rejects(
        db_session,
        _discrepancy(graph, receipt, item, DiscrepancyType.DAMAGE),
        match="completed receipt sessions are immutable",
    )


@pytest.mark.asyncio
async def test_discrepancy_types_semantics_and_composite_identity(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    other = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    for kind in DiscrepancyType:
        db_session.add(_discrepancy(graph, receipt, item, kind))
    await db_session.flush()
    invalid = (
        _discrepancy(graph, receipt, item, DiscrepancyType.DAMAGE, quantity=0),
        _discrepancy(
            graph,
            receipt,
            item,
            DiscrepancyType.SHORTAGE,
            quarantine_disposition=QuarantineDisposition.QUARANTINED,
        ),
        _discrepancy(
            graph,
            receipt,
            item,
            DiscrepancyType.EXCESS,
            quarantine_disposition=QuarantineDisposition.NOT_APPLICABLE,
        ),
        _discrepancy(
            graph,
            receipt,
            item,
            DiscrepancyType.WRONG_ITEM,
            observed_item_identity=None,
        ),
        _discrepancy(
            graph,
            receipt,
            item,
            DiscrepancyType.WRONG_ITEM,
            observed_item_identity=" sku",
        ),
        _discrepancy(
            graph, receipt, item, DiscrepancyType.DAMAGE, observed_item_identity="sku"
        ),
        _discrepancy(
            graph, receipt, item, DiscrepancyType.DAMAGE, order_id=other["order"].id
        ),
        _discrepancy(
            graph, receipt, item, DiscrepancyType.DAMAGE, receipt_item_id=uuid.uuid4()
        ),
    )
    for row in invalid:
        await _rejects(db_session, row)


@pytest.mark.asyncio
async def test_qc_inspection_quantity_decision_and_cross_aggregate_safety(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user, quantity=3)
    other = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt, received_quantity=2)
    qc = _qc(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()
    for overrides, match in (
        ({"inspected_quantity": 3}, "exceeds received"),
        ({"inspected_quantity": 0}, "quantity_positive"),
        ({"decision": QCDecision.FAIL, "reason_code": None}, "decision_semantics"),
        (
            {
                "decision": QCDecision.REJECTED,
                "quarantine_disposition": QuarantineDisposition.NOT_APPLICABLE,
            },
            "decision_semantics",
        ),
        (
            {
                "decision": QCDecision.PASS,
                "quarantine_disposition": QuarantineDisposition.QUARANTINED,
            },
            "decision_semantics",
        ),
        ({"order_id": other["order"].id}, "identity"),
        ({"receipt_item_id": uuid.uuid4()}, "exceeds received"),
    ):
        await _rejects(
            db_session, _inspection(graph, receipt, item, qc, **overrides), match=match
        )
    inspection = _inspection(graph, receipt, item, qc, inspected_quantity=2)
    db_session.add(inspection)
    await db_session.flush()
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_inspections SET qc_session_id=:target WHERE id=:id",
        params={"id": inspection.id, "target": uuid.uuid4()},
        match="aggregate identity is immutable",
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_inspections SET inspected_quantity = 3 WHERE id = :id",
        params={"id": inspection.id},
        match="exceeds received",
    )


@pytest.mark.asyncio
async def test_evidence_purpose_subject_privacy_retention_and_aggregate_binding(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    other = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    qc = _qc(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()
    inspection = _inspection(graph, receipt, item, qc)
    discrepancy = _discrepancy(graph, receipt, item, DiscrepancyType.DAMAGE)
    db_session.add_all([inspection, discrepancy])
    await db_session.flush()
    remediation = _remediation(graph, receipt, qc, inspection)
    db_session.add(remediation)
    await db_session.flush()
    subjects = {
        EvidencePurpose.HUB_RECEIPT: {},
        EvidencePurpose.DISCREPANCY: {"discrepancy_id": discrepancy.id},
        EvidencePurpose.QC_INSPECTION: {"inspection_id": inspection.id},
        EvidencePurpose.REMEDIATION: {"remediation_id": remediation.id},
    }
    for purpose, subject in subjects.items():
        db_session.add(_evidence(graph, receipt, purpose, **subject))
    await db_session.flush()
    invalid = (
        _evidence(
            graph, receipt, EvidencePurpose.HUB_RECEIPT, inspection_id=inspection.id
        ),
        _evidence(graph, receipt, EvidencePurpose.DISCREPANCY),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.DISCREPANCY,
            discrepancy_id=discrepancy.id,
            inspection_id=inspection.id,
        ),
        _evidence(
            graph, receipt, EvidencePurpose.QC_INSPECTION, discrepancy_id=discrepancy.id
        ),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.REMEDIATION,
            remediation_id=remediation.id,
            order_id=other["order"].id,
        ),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.HUB_RECEIPT,
            storage_reference="https://public.example/evidence",
        ),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.HUB_RECEIPT,
            storage_reference=" private/key",
        ),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.HUB_RECEIPT,
            storage_reference="//public.example/evidence",
        ),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.HUB_RECEIPT,
            storage_reference="private/hub/evidence?signature=public",
        ),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.HUB_RECEIPT,
            storage_reference="private/hub/evidence#public",
        ),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.HUB_RECEIPT,
            storage_reference="private/hub/../public",
        ),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.HUB_RECEIPT,
            storage_reference="private/hub//evidence",
        ),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.HUB_RECEIPT,
            storage_reference=r"private\hub\evidence",
        ),
        _evidence(graph, receipt, EvidencePurpose.HUB_RECEIPT, integrity_hash="A" * 64),
        _evidence(graph, receipt, EvidencePurpose.HUB_RECEIPT, integrity_hash="a" * 63),
        _evidence(graph, receipt, EvidencePurpose.HUB_RECEIPT, access_scope=" private"),
        _evidence(graph, receipt, EvidencePurpose.HUB_RECEIPT, access_scope="public"),
        _evidence(graph, receipt, EvidencePurpose.HUB_RECEIPT, byte_size=0),
        _evidence(
            graph,
            receipt,
            EvidencePurpose.HUB_RECEIPT,
            retention_until=NOW - timedelta(days=1),
        ),
    )
    for row in invalid:
        await _rejects(db_session, row)
    columns = set(HubEvidence.__table__.columns.keys())
    assert not columns.intersection(
        {"raw_data", "file_data", "public_url", "signed_url", "upload_url"}
    )


@pytest.mark.asyncio
async def test_receipt_and_qc_sessions_must_start_incomplete(
    db_session, vendor_user, customer_user
):
    receipt_graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(receipt_graph)
    receipt.completed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await _rejects(db_session, receipt, match="receipt sessions must start incomplete")

    qc_graph = await _graph(db_session, vendor_user, customer_user)
    qc_receipt = _receipt(qc_graph)
    db_session.add(qc_receipt)
    await db_session.flush()
    qc = _qc(qc_graph, qc_receipt)
    qc.completed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await _rejects(db_session, qc, match="QC sessions must start incomplete")


@pytest.mark.asyncio
async def test_receipt_and_qc_completion_timestamps_cannot_be_future_dated(
    db_session, vendor_user, customer_user
):
    receipt_graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(receipt_graph)
    receipt_item = _receipt_item(receipt_graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(receipt_item)
    await db_session.flush()
    future_clock = await db_session.scalar(
        text("SELECT clock_timestamp() + interval '1 day'")
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_receipt_sessions SET completed_at=:at WHERE id=:id",
        params={"id": receipt.id, "at": future_clock},
        match="receipt completion timestamp cannot be future-dated",
    )

    qc_graph = await _graph(db_session, vendor_user, customer_user)
    qc_receipt = _receipt(qc_graph)
    qc_item = _receipt_item(qc_graph, qc_receipt)
    qc = _qc(qc_graph, qc_receipt)
    db_session.add(qc_receipt)
    await db_session.flush()
    db_session.add(qc_item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()
    db_session.add(
        _inspection(
            qc_graph,
            qc_receipt,
            qc_item,
            qc,
            decision=QCDecision.PASS,
            reason_code=None,
            quarantine_disposition=QuarantineDisposition.NOT_APPLICABLE,
        )
    )
    await db_session.flush()
    qc_receipt.completed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.flush()
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_sessions SET state='qc_passed', completed_at=:at WHERE id=:id",
        params={"id": qc.id, "at": future_clock},
        match="QC completion timestamp cannot be future-dated",
    )


@pytest.mark.asyncio
async def test_receipt_quantity_cannot_drop_below_existing_inspection(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    qc = _qc(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()
    inspection = _inspection(graph, receipt, item, qc)
    db_session.add(inspection)
    await db_session.flush()

    await _rejects(
        db_session,
        statement="UPDATE hub_receipt_items SET received_quantity=:quantity WHERE id=:id",
        params={"id": item.id, "quantity": inspection.inspected_quantity - 1},
        match="below inspected quantity",
    )


@pytest.mark.asyncio
async def test_qc_completion_requires_terminal_outcome_matching_inspections(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    qc = _qc(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()

    await _rejects(
        db_session,
        statement="UPDATE hub_qc_sessions SET completed_at=clock_timestamp() WHERE id=:id",
        params={"id": qc.id},
        match="terminal state",
    )
    db_session.add(
        _inspection(
            graph,
            receipt,
            item,
            qc,
            decision=QCDecision.PASS,
            reason_code=None,
            quarantine_disposition=QuarantineDisposition.NOT_APPLICABLE,
        )
    )
    await db_session.flush()
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_sessions SET state='qc_passed', completed_at=clock_timestamp() WHERE id=:id",
        params={"id": qc.id},
        match="completed receipt session",
    )
    receipt.completed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.flush()
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_sessions SET state='qc_failed', completed_at=clock_timestamp() WHERE id=:id",
        params={"id": qc.id},
        match="failed or rejected inspection",
    )
    await db_session.execute(
        text(
            "UPDATE hub_qc_sessions SET state='qc_passed', completed_at=clock_timestamp() WHERE id=:id"
        ),
        {"id": qc.id},
    )

    failing_graph = await _graph(db_session, vendor_user, customer_user)
    failing_receipt = _receipt(failing_graph)
    failing_item = _receipt_item(failing_graph, failing_receipt)
    failing_qc = _qc(failing_graph, failing_receipt)
    db_session.add(failing_receipt)
    await db_session.flush()
    db_session.add(failing_item)
    await db_session.flush()
    db_session.add(failing_qc)
    await db_session.flush()
    db_session.add(
        _inspection(failing_graph, failing_receipt, failing_item, failing_qc)
    )
    await db_session.flush()
    failing_receipt.completed_at = await db_session.scalar(
        text("SELECT clock_timestamp()")
    )
    await db_session.flush()
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_sessions SET state='qc_passed', completed_at=clock_timestamp() WHERE id=:id",
        params={"id": failing_qc.id},
        match="all receipt items to pass",
    )
    await db_session.execute(
        text(
            "UPDATE hub_qc_sessions SET state='qc_failed', completed_at=clock_timestamp() WHERE id=:id"
        ),
        {"id": failing_qc.id},
    )


@pytest.mark.asyncio
async def test_qc_completion_serializes_against_concurrent_inspection_insert(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    qc = _qc(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()
    db_session.add(_inspection(graph, receipt, item, qc))
    await db_session.flush()
    receipt.completed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.commit()

    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    completing = sessions()
    await completing.execute(
        text(
            "UPDATE hub_qc_sessions "
            "SET state='qc_failed', completed_at=clock_timestamp() WHERE id=:id"
        ),
        {"id": qc.id},
    )

    async def insert_inspection():
        async with sessions() as concurrent:
            concurrent.add(_inspection(graph, receipt, item, qc))
            try:
                await concurrent.flush()
            except IntegrityError as exc:
                await concurrent.rollback()
                return str(exc)
            await concurrent.rollback()
            return None

    insert_task = asyncio.create_task(insert_inspection())
    await asyncio.sleep(0.1)
    assert not insert_task.done(), "inspection insert did not wait for the QC row lock"
    await completing.commit()
    rejection = await asyncio.wait_for(insert_task, timeout=2)
    await completing.close()
    assert rejection is not None
    assert "inspections in completed QC sessions are immutable" in rejection


@pytest.mark.asyncio
async def test_remediation_approval_audit_owner_and_failed_inspection_linkage(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    other = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    qc = _qc(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()
    inspection = _inspection(graph, receipt, item, qc)
    db_session.add(inspection)
    await db_session.flush()
    pending = _remediation(graph, receipt, qc, inspection)
    db_session.add(pending)
    await db_session.flush()
    assert pending.owner_id == graph["operator_id"]
    for overrides in (
        {
            "state": RemediationState.PENDING_APPROVAL,
            "approved_by_id": graph["operator_id"],
            "approved_at": NOW,
        },
        {"state": RemediationState.APPROVED},
        {
            "state": RemediationState.COMPLETED,
            "approved_by_id": graph["operator_id"],
            "approved_at": NOW,
        },
        {
            "state": RemediationState.APPROVED,
            "approved_by_id": graph["operator_id"],
            "approved_at": NOW,
            "completed_at": NOW - timedelta(seconds=1),
        },
        {"owner_id": None},
        {"failed_inspection_id": uuid.uuid4()},
        {"order_id": other["order"].id},
    ):
        await _rejects(
            db_session, _remediation(graph, receipt, qc, inspection, **overrides)
        )

    other_receipt = _receipt(other)
    other_item = _receipt_item(other, other_receipt)
    other_qc = _qc(other, other_receipt)
    db_session.add(other_receipt)
    await db_session.flush()
    db_session.add(other_item)
    await db_session.flush()
    db_session.add(other_qc)
    await db_session.flush()
    passing = _inspection(
        other,
        other_receipt,
        other_item,
        other_qc,
        decision=QCDecision.PASS,
        reason_code=None,
        quarantine_disposition=QuarantineDisposition.NOT_APPLICABLE,
    )
    db_session.add(passing)
    await db_session.flush()
    await _rejects(
        db_session,
        _remediation(other, other_receipt, other_qc, passing),
        match="failed or rejected inspection",
    )


async def _failed_cycle(db_session, graph):
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    qc = _qc(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()
    inspection = _inspection(graph, receipt, item, qc)
    db_session.add(inspection)
    await db_session.flush()
    cycle_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    receipt.completed_at = cycle_clock
    await db_session.flush()
    qc.state = "qc_failed"
    qc.completed_at = cycle_clock
    await db_session.flush()
    remediation = _remediation(
        graph,
        receipt,
        qc,
        inspection,
        created_at=cycle_clock,
    )
    db_session.add(remediation)
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE hub_remediations SET state='approved', approved_by_id=:actor, approved_at=:at WHERE id=:id"
        ),
        {"id": remediation.id, "actor": graph["operator_id"], "at": cycle_clock},
    )
    await db_session.execute(
        text("UPDATE hub_remediations SET state='in_progress' WHERE id=:id"),
        {"id": remediation.id},
    )
    await db_session.execute(
        text(
            "UPDATE hub_remediations SET state='completed', completed_at=:at WHERE id=:id"
        ),
        {"id": remediation.id, "at": cycle_clock},
    )
    await db_session.refresh(remediation)
    return receipt, item, qc, inspection, remediation


@pytest.mark.asyncio
async def test_reinspection_requires_exact_completed_failed_remediated_lineage(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt, _item, prior, _inspection_row, remediation = await _failed_cycle(
        db_session, graph
    )
    await _rejects(
        db_session,
        _qc(
            graph,
            receipt,
            sequence=2,
            previous_session_id=prior.id,
            remediation_id=remediation.id,
            started_at=remediation.completed_at - timedelta(microseconds=1),
        ),
        match="reinspection must start after remediation completion",
    )
    valid = _qc(
        graph,
        receipt,
        sequence=2,
        previous_session_id=prior.id,
        remediation_id=remediation.id,
        started_at=NOW + timedelta(minutes=4),
    )
    db_session.add(valid)
    await db_session.flush()
    assert valid.sequence == 2
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_sessions SET remediation_id=:replacement WHERE id=:id",
        params={"id": valid.id, "replacement": uuid.uuid4()},
        match="aggregate lineage is immutable",
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_sessions SET started_at=:replacement WHERE id=:id",
        params={
            "id": valid.id,
            "replacement": valid.started_at + timedelta(microseconds=1),
        },
        match="aggregate lineage is immutable",
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_remediations SET private_notes='rewrite' WHERE id=:id",
        params={"id": remediation.id},
        match="immutable",
    )
    for overrides in (
        {
            "sequence": 1,
            "previous_session_id": prior.id,
            "remediation_id": remediation.id,
        },
        {
            "sequence": 3,
            "previous_session_id": prior.id,
            "remediation_id": remediation.id,
        },
        {
            "sequence": 2,
            "previous_session_id": prior.id,
            "remediation_id": uuid.uuid4(),
        },
    ):
        await _rejects(db_session, _qc(graph, receipt, **overrides))

    other_graph = await _graph(db_session, vendor_user, customer_user)
    _other_receipt, _oi, _oqc, _oinsp, other_remediation = await _failed_cycle(
        db_session, other_graph
    )
    await _rejects(
        db_session,
        _qc(
            graph,
            receipt,
            sequence=2,
            previous_session_id=prior.id,
            remediation_id=other_remediation.id,
        ),
    )


@pytest.mark.asyncio
async def test_reinspection_defends_against_legacy_unfinished_previous_qc(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    prior = _qc(graph, receipt, state="qc_failed")
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(prior)
    await db_session.flush()
    inspection = _inspection(graph, receipt, item, prior)
    db_session.add(inspection)
    await db_session.flush()
    remediation_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    remediation = _remediation(
        graph,
        receipt,
        prior,
        inspection,
        state=RemediationState.COMPLETED,
        approved_by_id=graph["operator_id"],
        created_at=remediation_clock,
        approved_at=remediation_clock,
        completed_at=remediation_clock,
    )
    await db_session.execute(
        text(
            "ALTER TABLE hub_remediations DISABLE TRIGGER tr_hub_remediations_invariants"
        )
    )
    try:
        db_session.add(remediation)
        await db_session.flush()
    finally:
        await db_session.execute(
            text(
                "ALTER TABLE hub_remediations ENABLE TRIGGER tr_hub_remediations_invariants"
            )
        )
    await _rejects(
        db_session,
        _qc(
            graph,
            receipt,
            sequence=2,
            previous_session_id=prior.id,
            remediation_id=remediation.id,
            started_at=remediation_clock + timedelta(microseconds=1),
        ),
        match="completed failed previous QC session",
    )


@pytest.mark.asyncio
async def test_reinspection_rejects_unfinished_remediation(
    db_session, vendor_user, customer_user
):
    pending_graph = await _graph(db_session, vendor_user, customer_user)
    pending_receipt = _receipt(pending_graph)
    pending_item = _receipt_item(pending_graph, pending_receipt)
    pending_prior = _qc(pending_graph, pending_receipt, state="qc_failed")
    db_session.add(pending_receipt)
    await db_session.flush()
    db_session.add(pending_item)
    await db_session.flush()
    db_session.add(pending_prior)
    await db_session.flush()
    pending_inspection = _inspection(
        pending_graph, pending_receipt, pending_item, pending_prior
    )
    db_session.add(pending_inspection)
    await db_session.flush()
    completion_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    pending_receipt.completed_at = completion_clock
    await db_session.flush()
    pending_prior.completed_at = completion_clock
    await db_session.flush()
    pending_remediation = _remediation(
        pending_graph, pending_receipt, pending_prior, pending_inspection
    )
    db_session.add(pending_remediation)
    await db_session.flush()
    await _rejects(
        db_session,
        _qc(
            pending_graph,
            pending_receipt,
            sequence=2,
            previous_session_id=pending_prior.id,
            remediation_id=pending_remediation.id,
        ),
        match="completed remediation",
    )


@pytest.mark.asyncio
async def test_completed_qc_immutability_transition_and_all_audit_deletes(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    qc = _qc(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()
    inspection = _inspection(graph, receipt, item, qc)
    discrepancy = _discrepancy(graph, receipt, item, DiscrepancyType.DAMAGE)
    db_session.add_all([inspection, discrepancy])
    await db_session.flush()
    remediation = _remediation(graph, receipt, qc, inspection)
    db_session.add(remediation)
    await db_session.flush()
    evidence = _evidence(graph, receipt, EvidencePurpose.HUB_RECEIPT)
    db_session.add(evidence)
    await db_session.flush()
    for assignment in (
        "decision='rejected'",
        "reason_code='rewritten'",
        "quarantine_disposition='return_to_vendor'",
        "inspected_quantity=1",
        "inspected_at=clock_timestamp()",
        "private_notes='rewritten'",
        "version=version+1",
    ):
        await _rejects(
            db_session,
            statement=f"UPDATE hub_qc_inspections SET {assignment} WHERE id=:id",
            params={"id": inspection.id},
            match="remediated inspections are immutable",
        )
    await _rejects(
        db_session,
        statement="UPDATE hub_discrepancies SET private_notes='rewrite' WHERE id=:id",
        params={"id": discrepancy.id},
        match="audit records are immutable",
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_evidence SET integrity_hash=:hash WHERE id=:id",
        params={"id": evidence.id, "hash": "b" * 64},
        match="audit records are immutable",
    )
    completion_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    receipt.completed_at = completion_clock
    await db_session.flush()
    qc.state = "qc_failed"
    qc.completed_at = completion_clock
    await db_session.flush()  # transition into completion is allowed
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_sessions SET state='qc_passed' WHERE id=:id",
        params={"id": qc.id},
        match="immutable",
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_inspections SET private_notes='rewrite' WHERE id=:id",
        params={"id": inspection.id},
        match="immutable",
    )
    await _rejects(
        db_session,
        _inspection(graph, receipt, item, qc),
        match="immutable",
    )
    for table, row_id in (
        ("hub_evidence", evidence.id),
        ("hub_remediations", remediation.id),
        ("hub_discrepancies", discrepancy.id),
        ("hub_qc_inspections", inspection.id),
        ("hub_qc_sessions", qc.id),
        ("hub_receipt_items", item.id),
        ("hub_receipt_sessions", receipt.id),
    ):
        await _rejects(
            db_session,
            statement=f"DELETE FROM {table} WHERE id=:id",
            params={"id": row_id},
            match="cannot be deleted",
        )


@pytest.mark.asyncio
async def test_optimistic_versioning_for_all_mutable_hub_records(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    qc = _qc(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()
    inspection = _inspection(graph, receipt, item, qc)
    db_session.add(inspection)
    await db_session.flush()
    remediation = _remediation(graph, receipt, qc, inspection)
    await db_session.commit()
    assert all(
        inspect(model).version_id_col is model.__table__.c.version
        for model in (HubReceiptSession, HubQCSession, HubQCInspection, HubRemediation)
    )

    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    completion_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    changes = (
        (
            HubReceiptSession,
            receipt.id,
            "completed_at",
            completion_clock,
            completion_clock,
        ),
        (HubQCSession, qc.id, "state", "qc_pending", "qc_in_progress"),
        (HubQCInspection, inspection.id, "private_notes", "first", "stale"),
    )
    for model, row_id, attr, first_value, stale_value in changes:
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

    db_session.add(remediation)
    await db_session.commit()
    async with sessions() as first, sessions() as stale:
        current = await first.get(HubRemediation, remediation.id)
        outdated = await stale.get(HubRemediation, remediation.id)
        current.private_notes = "first"
        outdated.private_notes = "stale"
        await first.commit()
        assert current.version == 2
        with pytest.raises(StaleDataError):
            await stale.commit()
        await stale.rollback()


async def _remediation_fixture(db_session, vendor_user, customer_user, *, add=True):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    item = _receipt_item(graph, receipt)
    qc = _qc(graph, receipt)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(item)
    await db_session.flush()
    db_session.add(qc)
    await db_session.flush()
    inspection = _inspection(graph, receipt, item, qc)
    db_session.add(inspection)
    await db_session.flush()
    remediation = _remediation(graph, receipt, qc, inspection)
    if add:
        db_session.add(remediation)
        await db_session.flush()
    return graph, receipt, qc, inspection, remediation


@pytest.mark.asyncio
async def test_pending_remediation_can_cancel_and_then_freezes(
    db_session, vendor_user, customer_user
):
    _graph_row, _receipt_row, _qc_row, _inspection_row, remediation = (
        await _remediation_fixture(db_session, vendor_user, customer_user)
    )
    await db_session.execute(
        text("UPDATE hub_remediations SET state='cancelled' WHERE id=:id"),
        {"id": remediation.id},
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_remediations SET private_notes='rewrite' WHERE id=:id",
        params={"id": remediation.id},
        match="terminal or consumed remediation is immutable",
    )


@pytest.mark.asyncio
async def test_remediation_must_start_pending_and_approval_follows_qc_completion(
    db_session, vendor_user, customer_user
):
    graph, receipt, qc, _inspection_row, remediation = await _remediation_fixture(
        db_session, vendor_user, customer_user, add=False
    )
    creation_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    remediation.created_at = creation_clock
    remediation.state = RemediationState.APPROVED
    remediation.approved_by_id = graph["operator_id"]
    remediation.approved_at = creation_clock
    await _rejects(db_session, remediation, match="remediations must start pending")

    remediation.state = RemediationState.PENDING_APPROVAL
    remediation.approved_by_id = None
    remediation.approved_at = None
    db_session.add(remediation)
    await db_session.flush()
    parent_completion = await db_session.scalar(text("SELECT clock_timestamp()"))
    receipt.completed_at = parent_completion
    await db_session.flush()
    qc.state = "qc_failed"
    qc.completed_at = parent_completion
    await db_session.flush()
    await _rejects(
        db_session,
        statement="UPDATE hub_remediations SET state='approved', approved_by_id=:actor, approved_at=:at WHERE id=:id",
        params={
            "id": remediation.id,
            "actor": graph["operator_id"],
            "at": creation_clock,
        },
        match="remediation approval must follow QC completion",
    )


@pytest.mark.asyncio
async def test_noncompleted_remediation_rejects_completion_timestamp(
    db_session, vendor_user, customer_user
):
    graph, receipt, qc, _inspection_row, remediation = await _remediation_fixture(
        db_session, vendor_user, customer_user, add=False
    )
    db_session.add(remediation)
    await db_session.flush()
    parent_completion = await db_session.scalar(text("SELECT clock_timestamp()"))
    receipt.completed_at = parent_completion
    await db_session.flush()
    qc.state = "qc_failed"
    qc.completed_at = parent_completion
    await db_session.flush()
    approval_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    await _rejects(
        db_session,
        statement=(
            "UPDATE hub_remediations SET state='approved', approved_by_id=:actor, "
            "approved_at=:at, completed_at=:at WHERE id=:id"
        ),
        params={
            "id": remediation.id,
            "actor": graph["operator_id"],
            "at": approval_clock,
        },
        match="completion timestamp requires completion transition",
    )


@pytest.mark.asyncio
async def test_open_receipt_identity_is_frozen_but_completion_is_allowed(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    other = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    db_session.add(receipt)
    await db_session.flush()
    await _rejects(
        db_session,
        statement="UPDATE hub_receipt_sessions SET idempotency_key=:key WHERE id=:id",
        params={"id": receipt.id, "key": f"changed-{uuid.uuid4().hex}"},
        match="identity is immutable",
    )
    await _rejects(
        db_session,
        statement="""
        UPDATE hub_receipt_sessions SET inbound_transfer_id=:transfer,
          cohort_id=:cohort, order_id=:order_id, vendor_id=:vendor,
          hub_id=:hub, operator_id=:operator, started_at=:started
        WHERE id=:id
        """,
        params={
            "id": receipt.id,
            "transfer": other["transfer"].id,
            "cohort": other["cohort"].id,
            "order_id": other["order"].id,
            "vendor": other["vendor_id"],
            "hub": other["hub"].id,
            "operator": other["operator_id"],
            "started": NOW + timedelta(seconds=1),
        },
        match="identity is immutable",
    )
    completion_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.execute(
        text(
            "UPDATE hub_receipt_sessions SET completed_at=:at, version=version+1, updated_at=:at WHERE id=:id"
        ),
        {"id": receipt.id, "at": completion_clock},
    )


@pytest.mark.asyncio
async def test_remediation_identity_terms_and_forward_only_lifecycle(
    db_session, vendor_user, customer_user
):
    graph, receipt_row, qc_row, _inspection_row, remediation = (
        await _remediation_fixture(db_session, vendor_user, customer_user)
    )
    other, other_receipt, other_qc, other_inspection, _ = await _remediation_fixture(
        db_session, vendor_user, customer_user, add=False
    )
    await _rejects(
        db_session,
        statement="""
        UPDATE hub_remediations SET failed_inspection_id=:inspection,
          qc_session_id=:qc, receipt_session_id=:receipt, order_id=:order_id,
          vendor_id=:vendor, hub_id=:hub WHERE id=:id
        """,
        params={
            "id": remediation.id,
            "inspection": other_inspection.id,
            "qc": other_qc.id,
            "receipt": other_receipt.id,
            "order_id": other["order"].id,
            "vendor": other["vendor_id"],
            "hub": other["hub"].id,
        },
        match="identity is immutable",
    )
    await db_session.execute(
        text(
            "UPDATE hub_remediations SET action='refund', disposition='refund', private_notes='proposal' WHERE id=:id"
        ),
        {"id": remediation.id},
    )
    approval_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    for invalid_approved_at in (
        remediation.created_at - timedelta(milliseconds=1),
        approval_clock + timedelta(days=1),
    ):
        await _rejects(
            db_session,
            statement="UPDATE hub_remediations SET state='approved', approved_by_id=:actor, approved_at=:at WHERE id=:id",
            params={
                "id": remediation.id,
                "actor": graph["operator_id"],
                "at": invalid_approved_at,
            },
            match="approval timestamp",
        )
    await _rejects(
        db_session,
        statement="UPDATE hub_remediations SET state='approved', approved_by_id=:actor, approved_at=:at WHERE id=:id",
        params={
            "id": remediation.id,
            "actor": graph["operator_id"],
            "at": approval_clock,
        },
        match="completed failed QC session",
    )
    receipt_row.completed_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.flush()
    await db_session.execute(
        text(
            "UPDATE hub_qc_sessions SET state='qc_failed', completed_at=clock_timestamp() WHERE id=:id"
        ),
        {"id": qc_row.id},
    )
    approved_at = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.execute(
        text(
            "UPDATE hub_remediations SET state='approved', approved_by_id=:actor, approved_at=:at WHERE id=:id"
        ),
        {"id": remediation.id, "actor": graph["operator_id"], "at": approved_at},
    )
    for assignment, extra in (
        ("action='rework'", {}),
        ("disposition='rework'", {}),
        ("owner_id=:actor", {"actor": customer_user["user"].id}),
        ("approved_by_id=:actor", {"actor": customer_user["user"].id}),
        ("approved_at=:changed", {"changed": approved_at + timedelta(seconds=1)}),
        ("state='pending_approval'", {}),
        (
            "state='completed', completed_at=:changed",
            {"changed": approved_at + timedelta(milliseconds=1)},
        ),
    ):
        await _rejects(
            db_session,
            statement=f"UPDATE hub_remediations SET {assignment} WHERE id=:id",
            params={"id": remediation.id, **extra},
        )
    await db_session.execute(
        text(
            "UPDATE hub_remediations SET state='in_progress', private_notes='working' WHERE id=:id"
        ),
        {"id": remediation.id},
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_remediations SET state='approved' WHERE id=:id",
        params={"id": remediation.id},
    )
    completion_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    await db_session.execute(
        text(
            "UPDATE hub_remediations SET state='completed', completed_at=:at WHERE id=:id"
        ),
        {"id": remediation.id, "at": completion_clock},
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_remediations SET private_notes='rewrite' WHERE id=:id",
        params={"id": remediation.id},
        match="immutable",
    )

    (
        cancelled_graph,
        cancelled_receipt,
        cancelled_qc,
        cancelled_inspection,
        cancelled,
    ) = await _remediation_fixture(db_session, vendor_user, customer_user, add=False)
    db_session.add(cancelled)
    await db_session.flush()
    await db_session.execute(
        text("UPDATE hub_remediations SET state='cancelled' WHERE id=:id"),
        {"id": cancelled.id},
    )
    await _rejects(
        db_session,
        statement="UPDATE hub_remediations SET private_notes='rewrite' WHERE id=:id",
        params={"id": cancelled.id},
        match="immutable",
    )


@pytest.mark.asyncio
async def test_evidence_retention_changes_require_append_only_exact_previous_events(
    db_session, vendor_user, customer_user
):
    assert hasattr(models, "HubEvidenceRetentionEvent")
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt = _receipt(graph)
    evidence = _evidence(graph, receipt, EvidencePurpose.HUB_RECEIPT)
    db_session.add(receipt)
    await db_session.flush()
    db_session.add(evidence)
    await db_session.flush()
    original = evidence.retention_until
    extended = original + timedelta(days=30)
    for assignment in ("legal_hold=true", "retention_until=:retention"):
        await _rejects(
            db_session,
            statement=f"UPDATE hub_evidence SET {assignment} WHERE id=:id",
            params={"id": evidence.id, "retention": extended},
            match="retention event",
        )

    hold_id = uuid.uuid4()
    insert_event = """
        INSERT INTO hub_evidence_retention_events
          (id, evidence_id, actor_id, occurred_at, reason,
           previous_legal_hold, resulting_legal_hold,
           previous_retention_until, resulting_retention_until)
        VALUES (:id, :evidence, :actor, :occurred, :reason,
                :previous_hold, :resulting_hold, :previous, :resulting)
    """
    event_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    for invalid_occurred in (
        evidence.created_at - timedelta(milliseconds=1),
        event_clock + timedelta(days=1),
    ):
        await _rejects(
            db_session,
            statement=insert_event,
            params={
                "id": uuid.uuid4(),
                "evidence": evidence.id,
                "actor": graph["operator_id"],
                "occurred": invalid_occurred,
                "reason": "invalid event timestamp",
                "previous_hold": False,
                "resulting_hold": True,
                "previous": original,
                "resulting": extended,
            },
            match="event timestamp",
        )
    hold_occurred = event_clock
    await db_session.execute(
        text(insert_event),
        {
            "id": hold_id,
            "evidence": evidence.id,
            "actor": graph["operator_id"],
            "occurred": hold_occurred,
            "reason": "Litigation hold requested",
            "previous_hold": False,
            "resulting_hold": True,
            "previous": original,
            "resulting": extended,
        },
    )
    snapshot = (
        await db_session.execute(
            text("SELECT legal_hold, retention_until FROM hub_evidence WHERE id=:id"),
            {"id": evidence.id},
        )
    ).one()
    assert snapshot == (True, extended)
    stale_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    await _rejects(
        db_session,
        statement=insert_event,
        params={
            "id": uuid.uuid4(),
            "evidence": evidence.id,
            "actor": graph["operator_id"],
            "occurred": stale_clock,
            "reason": "stale request",
            "previous_hold": False,
            "resulting_hold": False,
            "previous": original,
            "resulting": original + timedelta(days=1),
        },
        match="previous state",
    )
    shortened = original + timedelta(days=1)
    await _rejects(
        db_session,
        statement=insert_event,
        params={
            "id": uuid.uuid4(),
            "evidence": evidence.id,
            "actor": graph["operator_id"],
            "occurred": hold_occurred,
            "reason": "non-monotonic chronology",
            "previous_hold": True,
            "resulting_hold": False,
            "previous": extended,
            "resulting": shortened,
        },
        match="strictly increase",
    )
    release_clock = await db_session.scalar(text("SELECT clock_timestamp()"))
    release_id = uuid.uuid4()
    await db_session.execute(
        text(insert_event),
        {
            "id": release_id,
            "evidence": evidence.id,
            "actor": graph["operator_id"],
            "occurred": release_clock,
            "reason": "Counsel released hold",
            "previous_hold": True,
            "resulting_hold": False,
            "previous": extended,
            "resulting": shortened,
        },
    )
    for statement in (
        "UPDATE hub_evidence_retention_events SET reason='rewrite' WHERE id=:id",
        "DELETE FROM hub_evidence_retention_events WHERE id=:id",
    ):
        await _rejects(db_session, statement=statement, params={"id": release_id})
    await _rejects(
        db_session,
        statement="UPDATE hub_evidence SET legal_hold=true, integrity_hash=:hash WHERE id=:id",
        params={"id": evidence.id, "hash": "b" * 64},
        match="audit records are immutable",
    )
