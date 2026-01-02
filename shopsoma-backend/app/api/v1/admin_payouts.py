"""Admin payouts management endpoints"""
from typing import Optional
from datetime import datetime
import csv
import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.orm import selectinload
from uuid import UUID
from starlette.responses import StreamingResponse

from app.core.database import get_db
from app.api.dependencies import get_current_admin
from app.models import Payout, Vendor, User
from app.models.payment import PayoutStatus
from app.services.email_service import email_service
from app.schemas.admin_payout import (
    AdminPayoutList,
    AdminPayoutResponse,
    AdminPayoutStatusUpdate,
    AdminPayoutBulkStatusUpdate,
    AdminPayoutAccountDetails,
)

router = APIRouter(prefix="/admin/payouts", tags=["Admin Payouts"])
logger = logging.getLogger(__name__)


@router.get("", response_model=AdminPayoutList)
async def list_payouts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[PayoutStatus] = Query(None, alias="status"),
    vendor_id: Optional[UUID] = Query(None),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search by vendor or reference"),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List payouts for admin management."""
    from datetime import date, time

    def parse_date(value: Optional[str], label: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()
            return datetime.combine(parsed, time.min)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {label}. Use YYYY-MM-DD."
            ) from exc

    start_dt = parse_date(start_date, "start_date")
    end_dt = None
    if end_date:
        try:
            parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()
            end_dt = datetime.combine(parsed_end, time.max)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date. Use YYYY-MM-DD."
            ) from exc

    query = select(Payout).options(
        selectinload(Payout.vendor).selectinload(Vendor.user)
    )

    filters = []
    if status_filter:
        filters.append(Payout.status == status_filter)
    if vendor_id:
        filters.append(Payout.vendor_id == vendor_id)
    if start_dt:
        filters.append(Payout.created_at >= start_dt)
    if end_dt:
        filters.append(Payout.created_at <= end_dt)
    if search:
        query = query.join(Payout.vendor).join(Vendor.user).where(
            or_(
                Vendor.business_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                Payout.payment_reference.ilike(f"%{search}%"),
                Payout.notes.ilike(f"%{search}%")
            )
        )

    if filters:
        query = query.where(and_(*filters))

    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(desc(Payout.created_at)).offset(offset).limit(page_size)
    result = await db.execute(query)
    payouts = result.scalars().all()

    return AdminPayoutList(
        payouts=[
            AdminPayoutResponse(
                id=payout.id,
                vendor={
                    "id": payout.vendor.id,
                    "business_name": payout.vendor.business_name,
                    "email": payout.vendor.user.email if payout.vendor.user else None,
                    "phone": payout.vendor.business_phone,
                },
                payout_period_start=payout.payout_period_start,
                payout_period_end=payout.payout_period_end,
                total_sales=payout.total_sales,
                commission_amount=payout.commission_amount,
                payout_amount=payout.payout_amount,
                status=payout.status,
                processed_at=payout.processed_at,
                payment_reference=payout.payment_reference,
                notes=payout.notes,
                created_at=payout.created_at,
            )
            for payout in payouts
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.patch("/bulk/status")
async def bulk_update_payout_status(
    payload: AdminPayoutBulkStatusUpdate,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update payout statuses."""
    result = await db.execute(
        select(Payout)
        .options(selectinload(Payout.vendor).selectinload(Vendor.user))
        .where(Payout.id.in_(payload.payout_ids))
    )
    payouts = result.scalars().all()

    if not payouts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No payouts found")

    updated_count = 0
    note = None
    if payload.notes:
        note = f"[{datetime.utcnow().isoformat()}] Bulk update: {payload.notes}"

    for payout in payouts:
        payout.status = payload.status
        if note:
            if payout.notes:
                payout.notes += f"\n\n{note}"
            else:
                payout.notes = note

        if payload.status in {PayoutStatus.COMPLETED, PayoutStatus.FAILED}:
            payout.processed_at = datetime.utcnow()
            payout.processed_by = current_admin.id

        updated_count += 1

    await db.commit()

    for payout in payouts:
        if payout.vendor and payout.vendor.user and payout.vendor.user.email:
            try:
                await email_service.send_vendor_payout_status_update_email(
                    email=payout.vendor.user.email,
                    name=payout.vendor.business_name,
                    payout_amount=float(payout.payout_amount),
                    status=payout.status.value,
                    processed_at=payout.processed_at,
                    payment_reference=payout.payment_reference,
                    notes=payout.notes,
                )
            except Exception:
                logger.exception(
                    "[Admin Payout] Failed to send bulk payout update email for payout_id=%s",
                    payout.id
                )

    return {
        "success": True,
        "updated_count": updated_count,
        "message": f"Successfully updated {updated_count} payouts",
    }


@router.patch("/{payout_id}/status", response_model=AdminPayoutResponse)
async def update_payout_status(
    payout_id: UUID,
    payload: AdminPayoutStatusUpdate,
    current_admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update payout status."""
    result = await db.execute(
        select(Payout).options(selectinload(Payout.vendor).selectinload(Vendor.user)).where(Payout.id == payout_id)
    )
    payout = result.scalar_one_or_none()

    if not payout:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payout not found")

    previous_status = payout.status
    payout.status = payload.status
    payout.payment_reference = payload.payment_reference
    if payload.notes is not None:
        payout.notes = payload.notes

    if payload.status in {PayoutStatus.COMPLETED, PayoutStatus.FAILED}:
        payout.processed_at = datetime.utcnow()
        payout.processed_by = current_admin.id

    await db.commit()
    await db.refresh(payout)

    if previous_status != payout.status and payout.vendor and payout.vendor.user and payout.vendor.user.email:
        try:
            await email_service.send_vendor_payout_status_update_email(
                email=payout.vendor.user.email,
                name=payout.vendor.business_name,
                payout_amount=float(payout.payout_amount),
                status=payout.status.value,
                processed_at=payout.processed_at,
                payment_reference=payout.payment_reference,
                notes=payout.notes,
            )
        except Exception:
            logger.exception(
                "[Admin Payout] Failed to send payout status email for payout_id=%s",
                payout.id
            )

    return AdminPayoutResponse(
        id=payout.id,
        vendor={
            "id": payout.vendor.id,
            "business_name": payout.vendor.business_name,
            "email": payout.vendor.user.email if payout.vendor.user else None,
            "phone": payout.vendor.business_phone,
        },
        payout_period_start=payout.payout_period_start,
        payout_period_end=payout.payout_period_end,
        total_sales=payout.total_sales,
        commission_amount=payout.commission_amount,
        payout_amount=payout.payout_amount,
        status=payout.status,
        processed_at=payout.processed_at,
        payment_reference=payout.payment_reference,
        notes=payout.notes,
        created_at=payout.created_at,
    )


@router.get("/export/csv")
async def export_payouts_csv(
    status_filter: Optional[PayoutStatus] = Query(None, alias="status"),
    vendor_id: Optional[UUID] = Query(None),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search by vendor or reference"),
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Export payouts to CSV."""
    from datetime import date, time

    def parse_date(value: Optional[str], label: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()
            return datetime.combine(parsed, time.min)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {label}. Use YYYY-MM-DD."
            ) from exc

    start_dt = parse_date(start_date, "start_date")
    end_dt = None
    if end_date:
        try:
            parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()
            end_dt = datetime.combine(parsed_end, time.max)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date. Use YYYY-MM-DD."
            ) from exc

    query = select(Payout).options(
        selectinload(Payout.vendor).selectinload(Vendor.user)
    )

    filters = []
    if status_filter:
        filters.append(Payout.status == status_filter)
    if vendor_id:
        filters.append(Payout.vendor_id == vendor_id)
    if start_dt:
        filters.append(Payout.created_at >= start_dt)
    if end_dt:
        filters.append(Payout.created_at <= end_dt)
    if search:
        query = query.join(Payout.vendor).join(Vendor.user).where(
            or_(
                Vendor.business_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                Payout.payment_reference.ilike(f"%{search}%"),
                Payout.notes.ilike(f"%{search}%")
            )
        )

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(desc(Payout.created_at))
    result = await db.execute(query)
    payouts = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Vendor",
        "Vendor Email",
        "Payout Period Start",
        "Payout Period End",
        "Total Sales",
        "Commission Amount",
        "Payout Amount",
        "Status",
        "Processed At",
        "Payment Reference",
        "Notes",
        "Created At",
    ])

    for payout in payouts:
        writer.writerow([
            payout.vendor.business_name if payout.vendor else "",
            payout.vendor.user.email if payout.vendor and payout.vendor.user else "",
            payout.payout_period_start.isoformat(),
            payout.payout_period_end.isoformat(),
            float(payout.total_sales),
            float(payout.commission_amount),
            float(payout.payout_amount),
            payout.status.value,
            payout.processed_at.isoformat() if payout.processed_at else "",
            payout.payment_reference or "",
            payout.notes or "",
            payout.created_at.isoformat(),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=payouts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        },
    )


@router.get("/{payout_id}/account-details", response_model=AdminPayoutAccountDetails)
async def get_payout_account_details(
    payout_id: UUID,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Fetch vendor bank details for a payout."""
    result = await db.execute(
        select(Payout)
        .options(selectinload(Payout.vendor).selectinload(Vendor.payment_methods))
        .where(Payout.id == payout_id)
    )
    payout = result.scalar_one_or_none()

    if not payout or not payout.vendor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payout not found")

    payment_methods = payout.vendor.payment_methods or []
    payment_methods = sorted(
        payment_methods,
        key=lambda method: (not method.is_default, method.created_at),
    )
    selected_method = payment_methods[0] if payment_methods else None

    if selected_method:
        return AdminPayoutAccountDetails(
            payout_id=payout.id,
            vendor_id=payout.vendor_id,
            vendor_name=payout.vendor.business_name,
            bank_name=selected_method.bank_name,
            account_number=selected_method.account_number,
            account_holder=selected_method.account_holder,
            account_type=selected_method.account_type,
            is_default=selected_method.is_default,
            payment_method_id=selected_method.id,
            source="payment_method",
        )

    if payout.vendor.bank_name and payout.vendor.bank_account_number and payout.vendor.bank_account_name:
        return AdminPayoutAccountDetails(
            payout_id=payout.id,
            vendor_id=payout.vendor_id,
            vendor_name=payout.vendor.business_name,
            bank_name=payout.vendor.bank_name,
            account_number=payout.vendor.bank_account_number,
            account_holder=payout.vendor.bank_account_name,
            account_type=None,
            is_default=True,
            payment_method_id=None,
            source="vendor_profile",
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Vendor bank details not found",
    )
