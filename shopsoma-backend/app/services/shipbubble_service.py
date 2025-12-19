"""
ShipBubble Shipping Integration Service

Official API Docs: https://docs.shipbubble.com

This service handles all interactions with ShipBubble API:
- Fetching shipping rates
- Creating shipments
- Tracking shipments
- Cancelling shipments
"""
import httpx
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from decimal import Decimal

from app.core.config import settings

logger = logging.getLogger(__name__)


class ShipBubbleError(Exception):
    """Custom exception for ShipBubble API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(self.message)


class ShipBubbleService:
    """Service for interacting with ShipBubble shipping API"""

    BASE_URL = "https://api.shipbubble.com/v1"

    def __init__(self):
        self.api_key = settings.SHIPBUBBLE_API_KEY
        if not self.api_key:
            logger.error("❌ [ShipBubble] API key not configured")
            raise ValueError("ShipBubble API key is required")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        logger.info(f"✅ [ShipBubble] Service initialized with API key: {self.api_key[:20]}...")

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request to ShipBubble API with comprehensive error handling

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., "/shipping/fetch_rates")
            data: Request body for POST/PUT requests
            params: Query parameters for GET requests

        Returns:
            Parsed JSON response from ShipBubble API

        Raises:
            ShipBubbleError: On API errors with detailed logging
        """
        url = f"{self.BASE_URL}{endpoint}"

        logger.info(f"📤 [ShipBubble] {method} {endpoint}")
        if data:
            logger.debug(f"📝 [ShipBubble] Request data: {data}")
        if params:
            logger.debug(f"🔍 [ShipBubble] Query params: {params}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=data if method in ["POST", "PUT"] else None,
                    params=params
                )

                logger.info(f"📥 [ShipBubble] Response status: {response.status_code}")

                # Try to parse response JSON
                try:
                    response_data = response.json()
                    logger.debug(f"📄 [ShipBubble] Response data: {response_data}")
                except Exception as json_error:
                    logger.error(f"❌ [ShipBubble] Failed to parse response JSON: {json_error}")
                    logger.error(f"📄 [ShipBubble] Raw response: {response.text[:500]}")
                    response_data = {"raw_response": response.text}

                # Handle error responses
                if response.status_code >= 400:
                    error_message = self._extract_error_message(response_data, response.status_code)
                    logger.error(f"❌ [ShipBubble] API Error: {error_message}")
                    logger.error(f"📄 [ShipBubble] Full error response: {response_data}")

                    raise ShipBubbleError(
                        message=error_message,
                        status_code=response.status_code,
                        response_data=response_data
                    )

                logger.info(f"✅ [ShipBubble] Request successful")
                return response_data

        except httpx.TimeoutException as e:
            logger.error(f"⏱️ [ShipBubble] Request timeout: {str(e)}")
            raise ShipBubbleError("ShipBubble API request timed out after 30 seconds")

        except httpx.NetworkError as e:
            logger.error(f"🌐 [ShipBubble] Network error: {str(e)}")
            raise ShipBubbleError(f"Network error connecting to ShipBubble: {str(e)}")

        except ShipBubbleError:
            # Re-raise our custom errors
            raise

        except Exception as e:
            logger.error(f"💥 [ShipBubble] Unexpected error: {str(e)}", exc_info=True)
            raise ShipBubbleError(f"Unexpected error calling ShipBubble API: {str(e)}")

    def _extract_error_message(self, response_data: Dict, status_code: int) -> str:
        """Extract error message from ShipBubble API response"""

        # Common error field names in APIs
        error_fields = ['message', 'error', 'detail', 'error_message', 'description']

        for field in error_fields:
            if field in response_data:
                return f"ShipBubble API Error ({status_code}): {response_data[field]}"

        # If no standard error field, return generic message
        return f"ShipBubble API Error ({status_code}): {response_data}"

    async def create_address(
        self,
        name: str,
        phone: str,
        email: str,
        address: str,
        city: str,
        state: str,
        country: str = "Nigeria",
        postal_code: str = ""
    ) -> str:
        """
        Create an address in ShipBubble and get address code

        Args:
            name: Contact name
            phone: Phone number
            email: Email address
            address: Street address
            city: City
            state: State/Province
            country: Country (default: Nigeria)
            postal_code: Postal/ZIP code

        Returns:
            Address code (string like "SB-ADDR-XXX") to use in rate/shipment requests
        """
        logger.info(f"📍 [ShipBubble] Creating address for {name} in {city}, {state}")

        try:
            payload = {
                "name": name,
                "phone": phone,
                "email": email,
                "address": address,
                "city": city,
                "state": state,
                "country": country,
                "postal_code": postal_code
            }

            response = await self._make_request("POST", "/addresses/create", data=payload)

            # Extract address code from response
            # ShipBubble returns: {"status": true, "data": {"code": "SB-ADDR-XXX", ...}}
            data = response.get("data", {})
            address_code = data.get("code") or data.get("address_code") or response.get("code") or response.get("address_code")

            if not address_code:
                logger.error(f"❌ [ShipBubble] No address code in response: {response}")
                raise ShipBubbleError("Failed to get address code from ShipBubble response")

            logger.info(f"✅ [ShipBubble] Address created with code: {address_code}")
            # Address code is a string like "SB-ADDR-123", not an integer
            return address_code

        except ShipBubbleError:
            raise
        except Exception as e:
            logger.error(f"💥 [ShipBubble] Error creating address: {str(e)}", exc_info=True)
            raise ShipBubbleError(f"Failed to create address: {str(e)}")

    async def get_shipping_rates(
        self,
        sender_address_code: str,
        receiver_address_code: str,
        pickup_date: str,
        category_id: int,
        package_items: List[Dict[str, Any]],
        package_dimension: Dict[str, float],
        service_type: Optional[str] = None,
        delivery_instructions: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch shipping rates from ShipBubble

        Args:
            sender_address_code: Address code from create_address() for sender (string like "SB-ADDR-XXX")
            receiver_address_code: Address code from create_address() for receiver (string like "SB-ADDR-XXX")
            pickup_date: Pickup date in format "YYYY-MM-DD"
            category_id: Package category ID (get from categories API)
            package_items: List of items with keys: name, description, unit_weight (kg), unit_amount, quantity
            package_dimension: Dict with keys: length, width, height (all in CM)
            service_type: Optional - "dropoff" or "pickup"
            delivery_instructions: Optional delivery notes

        Returns:
            List of shipping rate options with courier, price, delivery_time

        Example response:
            [
                {
                    "courier": "DHL",
                    "service_code": "dhl_express",
                    "price": 2500.00,
                    "currency": "NGN",
                    "estimated_days": 2,
                    "description": "Express delivery"
                }
            ]
        """
        logger.info(f"🚚 [ShipBubble] Fetching shipping rates")
        logger.debug(f"📍 [ShipBubble] Sender address code: {sender_address_code}")
        logger.debug(f"📍 [ShipBubble] Receiver address code: {receiver_address_code}")
        logger.debug(f"📦 [ShipBubble] Pickup date: {pickup_date}")

        try:
            payload = {
                "sender_address_code": sender_address_code,
                "reciever_address_code": receiver_address_code,  # Note: ShipBubble API uses "reciever" (sic)
                "pickup_date": pickup_date,
                "category_id": category_id,
                "package_items": package_items,
                "package_dimension": package_dimension
            }

            if service_type:
                payload["service_type"] = service_type
            if delivery_instructions:
                payload["delivery_instructions"] = delivery_instructions

            response = await self._make_request("POST", "/shipping/fetch_rates", data=payload)

            # Parse rates from response
            rates = self._parse_rates_response(response)

            logger.info(f"✅ [ShipBubble] Retrieved {len(rates)} shipping rates")
            for rate in rates:
                logger.debug(f"💰 [ShipBubble] {rate['courier']}: ₦{rate['price']} ({rate['estimated_days']} days)")

            return rates

        except ShipBubbleError as e:
            logger.error(f"❌ [ShipBubble] Failed to fetch rates: {e.message}")
            # Return empty list on error - caller should handle gracefully
            return []

        except Exception as e:
            logger.error(f"💥 [ShipBubble] Unexpected error fetching rates: {str(e)}", exc_info=True)
            return []

    def _parse_rates_response(self, response: Dict) -> List[Dict[str, Any]]:
        """Parse ShipBubble rates response into standardized format"""

        # ShipBubble response structure (adjust based on actual API response)
        rates = []

        # Assuming response has 'rates' or 'data' key with list of rate options
        rate_data = response.get('rates') or response.get('data') or []

        if not isinstance(rate_data, list):
            rate_data = [rate_data] if rate_data else []

        for rate in rate_data:
            rates.append({
                "courier": rate.get("courier_name") or rate.get("courier"),
                "service_code": rate.get("service_code") or rate.get("code"),
                "price": float(rate.get("price") or rate.get("amount") or 0),
                "currency": rate.get("currency", "NGN"),
                "estimated_days": int(rate.get("estimated_days") or rate.get("delivery_time") or 3),
                "description": rate.get("description") or rate.get("service_name") or ""
            })

        return rates

    async def create_shipment(
        self,
        order_number: str,
        sender: Dict[str, Any],
        receiver: Dict[str, Any],
        items: List[Dict[str, Any]],
        service_code: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a shipment in ShipBubble

        Args:
            order_number: Unique order reference
            sender: Sender details (name, phone, address, city, state, country)
            receiver: Receiver details (name, phone, address, city, state, country)
            items: List of items (name, quantity, value, weight)
            service_code: Shipping service code from rates response
            **kwargs: Additional options (insurance, pickup_date, etc.)

        Returns:
            Shipment details including shipment_id and tracking_number

        Example response:
            {
                "shipment_id": "SB123456",
                "tracking_number": "TRACK123456",
                "label_url": "https://...",
                "status": "pending_pickup"
            }
        """
        logger.info(f"📦 [ShipBubble] Creating shipment for order {order_number}")
        logger.debug(f"🚚 [ShipBubble] Service: {service_code}")
        logger.debug(f"📍 [ShipBubble] Sender: {sender.get('name')} ({sender.get('city')})")
        logger.debug(f"📍 [ShipBubble] Receiver: {receiver.get('name')} ({receiver.get('city')})")

        try:
            payload = {
                "order_reference": order_number,
                "service_code": service_code,
                "sender": {
                    "name": sender.get("name"),
                    "phone": sender.get("phone"),
                    "email": sender.get("email", ""),
                    "address": sender.get("address"),
                    "city": sender.get("city"),
                    "state": sender.get("state"),
                    "country": sender.get("country", "Nigeria"),
                    "postal_code": sender.get("postal_code", "")
                },
                "receiver": {
                    "name": receiver.get("name"),
                    "phone": receiver.get("phone"),
                    "email": receiver.get("email", ""),
                    "address": receiver.get("address"),
                    "city": receiver.get("city"),
                    "state": receiver.get("state"),
                    "country": receiver.get("country", "Nigeria"),
                    "postal_code": receiver.get("postal_code", "")
                },
                "items": [
                    {
                        "name": item.get("name"),
                        "quantity": item.get("quantity", 1),
                        "value": float(item.get("value", 0)),
                        "weight": float(item.get("weight", 0.5)),
                        "description": item.get("description", "")
                    }
                    for item in items
                ],
                **kwargs  # pickup_date, insurance_value, etc.
            }

            response = await self._make_request("POST", "/shipping/create", data=payload)

            shipment_data = self._parse_shipment_response(response)

            logger.info(f"✅ [ShipBubble] Shipment created: {shipment_data['shipment_id']}")
            logger.info(f"🔢 [ShipBubble] Tracking: {shipment_data.get('tracking_number')}")

            return shipment_data

        except ShipBubbleError as e:
            logger.error(f"❌ [ShipBubble] Failed to create shipment: {e.message}")
            logger.error(f"📄 [ShipBubble] Error details: {e.response_data}")
            raise

        except Exception as e:
            logger.error(f"💥 [ShipBubble] Unexpected error creating shipment: {str(e)}", exc_info=True)
            raise ShipBubbleError(f"Failed to create shipment: {str(e)}")

    def _parse_shipment_response(self, response: Dict) -> Dict[str, Any]:
        """Parse ShipBubble shipment creation response"""

        # Extract data from response (adjust based on actual API response)
        data = response.get('data') or response

        return {
            "shipment_id": data.get("shipment_id") or data.get("id"),
            "tracking_number": data.get("tracking_number") or data.get("tracking_code"),
            "label_url": data.get("label_url") or data.get("shipping_label"),
            "status": data.get("status", "pending"),
            "courier": data.get("courier_name") or data.get("courier"),
            "created_at": data.get("created_at"),
            "raw_response": response  # Store full response for debugging
        }

    async def track_shipment(self, tracking_number: str) -> Dict[str, Any]:
        """
        Track a shipment using tracking number

        Args:
            tracking_number: ShipBubble tracking number

        Returns:
            Tracking information with current status and history

        Example response:
            {
                "tracking_number": "TRACK123",
                "status": "in_transit",
                "current_location": "Lagos",
                "estimated_delivery": "2025-12-20",
                "history": [...]
            }
        """
        logger.info(f"🔍 [ShipBubble] Tracking shipment: {tracking_number}")

        try:
            response = await self._make_request("GET", f"/shipping/track/{tracking_number}")

            tracking_data = self._parse_tracking_response(response)

            logger.info(f"✅ [ShipBubble] Tracking status: {tracking_data['status']}")
            logger.debug(f"📍 [ShipBubble] Current location: {tracking_data.get('current_location')}")

            return tracking_data

        except ShipBubbleError as e:
            logger.error(f"❌ [ShipBubble] Failed to track shipment: {e.message}")
            raise

        except Exception as e:
            logger.error(f"💥 [ShipBubble] Unexpected error tracking shipment: {str(e)}", exc_info=True)
            raise ShipBubbleError(f"Failed to track shipment: {str(e)}")

    def _parse_tracking_response(self, response: Dict) -> Dict[str, Any]:
        """Parse ShipBubble tracking response"""

        data = response.get('data') or response

        return {
            "tracking_number": data.get("tracking_number"),
            "status": data.get("status"),
            "current_location": data.get("current_location") or data.get("location"),
            "estimated_delivery": data.get("estimated_delivery_date") or data.get("eta"),
            "last_updated": data.get("last_updated") or data.get("updated_at"),
            "history": data.get("tracking_history") or data.get("history") or [],
            "raw_response": response
        }

    async def cancel_shipment(self, shipment_id: str, reason: Optional[str] = None) -> bool:
        """
        Cancel a shipment in ShipBubble

        Args:
            shipment_id: ShipBubble shipment ID
            reason: Optional cancellation reason

        Returns:
            True if successfully cancelled
        """
        logger.info(f"❌ [ShipBubble] Cancelling shipment: {shipment_id}")
        if reason:
            logger.debug(f"📝 [ShipBubble] Reason: {reason}")

        try:
            payload = {"reason": reason} if reason else {}

            response = await self._make_request(
                "POST",
                f"/shipping/cancel/{shipment_id}",
                data=payload
            )

            logger.info(f"✅ [ShipBubble] Shipment cancelled successfully")
            return True

        except ShipBubbleError as e:
            logger.error(f"❌ [ShipBubble] Failed to cancel shipment: {e.message}")
            return False

        except Exception as e:
            logger.error(f"💥 [ShipBubble] Unexpected error cancelling shipment: {str(e)}", exc_info=True)
            return False


# Singleton instance
_shipbubble_service = None

def get_shipbubble_service() -> ShipBubbleService:
    """Get or create ShipBubble service instance"""
    global _shipbubble_service
    if _shipbubble_service is None:
        _shipbubble_service = ShipBubbleService()
    return _shipbubble_service
