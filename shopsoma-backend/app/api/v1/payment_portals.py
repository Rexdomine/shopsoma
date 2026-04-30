"""
Payment Portal API endpoints for Paystack and Stripe customer portals
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.api.dependencies import get_current_active_user
from app.models.user import User
from app.schemas.payment import CustomerPortalResponse
import stripe
import requests

router = APIRouter()

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY

# Paystack configuration
PAYSTACK_SECRET_KEY = settings.PAYSTACK_SECRET_KEY
PAYSTACK_API_BASE = "https://api.paystack.co"


@router.post("/paystack/customer-portal", response_model=CustomerPortalResponse)
async def get_paystack_customer_portal(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Generate Paystack customer portal URL for managing payment methods.

    Paystack doesn't have a built-in customer portal like Stripe,
    so we redirect users to save their cards via a payment page.
    """
    try:
        if not PAYSTACK_SECRET_KEY:
            raise HTTPException(
                status_code=500,
                detail="Paystack is not configured. Please contact support."
            )

        headers = {
            "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json"
        }

        # Initialize a transaction for card authorization (minimum 100 kobo)
        payload = {
            "email": current_user.email,
            "amount": 100,  # 1 NGN (100 kobo) - minimum for card authorization
            "callback_url": settings.FRONTEND_BASE_URL + "/profile/payments?paystack=success",
            "metadata": {
                "custom_fields": [
                    {
                        "display_name": "Purpose",
                        "variable_name": "purpose",
                        "value": "Card Authorization"
                    }
                ],
                "cancel_action": settings.FRONTEND_BASE_URL + "/profile/payments"
            },
            "channels": ["card"],
        }

        response = requests.post(
            f"{PAYSTACK_API_BASE}/transaction/initialize",
            json=payload,
            headers=headers,
            timeout=10
        )

        response_data = response.json()

        if response.status_code != 200:
            error_message = response_data.get("message", "Unknown error from Paystack")
            raise HTTPException(
                status_code=500,
                detail=f"Paystack API error: {error_message}"
            )

        if not response_data.get("status"):
            error_message = response_data.get("message", "Failed to create Paystack session")

            # Provide helpful message for common Paystack setup issues
            if "no active channel" in error_message.lower():
                raise HTTPException(
                    status_code=503,
                    detail="Paystack card payments are currently unavailable. The merchant account needs to be activated. Please contact support or use Stripe for now."
                )

            raise HTTPException(
                status_code=500,
                detail=f"Paystack error: {error_message}"
            )

        portal_url = response_data["data"]["authorization_url"]

        return CustomerPortalResponse(
            url=portal_url,
            provider="paystack"
        )

    except HTTPException:
        raise
    except requests.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Network error connecting to Paystack: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


@router.post("/stripe/customer-portal", response_model=CustomerPortalResponse)
async def get_stripe_customer_portal(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Generate Stripe customer portal URL for managing payment methods,
    subscriptions, and billing history.
    """
    try:
        # Get or create Stripe customer ID
        stripe_customer_id = current_user.stripe_customer_id

        if not stripe_customer_id:
            # Create a new Stripe customer
            customer = stripe.Customer.create(
                email=current_user.email,
                name=current_user.full_name,
                metadata={
                    "user_id": str(current_user.id)
                }
            )
            stripe_customer_id = customer.id

            # Update user with Stripe customer ID
            current_user.stripe_customer_id = stripe_customer_id
            db.commit()

        # Create Stripe billing portal session
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=settings.FRONTEND_BASE_URL + "/profile/payments",
        )

        return CustomerPortalResponse(
            url=session.url,
            provider="stripe"
        )

    except stripe.error.StripeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Stripe error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create Stripe customer portal: {str(e)}"
        )
