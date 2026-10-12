"""Service for eligible pending checkout payment reminders with durable idempotency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import socket
from typing import Optional
import uuid

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
from app.models.payment import Payment, TransactionStatus
from app.models.payment_reminder import OrderPaymentReminder
from app.services.email_service import EmailService, email_service

logger = logging.getLogger(__name__)

REMINDER_TYPE_24H = "pending_payment_24h"
REMINDER_WINDOW_HOURS = 24
MAX_ATTEMPTS = 3
DEFAULT_LEASE_SECONDS = 300


def compute_reminder_idempotency_key(
    order_id: uuid.UUID,
    payment_id: uuid.UUID | None,
    reminder_type: str = REMINDER_TYPE_24H,
) -> str:
    """Generate a durable idempotency key scoped to the order and payment attempt."""
    payment_key = str(payment_id) if payment_id else "order_checkout"
    return f"pending_payment_reminder:{reminder_type}:{order_id}:{payment_key}"


def is_order_eligible_for_pending_reminder(
    order: Order | None,
    payment: Payment | None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Validate full eligibility for sending a pending payment reminder."""
    if order is None:
        return False, "order_not_found"

    if order.payment_status != PaymentStatus.PENDING:
        return False, f"order_not_pending:{order.payment_status}"

    if (
        order.fulfillment_status == FulfillmentStatus.CANCELLED
        or order.cancelled_at is not None
    ):
        return False, "order_cancelled"

    if not order.customer or not getattr(order.customer, "email", None):
        return False, "missing_customer_email"

    if payment is None:
        return False, "no_payment_record"

    if payment.status != TransactionStatus.PENDING:
        return False, f"payment_not_pending:{payment.status}"

    if payment.order_id != order.id:
        return False, "payment_order_mismatch"

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    payment_ts = payment.created_at or order.created_at
    if payment_ts.tzinfo is None:
        payment_ts = payment_ts.replace(tzinfo=timezone.utc)

    eligible_after = payment_ts + timedelta(hours=REMINDER_WINDOW_HOURS)
    if now < eligible_after:
        return False, f"timing_not_elapsed:eligible_at_{eligible_after.isoformat()}"

    return True, "eligible"


def extract_safe_payment_urls(
    order: Order, payment: Payment | None
) -> tuple[str, str]:
    """Extract safe paths back to payment without exposing secrets or credentials."""
    frontend_base = (getattr(settings, "FRONTEND_BASE_URL", "") or "").rstrip("/")
    order_url = f"{frontend_base}/orders/{order.id}"
    payment_url = order_url

    if payment and isinstance(payment.gateway_response, dict):
        response_data = payment.gateway_response.get("data")
        auth_url = None
        if isinstance(response_data, dict):
            auth_url = response_data.get("authorization_url")
        if not auth_url and isinstance(payment.gateway_response.get("authorization_url"), str):
            auth_url = payment.gateway_response.get("authorization_url")

        if auth_url and isinstance(auth_url, str) and auth_url.startswith(("http://", "https://")):
            # Paystack hosted checkout link contains only the transaction access reference,
            # never any secret keys or API tokens.
            payment_url = auth_url

    return payment_url, order_url


async def scan_and_claim_pending_payment_reminders(
    session: AsyncSession,
    *,
    owner: str,
    now: datetime | None = None,
    limit: int = 50,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> list[OrderPaymentReminder]:
    """Scan database for eligible unpaid pending orders and acquire distributed lease claims."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    cutoff_time = now - timedelta(hours=REMINDER_WINDOW_HOURS)

    # Find pending orders with pending payments created at or before cutoff
    query = (
        select(Order, Payment)
        .join(Payment, Payment.order_id == Order.id)
        .options(
            selectinload(Order.customer),
            selectinload(Order.items).selectinload(OrderItem.product),
        )
        .where(
            Order.payment_status == PaymentStatus.PENDING,
            Order.fulfillment_status != FulfillmentStatus.CANCELLED,
            Order.cancelled_at.is_(None),
            Payment.status == TransactionStatus.PENDING,
            Payment.created_at <= cutoff_time,
        )
        .order_by(Payment.created_at.asc())
        .limit(limit)
    )

    results = (await session.execute(query)).all()
    claimed_reminders: list[OrderPaymentReminder] = []

    for order, payment in results:
        is_eligible, reason = is_order_eligible_for_pending_reminder(order, payment, now)
        if not is_eligible:
            continue

        idempotency_key = compute_reminder_idempotency_key(order.id, payment.id)

        # Check existing reminder record
        existing_query = select(OrderPaymentReminder).where(
            OrderPaymentReminder.idempotency_key == idempotency_key
        ).with_for_update()
        existing = (await session.execute(existing_query)).scalar_one_or_none()

        if existing:
            # If already sent or cancelled, never repeat
            if existing.status in {"sent", "cancelled"}:
                continue
            # If currently active claim by another unexpired worker, skip
            if (
                existing.status == "claimed"
                and existing.claim_expires_at
                and existing.claim_expires_at > now
            ):
                continue
            if existing.attempt_count >= MAX_ATTEMPTS:
                continue

            # Re-claim existing pending/stale lease
            existing.status = "claimed"
            existing.claim_owner = owner
            existing.claim_token = uuid.uuid4()
            existing.claim_expires_at = now + timedelta(seconds=lease_seconds)
            session.add(existing)
            claimed_reminders.append(existing)
        else:
            # Create a new claimed reminder record with unique idempotency key
            claim_token = uuid.uuid4()
            reminder = OrderPaymentReminder(
                id=uuid.uuid4(),
                order_id=order.id,
                payment_id=payment.id,
                reminder_type=REMINDER_TYPE_24H,
                idempotency_key=idempotency_key,
                recipient_email=order.customer.email,
                status="claimed",
                claim_owner=owner,
                claim_token=claim_token,
                claim_expires_at=now + timedelta(seconds=lease_seconds),
                attempt_count=0,
                payment_created_at=payment.created_at,
                scheduled_for=payment.created_at + timedelta(hours=REMINDER_WINDOW_HOURS),
            )
            session.add(reminder)
            claimed_reminders.append(reminder)

    return claimed_reminders


async def dispatch_single_reminder(
    session_factory,
    *,
    reminder_id: uuid.UUID,
    owner: str,
    claim_token: uuid.UUID,
    now: datetime | None = None,
    email_client: EmailService | None = None,
) -> bool:
    """Safely dispatch one claimed reminder with re-checked eligibility and audit marker."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    client = email_client or email_service

    async with session_factory() as session:
        reminder = (
            await session.execute(
                select(OrderPaymentReminder)
                .where(
                    OrderPaymentReminder.id == reminder_id,
                    OrderPaymentReminder.claim_token == claim_token,
                    OrderPaymentReminder.status == "claimed",
                )
                .with_for_update()
            )
        ).scalar_one_or_none()

        if not reminder:
            return False

        order = (
            await session.execute(
                select(Order)
                .options(
                    selectinload(Order.customer),
                    selectinload(Order.items).selectinload(OrderItem.product),
                )
                .where(Order.id == reminder.order_id)
                .with_for_update()
            )
        ).scalar_one_or_none()

        payment = (
            await session.execute(
                select(Payment)
                .where(Payment.id == reminder.payment_id)
                .with_for_update()
            )
        ).scalar_one_or_none() if reminder.payment_id else None

        # Re-check eligibility: payment might have been confirmed or order cancelled
        is_eligible, ineligible_reason = is_order_eligible_for_pending_reminder(
            order, payment, now
        )

        if not is_eligible:
            logger.info(
                "Pending payment reminder %s ineligible before send: %s",
                reminder.idempotency_key,
                ineligible_reason,
            )
            reminder.status = "cancelled"
            reminder.claim_owner = None
            reminder.claim_token = None
            reminder.claim_expires_at = None
            reminder.evidence_payload = {
                "cancelled_reason": ineligible_reason,
                "cancelled_at": now.isoformat(),
            }
            audit = AuditLog(
                action="pending_payment_reminder_cancelled",
                entity_type="order",
                entity_id=order.id if order else reminder.order_id,
                new_values={
                    "reason": ineligible_reason,
                    "idempotency_key": reminder.idempotency_key,
                    "cancelled_at": now.isoformat(),
                },
            )
            session.add(audit)
            await session.commit()
            return False

        # Build items for email
        email_items = []
        for item in order.items:
            email_items.append(
                {
                    "product_name": item.product_title,
                    "quantity": item.quantity,
                    "price": float(item.unit_price),
                    "currency": item.currency,
                    "subtotal": float(item.subtotal),
                    "variant_details": item.variant_details,
                }
            )

        payment_url, order_url = extract_safe_payment_urls(order, payment)

        try:
            send_success = await client.send_pending_payment_reminder_email(
                email=reminder.recipient_email,
                name=order.customer.full_name or reminder.recipient_email,
                order_number=order.order_number,
                order_date=order.created_at,
                items=email_items,
                total=float(order.total_amount),
                currency=order.currency or "NGN",
                payment_url=payment_url,
                order_url=order_url,
            )

            if send_success:
                reminder.status = "sent"
                reminder.sent_at = now
                reminder.claim_owner = None
                reminder.claim_token = None
                reminder.claim_expires_at = None
                reminder.evidence_payload = {
                    "sent_at": now.isoformat(),
                    "recipient": reminder.recipient_email,
                    "payment_url": payment_url,
                    "order_url": order_url,
                }

                audit = AuditLog(
                    action="pending_payment_reminder_sent",
                    entity_type="order",
                    entity_id=order.id,
                    new_values={
                        "order_number": order.order_number,
                        "payment_id": str(payment.id) if payment else None,
                        "recipient_email": reminder.recipient_email,
                        "sent_at": now.isoformat(),
                        "idempotency_key": reminder.idempotency_key,
                        "payment_url": payment_url,
                    },
                )
                session.add(audit)
                await session.commit()
                logger.info(
                    "Successfully sent pending payment reminder for order %s to %s",
                    order.order_number,
                    reminder.recipient_email,
                )
                return True
            else:
                reminder.attempt_count += 1
                if reminder.attempt_count >= MAX_ATTEMPTS:
                    reminder.status = "failed"
                    reminder.evidence_payload = {
                        "failed_at": now.isoformat(),
                        "reason": "email_service_returned_false",
                    }
                else:
                    reminder.status = "pending"

                reminder.claim_owner = None
                reminder.claim_token = None
                reminder.claim_expires_at = None
                await session.commit()
                return False

        except Exception as exc:
            logger.exception(
                "Exception dispatching pending payment reminder for order %s: %s",
                order.order_number,
                exc,
            )
            reminder.attempt_count += 1
            if reminder.attempt_count >= MAX_ATTEMPTS:
                reminder.status = "failed"
                reminder.evidence_payload = {
                    "failed_at": now.isoformat(),
                    "reason": str(exc),
                }
            else:
                reminder.status = "pending"

            reminder.claim_owner = None
            reminder.claim_token = None
            reminder.claim_expires_at = None
            await session.commit()
            return False


async def dispatch_pending_payment_reminders_once(
    *,
    session_factory=AsyncSessionLocal,
    owner: str | None = None,
    now: datetime | None = None,
    limit: int = 50,
    email_client: EmailService | None = None,
) -> dict[str, int]:
    """Execute one scan-and-dispatch pass for pending payment reminders."""
    owner = owner or f"pending-payment-reminders:{socket.gethostname()}"
    now = now or datetime.now(timezone.utc)
    counts = {"claimed": 0, "sent": 0, "cancelled": 0, "failed": 0, "skipped": 0}

    async with session_factory() as session:
        claimed_reminders = await scan_and_claim_pending_payment_reminders(
            session, owner=owner, now=now, limit=limit
        )
        counts["claimed"] = len(claimed_reminders)
        await session.commit()

    for reminder in claimed_reminders:
        success = await dispatch_single_reminder(
            session_factory,
            reminder_id=reminder.id,
            owner=owner,
            claim_token=reminder.claim_token,
            now=now,
            email_client=email_client,
        )
        if success:
            counts["sent"] += 1
        else:
            # Determine resulting status
            async with session_factory() as check_session:
                check = await check_session.get(OrderPaymentReminder, reminder.id)
                if check and check.status == "cancelled":
                    counts["cancelled"] += 1
                elif check and check.status == "failed":
                    counts["failed"] += 1
                else:
                    counts["skipped"] += 1

    return counts


__all__ = [
    "REMINDER_TYPE_24H",
    "compute_reminder_idempotency_key",
    "is_order_eligible_for_pending_reminder",
    "extract_safe_payment_urls",
    "scan_and_claim_pending_payment_reminders",
    "dispatch_single_reminder",
    "dispatch_pending_payment_reminders_once",
]
