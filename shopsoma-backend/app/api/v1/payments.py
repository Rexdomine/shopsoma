"""Payment endpoints for Paystack and Stripe integration"""

import hmac
import hashlib
import re
import stripe
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from decimal import Decimal
import httpx

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.order import Order, PaymentStatus
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.models.stock_payment_persistence import PaymentAttempt
from app.schemas.payment import (
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
    PaymentResponse,
)
from app.api.dependencies import get_current_active_user, get_optional_user
from app.services.email_service import email_service
from app.services.account_claim import send_account_claim_email_if_guest
from app.services.payments.fulfilment_bridge import (
    PaymentBridgeError,
    PaymentRecoveryUnavailable,
    PaymentTruthMismatch,
    finalize_failed_payment,
    finalize_verified_payment,
    payment_initialization_truth,
    recover_failed_payment_mapping,
    recover_pending_payment_mapping,
    recover_payment_mapping,
)
from app.services.shipping.capabilities import domestic_shipping_capabilities
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/payments", tags=["Payments"])

# Payment gateway configuration
PAYSTACK_SECRET_KEY = settings.PAYSTACK_SECRET_KEY
PAYSTACK_BASE_URL = "https://api.paystack.co"
stripe.api_key = settings.STRIPE_SECRET_KEY


@router.post("/initialize", response_model=PaymentInitializeResponse)
async def initialize_payment(
    payment_data: PaymentInitializeRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Initialize a payment for an order

    Supports both Paystack (NGN) and Stripe (NGN, USD) payment gateways.
    """
    # Validate payment gateway and currency combination
    if payment_data.payment_gateway == "paystack" and payment_data.currency != "NGN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Paystack only supports NGN currency. Current currency: {payment_data.currency}",
        )

    # Get order
    order_query = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == payment_data.order_id)
    )

    # If authenticated, verify order ownership
    if current_user:
        order_query = order_query.where(Order.customer_id == current_user.id)

    order_result = await db.execute(order_query)
    order = order_result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )

    order_currency = (order.currency or "NGN").upper()
    if payment_data.currency != order_currency:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This order must be paid in {order_currency}.",
        )

    # Check if order is already paid
    if order.payment_status == PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has already been paid",
        )

    # Route to appropriate payment gateway
    if payment_data.payment_gateway == "stripe":
        return await _initialize_stripe_payment(payment_data, order, db)
    else:
        return await _initialize_paystack_payment(payment_data, order, db)


async def _initialize_stripe_payment(
    payment_data: PaymentInitializeRequest, order: Order, db: AsyncSession
) -> PaymentInitializeResponse:
    """Initialize Stripe payment using Payment Intents"""
    try:
        truth = await payment_initialization_truth(
            db,
            order=order,
            provider="stripe",
            capabilities=domestic_shipping_capabilities(settings),
        )
        if truth.bridge_applied:
            # Every Stripe SDK boundary follows the committed attempt fence.
            await db.commit()
        # Ensure Stripe customer exists so saved cards can be reused
        user_query = select(User).where(User.id == order.customer_id)
        user_result = await db.execute(user_query)
        customer_record = user_result.scalar_one()

        stripe_customer_id = customer_record.stripe_customer_id
        customer_idempotency_key = (
            f"shopsoma-payment-attempt:{truth.attempt_id}:customer"
            if truth.bridge_applied
            else None
        )
        intent_idempotency_key = (
            f"shopsoma-payment-attempt:{truth.attempt_id}:payment-intent"
            if truth.bridge_applied
            else None
        )
        if not stripe_customer_id:
            # Try to reuse any existing Stripe customer for this email so saved cards carry over
            sanitized_email = payment_data.email.replace("'", r"\'")
            search_result = stripe.Customer.search(
                query=f"email:'{sanitized_email}'",
                limit=1,
            )
            if search_result.data:
                stripe_customer_id = search_result.data[0].id
            else:
                customer = stripe.Customer.create(
                    idempotency_key=customer_idempotency_key,
                    email=payment_data.email,
                    name=customer_record.full_name or payment_data.email,
                )
                stripe_customer_id = customer.id

            customer_record.stripe_customer_id = stripe_customer_id
            await db.commit()

        # Stripe uses cents; the source is always persisted server truth.
        amount_in_cents = int(truth.amount * 100)

        # Create Payment Intent
        intent = stripe.PaymentIntent.create(
            idempotency_key=intent_idempotency_key,
            amount=amount_in_cents,
            currency=truth.currency.lower(),
            customer=stripe_customer_id,
            payment_method_types=["card"],
            setup_future_usage="off_session",
            payment_method_options={
                "card": {
                    "setup_future_usage": "off_session",
                }
            },
            metadata={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "customer_email": payment_data.email,
                "shopsoma_payment_reference": truth.provider_reference or "",
            },
            receipt_email=payment_data.email,
        )

        payment = await db.scalar(
            select(Payment).where(Payment.transaction_id == intent.id)
        )
        if payment is None:
            payment = Payment(
                order_id=order.id,
                transaction_id=intent.id,
                payment_gateway=PaymentGateway.STRIPE,
                payment_method="stripe",
                amount=truth.amount,
                currency=truth.currency,
                status=TransactionStatus.PENDING,
                gateway_response={"payment_intent": intent.id},
            )
            db.add(payment)
            await db.commit()
        elif payment.order_id != order.id:
            raise PaymentTruthMismatch("verified payment truth does not match")

        return PaymentInitializeResponse(
            status=True,
            message="Stripe Payment Intent created successfully",
            client_secret=intent.client_secret,
            payment_intent_id=intent.id,
            payment_gateway="stripe",
        )

    except PaymentBridgeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Stripe error: {str(e)}",
        )


def _paystack_definitive_absence(payload: object) -> bool:
    if not isinstance(payload, dict) or payload.get("status") is not False:
        return False
    message = payload.get("message")
    if not isinstance(message, str):
        return False
    normalized_message = " ".join(message.casefold().split())
    return bool(
        re.fullmatch(
            r"(?:transaction(?: reference)?|reference) not found[.!]?",
            normalized_message,
        )
    )


async def _reconcile_paystack_initialization(
    client: httpx.AsyncClient,
    *,
    reference: str,
    headers: dict[str, str],
    db: AsyncSession,
) -> None:
    """Resolve a fenced Paystack POST outcome without issuing another POST."""
    provider_response = None
    try:
        response = await client.get(
            f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}",
            headers=headers,
            timeout=30.0,
        )
        response.raise_for_status()
        provider_response = response.json()
    except httpx.HTTPStatusError as error:
        try:
            error_payload = error.response.json()
        except Exception:
            error_payload = None
        definitive_absence = (
            error.response.status_code == status.HTTP_404_NOT_FOUND
            and _paystack_definitive_absence(error_payload)
        )
        if definitive_absence:
            provider_response = error_payload
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment initialization outcome is unavailable",
            ) from error
    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment initialization outcome is unavailable",
        ) from error

    if isinstance(provider_response, dict) and provider_response.get("status") is False:
        if not _paystack_definitive_absence(provider_response):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Payment initialization outcome is not definitive",
            )
        await recover_failed_payment_mapping(
            db,
            provider="paystack",
            provider_reference=reference,
            transaction_id=reference,
            event_id=f"initialize-absent:{reference}",
            evidence_payload=provider_response,
            failure_reason=provider_response["message"],
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment initialization was rejected",
        )

    transaction_data = provider_response.get("data", {})
    if (
        not provider_response.get("status")
        or transaction_data.get("status") != "failed"
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Payment initialization outcome is not definitive",
        )

    await recover_failed_payment_mapping(
        db,
        provider="paystack",
        provider_reference=transaction_data.get("reference", reference),
        transaction_id=transaction_data.get("reference", reference),
        event_id=f"initialize:{transaction_data.get('id', reference)}",
        evidence_payload=transaction_data,
        failure_reason=transaction_data.get("gateway_response") or "Payment failed",
    )
    await db.commit()
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=transaction_data.get("gateway_response") or "Payment failed",
    )


async def _stored_paystack_initialization_session(
    db: AsyncSession, *, order: Order, attempt_id: UUID | None, reference: str
) -> PaymentInitializeResponse | None:
    attempt = await db.get(PaymentAttempt, attempt_id)
    if (
        attempt is None
        or attempt.order_id != order.id
        or attempt.provider != "paystack"
        or attempt.provider_reference != reference
    ):
        raise PaymentTruthMismatch("stored payment attempt truth does not match")
    payment = await db.scalar(
        select(Payment).where(Payment.transaction_id == reference)
    )
    if payment is None:
        return None
    response = payment.gateway_response
    data = response.get("data") if isinstance(response, dict) else None
    authorization_url = (
        data.get("authorization_url") if isinstance(data, dict) else None
    )
    access_code = data.get("access_code") if isinstance(data, dict) else None
    stored_reference = data.get("reference") if isinstance(data, dict) else None
    valid = (
        payment.order_id == order.id
        and payment.payment_gateway == PaymentGateway.PAYSTACK
        and payment.payment_method == "paystack"
        and payment.amount == order.total_amount
        and payment.currency == order.currency
        and isinstance(response, dict)
        and response.get("status") is True
        and isinstance(authorization_url, str)
        and bool(authorization_url)
        and isinstance(access_code, str)
        and bool(access_code)
        and stored_reference == reference
    )
    if not valid:
        raise PaymentTruthMismatch("stored payment initialization truth does not match")
    return PaymentInitializeResponse(
        status=True,
        message="Payment session created successfully",
        authorization_url=authorization_url,
        access_code=access_code,
        reference=stored_reference,
        payment_gateway="paystack",
    )


async def _initialize_paystack_payment(
    payment_data: PaymentInitializeRequest, order: Order, db: AsyncSession
) -> PaymentInitializeResponse:
    """Initialize Paystack payment"""
    # Validate Paystack secret key
    if not PAYSTACK_SECRET_KEY or PAYSTACK_SECRET_KEY == "":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Paystack is not configured. Please contact support.",
        )

    # Validate key format
    if not PAYSTACK_SECRET_KEY.startswith(("sk_test_", "sk_live_")):
        print(
            "⚠️  Invalid Paystack key format. Key should start with 'sk_test_' or 'sk_live_'"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Invalid payment gateway configuration. Please contact support.",
        )

    try:
        truth = await payment_initialization_truth(
            db,
            order=order,
            provider="paystack",
            capabilities=domestic_shipping_capabilities(settings),
        )
    except PaymentBridgeError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if truth.bridge_applied:
        # Durable call_started truth must precede the provider boundary.
        await db.commit()
    reference = truth.provider_reference or f"SHP-{order.order_number}"
    if truth.bridge_applied and not truth.provider_call_required:
        try:
            stored_session = await _stored_paystack_initialization_session(
                db,
                order=order,
                attempt_id=truth.attempt_id,
                reference=reference,
            )
        except PaymentBridgeError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Stored payment initialization truth is unusable",
            ) from error
        if stored_session is not None:
            return stored_session

    # Paystack uses kobo; the source is always persisted server truth.
    amount_in_kobo = int(truth.amount * 100)

    callback_url = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/payment/verify"

    payload = {
        "email": payment_data.email,
        "amount": amount_in_kobo,
        "reference": reference,
        "currency": truth.currency,
        "callback_url": callback_url,
        "metadata": {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "customer_name": payment_data.email,
        },
    }

    # Call Paystack API
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        try:
            if not truth.provider_call_required:
                await _reconcile_paystack_initialization(
                    client,
                    reference=reference,
                    headers=headers,
                    db=db,
                )
            response = await client.post(
                f"{PAYSTACK_BASE_URL}/transaction/initialize",
                json=payload,
                headers=headers,
                timeout=30.0,
            )

            # Try to parse response regardless of status code for better error messages
            try:
                paystack_response = response.json()
            except Exception:
                paystack_response = {"message": response.text}

            # Check for HTTP errors
            if response.status_code != 200:
                if truth.bridge_applied:
                    await _reconcile_paystack_initialization(
                        client,
                        reference=reference,
                        headers=headers,
                        db=db,
                    )
                error_message = paystack_response.get(
                    "message", "Payment initialization failed"
                )
                print(
                    f"❌ Paystack API Error (HTTP {response.status_code}): {error_message}"
                )
                print(f"   Response: {paystack_response}")

                # Provide specific error messages
                if response.status_code == 401:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Payment gateway authentication failed. Please contact support.",
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, detail=error_message
                    )

            if not paystack_response.get("status"):
                error_message = paystack_response.get(
                    "message", "Payment initialization failed"
                )
                print(f"❌ Paystack returned status=false: {error_message}")
                if truth.bridge_applied and _paystack_definitive_absence(
                    paystack_response
                ):
                    await recover_failed_payment_mapping(
                        db,
                        provider="paystack",
                        provider_reference=reference,
                        transaction_id=reference,
                        event_id=f"initialize-absent:{reference}",
                        evidence_payload=paystack_response,
                        failure_reason=error_message,
                    )
                    await db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Payment initialization was rejected",
                    )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Payment initialization outcome is not definitive",
                )

            # Create payment record
            payment = Payment(
                order_id=order.id,
                transaction_id=reference,
                payment_gateway=PaymentGateway.PAYSTACK,
                payment_method="paystack",
                amount=truth.amount,
                currency=truth.currency,
                status=TransactionStatus.PENDING,
                gateway_response=paystack_response,
            )

            db.add(payment)
            await db.commit()

            data = paystack_response["data"]
            return PaymentInitializeResponse(
                status=True,
                message="Payment session created successfully",
                authorization_url=data["authorization_url"],
                access_code=data["access_code"],
                reference=data["reference"],
                payment_gateway="paystack",
            )

        except HTTPException:
            raise
        except httpx.HTTPError as e:
            if truth.bridge_applied:
                await _reconcile_paystack_initialization(
                    client,
                    reference=reference,
                    headers=headers,
                    db=db,
                )
            print(f"❌ HTTP Error connecting to Paystack: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Payment service connection error: {str(e)}",
            )


@router.post("/verify", response_model=PaymentVerifyResponse)
async def verify_payment(
    verify_data: PaymentVerifyRequest, db: AsyncSession = Depends(get_db)
):
    """
    Verify a payment

    Supports both Paystack and Stripe payment verification.
    """
    if verify_data.payment_gateway == "stripe":
        return await _verify_stripe_payment(verify_data, db)
    else:
        return await _verify_paystack_payment(verify_data, db)


async def _verify_stripe_payment(
    verify_data: PaymentVerifyRequest, db: AsyncSession
) -> PaymentVerifyResponse:
    """Verify Stripe payment using Payment Intent"""
    try:
        # Retrieve Payment Intent from Stripe
        intent = stripe.PaymentIntent.retrieve(verify_data.payment_intent_id)

        # Get payment record
        payment_query = select(Payment).where(
            Payment.transaction_id == verify_data.payment_intent_id
        )
        payment_result = await db.execute(payment_query)
        payment = payment_result.scalar_one_or_none()

        claim_customer = None

        # Update payment status based on authenticated intent truth
        if intent.status == "succeeded":
            provider_reference = (
                intent.metadata.get("shopsoma_payment_reference")
                if getattr(intent, "metadata", None)
                else intent.id
            )
            authenticated = {
                "id": intent.id,
                "status": intent.status,
                "amount": intent.amount,
                "currency": intent.currency,
            }
            if payment is None:
                payment, result = await recover_payment_mapping(
                    db,
                    provider="stripe",
                    provider_reference=provider_reference,
                    transaction_id=intent.id,
                    observed_amount=Decimal(intent.amount) / 100,
                    observed_currency=intent.currency,
                    event_id=f"verify:{intent.id}",
                    evidence_payload=authenticated,
                )
            else:
                result = await finalize_verified_payment(
                    db,
                    payment=payment,
                    provider="stripe",
                    provider_reference=provider_reference,
                    observed_amount=Decimal(intent.amount) / 100,
                    observed_currency=intent.currency,
                    event_id=f"verify:{intent.id}",
                    evidence_payload=authenticated,
                )
            payment.gateway_response = {
                "payment_intent": intent.id,
                "status": intent.status,
            }
            order = await db.scalar(
                select(Order)
                .options(selectinload(Order.customer))
                .where(Order.id == payment.order_id)
            )
            if order and order.customer and not result.replay:
                claim_customer = order.customer

        elif intent.status in [
            "requires_payment_method",
            "requires_confirmation",
            "requires_action",
            "processing",
        ]:
            provider_reference = (
                intent.metadata.get("shopsoma_payment_reference")
                if getattr(intent, "metadata", None)
                else intent.id
            )
            if payment is None:
                payment = await recover_pending_payment_mapping(
                    db,
                    provider="stripe",
                    provider_reference=provider_reference,
                    transaction_id=intent.id,
                    observed_amount=Decimal(intent.amount) / 100,
                    observed_currency=intent.currency,
                    evidence_payload={
                        "id": intent.id,
                        "status": intent.status,
                        "amount": intent.amount,
                        "currency": intent.currency,
                    },
                )
                owner_order_id = (
                    intent.metadata.get("order_id")
                    if getattr(intent, "metadata", None)
                    else None
                )
                if owner_order_id and str(payment.order_id) != owner_order_id:
                    raise PaymentTruthMismatch("verified payment truth does not match")
            elif payment.status != TransactionStatus.COMPLETED:
                payment.status = TransactionStatus.PENDING
        else:
            failure_reason = (
                intent.last_payment_error.message
                if intent.last_payment_error
                else "Payment failed"
            )
            provider_reference = (
                intent.metadata.get("shopsoma_payment_reference")
                if getattr(intent, "metadata", None)
                else intent.id
            )
            authenticated = {
                "id": intent.id,
                "status": intent.status,
                "amount": intent.amount,
                "currency": intent.currency,
            }
            if payment is None:
                payment, _ = await recover_failed_payment_mapping(
                    db,
                    provider="stripe",
                    provider_reference=provider_reference,
                    transaction_id=intent.id,
                    event_id=f"verify:{intent.id}",
                    evidence_payload=authenticated,
                    failure_reason=failure_reason,
                )
            else:
                await finalize_failed_payment(
                    db,
                    payment=payment,
                    provider="stripe",
                    provider_reference=provider_reference,
                    event_id=f"verify:{intent.id}",
                    evidence_payload=authenticated,
                    failure_reason=failure_reason,
                )

        await db.commit()
        await db.refresh(payment)

        if claim_customer:
            try:
                await email_service.send_payment_receipt_email(
                    email=claim_customer.email,
                    name=claim_customer.full_name,
                    order_number=order.order_number,
                    amount=float(payment.amount),
                    currency=payment.currency,
                    payment_method="Stripe",
                    reference=payment.transaction_id,
                )
            except Exception as e:
                print(f"Failed to send payment receipt email: {e}")
            await send_account_claim_email_if_guest(claim_customer)

        return PaymentVerifyResponse(
            status=intent.status == "succeeded",
            message=(
                "Payment verification successful"
                if intent.status == "succeeded"
                else "Payment not completed"
            ),
            data={
                "status": intent.status,
                "amount": intent.amount,
                "currency": intent.currency,
            },
        )

    except PaymentRecoveryUnavailable as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
        )
    except (PaymentBridgeError, PaymentTruthMismatch) as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Stripe verification error: {str(e)}",
        )


async def _verify_paystack_payment(
    verify_data: PaymentVerifyRequest, db: AsyncSession
) -> PaymentVerifyResponse:
    """Verify Paystack payment"""
    # Call Paystack verify endpoint
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{PAYSTACK_BASE_URL}/transaction/verify/{verify_data.reference}",
                headers=headers,
                timeout=30.0,
            )
            response.raise_for_status()
            paystack_response = response.json()

            if not paystack_response.get("status"):
                return PaymentVerifyResponse(
                    status=False,
                    message=paystack_response.get("message", "Verification failed"),
                    data=None,
                )

            transaction_data = paystack_response["data"]
            if transaction_data.get("reference") != verify_data.reference:
                raise PaymentTruthMismatch("verified payment truth does not match")

            # Get payment record
            payment_query = select(Payment).where(
                Payment.transaction_id == verify_data.reference
            )
            payment_result = await db.execute(payment_query)
            payment = payment_result.scalar_one_or_none()

            claim_customer = None

            # Update payment status from authenticated Paystack truth.
            if transaction_data["status"] == "success":
                observed_amount = (
                    Decimal(transaction_data["amount"]) / 100
                    if transaction_data.get("amount") is not None
                    else None
                )
                if payment is None:
                    payment, result = await recover_payment_mapping(
                        db,
                        provider="paystack",
                        provider_reference=transaction_data["reference"],
                        transaction_id=transaction_data["reference"],
                        observed_amount=observed_amount,
                        observed_currency=transaction_data.get("currency"),
                        event_id=f"verify:{transaction_data.get('id', transaction_data['reference'])}",
                        evidence_payload=transaction_data,
                    )
                else:
                    result = await finalize_verified_payment(
                        db,
                        payment=payment,
                        provider="paystack",
                        provider_reference=transaction_data["reference"],
                        observed_amount=observed_amount,
                        observed_currency=transaction_data.get("currency"),
                        event_id=f"verify:{transaction_data.get('id', transaction_data['reference'])}",
                        evidence_payload=transaction_data,
                    )
                payment.gateway_response = paystack_response
                order = await db.scalar(
                    select(Order)
                    .options(selectinload(Order.customer))
                    .where(Order.id == payment.order_id)
                )
                if order and order.customer and not result.replay:
                    claim_customer = order.customer
            elif transaction_data["status"] == "failed":
                if payment is None:
                    payment, _ = await recover_failed_payment_mapping(
                        db,
                        provider="paystack",
                        provider_reference=transaction_data["reference"],
                        transaction_id=transaction_data["reference"],
                        event_id=f"verify:{transaction_data.get('id', transaction_data['reference'])}",
                        evidence_payload=transaction_data,
                        failure_reason=transaction_data.get("gateway_response")
                        or "Payment failed",
                    )
                elif payment.status != TransactionStatus.COMPLETED:
                    await finalize_failed_payment(
                        db,
                        payment=payment,
                        provider="paystack",
                        provider_reference=transaction_data["reference"],
                        event_id=f"verify:{transaction_data.get('id', transaction_data['reference'])}",
                        evidence_payload=transaction_data,
                        failure_reason=transaction_data.get("gateway_response")
                        or "Payment failed",
                    )
                payment.gateway_response = paystack_response
            elif transaction_data["status"] in {
                "ongoing",
                "pending",
                "processing",
                "queued",
            }:
                observed_amount = (
                    Decimal(transaction_data["amount"]) / 100
                    if transaction_data.get("amount") is not None
                    else None
                )
                if payment is None:
                    payment = await recover_pending_payment_mapping(
                        db,
                        provider="paystack",
                        provider_reference=transaction_data["reference"],
                        transaction_id=transaction_data["reference"],
                        observed_amount=observed_amount,
                        observed_currency=transaction_data.get("currency"),
                        evidence_payload=transaction_data,
                    )
                    payment.gateway_response = paystack_response

            await db.commit()
            await db.refresh(payment)

            if claim_customer:
                try:
                    await email_service.send_payment_receipt_email(
                        email=claim_customer.email,
                        name=claim_customer.full_name,
                        order_number=order.order_number,
                        amount=float(payment.amount),
                        currency=payment.currency,
                        payment_method="Paystack",
                        reference=payment.transaction_id,
                    )
                except Exception as e:
                    print(f"Failed to send payment receipt email: {e}")
                await send_account_claim_email_if_guest(claim_customer)

            return PaymentVerifyResponse(
                status=True,
                message="Payment verification successful",
                data=transaction_data,
            )

        except PaymentRecoveryUnavailable as e:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e)
            )
        except (PaymentBridgeError, PaymentTruthMismatch) as e:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Payment verification error: {str(e)}",
            )


@router.post("/webhook/paystack")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook endpoint for Paystack events

    Paystack sends notifications about payment events to this endpoint.
    We verify the signature and update payment/order status accordingly.
    """
    # Get raw body
    body = await request.body()

    # Verify signature
    if not x_paystack_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No signature provided"
        )
    if not PAYSTACK_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Paystack webhook secret is not configured",
        )

    # Compute HMAC hash
    computed_signature = hmac.new(
        PAYSTACK_SECRET_KEY.encode("utf-8"), body, hashlib.sha512
    ).hexdigest()

    if computed_signature != x_paystack_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature"
        )

    # Parse event
    event_data = await request.json()
    event_type = event_data.get("event")
    data = event_data.get("data", {})

    # Handle charge.success event
    if event_type == "charge.success":
        reference = data.get("reference")

        # Get payment record
        payment_query = select(Payment).where(Payment.transaction_id == reference)
        payment_result = await db.execute(payment_query)
        payment = payment_result.scalar_one_or_none()

        try:
            if payment is None:
                payment, result = await recover_payment_mapping(
                    db,
                    provider="paystack",
                    provider_reference=reference,
                    transaction_id=reference,
                    observed_amount=Decimal(data["amount"]) / 100,
                    observed_currency=data["currency"],
                    event_id=str(data.get("id", reference)),
                    evidence_payload=data,
                )
            else:
                result = await finalize_verified_payment(
                    db,
                    payment=payment,
                    provider="paystack",
                    provider_reference=reference,
                    observed_amount=Decimal(data["amount"]) / 100,
                    observed_currency=data["currency"],
                    event_id=str(data.get("id", reference)),
                    evidence_payload=data,
                )
            payment.gateway_response = event_data
            completed_order = await db.scalar(
                select(Order)
                .options(selectinload(Order.customer))
                .where(Order.id == payment.order_id)
            )
            await db.commit()
            if completed_order and completed_order.customer and not result.replay:
                await send_account_claim_email_if_guest(completed_order.customer)
        except PaymentRecoveryUnavailable as error:
            await db.rollback()
            raise HTTPException(status_code=503, detail=str(error))
        except (PaymentBridgeError, PaymentTruthMismatch) as error:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))

    elif event_type == "charge.failed":
        reference = data.get("reference")
        payment = await db.scalar(
            select(Payment).where(Payment.transaction_id == reference)
        )
        if payment is None or payment.status != TransactionStatus.COMPLETED:
            try:
                if payment is None:
                    payment, _ = await recover_failed_payment_mapping(
                        db,
                        provider="paystack",
                        provider_reference=reference,
                        transaction_id=reference,
                        event_id=str(data.get("id", reference)),
                        evidence_payload=data,
                        failure_reason=data.get("gateway_response") or "Payment failed",
                    )
                else:
                    await finalize_failed_payment(
                        db,
                        payment=payment,
                        provider="paystack",
                        provider_reference=reference,
                        event_id=str(data.get("id", reference)),
                        evidence_payload=data,
                        failure_reason=data.get("gateway_response") or "Payment failed",
                    )
                payment.gateway_response = event_data
                await db.commit()
            except PaymentRecoveryUnavailable as error:
                await db.rollback()
                raise HTTPException(status_code=503, detail=str(error))
            except (PaymentBridgeError, PaymentTruthMismatch) as error:
                await db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=str(error)
                )

    return {"status": "success"}


@router.post("/webhook/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook endpoint for Stripe events

    Stripe sends notifications about payment events to this endpoint.
    """
    body = await request.body()

    try:
        if settings.STRIPE_WEBHOOK_SECRET:
            if not stripe_signature:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing Stripe signature",
                )
            event = stripe.Webhook.construct_event(
                payload=body,
                sig_header=stripe_signature,
                secret=settings.STRIPE_WEBHOOK_SECRET,
            )
        elif settings.ENVIRONMENT.lower() in {"staging", "production"}:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Stripe webhook secret is not configured",
            )
        else:
            event = stripe.Event.construct_from(await request.json(), stripe.api_key)

        # Handle payment_intent.succeeded event
        if event.type == "payment_intent.succeeded":
            payment_intent = event.data.object

            # Get payment record
            payment_query = select(Payment).where(
                Payment.transaction_id == payment_intent.id
            )
            payment_result = await db.execute(payment_query)
            payment = payment_result.scalar_one_or_none()

            authenticated = {
                "event_id": str(event.id),
                "payment_intent_id": payment_intent.id,
                "amount": payment_intent.amount_received,
                "currency": payment_intent.currency,
            }
            provider_reference = (
                payment_intent.metadata.get("shopsoma_payment_reference")
                if getattr(payment_intent, "metadata", None)
                else payment_intent.id
            )
            if payment is None:
                payment, result = await recover_payment_mapping(
                    db,
                    provider="stripe",
                    provider_reference=provider_reference,
                    transaction_id=payment_intent.id,
                    observed_amount=Decimal(payment_intent.amount_received) / 100,
                    observed_currency=payment_intent.currency,
                    event_id=str(event.id),
                    evidence_payload=authenticated,
                )
            else:
                result = await finalize_verified_payment(
                    db,
                    payment=payment,
                    provider="stripe",
                    provider_reference=provider_reference,
                    observed_amount=Decimal(payment_intent.amount_received) / 100,
                    observed_currency=payment_intent.currency,
                    event_id=str(event.id),
                    evidence_payload=authenticated,
                )
            payment.gateway_response = {"payment_intent_id": payment_intent.id}
            completed_order = await db.scalar(
                select(Order)
                .options(selectinload(Order.customer))
                .where(Order.id == payment.order_id)
            )
            await db.commit()
            if completed_order and completed_order.customer and not result.replay:
                await send_account_claim_email_if_guest(completed_order.customer)

        # Cancellation is definitive; payment_failed can still be retryable.
        elif event.type in {
            "payment_intent.canceled",
            "payment_intent.payment_failed",
        }:
            payment_intent = event.data.object

            # Get payment record
            payment_query = select(Payment).where(
                Payment.transaction_id == payment_intent.id
            )
            payment_result = await db.execute(payment_query)
            payment = payment_result.scalar_one_or_none()

            if payment_intent.status == "canceled" and (
                payment is None or payment.status != TransactionStatus.COMPLETED
            ):
                failure_reason = (
                    payment_intent.last_payment_error.message
                    if payment_intent.last_payment_error
                    else "Payment failed"
                )
                provider_reference = (
                    payment_intent.metadata.get("shopsoma_payment_reference")
                    if getattr(payment_intent, "metadata", None)
                    else payment_intent.id
                )
                evidence_payload = {
                    "event_id": str(event.id),
                    "payment_intent_id": payment_intent.id,
                    "status": payment_intent.status,
                }
                if payment is None:
                    payment, _ = await recover_failed_payment_mapping(
                        db,
                        provider="stripe",
                        provider_reference=provider_reference,
                        transaction_id=payment_intent.id,
                        event_id=str(event.id),
                        evidence_payload=evidence_payload,
                        failure_reason=failure_reason,
                    )
                else:
                    await finalize_failed_payment(
                        db,
                        payment=payment,
                        provider="stripe",
                        provider_reference=provider_reference,
                        event_id=str(event.id),
                        evidence_payload=evidence_payload,
                        failure_reason=failure_reason,
                    )

                await db.commit()

        return {"status": "success"}

    except stripe.error.SignatureVerificationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Stripe signature"
        )
    except PaymentRecoveryUnavailable as error:
        await db.rollback()
        raise HTTPException(status_code=503, detail=str(error))
    except (PaymentBridgeError, PaymentTruthMismatch) as error:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error))
    except HTTPException:
        raise
    except Exception as e:
        print(f"Stripe webhook error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Webhook error: {str(e)}"
        )


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get payment details by ID"""
    payment_query = select(Payment).where(Payment.id == payment_id)
    payment_result = await db.execute(payment_query)
    payment = payment_result.scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        )

    # Verify user has access to this payment's order
    order_query = select(Order).where(Order.id == payment.order_id)
    order_result = await db.execute(order_query)
    order = order_result.scalar_one_or_none()

    if order and order.customer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this payment",
        )

    return payment
