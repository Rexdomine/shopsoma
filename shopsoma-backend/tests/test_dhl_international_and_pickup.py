"""Unit tests for Phase 0–4 DHL Express international export, customs, production gate, and hub pickup."""

from __future__ import annotations

import logging
import socket
import uuid
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from app.core.config import Settings
from app.services.dhl.client import (
    DHLAPIError,
    DHLClient,
    _dhl_httpx_log_context,
    _dhl_resilient_getaddrinfo,
)
from app.services.dhl.customs import (
    DEFAULT_HS_CODE,
    build_export_content_fields,
    resolve_hs_code,
)
from app.services.dhl.rating import DHLDomesticRateAdapter, DHLResolvedHub
from app.services.dhl.shipments import (
    DHLShipmentAdapter,
    QuotedShipmentService,
    ShipmentPhase4Error,
    _ensure_sandbox_booking_allowed,
    build_hub_pickup_payload,
)
from app.services.fulfillment.contracts import (
    FulfillmentCohortRef,
    HubRef,
    PackageItemRef,
    PackageRef,
    ParcelMeasurement,
    SealRef,
    build_shipping_address,
    resolve_country_code,
)
from app.services.shipping.contracts import DomesticRateRequest


class _Secret:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def _make_settings(
    *,
    environment: str = "sandbox",
    live_enabled: bool = False,
    export_enabled: bool = True,
    allowed_export: str = "GH,US,GB,CA,ZA,KE,AE,FR,DE",
    cohort_id: uuid.UUID | None = None,
) -> Any:
    cohort_set = frozenset({cohort_id}) if cohort_id else frozenset({uuid.uuid4()})
    export_codes = (
        frozenset(c.strip().upper() for c in allowed_export.split(",") if c.strip())
        if export_enabled
        else frozenset()
    )
    base_url = (
        "https://express.api.dhl.com/mydhlapi"
        if environment == "production"
        else "https://express.api.dhl.com/mydhlapi/test"
    )
    return SimpleNamespace(
        DHL_ENABLED=True,
        DHL_ENVIRONMENT=environment,
        DHL_LIVE_ENABLED=live_enabled,
        DHL_EXPORT_ENABLED=export_enabled,
        DHL_ALLOWED_EXPORT_COUNTRIES=allowed_export,
        dhl_allowed_export_countries=export_codes,
        dhl_supported_country_codes=frozenset({"NG"}) | export_codes,
        dhl_base_url=base_url,
        dhl_configured=True,
        DHL_REQUEST_TIMEOUT_SECONDS=15.0,
        DHL_DOMESTIC_QUOTE_TTL_SECONDS=1800,
        DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=True,
        DHL_DOMESTIC_WORKFLOW_ENABLED=True,
        DHL_DOMESTIC_CHECKOUT_ENABLED=True,
        DHL_DOMESTIC_QUOTE_ENFORCEMENT_ENABLED=True,
        DHL_DOMESTIC_BOOKING_ENABLED=True,
        dhl_domestic_sandbox_cohort_ids=cohort_set,
        DHL_API_USERNAME=_Secret("test-user"),
        DHL_API_PASSWORD=_Secret("test-pass"),
        DHL_EXPORT_ACCOUNT_NUMBER=_Secret("365156545"),
        DHL_IMPORT_ACCOUNT_NUMBER=_Secret("959090322"),
    )


def test_phase0_dns_fallback_only_applies_inside_dhl_context(monkeypatch: pytest.MonkeyPatch) -> None:
    def _failing_getaddrinfo(host: Any, port: Any, *args: Any, **kwargs: Any) -> Any:
        if host in ("express.api.dhl.com", b"express.api.dhl.com"):
            raise socket.gaierror("DNS lookup failed")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (str(host), int(port)))]

    monkeypatch.setattr("app.services.dhl.client._orig_getaddrinfo", _failing_getaddrinfo)

    with pytest.raises(socket.gaierror):
        _dhl_resilient_getaddrinfo("express.api.dhl.com", 443)

    token = _dhl_httpx_log_context.set(True)
    try:
        resolved = _dhl_resilient_getaddrinfo("express.api.dhl.com", 443)
        assert resolved[0][4][0] == "156.137.1.116"
    finally:
        _dhl_httpx_log_context.reset(token)


@pytest.mark.asyncio
async def test_phase0_error_log_redacts_raw_response_body(caplog: pytest.LogCaptureFixture) -> None:
    secret_body = '{"detail":"SENSITIVE-CUSTOMER-ADDRESS-AND-ACCOUNT-365156545"}'

    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, text=secret_body)

    settings = _make_settings()
    client = DHLClient(config=cast(Settings, settings), transport=httpx.MockTransport(_handler))

    with caplog.at_level(logging.ERROR):
        with pytest.raises(DHLAPIError):
            await client.request_json("POST", "/shipments", json={"test": True})

    logged_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "SENSITIVE-CUSTOMER-ADDRESS" not in logged_text
    assert "365156545" not in logged_text
    assert "DHL error response: status=422" in logged_text


def test_phase1_resolve_country_code_and_build_shipping_address() -> None:
    assert resolve_country_code("Nigeria") == "NG"
    assert resolve_country_code("ng") == "NG"
    assert resolve_country_code("Ghana") == "GH"
    assert resolve_country_code("United States") == "US"
    assert resolve_country_code("UK") == "GB"
    assert resolve_country_code("United Kingdom") == "GB"
    assert resolve_country_code("Canada") == "CA"

    gh_addr = build_shipping_address(
        contact_name="Kwame Mensah",
        phone="+233244000000",
        line1="14 Ring Road Central",
        line2=None,
        city="Accra",
        state="Greater Accra",
        postal_code="00000",
        country_code="Ghana",
    )
    assert gh_addr.country_code == "GH"
    assert gh_addr.postal_code == "00000"


@pytest.mark.asyncio
async def test_phase1_rate_adapter_supports_international_export_and_customs_declarable() -> None:
    cohort_id = uuid.uuid4()
    settings = _make_settings(cohort_id=cohort_id)
    captured_payloads: list[dict[str, Any]] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        captured_payloads.append(_json.loads(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "products": [
                    {
                        "productCode": "P",
                        "localProductCode": "P",
                        "productName": "EXPRESS WORLDWIDE",
                        "totalPrice": [
                            {
                                "currencyType": "BILLC",
                                "priceCurrency": "NGN",
                                "price": 185000.0,
                            }
                        ],
                        "detailedPriceBreakdown": [],
                        "deliveryCapabilities": {
                            "estimatedDeliveryDateAndTime": "2026-11-16T18:00:00",
                        },
                    }
                ]
            },
        )

    adapter = DHLDomesticRateAdapter(
        config=cast(Settings, settings),
        transport=httpx.MockTransport(_handler),
        identity_key=b"test-identity-key-32-bytes-long!",
        identity_key_version="v1",
    )
    hub_ref = HubRef(id=uuid.uuid4())
    cohort_ref = FulfillmentCohortRef(id=cohort_id, hub=hub_ref)
    pkg_id = uuid.uuid4()
    package = PackageRef(
        package_id=pkg_id,
        package_version=1,
        composition=(
            PackageItemRef(
                cohort=cohort_ref,
                order_item_id=uuid.uuid4(),
                quantity=1,
            ),
        ),
        measurement=ParcelMeasurement(
            weight_kg=Decimal("1.5"),
            length_cm=Decimal("30"),
            width_cm=Decimal("25"),
            height_cm=Decimal("10"),
        ),
        seal=SealRef(value="SEAL-001"),
    )
    destination = build_shipping_address(
        contact_name="Jane Doe",
        phone="+447700900077",
        line1="123 Oxford Street",
        line2="Suite 4",
        city="London",
        state="England",
        postal_code="W1D 1BS",
        country_code="United Kingdom",
    )
    resolved_hub = DHLResolvedHub(
        hub=hub_ref,
        hub_version=1,
        intent_id=uuid.uuid4(),
        order_id=uuid.uuid4(),
        seal_id=uuid.uuid4(),
        package_id=pkg_id,
        package_version=1,
        destination=destination,
        package=package,
        contact_name="ShopSoma Hub",
        phone="+2348000000000",
        line1="12 Admiralty Way",
        line2=None,
        city="Lagos",
        state="Lagos",
        postal_code="100001",
        country_code="NG",
        cohort_count=1,
    )
    rate_request = DomesticRateRequest(
        origin=hub_ref,
        destination=destination,
        package=package,
        planned_ship_date=date(2026, 11, 12),
    )

    result = await adapter.rate(resolved_hub, rate_request)
    assert result.result_kind == "success"
    assert len(result.offers) == 1
    assert result.offers[0].provider_product_code == "P"
    assert result.offers[0].service_label == "EXPRESS WORLDWIDE"
    assert captured_payloads[0]["isCustomsDeclarable"] is True
    assert captured_payloads[0]["customerDetails"]["receiverDetails"]["countryCode"] == "GB"


def test_phase2_customs_hs_code_and_export_declaration() -> None:
    assert resolve_hs_code("Dresses", "Silk Midi Dress") == "62044200"
    assert resolve_hs_code("Tops", "Cotton Shirt") == "62052000"
    assert resolve_hs_code("Trousers", "Wide Leg Pants") == "62034200"
    assert resolve_hs_code("Traditional", "Adire Agbada Set") == "62114200"
    assert resolve_hs_code("Bags", "Leather Clutch") == "42022200"
    assert resolve_hs_code("Footwear", "Strappy Heels") == "64039900"
    assert resolve_hs_code("Jewelry", "Gold Brass Earrings") == "71171900"
    assert resolve_hs_code("Headwraps", "Aso Oke Gele") == "62149000"
    assert resolve_hs_code(None, "Unknown Item") == DEFAULT_HS_CODE

    order = SimpleNamespace(
        id=uuid.uuid4(),
        order_number="SS-EXP-1001",
        currency="USD",
        subtotal=Decimal("240.00"),
        total_amount=Decimal("285.00"),
        items=[
            SimpleNamespace(
                product_title="Adire Silk Dress",
                quantity=2,
                unit_price=Decimal("120.00"),
            )
        ],
    )
    package_version = SimpleNamespace(weight_kg=Decimal("1.8"))
    export_fields = build_export_content_fields(
        order=order,
        package_version=package_version,
        planned_ship_date=date(2026, 11, 12),
    )
    assert export_fields["isCustomsDeclarable"] is True
    assert export_fields["incoterm"] == "DAP"
    assert export_fields["declaredValue"] == 240.0
    assert export_fields["declaredValueCurrency"] == "USD"
    declaration = cast(dict[str, Any], export_fields["exportDeclaration"])
    assert declaration["exportReasonType"] == "permanent"
    assert declaration["placeOfIncoterm"] == "LAGOS"
    assert declaration["shipmentType"] == "commercial"
    assert len(declaration["lineItems"]) == 1
    assert declaration["lineItems"][0]["manufacturerCountry"] == "NG"
    assert declaration["lineItems"][0]["commodityCodes"][0]["value"] == "62044200"


def test_phase2_shipment_payload_domestic_vs_international() -> None:
    settings = _make_settings()
    adapter = DHLShipmentAdapter(cast(Settings, settings))
    now_dt = datetime.now()
    hub = SimpleNamespace(
        name="ShopSoma Lagos Hub",
        contact_name="ShopSoma Dispatch",
        contact_phone="+2348000000000",
        contact_email="hub@shopsoma.com",
        address_line1="12 Admiralty Way",
        address_line2=None,
        city="Lagos",
        state="Lagos",
        postal_code="100001",
        country_code="NG",
        version=1,
    )
    package_version = SimpleNamespace(
        weight_kg=Decimal("1.5"),
        length_cm=Decimal("30"),
        width_cm=Decimal("25"),
        height_cm=Decimal("10"),
    )
    order = SimpleNamespace(
        id=uuid.uuid4(),
        order_number="SS-INTL-202",
        currency="USD",
        subtotal=Decimal("150.00"),
        items=[SimpleNamespace(product_title="Ankara Gown", quantity=1, unit_price=Decimal("150.00"))],
    )

    ng_intent = SimpleNamespace(
        created_at=now_dt,
        destination_name="Ada Obi",
        destination_phone="+2348012345678",
        destination_address_line1="5 Wuse Zone 4",
        destination_address_line2=None,
        destination_city="Abuja",
        destination_state="FCT",
        destination_postal_code="900001",
        destination_country_code="NG",
    )
    from app.services.admin_shadow_quote import _planned_ship_date_for_shadow_quote

    planned_date = _planned_ship_date_for_shadow_quote(now_dt)
    ng_quoted = QuotedShipmentService(
        product_code="N",
        service_code="DOMESTIC EXPRESS",
        hub_version=1,
        planned_ship_date=planned_date,
    )
    ng_payload = adapter.prepare_booking_payload(
        cast(Any, ng_intent),
        cast(Any, order),
        cast(Any, hub),
        cast(Any, package_version),
        ng_quoted,
    )
    ng_content = cast(dict[str, Any], ng_payload["content"])
    assert ng_content["isCustomsDeclarable"] is False
    assert "exportDeclaration" not in ng_content

    us_intent = SimpleNamespace(
        created_at=now_dt,
        destination_name="Jane Doe",
        destination_phone="+12125550199",
        destination_address_line1="350 Fifth Avenue",
        destination_address_line2="Floor 21",
        destination_city="New York",
        destination_state="NY",
        destination_postal_code="10118",
        destination_country_code="US",
    )
    us_quoted = QuotedShipmentService(
        product_code="P",
        service_code="EXPRESS WORLDWIDE",
        hub_version=1,
        planned_ship_date=planned_date,
    )
    us_payload = adapter.prepare_booking_payload(
        cast(Any, us_intent),
        cast(Any, order),
        cast(Any, hub),
        cast(Any, package_version),
        us_quoted,
    )
    us_content = cast(dict[str, Any], us_payload["content"])
    assert us_content["isCustomsDeclarable"] is True
    assert us_content["incoterm"] == "DAP"
    assert "exportDeclaration" in us_content
    image_opts = cast(dict[str, Any], us_payload["outputImageProperties"])["imageOptions"]
    assert any(opt.get("typeCode") == "invoice" for opt in image_opts)


def test_phase3_pickup_payload_and_phase4_production_gate() -> None:
    cohort_id = uuid.uuid4()
    prod_disabled = _make_settings(environment="production", live_enabled=False, cohort_id=cohort_id)
    with pytest.raises(ShipmentPhase4Error, match="DHL_LIVE_ENABLED=True"):
        _ensure_sandbox_booking_allowed(cast(Settings, prod_disabled), cohort_ids=frozenset({cohort_id}))

    prod_enabled = _make_settings(environment="production", live_enabled=True, cohort_id=cohort_id)
    _ensure_sandbox_booking_allowed(cast(Settings, prod_enabled), cohort_ids=frozenset({cohort_id}))

    booking = SimpleNamespace(tracking_number="1234567890")
    intent = SimpleNamespace(
        destination_name="Kwame Mensah",
        destination_phone="+233244000000",
        destination_address_line1="14 Ring Road Central",
        destination_address_line2=None,
        destination_city="Accra",
        destination_state="Greater Accra",
        destination_postal_code="00000",
        destination_country_code="GH",
    )
    order = SimpleNamespace(customer_email="kwame@example.com")
    hub = SimpleNamespace(
        name="ShopSoma Lagos Hub",
        contact_name="ShopSoma Dispatch",
        contact_phone="+2348000000000",
        contact_email="hub@shopsoma.com",
        address_line1="12 Admiralty Way",
        address_line2=None,
        city="Lagos",
        state="Lagos",
        postal_code="100001",
        country_code="NG",
    )
    package_version = SimpleNamespace(
        weight_kg=Decimal("2.0"),
        length_cm=Decimal("35"),
        width_cm=Decimal("25"),
        height_cm=Decimal("12"),
    )
    pickup_payload = build_hub_pickup_payload(
        settings=cast(Settings, prod_enabled),
        booking=cast(Any, booking),
        intent=cast(Any, intent),
        order=cast(Any, order),
        hub=cast(Any, hub),
        package_version=cast(Any, package_version),
        planned_pickup_at=datetime(2026, 11, 12, 14, 0),
    )
    assert pickup_payload["locationType"] == "business"
    shipment_details = cast(list[dict[str, Any]], pickup_payload["shipmentDetails"])
    assert shipment_details[0]["productCode"] == "P"
    assert shipment_details[0]["isCustomsDeclarable"] is True
    assert shipment_details[0]["shipmentTrackingNumber"] == "1234567890"
