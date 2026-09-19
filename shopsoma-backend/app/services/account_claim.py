"""Helpers for silent guest account claim flow."""

import logging

from fastapi import BackgroundTasks
from typing import Optional

from app.core.config import settings
from app.core.security import create_account_claim_token
from app.models.user import User
from app.services.email_service import email_service

logger = logging.getLogger(__name__)


def _claim_route_base() -> str:
    """Resolve the base URL for claim links."""
    base = settings.FRONTEND_BASE_URL or "http://localhost:5173"
    return base.rstrip("/") + "/claim-account"


def build_account_claim_link(email: str) -> str:
    """Generate a signed account claim link for the provided email."""
    token = create_account_claim_token(email)
    return f"{_claim_route_base()}?token={token}&email={email}"


def queue_account_claim_email(
    user: User, background_tasks: Optional[BackgroundTasks]
) -> None:
    """
    Queue an account claim email for a guest user.

    The task is skipped if the user already has a password or if background tasks aren't available.
    """
    if not background_tasks or not user or user.hashed_password:
        return

    claim_link = build_account_claim_link(user.email)
    background_tasks.add_task(
        email_service.send_account_claim_email,
        user.email,
        user.full_name or "there",
        claim_link,
    )


async def send_account_claim_email_if_guest(user: Optional[User]) -> bool:
    """
    Send an account claim email for a paid guest-created account.

    Registered users and users that already claimed their account are skipped.
    """
    if not user or not user.email or user.hashed_password or not user.is_guest_created:
        return False

    claim_link = build_account_claim_link(user.email)
    try:
        return await email_service.send_account_claim_email(
            user.email,
            user.full_name or "there",
            claim_link,
        )
    except Exception as exc:
        logger.exception(
            "Failed to send account claim email to %s: %s", user.email, exc
        )
        return False
