"""Adversarial PostgreSQL contracts for Lane 2A-3C hub quality persistence."""

import asyncio
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
import uuid

import pytest
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
    receipt.completed_at = NOW + timedelta(minutes=1)
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
    await db_session.commit()

    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    completing = sessions()
    await completing.execute(
        text(
            "UPDATE hub_qc_sessions "
            "SET state='qc_failed', completed_at=:completed WHERE id=:id"
        ),
        {"id": qc.id, "completed": NOW + timedelta(minutes=1)},
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
    qc.state = "qc_failed"
    qc.completed_at = NOW + timedelta(minutes=1)
    await db_session.flush()
    remediation = _remediation(
        graph,
        receipt,
        qc,
        inspection,
        state=RemediationState.COMPLETED,
        approved_by_id=graph["operator_id"],
        approved_at=NOW + timedelta(minutes=2),
        completed_at=NOW + timedelta(minutes=3),
    )
    db_session.add(remediation)
    await db_session.flush()
    return receipt, item, qc, inspection, remediation


@pytest.mark.asyncio
async def test_reinspection_requires_exact_completed_failed_remediated_lineage(
    db_session, vendor_user, customer_user
):
    graph = await _graph(db_session, vendor_user, customer_user)
    receipt, _item, prior, _inspection_row, remediation = await _failed_cycle(
        db_session, graph
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
async def test_reinspection_rejects_unfinished_previous_or_remediation(
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
    remediation = _remediation(
        graph,
        receipt,
        prior,
        inspection,
        state=RemediationState.COMPLETED,
        approved_by_id=graph["operator_id"],
        approved_at=NOW + timedelta(minutes=1),
        completed_at=NOW + timedelta(minutes=2),
    )
    db_session.add(remediation)
    await db_session.flush()
    await _rejects(
        db_session,
        _qc(
            graph,
            receipt,
            sequence=2,
            previous_session_id=prior.id,
            remediation_id=remediation.id,
        ),
        match="completed failed",
    )

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
    pending_prior.completed_at = NOW + timedelta(minutes=1)
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
    await _rejects(
        db_session,
        statement="UPDATE hub_qc_inspections SET decision='pass' WHERE id=:id",
        params={"id": inspection.id},
        match="remediated inspection decisions are immutable",
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
    qc.state = "qc_failed"
    qc.completed_at = NOW + timedelta(minutes=1)
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
    db_session.add(remediation)
    await db_session.commit()
    assert all(
        inspect(model).version_id_col is model.__table__.c.version
        for model in (HubReceiptSession, HubQCSession, HubQCInspection, HubRemediation)
    )

    sessions = async_sessionmaker(bind=db_session.bind, expire_on_commit=False)
    changes = (
        (
            HubReceiptSession,
            receipt.id,
            "completed_at",
            NOW + timedelta(minutes=1),
            NOW + timedelta(minutes=2),
        ),
        (HubQCSession, qc.id, "state", "qc_pending", "qc_in_progress"),
        (HubQCInspection, inspection.id, "private_notes", "first", "stale"),
        (HubRemediation, remediation.id, "private_notes", "first", "stale"),
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
