import asyncio
from collections import Counter
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1 import admin as admin_api
from tests.conftest import TestSessionLocal
from app.models.product import ModerationStatus, Product, ProductStatus
from app.schemas.product import ProductApprovalRequest, ProductRejectionRequest
from app.services.product_moderation import mark_product_content_pending


async def _pending_product(db_session, vendor_user):
    product = Product(
        id=uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Atomic Moderation Product",
        description="Product used for atomic moderation tests",
        base_price=100,
        total_stock=2,
        status=ProductStatus.DRAFT,
        moderation_status=ModerationStatus.PENDING,
    )
    db_session.add(product)
    await db_session.commit()
    return product


async def _call_moderation(action, product_id, admin_user, session):
    expected_updated_at = await session.scalar(select(Product.updated_at).where(Product.id == product_id))
    if action == "approve":
        return await admin_api.approve_product(
            product_id,
            ProductApprovalRequest(notes="approved by test", expected_updated_at=expected_updated_at),
            admin_user["user"],
            session,
        )
    return await admin_api.reject_product(
        product_id,
        ProductRejectionRequest(reason="insufficient product information", expected_updated_at=expected_updated_at),
        admin_user["user"],
        session,
    )


@pytest.mark.asyncio
async def test_vendor_child_write_returns_approved_product_to_pending(
    db_session, vendor_user, admin_user
):
    product = await _pending_product(db_session, vendor_user)
    product.moderation_status = ModerationStatus.APPROVED
    product.moderated_by = admin_user["user"].id
    await db_session.commit()

    await mark_product_content_pending(db=db_session, product_id=product.id)
    await db_session.commit()

    async with TestSessionLocal() as verification_session:
        persisted = await verification_session.scalar(
            select(Product).where(Product.id == product.id)
        )
    assert persisted.moderation_status is ModerationStatus.PENDING
    assert persisted.moderated_at is None
    assert persisted.moderated_by is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("first_action", "second_action"),
    [("approve", "approve"), ("reject", "reject"), ("approve", "reject")],
)
async def test_concurrent_moderation_has_one_winner_and_one_notification(
    first_action,
    second_action,
    db_session,
    vendor_user,
    admin_user,
    monkeypatch,
):
    product = await _pending_product(db_session, vendor_user)
    calls = Counter()
    both_read_subject = asyncio.Event()
    subject_count = 0
    subject_lock = asyncio.Lock()
    original_subject = admin_api._moderation_subject

    async def synchronized_subject(session, product_id):
        nonlocal subject_count
        subject = await original_subject(session, product_id)
        async with subject_lock:
            subject_count += 1
            if subject_count == 2:
                both_read_subject.set()
        await both_read_subject.wait()
        return subject

    async def approved_email(**_kwargs):
        calls["approve"] += 1

    async def rejected_email(**_kwargs):
        calls["reject"] += 1

    monkeypatch.setattr(admin_api, "_moderation_subject", synchronized_subject)
    monkeypatch.setattr(
        "app.services.email_service.email_service.send_product_approved_email",
        approved_email,
    )
    monkeypatch.setattr(
        "app.services.email_service.email_service.send_product_rejected_email",
        rejected_email,
    )

    async with TestSessionLocal() as first_session, TestSessionLocal() as second_session:
        results = await asyncio.gather(
            _call_moderation(first_action, product.id, admin_user, first_session),
            _call_moderation(second_action, product.id, admin_user, second_session),
            return_exceptions=True,
        )

    successes = [result for result in results if isinstance(result, dict)]
    conflicts = [
        result
        for result in results
        if isinstance(result, HTTPException) and result.status_code == 409
    ]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert sum(calls.values()) == 1

    async with TestSessionLocal() as verification_session:
        persisted = await verification_session.scalar(
            select(Product).where(Product.id == product.id)
        )
    assert persisted.moderation_status in {
        ModerationStatus.APPROVED,
        ModerationStatus.REJECTED,
    }
    assert persisted.moderation_status == (
        ModerationStatus.APPROVED
        if successes[0]["moderation_status"] == "approved"
        else ModerationStatus.REJECTED
    )


@pytest.mark.asyncio
async def test_terminal_retry_returns_conflict_without_second_notification(
    db_session, vendor_user, admin_user, monkeypatch
):
    product = await _pending_product(db_session, vendor_user)
    calls = 0

    async def approved_email(**_kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(
        "app.services.email_service.email_service.send_product_approved_email",
        approved_email,
    )

    async with TestSessionLocal() as session:
        expected_updated_at = await session.scalar(select(Product.updated_at).where(Product.id == product.id))
        first = await admin_api.approve_product(
            product.id,
            ProductApprovalRequest(notes=None, expected_updated_at=expected_updated_at),
            admin_user["user"],
            session,
        )
        with pytest.raises(HTTPException, match="already been decided") as error:
            await admin_api.approve_product(
                product.id,
                ProductApprovalRequest(notes=None, expected_updated_at=expected_updated_at),
                admin_user["user"],
                session,
            )

    assert first["moderation_status"] == "approved"
    assert error.value.status_code == 409
    assert calls == 1


@pytest.mark.asyncio
async def test_notification_failure_does_not_rollback_winning_transition(
    db_session, vendor_user, admin_user, monkeypatch
):
    product = await _pending_product(db_session, vendor_user)

    async def failed_email(**_kwargs):
        raise RuntimeError("mail transport unavailable")

    monkeypatch.setattr(
        "app.services.email_service.email_service.send_product_rejected_email",
        failed_email,
    )

    async with TestSessionLocal() as session:
        expected_updated_at = await session.scalar(select(Product.updated_at).where(Product.id == product.id))
        response = await admin_api.reject_product(
            product.id,
            ProductRejectionRequest(reason="insufficient product information", expected_updated_at=expected_updated_at),
            admin_user["user"],
            session,
        )

    async with TestSessionLocal() as verification_session:
        persisted = await verification_session.scalar(
            select(Product).where(Product.id == product.id)
        )
    assert response["moderation_status"] == "rejected"
    assert persisted.moderation_status is ModerationStatus.REJECTED


@pytest.mark.asyncio
async def test_stale_product_revision_cannot_be_moderated(
    db_session, vendor_user, admin_user, monkeypatch
):
    product = await _pending_product(db_session, vendor_user)
    expected_updated_at = product.updated_at
    product.title = "Vendor revised after admin review"
    await db_session.commit()
    calls = 0

    async def approved_email(**_kwargs):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(
        "app.services.email_service.email_service.send_product_approved_email",
        approved_email,
    )

    async with TestSessionLocal() as session:
        with pytest.raises(HTTPException) as error:
            await admin_api.approve_product(
                product.id,
                ProductApprovalRequest(notes=None, expected_updated_at=expected_updated_at),
                admin_user["user"],
                session,
            )

    assert error.value.status_code == 409
    assert calls == 0
