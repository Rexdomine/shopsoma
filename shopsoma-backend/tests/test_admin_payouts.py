from datetime import datetime, date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_admin_list_payouts_with_filters(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
    vendor_user,
):
    from app.models.payment import Payout, PayoutStatus

    vendor = vendor_user["vendor"]
    today = date.today()
    created_at = datetime.utcnow()

    payout_pending = Payout(
        id=uuid4(),
        vendor_id=vendor.id,
        payout_period_start=today,
        payout_period_end=today,
        total_sales=Decimal("500.00"),
        commission_amount=Decimal("50.00"),
        payout_amount=Decimal("450.00"),
        status=PayoutStatus.PENDING,
        payment_reference="REF-PENDING",
        notes="Pending payout",
        created_at=created_at,
    )
    payout_completed = Payout(
        id=uuid4(),
        vendor_id=vendor.id,
        payout_period_start=today,
        payout_period_end=today,
        total_sales=Decimal("800.00"),
        commission_amount=Decimal("80.00"),
        payout_amount=Decimal("720.00"),
        status=PayoutStatus.COMPLETED,
        payment_reference="REF-DONE",
        notes="Completed payout",
        created_at=created_at - timedelta(days=2),
    )
    db_session.add_all([payout_pending, payout_completed])
    await db_session.commit()

    response = await client.get(
        "/api/v1/admin/payouts",
        params={
            "status": "pending",
            "search": "Test Business",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["payouts"][0]["status"] == "pending"

    response = await client.get(
        "/api/v1/admin/payouts",
        params={
            "start_date": today.strftime("%Y-%m-%d"),
            "end_date": today.strftime("%Y-%m-%d"),
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["payouts"][0]["id"] == str(payout_pending.id)


@pytest.mark.asyncio
async def test_admin_update_payout_status(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
    vendor_user,
    monkeypatch,
):
    from app.models.payment import Payout, PayoutStatus
    from app.services.email_service import email_service

    vendor = vendor_user["vendor"]
    today = date.today()
    captured = {}

    async def fake_send_processed(email, name, payout_amount, processed_at, payout_method=None):
        captured["email"] = email
        captured["processed_at"] = processed_at
        return True

    monkeypatch.setattr(email_service, "send_vendor_payout_processed_email", fake_send_processed)

    payout = Payout(
        id=uuid4(),
        vendor_id=vendor.id,
        payout_period_start=today,
        payout_period_end=today,
        total_sales=Decimal("600.00"),
        commission_amount=Decimal("60.00"),
        payout_amount=Decimal("540.00"),
        status=PayoutStatus.PENDING,
    )
    db_session.add(payout)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/admin/payouts/{payout.id}/status",
        json={
            "status": "completed",
            "payment_reference": "REF-PAID",
            "notes": "Paid via bank transfer",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["payment_reference"] == "REF-PAID"
    assert data["notes"] == "Paid via bank transfer"
    assert data["processed_at"] is not None
    assert captured["email"] == vendor.user.email
    assert captured["processed_at"] is not None


@pytest.mark.asyncio
async def test_admin_update_payout_status_failed_sends_email(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
    vendor_user,
    monkeypatch,
):
    from app.models.payment import Payout, PayoutStatus
    from app.services.email_service import email_service

    vendor = vendor_user["vendor"]
    today = date.today()
    captured = {}

    async def fake_send_failed(email, name, payout_amount, failure_reason):
        captured["email"] = email
        captured["failure_reason"] = failure_reason
        return True

    monkeypatch.setattr(email_service, "send_vendor_payout_failed_email", fake_send_failed)

    payout = Payout(
        id=uuid4(),
        vendor_id=vendor.id,
        payout_period_start=today,
        payout_period_end=today,
        total_sales=Decimal("600.00"),
        commission_amount=Decimal("60.00"),
        payout_amount=Decimal("540.00"),
        status=PayoutStatus.PENDING,
    )
    db_session.add(payout)
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/admin/payouts/{payout.id}/status",
        json={
            "status": "failed",
            "payment_reference": "REF-FAILED",
            "notes": "Bank transfer failed",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "failed"
    assert captured["email"] == vendor.user.email
    assert captured["failure_reason"] == "Bank transfer failed"


@pytest.mark.asyncio
async def test_admin_bulk_update_payout_status(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
    vendor_user,
):
    from app.models.payment import Payout, PayoutStatus

    vendor = vendor_user["vendor"]
    today = date.today()

    payout_one = Payout(
        id=uuid4(),
        vendor_id=vendor.id,
        payout_period_start=today,
        payout_period_end=today,
        total_sales=Decimal("200.00"),
        commission_amount=Decimal("20.00"),
        payout_amount=Decimal("180.00"),
        status=PayoutStatus.PENDING,
    )
    payout_two = Payout(
        id=uuid4(),
        vendor_id=vendor.id,
        payout_period_start=today,
        payout_period_end=today,
        total_sales=Decimal("300.00"),
        commission_amount=Decimal("30.00"),
        payout_amount=Decimal("270.00"),
        status=PayoutStatus.PENDING,
    )
    db_session.add_all([payout_one, payout_two])
    await db_session.commit()

    response = await client.patch(
        "/api/v1/admin/payouts/bulk/status",
        json={
            "payout_ids": [str(payout_one.id), str(payout_two.id)],
            "status": "processing",
            "notes": "Batch update",
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated_count"] == 2


@pytest.mark.asyncio
async def test_admin_export_payouts_csv(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user,
    vendor_user,
):
    from app.models.payment import Payout, PayoutStatus

    vendor = vendor_user["vendor"]
    today = date.today()

    payout = Payout(
        id=uuid4(),
        vendor_id=vendor.id,
        payout_period_start=today,
        payout_period_end=today,
        total_sales=Decimal("400.00"),
        commission_amount=Decimal("40.00"),
        payout_amount=Decimal("360.00"),
        status=PayoutStatus.PENDING,
    )
    db_session.add(payout)
    await db_session.commit()

    response = await client.get(
        "/api/v1/admin/payouts/export/csv",
        params={"status": "pending"},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
