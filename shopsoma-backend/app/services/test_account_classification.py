"""Safe staging test-account classification operations."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User, UserRole

_ALLOWED_ROLES = (UserRole.CUSTOMER, UserRole.VENDOR)
_TAG_REASON = "staging-wide test data classification"


def _assert_staging() -> None:
    if os.getenv("ENVIRONMENT", "development").strip().lower() != "staging":
        raise RuntimeError("test-account classification is permitted only in staging")


async def classify_existing_staging_accounts(
    db: AsyncSession,
    *,
    actor_id: Any,
    apply: bool,
) -> dict[str, int | bool]:
    """Preview or idempotently classify every current customer/vendor account."""
    _assert_staging()
    role_counts = await db.execute(
        select(User.role, func.count(User.id))
        .where(User.role.in_(_ALLOWED_ROLES))
        .group_by(User.role)
    )
    eligible = {str(role.value): int(count) for role, count in role_counts.all()}

    pending_result = await db.execute(
        select(User.id).where(
            User.role.in_(_ALLOWED_ROLES),
            User.is_test_account.is_(False),
        )
    )
    pending_ids = [row[0] for row in pending_result.all()]
    if not apply:
        return {
            "applied": False,
            "eligible_count": sum(eligible.values()),
            "pending_count": len(pending_ids),
        }

    tagged_at = datetime.now(timezone.utc)
    tagged_result = await db.execute(
        update(User)
        .where(
            User.role.in_(_ALLOWED_ROLES),
            User.is_test_account.is_(False),
        )
        .values(
            is_test_account=True,
            test_account_tagged_at=tagged_at,
            test_account_tagged_by=actor_id,
            test_account_tag_reason=_TAG_REASON,
        )
        .returning(User.id)
    )
    tagged_ids = list(tagged_result.scalars().all())
    if tagged_ids:
        db.add_all(
            AuditLog(
                user_id=actor_id,
                action="user_test_account_tagged",
                entity_type="user",
                entity_id=user_id,
                old_values={"is_test_account": False},
                new_values={"is_test_account": True, "reason": _TAG_REASON},
            )
            for user_id in tagged_ids
        )
    await db.commit()
    return {
        "applied": True,
        "eligible_count": sum(eligible.values()),
        "pending_count": len(pending_ids),
        "tagged_count": len(tagged_ids),
    }


async def tag_staging_account(
    db: AsyncSession,
    *,
    account_id: Any,
    actor_id: Any,
) -> dict[str, Any]:
    """Idempotently tag one customer/vendor account in staging."""
    _assert_staging()
    result = await db.execute(select(User).where(User.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise LookupError("Account not found")
    if account.role not in _ALLOWED_ROLES:
        raise PermissionError("Admin accounts cannot be tagged as test accounts")
    if account.is_test_account:
        return {"tagged": False, "is_test_account": True, "user_id": str(account.id)}

    tagged_at = datetime.now(timezone.utc)
    tagged_result = await db.execute(
        update(User)
        .where(
            User.id == account_id,
            User.role.in_(_ALLOWED_ROLES),
            User.is_test_account.is_(False),
        )
        .values(
            is_test_account=True,
            test_account_tagged_at=tagged_at,
            test_account_tagged_by=actor_id,
            test_account_tag_reason="admin-marked test account",
        )
        .returning(User.id)
    )
    tagged_id = tagged_result.scalar_one_or_none()
    if tagged_id is None:
        await db.rollback()
        return {"tagged": False, "is_test_account": True, "user_id": str(account.id)}

    db.add(
        AuditLog(
            user_id=actor_id,
            action="user_test_account_tagged",
            entity_type="user",
            entity_id=account.id,
            old_values={"is_test_account": False},
            new_values={"is_test_account": True, "reason": "admin-marked test account"},
        )
    )
    await db.commit()
    return {"tagged": True, "is_test_account": True, "user_id": str(account.id)}
