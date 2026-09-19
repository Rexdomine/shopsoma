"""Secret-safe low-level client for the DHL Express MyDHL API."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Mapping, Optional

import httpx

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)

# HTTPX's INFO request log includes the complete URL, including path and query
# values that may contain private carrier references. Suppress only records made
# inside this client's async context; unrelated concurrent HTTPX callers retain
# their configured diagnostics.
_httpx_logger = logging.getLogger("httpx")
_dhl_httpx_log_context: ContextVar[bool] = getattr(
    _httpx_logger,
    "_shopsoma_dhl_log_context",
    ContextVar("dhl_httpx_log", default=False),
)
setattr(_httpx_logger, "_shopsoma_dhl_log_context", _dhl_httpx_log_context)


class _DHLHTTPXLogFilter(logging.Filter):
    _shopsoma_dhl_filter = True

    def filter(self, record: logging.LogRecord) -> bool:
        del record
        return not _dhl_httpx_log_context.get()


if not any(
    getattr(existing, "_shopsoma_dhl_filter", False)
    for existing in _httpx_logger.filters
):
    _httpx_logger.addFilter(_DHLHTTPXLogFilter())


class DHLConfigurationError(RuntimeError):
    """Raised when the DHL client is used without a complete enabled config."""


class DHLAPIError(RuntimeError):
    """Stable, non-sensitive representation of a MyDHL API failure."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        retryable: bool = False,
        request_reference: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.request_reference = request_reference


class DHLClient:
    """HTTP boundary shared by later typed DHL quote and shipment operations."""

    def __init__(
        self,
        *,
        config: Settings = settings,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        if not config.DHL_ENABLED:
            raise DHLConfigurationError("DHL integration is disabled")
        if not config.dhl_configured:
            raise DHLConfigurationError("DHL integration configuration is incomplete")

        self._base_url = config.dhl_base_url
        self._username = config.DHL_API_USERNAME.get_secret_value()
        self._password = config.DHL_API_PASSWORD.get_secret_value()
        self._timeout_seconds = config.DHL_REQUEST_TIMEOUT_SECONDS
        self._transport = transport

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        json: Optional[Mapping[str, Any]] = None,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> dict[str, Any]:
        """Call MyDHL and return a JSON object without logging payloads or secrets."""
        if "?" in path or "#" in path:
            raise ValueError(
                "DHL API path must not contain a query string or fragment; use params"
            )
        normalized_path = "/" + path.lstrip("/")
        request_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if headers:
            managed_headers = {"authorization", "accept", "content-type"}
            if any(key.lower() in managed_headers for key in headers):
                raise ValueError(
                    "Authorization and JSON content headers are managed by DHLClient"
                )
            request_headers.update(headers)

        logger.info("DHL API request started: method=%s", method.upper())

        log_context_token = _dhl_httpx_log_context.set(True)
        try:
            try:
                async with httpx.AsyncClient(
                    base_url=self._base_url,
                    auth=httpx.BasicAuth(self._username, self._password),
                    headers=request_headers,
                    timeout=self._timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = await client.request(
                        method.upper(),
                        normalized_path,
                        json=dict(json) if json is not None else None,
                        params=params,
                    )
            except httpx.TimeoutException as exc:
                logger.warning("DHL API request timed out: method=%s", method.upper())
                raise DHLAPIError("DHL API request timed out", retryable=True) from exc
            except httpx.RequestError as exc:
                logger.warning("DHL API transport failure: method=%s", method.upper())
                raise DHLAPIError("DHL API is unavailable", retryable=True) from exc
        finally:
            _dhl_httpx_log_context.reset(log_context_token)

        request_reference = response.headers.get("Message-Reference")
        if response.status_code >= 400:
            raise self._map_http_error(response.status_code, request_reference)

        try:
            payload = response.json()
        except ValueError as exc:
            raise DHLAPIError(
                "DHL API returned an invalid response",
                status_code=response.status_code,
                request_reference=request_reference,
            ) from exc

        if not isinstance(payload, dict):
            raise DHLAPIError(
                "DHL API returned an invalid response",
                status_code=response.status_code,
                request_reference=request_reference,
            )

        logger.info(
            "DHL API response: method=%s status=%s",
            method.upper(),
            response.status_code,
        )
        return payload

    @staticmethod
    def _map_http_error(
        status_code: int,
        request_reference: Optional[str],
    ) -> DHLAPIError:
        if status_code == 401:
            message = "DHL API authentication failed"
            retryable = False
        elif status_code == 403:
            message = "DHL API authorization failed"
            retryable = False
        elif status_code == 429:
            message = "DHL API rate limit exceeded"
            retryable = True
        elif status_code >= 500:
            message = "DHL API is unavailable"
            retryable = True
        else:
            message = "DHL API request was rejected"
            retryable = False

        return DHLAPIError(
            message,
            status_code=status_code,
            retryable=retryable,
            request_reference=request_reference,
        )
