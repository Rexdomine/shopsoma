"""Newsletter subscription endpoints"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from brevo_python.rest import ApiException

from app.services.newsletter_service import newsletter_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/newsletter", tags=["Newsletter"])


class NewsletterSubscribeRequest(BaseModel):
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    consent: bool = True


class NewsletterSubscribeResponse(BaseModel):
    message: str


@router.post("/subscribe", response_model=NewsletterSubscribeResponse)
async def subscribe_to_newsletter(payload: NewsletterSubscribeRequest):
    """Subscribe a user to the marketing newsletter via Brevo contacts API."""
    try:
        newsletter_service.subscribe(
            email=payload.email,
            first_name=payload.first_name,
            last_name=payload.last_name,
            consent=payload.consent,
        )
        return NewsletterSubscribeResponse(message="Subscribed successfully")
    except ValueError as exc:
        logger.error("Newsletter configuration error: %s", exc)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
    except ApiException as exc:
        detail = exc.body or exc.reason or "Failed to subscribe to newsletter"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    except Exception as exc:  # pragma: no cover - unexpected failures
        logger.exception("Unexpected error subscribing to newsletter")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to subscribe at this time")
