import asyncio
import base64
import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.config import Settings
from app.services.dhl.client import (
    DHLAPIError,
    DHLClient,
    DHLConfigurationError,
)
from app.services.dhl.shipments import (
    _aggregate_order_shipment_state,
    _highest_effective_tracking_snapshot_for_handoff,
    _map_tracking_status,
    DHLShipmentAdapter,
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
async def test_dhl_httpx_log_suppression_does_not_hide_unrelated_httpx_diagnostics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    dhl_started = asyncio.Event()
    release_dhl = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "express.api.dhl.com":
            dhl_started.set()
            await release_dhl.wait()
        return httpx.Response(200, json={"ok": True}, request=request)

    caplog.set_level(logging.INFO, logger="httpx")
    client = DHLClient(
        config=make_settings(),
        transport=httpx.MockTransport(handler),
    )
    dhl_task = asyncio.create_task(client.request_json("GET", "/rates"))
    await dhl_started.wait()
    try:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as unrelated:
            await unrelated.get("https://unrelated.example/health")
    finally:
        release_dhl.set()
    await dhl_task

    httpx_messages = [
        record.getMessage() for record in caplog.records if record.name == "httpx"
    ]
    assert all("express.api.dhl.com" not in message for message in httpx_messages)
    assert any("unrelated.example/health" in message for message in httpx_messages)


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


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        (("PU",), ("collected", "picked_up")),
        (("OK",), ("delivered", "delivered")),
        (("TRANSIT",), ("in_transit", "in_transit")),
        (("FAILURE",), ("exception", "delivery_exception")),
        (("PU", "TRANSIT"), ("collected", "picked_up")),
        (("UNKNOWN",), ("booked", "label_created")),
    ],
)
def test_map_tracking_status_handles_real_mydhl_codes(
    codes: tuple[str, ...],
    expected: tuple[str, str],
) -> None:
    assert _map_tracking_status(*codes) == expected


def test_aggregate_order_shipment_state_uses_slowest_non_cancelled_package() -> None:
    assert _aggregate_order_shipment_state(["label_ready", "awaiting_collection"]) == "label_ready"
    assert _aggregate_order_shipment_state(["awaiting_collection", "collected"]) == "awaiting_collection"
    assert _aggregate_order_shipment_state(["collected", "in_transit"]) == "collected"
    assert _aggregate_order_shipment_state(["delivered", "out_for_delivery"]) == "out_for_delivery"
    assert _aggregate_order_shipment_state(["delivered", "in_transit"]) == "in_transit"
    assert _aggregate_order_shipment_state(["delivered", "booked"]) == "booked"
    assert _aggregate_order_shipment_state(["delivered", "delivered"]) == "delivered"
    assert _aggregate_order_shipment_state(["cancelled", "delivered"]) == "delivered"
    assert _aggregate_order_shipment_state(["exception", "delivered"]) == "exception"


def test_handoff_snapshot_fold_preserves_highest_effective_state() -> None:
    delivered = SimpleNamespace(
        outbound_state="delivered",
        observed_at=datetime.fromisoformat("2026-09-04T10:00:00+00:00"),
        id="1",
        exception_code=None,
    )
    delayed_in_transit = SimpleNamespace(
        outbound_state="in_transit",
        observed_at=datetime.fromisoformat("2026-09-04T11:00:00+00:00"),
        id="2",
        exception_code=None,
    )

    snapshots: list[Any] = [delivered, delayed_in_transit]
    chosen = _highest_effective_tracking_snapshot_for_handoff(snapshots)

    assert chosen is not None
    assert chosen.snapshot is delivered
    assert chosen.resolved_observed_at == delivered.observed_at


def test_handoff_snapshot_fold_keeps_return_exception_sticky_against_later_movement() -> None:
    delivered = SimpleNamespace(
        outbound_state="delivered",
        observed_at=datetime.fromisoformat("2026-09-04T10:00:00+00:00"),
        id="1",
        exception_code=None,
    )
    returned = SimpleNamespace(
        outbound_state="exception",
        observed_at=datetime.fromisoformat("2026-09-04T11:00:00+00:00"),
        id="2",
        exception_code="RETURNED",
    )
    pickup_after_return = SimpleNamespace(
        outbound_state="collected",
        observed_at=datetime.fromisoformat("2026-09-04T12:00:00+00:00"),
        id="3",
        exception_code=None,
    )

    snapshots: list[Any] = [delivered, returned, pickup_after_return]
    chosen = _highest_effective_tracking_snapshot_for_handoff(snapshots)

    assert chosen is not None
    assert chosen.snapshot is returned
    assert chosen.resolved_observed_at == returned.observed_at


def test_handoff_snapshot_fold_allows_delivery_to_resolve_transient_exception() -> None:
    hold = SimpleNamespace(
        outbound_state="exception",
        observed_at=datetime.fromisoformat("2026-09-04T10:00:00+00:00"),
        id="1",
        exception_code="HOLD",
    )
    delivered = SimpleNamespace(
        outbound_state="delivered",
        observed_at=datetime.fromisoformat("2026-09-04T11:00:00+00:00"),
        id="2",
        exception_code=None,
    )

    snapshots: list[Any] = [hold, delivered]
    chosen = _highest_effective_tracking_snapshot_for_handoff(snapshots)

    assert chosen is not None
    assert chosen.snapshot is delivered
    assert chosen.resolved_observed_at == delivered.observed_at


def test_handoff_snapshot_fold_preserves_terminal_exception_across_later_transient_exception_and_delivery() -> None:
    returned = SimpleNamespace(
        outbound_state="exception",
        observed_at=datetime.fromisoformat("2026-09-04T10:00:00+00:00"),
        id="1",
        exception_code="RETURNED",
    )
    hold = SimpleNamespace(
        outbound_state="exception",
        observed_at=datetime.fromisoformat("2026-09-04T11:00:00+00:00"),
        id="2",
        exception_code="HOLD",
    )
    delivered = SimpleNamespace(
        outbound_state="delivered",
        observed_at=datetime.fromisoformat("2026-09-04T12:00:00+00:00"),
        id="3",
        exception_code=None,
    )

    snapshots: list[Any] = [returned, hold, delivered]
    chosen = _highest_effective_tracking_snapshot_for_handoff(snapshots)

    assert chosen is not None
    assert chosen.snapshot is returned
    assert chosen.resolved_observed_at == returned.observed_at


def test_handoff_snapshot_fold_restores_pre_exception_progress_when_transient_exception_clears() -> None:
    out_for_delivery = SimpleNamespace(
        outbound_state="out_for_delivery",
        observed_at=datetime.fromisoformat("2026-09-04T10:00:00+00:00"),
        id="1",
        exception_code=None,
    )
    hold = SimpleNamespace(
        outbound_state="exception",
        observed_at=datetime.fromisoformat("2026-09-04T11:00:00+00:00"),
        id="2",
        exception_code="HOLD",
    )
    in_transit = SimpleNamespace(
        outbound_state="in_transit",
        observed_at=datetime.fromisoformat("2026-09-04T12:00:00+00:00"),
        id="3",
        exception_code=None,
    )

    snapshots: list[Any] = [out_for_delivery, hold, in_transit]
    chosen = _highest_effective_tracking_snapshot_for_handoff(snapshots)

    assert chosen is not None
    assert chosen.snapshot is out_for_delivery
    assert chosen.resolved_observed_at == in_transit.observed_at


@pytest.mark.asyncio
async def test_tracking_adapter_parses_mydhl_shipments_events_envelope() -> None:
    tracking_response = {
        "shipments": [
            {
                "events": [
                    {
                        "typeCode": "PU",
                        "statusCode": "TRANSIT",
                        "description": "Shipment collected",
                        "date": "2026-09-03",
                        "time": "13:45:00+01:00",
                    },
                    {
                        "typeCode": "OK",
                        "statusCode": "DELIVERED",
                        "description": "Shipment delivered",
                        "date": "2026-09-04",
                        "time": "08:15:00+01:00",
                    },
                ]
            }
        ]
    }
    with patch(
        "app.services.dhl.client.DHLClient.request_json",
        new_callable=AsyncMock,
        return_value=tracking_response,
    ) as request_json:
        adapter = DHLShipmentAdapter(make_settings())
        observations = await adapter.track("TRACK123")

    request_json.assert_awaited_once_with("GET", "/shipments/TRACK123/tracking")
    assert [observation.provider_status_code for observation in observations] == [
        "PU",
        "OK",
    ]
    assert [observation.outbound_state for observation in observations] == [
        "collected",
        "delivered",
    ]
    assert observations[0].detail == "Shipment collected"
    assert observations[0].observed_at.isoformat() == "2026-09-03T13:45:00+01:00"
    assert observations[1].observed_at.isoformat() == "2026-09-04T08:15:00+01:00"


@pytest.mark.asyncio
async def test_tracking_adapter_preserves_terminal_exception_marker_from_all_codes() -> None:
    tracking_response = {
        "shipments": [
            {
                "events": [
                    {
                        "typeCode": "EXCEPTION",
                        "statusCode": "RETURNED",
                        "description": "Shipment returned",
                        "dateTime": "2026-09-04T08:15:00+01:00",
                    }
                ]
            }
        ]
    }
    with patch(
        "app.services.dhl.client.DHLClient.request_json",
        new_callable=AsyncMock,
        return_value=tracking_response,
    ):
        adapter = DHLShipmentAdapter(make_settings())
        observations = await adapter.track("TRACK123")

    assert len(observations) == 1
    assert observations[0].outbound_state == "exception"
    assert observations[0].exception_code == "RETURNED"


@pytest.mark.asyncio
async def test_tracking_adapter_url_encodes_tracking_number_path_segment() -> None:
    tracking_response = {"shipments": []}
    with patch(
        "app.services.dhl.client.DHLClient.request_json",
        new_callable=AsyncMock,
        return_value=tracking_response,
    ) as request_json:
        adapter = DHLShipmentAdapter(make_settings())
        await adapter.track("TRACK/123?#frag")

    request_json.assert_awaited_once_with(
        "GET",
        "/shipments/TRACK%2F123%3F%23frag/tracking",
    )


@pytest.mark.asyncio
async def test_tracking_adapter_skips_malformed_checkpoint_timestamp_candidates() -> None:
    tracking_response = {
        "shipments": [
            {
                "timestamp": "2026-09-04T08:15:00Z",
                "events": [
                    {
                        "typeCode": "PU",
                        "statusCode": "TRANSIT",
                        "description": "Shipment collected",
                        "timestamp": "not-a-timestamp",
                        "dateTime": "2026-09-03T13:45:00+01:00",
                    },
                    {
                        "typeCode": "OK",
                        "statusCode": "DELIVERED",
                        "description": "Shipment delivered",
                        "timestamp": "still-bad",
                    },
                ],
            }
        ]
    }
    with patch(
        "app.services.dhl.client.DHLClient.request_json",
        new_callable=AsyncMock,
        return_value=tracking_response,
    ):
        adapter = DHLShipmentAdapter(make_settings())
        observations = await adapter.track("TRACK123")

    assert observations[0].observed_at.isoformat() == "2026-09-03T13:45:00+01:00"
    assert observations[1].observed_at.isoformat() == "2026-09-04T08:15:00+00:00"


@pytest.mark.asyncio
async def test_booking_adapter_omits_blank_optional_address_line2() -> None:
    booking_response = {
        "documents": [
            {
                "content": base64.b64encode(b"%PDF-1.4 label").decode(),
                "mimeType": "application/pdf",
            }
        ],
        "trackingNumber": "TRACK123",
        "shipmentReference": "REF123",
        "productCode": "N",
        "timestamp": "2026-09-04T08:15:00Z",
    }
    with patch(
        "app.services.dhl.client.DHLClient.request_json",
        new_callable=AsyncMock,
        return_value=booking_response,
    ) as request_json:
        adapter = DHLShipmentAdapter(make_settings())
        await adapter.book(
            cast(
                Any,
                SimpleNamespace(
                    created_at=datetime.fromisoformat("2026-09-04T08:00:00+00:00"),
                    destination_country_code="NG",
                    destination_postal_code=None,
                    destination_city="Lagos",
                    destination_state="Lagos",
                    destination_address_line1="123 Example Street",
                    destination_address_line2="   ",
                    destination_name="Receiver Name",
                    destination_phone="08030000000",
                ),
            ),
            cast(Any, SimpleNamespace()),
            cast(
                Any,
                SimpleNamespace(
                    country_code="NG",
                    postal_code=None,
                    city="Lagos",
                    state="LA",
                    address_line1="Warehouse Block 3",
                    address_line2="",
                    contact_name="Hub Contact",
                    contact_phone="08020000000",
                ),
            ),
            cast(
                Any,
                SimpleNamespace(
                    weight_kg=1.25,
                    length_cm=20,
                    width_cm=15,
                    height_cm=10,
                ),
            ),
            cast(Any, SimpleNamespace(product_code="N")),
        )

    payload = cast(Any, request_json.await_args).kwargs["json"]
    shipper = payload["customerDetails"]["shipperDetails"]["postalAddress"]
    receiver = payload["customerDetails"]["receiverDetails"]["postalAddress"]
    assert all(not value.endswith(", ") for key, value in shipper.items() if key.startswith("addressLine"))
    assert all(not value.endswith(", ") for key, value in receiver.items() if key.startswith("addressLine"))
    assert all(", ," not in value for key, value in shipper.items() if key.startswith("addressLine"))
    assert all(", ," not in value for key, value in receiver.items() if key.startswith("addressLine"))


@pytest.mark.asyncio
async def test_booking_adapter_uses_provider_safe_addresses_and_required_content_metadata() -> None:
    booking_response = {
        "documents": [
            {
                "content": base64.b64encode(b"%PDF-1.4 label").decode(),
                "mimeType": "application/pdf",
            }
        ],
        "trackingNumber": "TRACK123",
        "shipmentReference": "REF123",
        "productCode": "N",
        "timestamp": "2026-09-04T08:15:00Z",
    }
    long_line1 = ("123 Example Street Segment " * 3).strip()
    destination_line2 = "Apartment 12B, Example Estate"
    with patch(
        "app.services.dhl.client.DHLClient.request_json",
        new_callable=AsyncMock,
        return_value=booking_response,
    ) as request_json:
        adapter = DHLShipmentAdapter(make_settings())
        result = await adapter.book(
            cast(
                Any,
                SimpleNamespace(
                    created_at=datetime.fromisoformat("2026-09-04T08:00:00+00:00"),
                    destination_country_code="NG",
                    destination_postal_code=None,
                    destination_city="Lagos",
                    destination_state="Lagos",
                    destination_address_line1=long_line1,
                    destination_address_line2=destination_line2,
                    destination_name="Receiver Name",
                    destination_phone="08030000000",
                ),
            ),
            cast(Any, SimpleNamespace()),
            cast(
                Any,
                SimpleNamespace(
                    country_code="NG",
                    postal_code=None,
                    city="Lagos",
                    state="LA",
                    address_line1=long_line1,
                    address_line2="Warehouse Block 3",
                    contact_name="Hub Contact",
                    contact_phone="08020000000",
                ),
            ),
            cast(
                Any,
                SimpleNamespace(
                    weight_kg=1.25,
                    length_cm=20,
                    width_cm=15,
                    height_cm=10,
                ),
            ),
            cast(Any, SimpleNamespace(product_code="N")),
        )

    request_json.assert_awaited_once()
    await_args = cast(Any, request_json.await_args)
    args = await_args.args
    payload = await_args.kwargs["json"]
    assert args == ("POST", "/shipments")
    assert payload["content"]["unitOfMeasurement"] == "metric"
    assert payload["content"]["isCustomsDeclarable"] is False
    shipper = payload["customerDetails"]["shipperDetails"]["postalAddress"]
    receiver = payload["customerDetails"]["receiverDetails"]["postalAddress"]
    assert shipper["countryCode"] == "NG"
    assert receiver["countryCode"] == "NG"
    assert all(len(value) <= 45 for key, value in shipper.items() if key.startswith("addressLine"))
    assert all(len(value) <= 45 for key, value in receiver.items() if key.startswith("addressLine"))
    assert "addressLine2" in shipper
    assert "addressLine3" in receiver
    assert result.provider_reference == "REF123"
    assert result.tracking_number == "TRACK123"
