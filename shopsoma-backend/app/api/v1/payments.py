"""Payment endpoints for Paystack integration"""
import hmac
import hashlib
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from uuid import UUID
from decimal import Decimal
import httpx

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.order import Order, PaymentStatus, FulfillmentStatus
from app.models.payment import Payment, PaymentGateway, TransactionStatus
from app.schemas.payment import (
    PaymentInitializeRequest,
    PaymentInitializeResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
    PaymentWebhookEvent,
    PaymentResponse,
)
from app.api.dependencies import get_current_active_user, get_optional_user

router = APIRouter(prefix="/payments", tags=["Payments"])

# Paystack configuration from settings
PAYSTACK_SECRET_KEY = settings.PAYSTACK_SECRET_KEY
PAYSTACK_BASE_URL = "https://api.paystack.co"


@router.post("/initialize", response_model=PaymentInitializeResponse)
async def initialize_payment(
    payment_data: PaymentInitializeRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Initialize a Paystack payment for an order

    This creates a payment session with Paystack and returns a URL
    where the customer can complete the payment.
    """
    # Get order
    order_query = select(Order).where(Order.id == payment_data.order_id)

    # If authenticated, verify order ownership
    if current_user:
        order_query = order_query.where(Order.customer_id == current_user.id)

    order_result = await db.execute(order_query)
    order = order_result.scalar_one_or_none()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found"
        )

    # Check if order is already paid
    if order.payment_status == PaymentStatus.PAID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order has already been paid"
        )

    # Generate unique reference
    reference = f"SHP-{order.order_number}"

    # Prepare Paystack request
    # Amount must be in kobo (multiply by 100)
    amount_in_kobo = int(order.total_amount * 100)

    payload = {
        "email": payment_data.email,
        "amount": amount_in_kobo,
        "reference": reference,
        "currency": "NGN",
        "callback_url": payment_data.callback_url or f"http://localhost:5173/payment/verify",
        "metadata": {
            "order_id": str(order.id),
            "order_number": order.order_number,
            "customer_name": payment_data.email,
        }
    }

    # Call Paystack API
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{PAYSTACK_BASE_URL}/transaction/initialize",
                json=payload,
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            paystack_response = response.json()

            if not paystack_response.get("status"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=paystack_response.get("message", "Payment initialization failed")
                )

            # Create payment record
            payment = Payment(
                order_id=order.id,
                transaction_id=reference,
                payment_gateway=PaymentGateway.PAYSTACK,
                payment_method="paystack",
                amount=order.total_amount,
                currency="NGN",
                status=TransactionStatus.PENDING,
                gateway_response=paystack_response
            )

            db.add(payment)
            await db.commit()

            data = paystack_response["data"]
            return PaymentInitializeResponse(
                status=True,
                message="Payment session created successfully",
                authorization_url=data["authorization_url"],
                access_code=data["access_code"],
                reference=data["reference"]
            )

        except httpx.HTTPStatusError as e:
            # Log the error response from Paystack
            error_detail = e.response.text if hasattr(e, 'response') else str(e)
            print(f"Paystack API Error: {error_detail}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Payment service error: {error_detail}"
            )
        except httpx.HTTPError as e:
            print(f"HTTP Error: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Payment service error: {str(e)}"
            )


@router.post("/verify", response_model=PaymentVerifyResponse)
async def verify_payment(
    verify_data: PaymentVerifyRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify a payment with Paystack

    This endpoint is called after the customer completes payment
    to verify the transaction status.
    """
    # Call Paystack verify endpoint
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{PAYSTACK_BASE_URL}/transaction/verify/{verify_data.reference}",
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            paystack_response = response.json()

            if not paystack_response.get("status"):
                return PaymentVerifyResponse(
                    status=False,
                    message=paystack_response.get("message", "Verification failed"),
                    data=None
                )

            transaction_data = paystack_response["data"]

            # Get payment record
            payment_query = select(Payment).where(
                Payment.transaction_id == verify_data.reference
            )
            payment_result = await db.execute(payment_query)
            payment = payment_result.scalar_one_or_none()

            if not payment:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Payment record not found"
                )

            # Update payment status
            if transaction_data["status"] == "success":
                payment.status = TransactionStatus.COMPLETED
                payment.gateway_response = paystack_response
                payment.completed_at = func.now()

                # Update order payment status
                await db.execute(
                    update(Order)
                    .where(Order.id == payment.order_id)
                    .values(
                        payment_status=PaymentStatus.PAID,
                        fulfillment_status=FulfillmentStatus.PROCESSING
                    )
                )
            elif transaction_data["status"] == "failed":
                payment.status = TransactionStatus.FAILED
                payment.gateway_response = paystack_response
                payment.failed_at = func.now()
                payment.failure_reason = transaction_data.get("gateway_response")

                await db.execute(
                    update(Order)
                    .where(Order.id == payment.order_id)
                    .values(payment_status=PaymentStatus.FAILED)
                )

            await db.commit()
            await db.refresh(payment)

            return PaymentVerifyResponse(
                status=True,
                message="Payment verification successful",
                data=transaction_data
            )

        except httpx.HTTPError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Payment verification error: {str(e)}"
            )


@router.post("/webhook")
async def paystack_webhook(
    request: Request,
    x_paystack_signature: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
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
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No signature provided"
        )

    # Compute HMAC hash
    computed_signature = hmac.new(
        PAYSTACK_SECRET_KEY.encode('utf-8'),
        body,
        hashlib.sha512
    ).hexdigest()

    if computed_signature != x_paystack_signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature"
        )

    # Parse event
    event_data = await request.json()
    event_type = event_data.get("event")
    data = event_data.get("data", {})

    # Handle charge.success event
    if event_type == "charge.success":
        reference = data.get("reference")

        # Get payment record
        payment_query = select(Payment).where(
            Payment.transaction_id == reference
        )
        payment_result = await db.execute(payment_query)
        payment = payment_result.scalar_one_or_none()

        if payment and payment.status != TransactionStatus.COMPLETED:
            payment.status = TransactionStatus.COMPLETED
            payment.gateway_response = event_data
            payment.completed_at = func.now()

            # Update order
            await db.execute(
                update(Order)
                .where(Order.id == payment.order_id)
                .values(
                    payment_status=PaymentStatus.PAID,
                    fulfillment_status=FulfillmentStatus.PROCESSING
                )
            )

            await db.commit()

    return {"status": "success"}


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db)
):
    """Get payment details by ID"""
    payment_query = select(Payment).where(Payment.id == payment_id)
    payment_result = await db.execute(payment_query)
    payment = payment_result.scalar_one_or_none()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found"
        )

    # Verify user has access to this payment's order
    order_query = select(Order).where(Order.id == payment.order_id)
    order_result = await db.execute(order_query)
    order = order_result.scalar_one_or_none()

    if order and order.customer_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this payment"
        )

    return payment
