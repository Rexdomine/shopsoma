"""
ShipBubble Shipping Integration Service

Official API Docs: https://docs.shipbubble.com
Base URL: https://api.shipbubble.com/v1

This service handles all interactions with the ShipBubble API:
- Validating addresses (returns address_code)
- Fetching live courier shipping rates (returns request_token and couriers)
- Booking shipping labels (/shipping/labels)
- Tracking shipments (/shipping/labels/list/:order_ids)
- Cancelling scheduled shipments (/shipping/labels/cancel/:order_id)
- Wallet balance checking
- Webhook simulation in sandbox
"""

import asyncio
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import logging
import re
import socket
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_CENT = Decimal("0.01")

_ORIG_GETADDRINFO = socket.getaddrinfo
_DNS_CACHE: Dict[tuple, list] = {}
_SHIPBUBBLE_FALLBACK_IPS = ("104.21.51.145", "172.67.181.106")
_ADDRESS_VALIDATION_CACHE: Dict[tuple, Dict[str, Any]] = {}


def _resilient_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    """Resilient getaddrinfo that prefers IPv4 and caches/falls back for api.shipbubble.com
    when Windows/ISP DNS intermittently fails with WSATRY_AGAIN (Errno 11002).
    """
    is_shipbubble = host in ("api.shipbubble.com", b"api.shipbubble.com")
    p = int(port) if port and str(port).isdigit() else 443
    cache_key = (str(host), p)
    try:
        effective_family = socket.AF_INET if (is_shipbubble and family == 0) else family
        res = _ORIG_GETADDRINFO(host, port, effective_family, type, proto, flags)
        if is_shipbubble and res:
            _DNS_CACHE[cache_key] = res
        return res
    except socket.gaierror as exc:
        if is_shipbubble:
            logger.warning("[ShipBubble] DNS lookup failed (%s); using cached/Cloudflare IPv4 fallback", exc)
            if cache_key in _DNS_CACHE:
                return _DNS_CACHE[cache_key]
            sock_type = type or socket.SOCK_STREAM
            sock_proto = proto or socket.IPPROTO_TCP
            return [
                (socket.AF_INET, sock_type, sock_proto, "", (ip, p))
                for ip in _SHIPBUBBLE_FALLBACK_IPS
            ]
        raise


if getattr(socket.getaddrinfo, "__name__", "") != "_resilient_getaddrinfo":
    socket.getaddrinfo = _resilient_getaddrinfo


class ShipBubbleError(Exception):
    """Custom exception for ShipBubble API errors"""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_data: Optional[Dict[str, Any]] = None,
        errors: Optional[List[str]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data or {}
        self.errors = errors or []
        super().__init__(self.message)


@dataclass(frozen=True)
class ShipbubbleRateOption:
    courier_id: str
    courier_name: str
    service_code: str
    rate_card_amount: Decimal  # Customer-facing charge
    total_wallet_amount: Decimal  # Debited from shipping wallet
    currency: str
    delivery_eta: str
    min_delivery_days: Optional[int]
    max_delivery_days: Optional[int]
    courier_image: Optional[str] = None
    service_type: str = "pickup"


@dataclass(frozen=True)
class ShipbubbleRatesResult:
    request_token: str
    couriers: List[ShipbubbleRateOption]
    cheapest_courier: Optional[ShipbubbleRateOption] = None
    fastest_courier: Optional[ShipbubbleRateOption] = None


@dataclass(frozen=True)
class ShipbubbleShipmentResult:
    order_id: str  # e.g. "SB-2CF48224272"
    status: str
    courier_name: str
    tracking_code: Optional[str] = None
    tracking_url: Optional[str] = None
    waybill_document_url: Optional[str] = None
    shipping_fee: Optional[Decimal] = None
    currency: str = "NGN"
    raw_response: Optional[Dict[str, Any]] = None


def parse_eta_days(eta_str: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """Parse delivery ETA string (e.g. 'Within 1 - 4 working days', 'Same day delivery', 'Within 23 hrs')

    Returns (min_days, max_days)
    """
    if not eta_str:
        return None, None
    lower = eta_str.lower()
    if "same day" in lower or "within 24 hr" in lower or "within 23 hr" in lower or "within 12 hr" in lower:
        return 0, 1
    # Match pattern like "1 - 4 working days" or "1-4 days"
    range_match = re.search(r"(\d+)\s*(?:-|to)\s*(\d+)\s*(?:working|business)?\s*days?", lower)
    if range_match:
        min_d = int(range_match.group(1))
        max_d = int(range_match.group(2))
        return min_d, max_d
    # Match single day pattern like "within 2 days" or "2 working days"
    single_match = re.search(r"(\d+)\s*(?:working|business)?\s*days?", lower)
    if single_match:
        days = int(single_match.group(1))
        return 1, max(1, days)
    return None, None


class ShipBubbleService:
    """Service for interacting with ShipBubble shipping API"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self.api_key = (api_key or settings.SHIPBUBBLE_API_KEY).strip()
        self.base_url = (base_url or settings.SHIPBUBBLE_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.SHIPBUBBLE_TIMEOUT_SECONDS
        self.transport = transport

    def _get_headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ShipBubbleError("ShipBubble API key is not configured", status_code=401)
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request to ShipBubble API with retry logic, strict error handling, and no credential logging."""
        headers = self._get_headers()
        url = f"{self.base_url}{endpoint}"
        max_attempts = 1 if self.transport is not None else 3

        for attempt in range(1, max_attempts + 1):
            try:
                effective_transport = (
                    self.transport
                    if self.transport is not None
                    else httpx.AsyncHTTPTransport(retries=2)
                )
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    transport=effective_transport,
                ) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        json=data if method in ["POST", "PUT", "PATCH"] else None,
                        params=params,
                    )

                    try:
                        response_json = response.json()
                    except Exception:
                        response_json = {"raw_response": response.text}

                    if response.status_code >= 400:
                        errors = response_json.get("errors") if isinstance(response_json.get("errors"), list) else []
                        msg = response_json.get("message") or response.text or f"HTTP {response.status_code}"
                        if errors:
                            msg = f"{msg}: {', '.join(errors)}"
                        logger.warning("[ShipBubble] API %s %s error: status=%s message=%s", method, endpoint, response.status_code, msg)
                        raise ShipBubbleError(
                            message=f"ShipBubble API error ({response.status_code}): {msg}",
                            status_code=response.status_code,
                            response_data=response_json,
                            errors=errors,
                        )

                    if response_json.get("status") == "failed":
                        msg = response_json.get("message") or "ShipBubble request indicated failure"
                        errors = response_json.get("errors") or []
                        logger.warning("[ShipBubble] API %s %s returned failed status: %s", method, endpoint, msg)
                        raise ShipBubbleError(
                            message=f"ShipBubble request failed: {msg}",
                            status_code=response.status_code,
                            response_data=response_json,
                            errors=errors,
                        )

                    return response_json

            except httpx.TimeoutException as exc:
                if attempt < max_attempts:
                    logger.warning("[ShipBubble] Timeout on %s %s (attempt %s/%s), retrying...", method, endpoint, attempt, max_attempts)
                    await asyncio.sleep(0.4 * attempt)
                    continue
                logger.error("[ShipBubble] Request timed out on %s %s after %ss", method, endpoint, self.timeout)
                raise ShipBubbleError(f"ShipBubble API request timed out after {self.timeout}s") from exc
            except httpx.NetworkError as exc:
                if attempt < max_attempts:
                    logger.warning("[ShipBubble] Network error on %s %s (attempt %s/%s): %s, retrying...", method, endpoint, attempt, max_attempts, exc)
                    await asyncio.sleep(0.4 * attempt)
                    continue
                logger.error("[ShipBubble] Network error connecting to ShipBubble on %s %s: %s", method, endpoint, exc)
                raise ShipBubbleError(f"Network error connecting to ShipBubble: {exc}") from exc
            except ShipBubbleError:
                raise
            except Exception as exc:
                logger.error("[ShipBubble] Unexpected error on %s %s: %s", method, endpoint, exc, exc_info=True)
                raise ShipBubbleError(f"Unexpected error communicating with ShipBubble: {exc}") from exc

        raise ShipBubbleError("ShipBubble API request failed after retries")

    async def validate_address(
        self,
        *,
        name: str,
        email: str,
        phone: str,
        address: str,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Validate an address via POST /shipping/address/validate.

        Returns data dict including 'address_code' (int).
        """
        cache_key = (
            name.strip().lower(),
            email.strip().lower(),
            phone.strip(),
            address.strip().lower(),
        )
        if self.transport is None and cache_key in _ADDRESS_VALIDATION_CACHE:
            return _ADDRESS_VALIDATION_CACHE[cache_key]

        payload: Dict[str, Any] = {
            "name": name.strip(),
            "email": email.strip(),
            "phone": phone.strip(),
            "address": address.strip(),
        }
        if latitude is not None and longitude is not None:
            payload["latitude"] = latitude
            payload["longitude"] = longitude

        res = await self._make_request("POST", "/shipping/address/validate", data=payload)
        data = res.get("data")
        if not data or "address_code" not in data:
            raise ShipBubbleError(
                "Address validation succeeded but no address_code was returned",
                response_data=res,
            )
        if self.transport is None:
            _ADDRESS_VALIDATION_CACHE[cache_key] = data
        return data

    async def get_categories(self) -> List[Dict[str, Any]]:
        """Fetch package categories via GET /shipping/labels/categories."""
        res = await self._make_request("GET", "/shipping/labels/categories")
        data = res.get("data")
        if isinstance(data, list):
            return data
        return []

    async def get_package_dimensions(self) -> List[Dict[str, Any]]:
        """Fetch preset package dimensions via GET /shipping/labels/boxes."""
        res = await self._make_request("GET", "/shipping/labels/boxes")
        data = res.get("data")
        if isinstance(data, list):
            return data
        return []

    async def fetch_rates(
        self,
        *,
        sender_address_code: int,
        receiver_address_code: int,
        pickup_date: str,
        category_id: int,
        package_items: List[Dict[str, Any]],
        package_dimension: Dict[str, Any],
        service_type: Optional[str] = None,
        delivery_instructions: Optional[str] = None,
        service_codes: Optional[List[str]] = None,
    ) -> ShipbubbleRatesResult:
        """Fetch live shipping rates from ShipBubble.

        Endpoint: POST /shipping/fetch_rates (or /shipping/fetch_rates/:service_codes)
        Note: The official API spelling is 'reciever_address_code'.
        """
        payload: Dict[str, Any] = {
            "sender_address_code": int(sender_address_code),
            "reciever_address_code": int(receiver_address_code),
            "pickup_date": pickup_date,
            "category_id": int(category_id),
            "package_items": package_items,
            "package_dimension": package_dimension,
        }
        if service_type:
            payload["service_type"] = service_type
        if delivery_instructions:
            payload["delivery_instructions"] = delivery_instructions

        endpoint = "/shipping/fetch_rates"
        if service_codes:
            joined = ",".join(s.strip() for s in service_codes if s.strip())
            if joined:
                endpoint = f"/shipping/fetch_rates/{joined}"

        res = await self._make_request("POST", endpoint, data=payload)
        data = res.get("data") or {}
        request_token = data.get("request_token")
        if not request_token:
            raise ShipBubbleError(
                "Rate request returned without request_token",
                response_data=res,
            )

        raw_couriers = data.get("couriers") or []
        couriers: List[ShipbubbleRateOption] = []
        for raw in raw_couriers:
            parsed = self._parse_courier_option(raw)
            if parsed:
                couriers.append(parsed)

        cheapest = self._parse_courier_option(data.get("cheapest_courier")) if data.get("cheapest_courier") else None
        fastest = self._parse_courier_option(data.get("fastest_courier")) if data.get("fastest_courier") else None

        return ShipbubbleRatesResult(
            request_token=request_token,
            couriers=couriers,
            cheapest_courier=cheapest,
            fastest_courier=fastest,
        )

    def _parse_courier_option(self, raw: Any) -> Optional[ShipbubbleRateOption]:
        if not isinstance(raw, dict):
            return None
        courier_id = str(raw.get("courier_id") or "")
        courier_name = str(raw.get("courier_name") or "")
        service_code = str(raw.get("service_code") or "")
        if not courier_id or not service_code:
            return None

        # Customer display amount is rate_card_amount; wallet debit is total
        raw_rate_card = raw.get("rate_card_amount")
        if raw_rate_card is None:
            raw_rate_card = raw.get("total") or 0
        raw_total = raw.get("total")
        if raw_total is None:
            raw_total = raw_rate_card

        rate_card = Decimal(str(raw_rate_card)).quantize(_CENT, rounding=ROUND_HALF_UP)
        total_wallet = Decimal(str(raw_total)).quantize(_CENT, rounding=ROUND_HALF_UP)
        currency = str(raw.get("currency") or "NGN").replace("₦", "NGN").strip()
        eta = str(raw.get("delivery_eta") or "")
        min_days, max_days = parse_eta_days(eta)

        return ShipbubbleRateOption(
            courier_id=courier_id,
            courier_name=courier_name,
            service_code=service_code,
            rate_card_amount=rate_card,
            total_wallet_amount=total_wallet,
            currency=currency,
            delivery_eta=eta,
            min_delivery_days=min_days,
            max_delivery_days=max_days,
            courier_image=raw.get("courier_image"),
            service_type=str(raw.get("service_type") or "pickup"),
        )

    async def create_label(
        self,
        *,
        request_token: str,
        service_code: str,
        courier_id: str,
        insurance_code: Optional[str] = None,
        is_cod_label: bool = False,
        duties_paid: bool = False,
    ) -> ShipbubbleShipmentResult:
        """Create a shipping label via POST /shipping/labels.

        Debits the account's shipping wallet.
        """
        payload: Dict[str, Any] = {
            "request_token": request_token,
            "service_code": service_code,
            "courier_id": str(courier_id),
        }
        if insurance_code:
            payload["insurance_code"] = insurance_code
        if is_cod_label:
            payload["is_cod_label"] = True
        if duties_paid:
            payload["duties_paid"] = True

        res = await self._make_request("POST", "/shipping/labels", data=payload)
        data = res.get("data") or {}
        order_id = data.get("order_id")
        if not order_id:
            raise ShipBubbleError(
                "Label created successfully but no order_id was returned",
                response_data=res,
            )

        courier_info = data.get("courier") or {}
        payment_info = data.get("payment") or {}
        fee_raw = payment_info.get("shipping_fee")
        fee = Decimal(str(fee_raw)).quantize(_CENT, rounding=ROUND_HALF_UP) if fee_raw is not None else None

        return ShipbubbleShipmentResult(
            order_id=order_id,
            status=str(data.get("status") or "pending"),
            courier_name=str(courier_info.get("name") or ""),
            tracking_code=courier_info.get("tracking_code"),
            tracking_url=data.get("tracking_url"),
            waybill_document_url=data.get("waybill_document"),
            shipping_fee=fee,
            currency=payment_info.get("currency", "NGN"),
            raw_response=res,
        )

    async def cancel_shipment(self, order_id: str) -> bool:
        """Cancel a scheduled shipment via POST /shipping/labels/cancel/:order_id."""
        res = await self._make_request("POST", f"/shipping/labels/cancel/{order_id}")
        return res.get("status") == "success"

    async def track_shipments(self, order_ids: List[str]) -> List[Dict[str, Any]]:
        """Track multiple shipments via GET /shipping/labels/list/:order_ids."""
        if not order_ids:
            return []
        ids_str = ",".join(order_ids[:50])
        res = await self._make_request("GET", f"/shipping/labels/list/{ids_str}")
        data = res.get("data")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("results") or []
        return []

    async def get_wallet_balance(self) -> Dict[str, Any]:
        """Fetch account wallet balance via GET /shipping/wallet/balance."""
        res = await self._make_request("GET", "/shipping/wallet/balance")
        return res.get("data") or {}

    async def simulate_webhook(self, order_id: str, status_code: str) -> Dict[str, Any]:
        """Simulate a webhook event in sandbox via POST /shipping/labels/webhooks/:order_id."""
        payload = {"status_code": status_code}
        return await self._make_request("POST", f"/shipping/labels/webhooks/{order_id}", data=payload)


# Singleton accessor
_shipbubble_service: Optional[ShipBubbleService] = None


def get_shipbubble_service(
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> ShipBubbleService:
    """Get or create ShipBubbleService singleton."""
    global _shipbubble_service
    if transport is not None:
        return ShipBubbleService(transport=transport)
    if _shipbubble_service is None:
        _shipbubble_service = ShipBubbleService()
    return _shipbubble_service
