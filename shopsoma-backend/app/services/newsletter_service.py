"""Newsletter service using Brevo Contacts API"""
import logging
from typing import Optional

import brevo_python
from brevo_python.rest import ApiException

from app.core.config import settings

logger = logging.getLogger(__name__)


class NewsletterService:
    """Service responsible for managing newsletter subscriptions."""

    def __init__(self) -> None:
        configuration = brevo_python.Configuration()
        configuration.api_key['api-key'] = settings.BREVO_API_KEY
        self.api_client = brevo_python.ApiClient(configuration)
        self.contacts_api = brevo_python.ContactsApi(self.api_client)
        self.list_id = settings.BREVO_NEWSLETTER_LIST_ID

    def subscribe(self, *, email: str, first_name: Optional[str] = None, last_name: Optional[str] = None, consent: bool = True) -> None:
        if not settings.BREVO_API_KEY:
            raise ValueError('Brevo API key is not configured')
        attributes = {
            "FIRSTNAME": first_name or "",
            "LASTNAME": last_name or "",
            "CONSENT": "true" if consent else "false",
            "SOURCE": "Shopsoma Website",
        }

        payload_kwargs = {
            "email": email,
            "attributes": attributes,
            "update_enabled": True,
        }
        if self.list_id:
            payload_kwargs["list_ids"] = [self.list_id]
        else:
            logger.warning("BREVO_NEWSLETTER_LIST_ID is not configured. Contact will be saved without list association.")

        contact = brevo_python.CreateContact(**payload_kwargs)

        try:
            self.contacts_api.create_contact(contact)
            logger.info("Subscribed %s to newsletter list %s", email, self.list_id)
        except ApiException as exc:
            logger.error("Brevo API error subscribing %s: %s", email, exc)
            raise
        except Exception as exc:  # pragma: no cover - unexpected errors
            logger.exception("Unexpected error subscribing %s", email)
            raise exc


newsletter_service = NewsletterService()
