"""Server-authoritative, provider-neutral payment/fulfilment bridge."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import FulfillmentStatus, Order, PaymentStatus
from app.models.package_custody import (
    HubPackage,
    HubPackageSeal,
    OutboundShipmentIntent,
    OutboundShipmentIntentInvalidation,
)
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.models.stock_payment_persistence import PaymentAttempt, PaymentAttemptEvidence
from app.services.shipping.capabilities import DomesticShippingCapabilities


class PaymentBridgeError(Exception):
    """Stable payment bridge error safe for route translation."""


class PaymentTruthMismatch(PaymentBridgeError):
    """Authenticated provider truth does not match immutable server truth."""


class PaymentRecoveryUnavailable(PaymentBridgeError):
    """Authenticated provider evidence cannot yet be durably associated."""


def _money(value: object) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise PaymentTruthMismatch("verified payment truth does not match") from None
    if not amount.is_finite() or amount <= 0:
        raise PaymentTruthMismatch("verified payment truth does not match")
    return amount


def authoritative_gateway_amount(amount: object, currency: str) -> tuple[Decimal, str]:
    """Return normalized gateway money from persisted server truth only."""
    normalized_currency = str(currency).upper()
    if len(normalized_currency) != 3 or not normalized_currency.isalpha():
        raise PaymentTruthMismatch("verified payment truth does not match")
    return _money(amount), normalized_currency


def validate_verified_payment_truth(
    *,
    expected_amount: object,
    expected_currency: str,
    expected_reference: str,
    observed_amount: object,
    observed_currency: str,
    observed_reference: str,
) -> None:
    expected = authoritative_gateway_amount(expected_amount, expected_currency)
    observed = authoritative_gateway_amount(observed_amount, observed_currency)
    if expected != observed or expected_reference != observed_reference:
        raise PaymentTruthMismatch("verified payment truth does not match")


def bridge_fulfilment_status(
    *,
    paid: bool,
    package_ready: bool,
    current_status: FulfillmentStatus,
) -> FulfillmentStatus:
    """Advance only when independent payment and package truth are both eligible."""
    if paid and package_ready and current_status == FulfillmentStatus.ORDER_RECEIVED:
        return FulfillmentStatus.PREPARING_FOR_PICKUP
    return current_status


@dataclass(frozen=True, slots=True)
class PaymentFinalizationResult:
    bridge_applied: bool
    replay: bool
    order: Order


@dataclass(frozen=True, slots=True)
class PaymentInitializationTruth:
    bridge_applied: bool
    amount: Decimal
    currency: str
    provider_reference: str | None
    lease_token: uuid.UUID | None
    attempt_id: uuid.UUID | None


async def payment_initialization_truth(
    session: AsyncSession,
    *,
    order: Order,
    provider: str,
    capabilities: DomesticShippingCapabilities,
) -> PaymentInitializationTruth:
    """Choose legacy totals or legally start a gated immutable bridge attempt."""
    legacy_amount, legacy_currency = authoritative_gateway_amount(
        order.total_amount, order.currency
    )
    if not capabilities.quote_enforcement_enabled:
        return PaymentInitializationTruth(
            False, legacy_amount, legacy_currency, None, None, None
        )

    attempt = await active_bridge_attempt(session, order_id=order.id, lock=True)
    if attempt is None:
        # Orders without a bridge attempt remain on the established checkout path.
        return PaymentInitializationTruth(
            False, legacy_amount, legacy_currency, None, None, None
        )
    if attempt.provider != provider:
        raise PaymentBridgeError("payment attempt is not ready for initialization")
    if attempt.state == "call_started" and provider == "stripe":
        amount, currency = authoritative_gateway_amount(
            attempt.amount, attempt.currency
        )
        return PaymentInitializationTruth(
            True,
            amount,
            currency,
            attempt.provider_reference,
            attempt.lease_token,
            attempt.id,
        )
    if attempt.state != "pending":
        raise PaymentBridgeError("payment attempt is not ready for initialization")
    await session.execute(
        text("SELECT coordinate_payment_attempt_write(:attempt_id, :order_id)"),
        {"attempt_id": attempt.id, "order_id": order.id},
    )
    attempt.state = "call_started"
    attempt.lease_token = uuid.uuid4()
    attempt.row_version += 1
    await session.flush()
    amount, currency = authoritative_gateway_amount(attempt.amount, attempt.currency)
    return PaymentInitializationTruth(
        True,
        amount,
        currency,
        attempt.provider_reference,
        attempt.lease_token,
        attempt.id,
    )


async def active_bridge_attempt(
    session: AsyncSession, *, order_id, lock: bool = False
) -> PaymentAttempt | None:
    statement = (
        select(PaymentAttempt)
        .where(PaymentAttempt.order_id == order_id)
        .order_by(PaymentAttempt.created_at.desc(), PaymentAttempt.id.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    return await session.scalar(statement)


async def recover_payment_mapping(
    session: AsyncSession,
    *,
    provider: str,
    provider_reference: str,
    transaction_id: str,
    observed_amount: object,
    observed_currency: str,
    event_id: str,
    evidence_payload: dict[str, Any],
) -> tuple[Payment, PaymentFinalizationResult]:
    """Recover and finalize one mapping under the immutable attempt lock."""
    attempt = await session.scalar(
        select(PaymentAttempt)
        .where(
            PaymentAttempt.provider == provider,
            PaymentAttempt.provider_reference == provider_reference,
        )
        .with_for_update()
    )
    if attempt is None:
        raise PaymentRecoveryUnavailable(
            "authenticated payment evidence cannot be durably associated"
        )
    payment = await session.scalar(
        select(Payment).where(Payment.transaction_id == transaction_id)
    )
    if payment is None:
        payment = Payment(
            order_id=attempt.order_id,
            transaction_id=transaction_id,
            payment_gateway=PaymentGateway(provider),
            payment_method=provider,
            amount=attempt.amount,
            currency=attempt.currency,
            status=TransactionStatus.PENDING,
            gateway_response=evidence_payload,
        )
        session.add(payment)
        await session.flush()
    elif payment.order_id != attempt.order_id:
        raise PaymentTruthMismatch("verified payment truth does not match")
    result = await finalize_verified_payment(
        session,
        payment=payment,
        provider=provider,
        provider_reference=provider_reference,
        observed_amount=observed_amount,
        observed_currency=observed_currency,
        event_id=event_id,
        evidence_payload=evidence_payload,
    )
    return payment, result


async def package_ready_for_attempt(
    session: AsyncSession, *, attempt: PaymentAttempt
) -> bool:
    return (
        await session.scalar(
            select(OutboundShipmentIntent.id)
            .join(HubPackage, HubPackage.id == OutboundShipmentIntent.package_id)
            .join(HubPackageSeal, HubPackageSeal.id == OutboundShipmentIntent.seal_id)
            .outerjoin(
                OutboundShipmentIntentInvalidation,
                OutboundShipmentIntentInvalidation.intent_id
                == OutboundShipmentIntent.id,
            )
            .where(
                OutboundShipmentIntent.id == attempt.intent_id,
                OutboundShipmentIntent.order_id == attempt.order_id,
                OutboundShipmentIntentInvalidation.id.is_(None),
                HubPackage.state == "ready",
                HubPackage.current_version == OutboundShipmentIntent.package_version,
                HubPackageSeal.retired_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )


def _evidence_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


async def finalize_verified_payment(
    session: AsyncSession,
    *,
    payment: Payment,
    provider: str,
    provider_reference: str,
    observed_amount: object | None,
    observed_currency: str | None,
    event_id: str,
    evidence_payload: dict[str, Any],
    observed_at: datetime | None = None,
) -> PaymentFinalizationResult:
    """Atomically finalize legacy or bridge payment truth without provider calls."""
    order = await session.scalar(
        select(Order).where(Order.id == payment.order_id).with_for_update()
    )
    if order is None:
        raise PaymentBridgeError("payment order was not found")

    attempt = await active_bridge_attempt(session, order_id=order.id, lock=True)
    if attempt is None:
        replay = payment.status == TransactionStatus.COMPLETED
        if not replay:
            payment.status = TransactionStatus.COMPLETED
            payment.completed_at = datetime.now(timezone.utc)
            order.payment_status = PaymentStatus.PAID
            order.fulfillment_status = FulfillmentStatus.PREPARING_FOR_PICKUP
        return PaymentFinalizationResult(False, replay, order)

    if observed_amount is None or observed_currency is None:
        raise PaymentTruthMismatch("verified payment truth does not match")
    validate_verified_payment_truth(
        expected_amount=attempt.amount,
        expected_currency=attempt.currency,
        expected_reference=attempt.provider_reference,
        observed_amount=observed_amount,
        observed_currency=observed_currency,
        observed_reference=provider_reference,
    )
    if attempt.provider != provider:
        raise PaymentTruthMismatch("verified payment truth does not match")

    if attempt.state == "verified":
        if payment.status != TransactionStatus.COMPLETED:
            payment.status = TransactionStatus.COMPLETED
            payment.completed_at = attempt.terminal_at
        order.payment_status = PaymentStatus.PAID
        order.fulfillment_status = bridge_fulfilment_status(
            paid=True,
            package_ready=await package_ready_for_attempt(session, attempt=attempt),
            current_status=order.fulfillment_status,
        )
        return PaymentFinalizationResult(True, True, order)

    if attempt.state not in {"call_started", "abandoned_unknown"}:
        raise PaymentBridgeError("payment attempt is not ready for verification")

    observed_at = observed_at or datetime.now(timezone.utc)
    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="payment.verified",
        event_id=f"{provider}:{provider_reference}",
        evidence_type="payment_verified",
        provider=provider,
        provider_reference=provider_reference,
        evidence_hash=_evidence_hash(evidence_payload),
        observed_at=observed_at,
    )
    session.add(evidence)
    await session.flush()

    await session.execute(
        text("SELECT coordinate_payment_attempt_write(:attempt_id, :order_id)"),
        {"attempt_id": attempt.id, "order_id": order.id},
    )
    if attempt.state == "call_started":
        await session.execute(
            text("SELECT set_config('shopsoma.payment_lease_token', :token, true)"),
            {"token": str(attempt.lease_token)},
        )
    attempt.state = "verified"
    attempt.terminal_evidence_id = evidence.id
    attempt.row_version += 1
    await session.flush()

    payment.status = TransactionStatus.COMPLETED
    payment.completed_at = observed_at
    order.payment_status = PaymentStatus.PAID
    order.fulfillment_status = bridge_fulfilment_status(
        paid=True,
        package_ready=await package_ready_for_attempt(session, attempt=attempt),
        current_status=order.fulfillment_status,
    )
    return PaymentFinalizationResult(True, False, order)


async def finalize_failed_payment(
    session: AsyncSession,
    *,
    payment: Payment,
    provider: str,
    provider_reference: str,
    event_id: str,
    evidence_payload: dict[str, Any],
    failure_reason: str,
    observed_at: datetime | None = None,
) -> PaymentFinalizationResult:
    """Atomically finalize authenticated provider failure and payment truth."""
    order = await session.scalar(
        select(Order).where(Order.id == payment.order_id).with_for_update()
    )
    if order is None:
        raise PaymentBridgeError("payment order was not found")

    attempt = await active_bridge_attempt(session, order_id=order.id, lock=True)
    if attempt is None:
        replay = payment.status in {
            TransactionStatus.FAILED,
            TransactionStatus.COMPLETED,
        }
        if payment.status != TransactionStatus.COMPLETED:
            payment.status = TransactionStatus.FAILED
            payment.failed_at = observed_at or datetime.now(timezone.utc)
            payment.failure_reason = failure_reason
            order.payment_status = PaymentStatus.FAILED
        return PaymentFinalizationResult(False, replay, order)

    if attempt.provider != provider or attempt.provider_reference != provider_reference:
        raise PaymentTruthMismatch("verified payment truth does not match")
    if attempt.state == "verified" or payment.status == TransactionStatus.COMPLETED:
        return PaymentFinalizationResult(True, True, order)
    if attempt.state == "failed":
        payment.status = TransactionStatus.FAILED
        payment.failed_at = attempt.terminal_at
        payment.failure_reason = failure_reason
        order.payment_status = PaymentStatus.FAILED
        return PaymentFinalizationResult(True, True, order)
    if attempt.state not in {"call_started", "abandoned_unknown"}:
        raise PaymentBridgeError("payment attempt is not ready for verification")

    observed_at = observed_at or datetime.now(timezone.utc)
    database_now = await session.scalar(text("SELECT clock_timestamp()"))
    if attempt.state == "call_started" and (
        attempt.claim_expires_at is None or database_now >= attempt.claim_expires_at
    ):
        unknown_evidence = PaymentAttemptEvidence(
            attempt_id=attempt.id,
            source="payment.failure_reconciliation",
            event_id=f"{provider}:lease-expired:{event_id}",
            evidence_type="outcome_unknown",
            provider=provider,
            provider_reference=provider_reference,
            evidence_hash=_evidence_hash(evidence_payload),
            observed_at=observed_at,
        )
        session.add(unknown_evidence)
        await session.flush()
        await session.execute(
            text("SELECT coordinate_payment_attempt_write(:attempt_id, :order_id)"),
            {"attempt_id": attempt.id, "order_id": order.id},
        )
        await session.execute(
            text("SELECT set_config('shopsoma.payment_lease_token', :token, true)"),
            {"token": str(attempt.lease_token)},
        )
        attempt.state = "abandoned_unknown"
        attempt.terminal_evidence_id = unknown_evidence.id
        attempt.row_version += 1
        await session.flush()
        observed_at = await session.scalar(text("SELECT clock_timestamp()"))

    evidence = PaymentAttemptEvidence(
        attempt_id=attempt.id,
        source="payment.failed",
        event_id=f"{provider}:{event_id}",
        evidence_type="payment_failed",
        provider=provider,
        provider_reference=provider_reference,
        evidence_hash=_evidence_hash(evidence_payload),
        observed_at=observed_at,
    )
    session.add(evidence)
    await session.flush()

    await session.execute(
        text("SELECT coordinate_payment_attempt_write(:attempt_id, :order_id)"),
        {"attempt_id": attempt.id, "order_id": order.id},
    )
    if attempt.state == "call_started":
        await session.execute(
            text("SELECT set_config('shopsoma.payment_lease_token', :token, true)"),
            {"token": str(attempt.lease_token)},
        )
    attempt.state = "failed"
    attempt.terminal_evidence_id = evidence.id
    attempt.row_version += 1
    await session.flush()

    payment.status = TransactionStatus.FAILED
    payment.failed_at = observed_at
    payment.failure_reason = failure_reason
    order.payment_status = PaymentStatus.FAILED
    return PaymentFinalizationResult(True, False, order)
