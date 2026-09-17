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
