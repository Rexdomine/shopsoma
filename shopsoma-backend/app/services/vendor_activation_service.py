"""Shared, server-authoritative eligibility for vendor activation."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.models.vendor import Vendor


def activation_eligibility():
    """Canonical SQL rule for admin resend and every public activation boundary."""
    return and_(
        Vendor.approved.is_(True),
        User.role == UserRole.VENDOR,
        User.is_active.is_(False),
        Vendor.is_onboarding.is_(True),
        Vendor.store_active.is_(True),
        Vendor.store_paused_at.is_(None),
        Vendor.store_deleted_at.is_(None),
        Vendor.onboarding_completed_at.is_(None),
        ~exists(
            select(AuditLog.id).where(
                AuditLog.action == "user_deactivated",
                AuditLog.entity_type == "user",
                AuditLog.entity_id == User.id,
            )
        ),
    )


async def lock_activation_identity(db: AsyncSession, *, vendor_id=None, user_id=None):
    """Lock both identity rows and refresh ORM state before a separate fresh check."""
    query = select(Vendor, User).join(User, Vendor.user_id == User.id)
    query = (
        query.where(Vendor.id == vendor_id)
        if vendor_id is not None
        else query.where(User.id == user_id)
    )
    return (
        await db.execute(
            query.execution_options(populate_existing=True).with_for_update()
        )
    ).first()


async def activation_is_eligible(db: AsyncSession, vendor_id):
    # A new statement after acquiring the locks sees lifecycle audits committed
    # while the locking statement was waiting under READ COMMITTED.
    return await db.scalar(
        select(activation_eligibility())
        .select_from(Vendor)
        .join(User, Vendor.user_id == User.id)
        .where(Vendor.id == vendor_id)
    )


async def require_activation_identity(db: AsyncSession, subject, email):
    try:
        user_id = UUID(str(subject))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid activation token")
    row = await lock_activation_identity(db, user_id=user_id)
    if not row or not email or row[1].email != email:
        raise HTTPException(status_code=401, detail="Invalid activation token")
    vendor, user = row
    if not await activation_is_eligible(db, vendor.id):
        raise HTTPException(
            status_code=409, detail="Vendor is not eligible for activation"
        )
    return vendor, user
