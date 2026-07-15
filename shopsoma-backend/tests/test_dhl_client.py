import base64

import httpx
import pytest

from app.core.config import Settings
from app.services.dhl.client import (
    DHLAPIError,
    DHLClient,
    DHLConfigurationError,
)


DUMMY_USERNAME = "dummy-api-user"
DUMMY_PASSWORD = "dummy-api-password"
DUMMY_ACCOUNT = "123456789"


def make_settings(**overrides) -> Settings:
    values = {
        "SECRET_KEY": "unit-test-secret",
        "DATABASE_URL": "postgresql://unit:unit@localhost:5432/shopsoma_unit",
        "DHL_ENABLED": True,
        "DHL_API_USERNAME": DUMMY_USERNAME,
        "DHL_API_PASSWORD": DUMMY_PASSWORD,
        "DHL_EXPORT_ACCOUNT_NUMBER": DUMMY_ACCOUNT,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.mark.asyncio
async def test_request_json_uses_official_url_basic_auth_and_json_headers() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://express.api.dhl.com/mydhlapi/test/rates"
        expected = base64.b64encode(
            f"{DUMMY_USERNAME}:{DUMMY_PASSWORD}".encode()
        ).decode()
        assert request.headers["Authorization"] == f"Basic {expected}"
        assert request.headers["Accept"] == "application/json"
        assert request.headers["Content-Type"] == "application/json"
        return httpx.Response(200, json={"products": [{"productCode": "P"}]})

    client = DHLClient(
        config=make_settings(),
        transport=httpx.MockTransport(handler),
    )

    payload = await client.request_json("GET", "/rates")

    assert payload == {"products": [{"productCode": "P"}]}


def test_disabled_configuration_cannot_initialize_client() -> None:
    with pytest.raises(DHLConfigurationError, match="disabled"):
        DHLClient(config=make_settings(DHL_ENABLED=False))


@pytest.mark.asyncio
@pytest.mark.parametrize("header_name", ["Authorization", "Accept", "Content-Type"])
async def test_caller_cannot_override_managed_headers(header_name: str) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = DHLClient(
        config=make_settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="managed by DHLClient"):
        await client.request_json(
            "GET",
            "/rates",
            headers={header_name: "caller-controlled"},
        )


@pytest.mark.asyncio
async def test_query_string_must_be_supplied_through_params() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = DHLClient(
        config=make_settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="query string"):
        await client.request_json("GET", f"/rates?account={DUMMY_ACCOUNT}")


@pytest.mark.asyncio
async def test_request_logs_exclude_paths_params_and_sensitive_values(caplog) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    client = DHLClient(
        config=make_settings(),
        transport=httpx.MockTransport(handler),
    )

    with caplog.at_level("INFO", logger="app.services.dhl.client"):
        await client.request_json(
            "GET",
            f"/shipments/{DUMMY_ACCOUNT}/tracking",
            params={"customer": "private-customer-reference"},
        )

    logs = caplog.text
    assert DUMMY_ACCOUNT not in logs
    assert "private-customer-reference" not in logs
    assert DUMMY_USERNAME not in logs
    assert DUMMY_PASSWORD not in logs


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_message", "retryable"),
    [
        (400, "rejected", False),
        (401, "authentication", False),
        (403, "authorization", False),
        (429, "rate limit", True),
        (500, "unavailable", True),
    ],
)
async def test_http_errors_map_without_leaking_response_body(
    status_code: int,
    expected_message: str,
    retryable: bool,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code,
            headers={"Message-Reference": "safe-request-reference"},
            json={
                "detail": "raw-customer-address-and-secret-must-not-leak",
                "credential": DUMMY_PASSWORD,
            },
        )

    client = DHLClient(
        config=make_settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(DHLAPIError) as exc_info:
        await client.request_json("POST", "/shipments", json={"account": DUMMY_ACCOUNT})

    error = exc_info.value
    assert error.status_code == status_code
    assert error.retryable is retryable
    assert error.request_reference == "safe-request-reference"
    assert expected_message in str(error).lower()
    assert "raw-customer-address" not in str(error)
    assert DUMMY_PASSWORD not in str(error)
    assert DUMMY_ACCOUNT not in str(error)


@pytest.mark.asyncio
async def test_timeout_maps_to_retryable_error_without_secret_leak() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream timed out", request=request)

    client = DHLClient(
        config=make_settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(DHLAPIError) as exc_info:
        await client.request_json("GET", "/rates")

    error = exc_info.value
    assert error.status_code is None
    assert error.retryable is True
    assert "timed out" in str(error).lower()
    assert DUMMY_PASSWORD not in str(error)


@pytest.mark.asyncio
async def test_network_failure_maps_to_retryable_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client = DHLClient(
        config=make_settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(DHLAPIError) as exc_info:
        await client.request_json("GET", "/rates")

    assert exc_info.value.retryable is True
    assert "unavailable" in str(exc_info.value).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type",
    [httpx.ProxyError, httpx.RemoteProtocolError, httpx.LocalProtocolError],
)
async def test_other_transport_failures_map_to_retryable_error(error_type) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise error_type("transport failed", request=request)

    client = DHLClient(
        config=make_settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(DHLAPIError) as exc_info:
        await client.request_json("GET", "/rates")

    assert exc_info.value.retryable is True
    assert "unavailable" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_successful_non_json_response_is_rejected_safely() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json and must not be reflected")

    client = DHLClient(
        config=make_settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(DHLAPIError) as exc_info:
        await client.request_json("GET", "/rates")

    assert exc_info.value.retryable is False
    assert "invalid response" in str(exc_info.value).lower()
    assert "not-json" not in str(exc_info.value)
