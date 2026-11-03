"""Service for eligible pending checkout payment reminders with durable idempotency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import socket
from typing import Optional
import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
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


_FORBIDDEN_URL_TOKENS = (
    "sk_test_",
    "sk_live_",
    "client_secret",
    "secret",
    "pepper",
    "api_key",
    "password",
    "checkout_capability",
)


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def is_order_eligible_for_pending_reminder(
    order: Order | None,
    payment: Payment | None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    """Validate full eligibility for sending a pending payment reminder."""
    if order is None:
        return False, "order_not_found"

    if getattr(order, "workflow_cohort", None) == "legacy_ambiguous_quarantined":
        return False, "order_quarantined"

    if order.payment_status != PaymentStatus.PENDING:
        return False, f"order_not_pending:{order.payment_status}"

    if (
        order.fulfillment_status == FulfillmentStatus.CANCELLED
        or order.cancelled_at is not None
    ):
        return False, "order_cancelled"

    if (
        order.fulfillment_status != FulfillmentStatus.ORDER_RECEIVED
        or getattr(order, "confirmed_at", None) is not None
    ):
        return False, f"order_fulfillment_ineligible:{order.fulfillment_status}"

    if not order.customer or not getattr(order.customer, "email", None):
        return False, "missing_customer_email"

    if payment is None:
        return False, "no_payment_record"

    if payment.status != TransactionStatus.PENDING:
        return False, f"payment_not_pending:{payment.status}"

    if (
        getattr(payment, "completed_at", None) is not None
        or getattr(payment, "failed_at", None) is not None
    ):
        return False, "payment_already_terminal"

    if payment.order_id != order.id:
        return False, "payment_order_mismatch"

    # Inspect sibling payments on the order if loaded in memory
    order_dict = getattr(order, "__dict__", {})
    sibling_payments = order_dict.get("payments")
    if sibling_payments:
        for sibling in sibling_payments:
            if sibling.id == payment.id:
                continue
            if (
                sibling.status in {TransactionStatus.COMPLETED, TransactionStatus.REFUNDED}
                or getattr(sibling, "completed_at", None) is not None
            ):
                return False, f"order_has_terminal_payment:{sibling.status}"

        # If a newer payment attempt failed and there is no newer pending payment,
        # the older pending payment is superseded by the failed attempt.
        payment_created = _normalize_utc(payment.created_at or order.created_at)
        newer_failed = [
            s
            for s in sibling_payments
            if s.id != payment.id
            and s.status == TransactionStatus.FAILED
            and s.created_at is not None
            and _normalize_utc(s.created_at) > payment_created
        ]
        if newer_failed:
            latest_failed_ts = max(_normalize_utc(s.created_at) for s in newer_failed)
            has_newer_pending = any(
                s.status == TransactionStatus.PENDING
                and s.created_at is not None
                and _normalize_utc(s.created_at) >= latest_failed_ts
                for s in sibling_payments
            )
            if not has_newer_pending:
                return False, "payment_superseded_by_failed_attempt"

    now = _normalize_utc(now or datetime.now(timezone.utc))
    payment_ts = _normalize_utc(payment.created_at or order.created_at)

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

        if (
            auth_url
            and isinstance(auth_url, str)
            and auth_url.startswith(("http://", "https://"))
            and not any(token in auth_url.lower() for token in _FORBIDDEN_URL_TOKENS)
        ):
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
    now = _normalize_utc(now or datetime.now(timezone.utc))
    cutoff_time = now - timedelta(hours=REMINDER_WINDOW_HOURS)

    # 1. Reconcile any pre-existing pending or lease-expired reminders whose order/payment
    # became paid, failed, refunded, or cancelled before dispatch.
    reconcile_query = (
        select(OrderPaymentReminder)
        .where(
            OrderPaymentReminder.reminder_type == REMINDER_TYPE_24H,
            or_(
                OrderPaymentReminder.status == "pending",
                and_(
                    OrderPaymentReminder.status == "claimed",
                    or_(
                        OrderPaymentReminder.claim_expires_at.is_(None),
                        OrderPaymentReminder.claim_expires_at <= now,
                    ),
                ),
            ),
        )
        .limit(limit)
        .with_for_update()
    )
    reconcilable_reminders = (await session.execute(reconcile_query)).scalars().all()
    for stale_reminder in reconcilable_reminders:
        stale_order = (
            await session.execute(
                select(Order)
                .options(
                    selectinload(Order.customer),
                    selectinload(Order.payments),
                )
                .where(Order.id == stale_reminder.order_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()
        stale_payment = (
            await session.get(Payment, stale_reminder.payment_id)
            if stale_reminder.payment_id
            else None
        )
        is_ok, reason = is_order_eligible_for_pending_reminder(
            stale_order, stale_payment, now
        )
        if not is_ok and not reason.startswith("timing_not_elapsed"):
            stale_reminder.status = "cancelled"
            stale_reminder.claim_owner = None
            stale_reminder.claim_token = None
            stale_reminder.claim_expires_at = None
            stale_reminder.evidence_payload = {
                "cancelled_reason": reason,
                "cancelled_at": now.isoformat(),
            }
            session.add(
                AuditLog(
                    action="pending_payment_reminder_cancelled",
                    entity_type="order",
                    entity_id=stale_order.id if stale_order else stale_reminder.order_id,
                    new_values={
                        "reason": reason,
                        "idempotency_key": stale_reminder.idempotency_key,
                        "cancelled_at": now.isoformat(),
                    },
                )
            )

    # 2. Find pending orders with pending payments created at or before cutoff
    query = (
        select(Order, Payment)
        .join(Payment, Payment.order_id == Order.id)
        .options(
            selectinload(Order.customer),
            selectinload(Order.items).selectinload(OrderItem.product),
            selectinload(Order.payments),
        )
        .where(
            Order.payment_status == PaymentStatus.PENDING,
            Order.fulfillment_status == FulfillmentStatus.ORDER_RECEIVED,
            Order.cancelled_at.is_(None),
            Order.confirmed_at.is_(None),
            Payment.status == TransactionStatus.PENDING,
            Payment.completed_at.is_(None),
            Payment.failed_at.is_(None),
            Payment.created_at <= cutoff_time,
        )
        .order_by(Payment.created_at.asc())
        .limit(limit)
        .execution_options(populate_existing=True)
    )

    results = (await session.execute(query)).all()
    claimed_reminders: list[OrderPaymentReminder] = []
    seen_order_ids: set[uuid.UUID] = set()

    for order, payment in results:
        if order.id in seen_order_ids:
            continue

        is_eligible, reason = is_order_eligible_for_pending_reminder(order, payment, now)
        if not is_eligible:
            continue

        idempotency_key = compute_reminder_idempotency_key(order.id, payment.id)

        # Check existing reminder records for this idempotency key OR for this order + reminder_type
        # so multiple payment attempts / page refreshes on the same order never send more than once.
        existing_query = (
            select(OrderPaymentReminder)
            .where(
                or_(
                    OrderPaymentReminder.idempotency_key == idempotency_key,
                    and_(
                        OrderPaymentReminder.order_id == order.id,
                        OrderPaymentReminder.reminder_type == REMINDER_TYPE_24H,
                    ),
                )
            )
            .order_by(OrderPaymentReminder.created_at.desc())
            .with_for_update()
        )
        existing_rows = (await session.execute(existing_query)).scalars().all()

        if existing_rows:
            # If any reminder for this order was already sent or cancelled, never repeat
            if any(r.status in {"sent", "cancelled"} for r in existing_rows):
                seen_order_ids.add(order.id)
                continue
            # If any reminder for this order is actively claimed by an unexpired worker, skip
            if any(
                r.status == "claimed"
                and r.claim_expires_at is not None
                and _normalize_utc(r.claim_expires_at) > now
                for r in existing_rows
            ):
                seen_order_ids.add(order.id)
                continue

            existing = existing_rows[0]
            if existing.attempt_count >= MAX_ATTEMPTS:
                seen_order_ids.add(order.id)
                continue

            # Re-claim existing pending/stale lease
            existing.status = "claimed"
            existing.claim_owner = owner
            existing.claim_token = uuid.uuid4()
            existing.claim_expires_at = now + timedelta(seconds=lease_seconds)
            session.add(existing)
            claimed_reminders.append(existing)
            seen_order_ids.add(order.id)
        else:
            # Create a new claimed reminder record inside a savepoint so concurrent workers
            # racing on insert do not abort the batch transaction.
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
            try:
                async with session.begin_nested():
                    session.add(reminder)
                    await session.flush()
            except IntegrityError:
                logger.info(
                    "Concurrent worker already claimed pending payment reminder for order %s",
                    order.id,
                )
                seen_order_ids.add(order.id)
                continue

            claimed_reminders.append(reminder)
            seen_order_ids.add(order.id)

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
    now = _normalize_utc(now or datetime.now(timezone.utc))

    client = email_client or email_service

    async with session_factory() as session:
        reminder = (
            await session.execute(
                select(OrderPaymentReminder)
                .where(
                    OrderPaymentReminder.id == reminder_id,
                    OrderPaymentReminder.claim_owner == owner,
                    OrderPaymentReminder.claim_token == claim_token,
                    OrderPaymentReminder.status == "claimed",
                    or_(
                        OrderPaymentReminder.claim_expires_at.is_(None),
                        OrderPaymentReminder.claim_expires_at > now,
                    ),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

        if not reminder:
            return False

        # Ensure no other reminder row for the same order and reminder_type was already sent
        already_sent = (
            await session.execute(
                select(OrderPaymentReminder.id).where(
                    OrderPaymentReminder.order_id == reminder.order_id,
                    OrderPaymentReminder.reminder_type == reminder.reminder_type,
                    OrderPaymentReminder.status == "sent",
                    OrderPaymentReminder.id != reminder.id,
                )
            )
        ).scalar_one_or_none()

        if already_sent is not None:
            reminder.status = "cancelled"
            reminder.claim_owner = None
            reminder.claim_token = None
            reminder.claim_expires_at = None
            reminder.evidence_payload = {
                "cancelled_reason": "already_sent_for_order",
                "cancelled_at": now.isoformat(),
            }
            await session.commit()
            return False

        order = (
            await session.execute(
                select(Order)
                .options(
                    selectinload(Order.customer),
                    selectinload(Order.items).selectinload(OrderItem.product),
                    selectinload(Order.payments),
                )
                .where(Order.id == reminder.order_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

        payment = (
            await session.execute(
                select(Payment)
                .where(Payment.id == reminder.payment_id)
                .with_for_update()
                .execution_options(populate_existing=True)
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
