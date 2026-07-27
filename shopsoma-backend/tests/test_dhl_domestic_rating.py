import inspect
import json
from dataclasses import replace
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import httpx
import pytest

from app.core.config import Settings
from app.services.dhl.client import DHLClient
from app.services.dhl.rating import (
    DHLDomesticRateAdapter,
    DHLRateAdapterError,
    DHLResolvedHub,
    create_sandbox_domestic_rate_adapter,
)
from app.services.fulfillment.contracts import (
    DomesticAddress,
    FulfillmentCohortRef,
    HubRef,
    PackageItemRef,
    PackageRef,
    ParcelMeasurement,
    SealRef,
)
from app.services.shipping.contracts import DomesticRateRequest
from app.services.shipping.rate_identity import (
    CANONICAL_RATE_VERSION,
    canonical_rate_fingerprint,
)

DUMMY_USERNAME = "synthetic-user"
DUMMY_PASSWORD = "synthetic-password"
DUMMY_ACCOUNT = "111111111"
IDENTITY_KEY = b"synthetic-rate-identity-key"
HUB_ID = UUID("11111111-1111-4111-8111-111111111111")
COHORT_A = UUID("22222222-2222-4222-8222-222222222222")
COHORT_B = UUID("33333333-3333-4333-8333-333333333333")
ITEM_A = UUID("44444444-4444-4444-8444-444444444444")
ITEM_B = UUID("55555555-5555-4555-8555-555555555555")
PACKAGE_ID = UUID("66666666-6666-4666-8666-666666666666")
INTENT_ID = UUID("77777777-7777-4777-8777-777777777777")
ORDER_ID = UUID("88888888-8888-4888-8888-888888888888")
SEAL_ID = UUID("99999999-9999-4999-8999-999999999999")


def config(**overrides: object) -> Settings:
    values = {
        "SECRET_KEY": "synthetic-app-secret",
        "DATABASE_URL": "postgresql://unit:***@localhost:5432/unit",
        "DHL_ENABLED": True,
        "DHL_ENVIRONMENT": "sandbox",
        "DHL_API_USERNAME": DUMMY_USERNAME,
        "DHL_API_PASSWORD": DUMMY_PASSWORD,
        "DHL_EXPORT_ACCOUNT_NUMBER": DUMMY_ACCOUNT,
        "DHL_DOMESTIC_WORKFLOW_ENABLED": True,
        "DHL_DOMESTIC_PROVIDER_CALLS_ENABLED": True,
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


def resolved_hub(**overrides: object) -> DHLResolvedHub:
    values = {
        "hub": HubRef(HUB_ID),
        "hub_version": 4,
        "intent_id": INTENT_ID,
        "order_id": ORDER_ID,
        "seal_id": SEAL_ID,
        "package_id": PACKAGE_ID,
        "package_version": 3,
        "contact_name": "ShopSoma Hub",
        "phone": "+2348000000000",
        "line1": "10 Synthetic Hub Road",
        "city": "Lagos",
        "state": "Lagos",
        "postal_code": "100001",
    }
    values.update(overrides)
    return DHLResolvedHub(**values)


def rate_request(**overrides: object) -> DomesticRateRequest:
    origin = overrides.pop("origin", HubRef(HUB_ID))
    composition = overrides.pop(
        "composition",
        (
            PackageItemRef(FulfillmentCohortRef(COHORT_B, origin), ITEM_B, 2),
            PackageItemRef(FulfillmentCohortRef(COHORT_A, origin), ITEM_A, 1),
        ),
    )
    package = overrides.pop(
        "package",
        PackageRef(
            package_id=PACKAGE_ID,
            package_version=3,
            composition=composition,
            measurement=ParcelMeasurement(
                weight_kg=Decimal("1.250"),
                length_cm=Decimal("30.00"),
                width_cm=Decimal("20.0"),
                height_cm=Decimal("10"),
            ),
            seal=SealRef("synthetic-seal-value"),
        ),
    )
    values = {
        "origin": origin,
        "destination": DomesticAddress(
            contact_name="Ada Customer",
            phone="+2348111111111",
            line1="20 Synthetic Customer Street",
            city="Abuja",
            state="FCT",
            postal_code="900001",
        ),
        "package": package,
        "planned_ship_date": date(2026, 7, 28),
    }
    values.update(overrides)
    return DomesticRateRequest(**values)


def product(
    code: str = "N",
    service_code: str | None = None,
    label: str = "Domestic Express",
    amount: str = "12500.5000",
    currency: str = "NGN",
    transit_days: int | None = 2,
    delivery_date: str | None = "2026-07-30",
) -> dict[str, object]:
    value: dict[str, object] = {
        "productCode": code,
        "localProductCode": service_code or code,
        "productName": label,
        "totalPrice": [{"price": amount, "priceCurrency": currency}],
    }
    capabilities: dict[str, object] = {}
    if transit_days is not None:
        capabilities["totalTransitDays"] = transit_days
    if delivery_date is not None:
        capabilities["estimatedDeliveryDateAndTime"] = delivery_date
    if capabilities:
        value["deliveryCapabilities"] = capabilities
    return value


def fingerprint(
    request: DomesticRateRequest, hub: DHLResolvedHub | None = None, **kw: object
) -> str:
    values = {
        "request": request,
        "resolved_hub": hub or resolved_hub(),
        "provider": "dhl",
        "environment": "sandbox",
        "account_alias": "export-primary",
        "adapter_version": "dhl-rates-v1",
        "schema_version": "mydhl-rates-v1",
        "key_version": "test-key-v1",
        "secret_key": IDENTITY_KEY,
    }
    values.update(kw)
    return canonical_rate_fingerprint(**values)


def test_fingerprint_is_versioned_keyed_deterministic_and_composition_sorted() -> None:
    request = rate_request()
    reversed_request = rate_request(
        composition=tuple(reversed(request.package.composition))
    )

    first = fingerprint(request)
    second = fingerprint(reversed_request)

    assert first == second
    assert CANONICAL_RATE_VERSION == "rate-canonical-v1"
    assert len(first) == 64
    assert fingerprint(request, secret_key=b"different-key") != first
    assert fingerprint(request, key_version="test-key-v2") != first


def test_fingerprint_preserves_exact_decimal_strings_and_changes_for_bound_fields() -> (
    None
):
    request = rate_request()
    base = fingerprint(request)
    changed_measurement = ParcelMeasurement(
        weight_kg=Decimal("1.2500"),
        length_cm=request.package.measurement.length_cm,
        width_cm=request.package.measurement.width_cm,
        height_cm=request.package.measurement.height_cm,
    )
    changed_package = replace(request.package, measurement=changed_measurement)

    assert fingerprint(replace(request, package=changed_package)) != base
    mutations = [
        replace(request, planned_ship_date=date(2026, 7, 29)),
        replace(request, destination=replace(request.destination, city="Kano")),
        replace(request, package=replace(request.package, package_version=4)),
        replace(request, package=replace(request.package, seal=SealRef("other-seal"))),
    ]
    assert all(fingerprint(value) != base for value in mutations)
    assert fingerprint(request, provider="other") != base
    assert fingerprint(request, account_alias="other-account") != base
    assert fingerprint(request, resolved_hub=resolved_hub(city="Ikeja")) != base
    assert fingerprint(request, resolved_hub=resolved_hub(hub_version=5)) != base
    assert fingerprint(request, resolved_hub=resolved_hub(intent_id=uuid4())) != base
    assert fingerprint(request, resolved_hub=resolved_hub(order_id=uuid4())) != base
    assert fingerprint(request, resolved_hub=resolved_hub(seal_id=uuid4())) != base
    assert fingerprint(request, resolved_hub=resolved_hub(package_id=uuid4())) != base
    assert fingerprint(request, resolved_hub=resolved_hub(package_version=4)) != base


def test_adapter_constructor_does_not_accept_an_injected_client() -> None:
    assert "client" not in inspect.signature(DHLDomesticRateAdapter).parameters


@pytest.mark.asyncio
async def test_observed_delivery_datetime_is_normalized_to_calendar_date() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"products": [product(delivery_date="2026-07-30T23:59:00")]},
        )

    adapter = create_sandbox_domestic_rate_adapter(
        config=config(),
        transport=httpx.MockTransport(handler),
        identity_key=IDENTITY_KEY,
        identity_key_version="test-key-v1",
    )
    result = await adapter.rate(resolved_hub(), rate_request())
    assert result.offers[0].rate.estimated_carrier_delivery_date == date(2026, 7, 30)


def test_fingerprint_rejects_empty_secret_without_reflecting_it() -> None:
    with pytest.raises(ValueError, match="secret key") as exc_info:
        fingerprint(rate_request(), secret_key=b"")
    assert DUMMY_PASSWORD not in str(exc_info.value)


def test_adapter_public_boundary_has_no_caller_overrides() -> None:
    factory_parameters = set(
        inspect.signature(create_sandbox_domestic_rate_adapter).parameters
    )
    assert factory_parameters == {
        "config",
        "transport",
        "identity_key",
        "identity_key_version",
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"DHL_ENVIRONMENT": "production"},
    ],
)
def test_factory_refuses_non_sandbox_before_transport(
    overrides: dict[str, object]
) -> None:
    called = False

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"products": []})

    with pytest.raises(DHLRateAdapterError, match="sandbox"):
        create_sandbox_domestic_rate_adapter(
            config=config(**overrides),
            transport=httpx.MockTransport(handler),
            identity_key=IDENTITY_KEY,
            identity_key_version="test-key-v1",
        )
    assert called is False


def test_factory_refuses_non_test_base_url_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"products": []})

    monkeypatch.setattr(
        Settings, "dhl_base_url", property(lambda _self: "https://example.invalid")
    )
    with pytest.raises(DHLRateAdapterError, match="test base"):
        create_sandbox_domestic_rate_adapter(
            config=config(),
            transport=httpx.MockTransport(handler),
            identity_key=IDENTITY_KEY,
            identity_key_version="test-key-v1",
        )
    assert called is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"DHL_DOMESTIC_WORKFLOW_ENABLED": False},
        {"DHL_DOMESTIC_PROVIDER_CALLS_ENABLED": False},
        {"DHL_ENABLED": False},
    ],
)
def test_adapter_factory_requires_effective_domestic_provider_capability(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(DHLRateAdapterError, match="provider calls are disabled"):
        create_sandbox_domestic_rate_adapter(
            config=config(**overrides),
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, json={"products": []})
            ),
            identity_key=IDENTITY_KEY,
            identity_key_version="test-key-v1",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [("package_id", uuid4()), ("package_version", 4)],
)
async def test_resolved_subject_package_must_match_request_before_transport(
    field: str,
    value: object,
) -> None:
    called = False

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"products": []})

    request_value = rate_request()
    mismatched = replace(request_value.package, **{field: value})
    adapter = create_sandbox_domestic_rate_adapter(
        config=config(),
        transport=httpx.MockTransport(handler),
        identity_key=b"k" * 32,
        identity_key_version="hmac-v1",
    )
    with pytest.raises(DHLRateAdapterError, match="authoritative package"):
        await adapter.rate(resolved_hub(), replace(request_value, package=mismatched))
    assert called is False


@pytest.mark.asyncio
async def test_exact_post_rates_request_uses_resolved_hub_managed_account_and_metric_package() -> (
    None
):
    request_value = rate_request()

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://express.api.dhl.com/mydhlapi/test/rates"
        body = json.loads(request.content)
        assert body == {
            "plannedShippingDate": "2026-07-28",
            "unitOfMeasurement": "metric",
            "isCustomsDeclarable": False,
            "accounts": [{"typeCode": "shipper", "number": DUMMY_ACCOUNT}],
            "customerDetails": {
                "shipperDetails": {
                    "postalAddress": {
                        "addressLine1": "10 Synthetic Hub Road",
                        "cityName": "Lagos",
                        "provinceCode": "Lagos",
                        "postalCode": "100001",
                        "countryCode": "NG",
                    },
                    "contactInformation": {
                        "fullName": "ShopSoma Hub",
                        "phone": "+2348000000000",
                    },
                },
                "receiverDetails": {
                    "postalAddress": {
                        "addressLine1": "20 Synthetic Customer Street",
                        "cityName": "Abuja",
                        "provinceCode": "FCT",
                        "postalCode": "900001",
                        "countryCode": "NG",
                    },
                    "contactInformation": {
                        "fullName": "Ada Customer",
                        "phone": "+2348111111111",
                    },
                },
            },
            "packages": [
                {
                    "weight": 1.250,
                    "dimensions": {"length": 30.00, "width": 20.0, "height": 10},
                }
            ],
        }
        return httpx.Response(200, json={"products": [product()]})

    adapter = create_sandbox_domestic_rate_adapter(
        config=config(),
        transport=httpx.MockTransport(handler),
        identity_key=IDENTITY_KEY,
        identity_key_version="test-key-v1",
    )
    result = await adapter.rate(resolved_hub(), request_value)

    assert result.result_kind == "success"
    assert len(result.offers) == 1
    assert result.offers[0].rate.package is request_value.package
    assert result.offers[0].rate.total_amount == Decimal("12500.5000")
    assert result.offers[0].rate.currency == "NGN"


@pytest.mark.asyncio
async def test_call_rechecks_sandbox_guards_before_transport() -> None:
    called = False

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"products": []})

    cfg = config()
    adapter = create_sandbox_domestic_rate_adapter(
        config=cfg,
        transport=httpx.MockTransport(handler),
        identity_key=IDENTITY_KEY,
        identity_key_version="test-key-v1",
    )
    object.__setattr__(cfg, "DHL_ENVIRONMENT", "production")
    with pytest.raises(DHLRateAdapterError, match="sandbox"):
        await adapter.rate(resolved_hub(), rate_request())
    assert called is False


@pytest.mark.asyncio
async def test_n_is_preferred_only_when_returned_and_other_services_are_one_to_one() -> (
    None
):
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "products": [
                    product("P", "P1", "P Express"),
                    product("N"),
                    product("D", "D1", "D Express"),
                ]
            },
        )

    adapter = create_sandbox_domestic_rate_adapter(
        config=config(),
        transport=httpx.MockTransport(handler),
        identity_key=IDENTITY_KEY,
        identity_key_version="test-key-v1",
    )
    result = await adapter.rate(resolved_hub(), rate_request())
    assert [offer.provider_product_code for offer in result.offers] == ["N", "D", "P"]
    assert [offer.provider_service_code for offer in result.offers] == ["N", "D1", "P1"]


@pytest.mark.asyncio
async def test_no_synthetic_n_and_empty_products_is_typed_no_service() -> None:
    responses = iter([{"products": [product("P", "P1")]}, {"products": []}])

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    adapter = create_sandbox_domestic_rate_adapter(
        config=config(),
        transport=httpx.MockTransport(handler),
        identity_key=IDENTITY_KEY,
        identity_key_version="test-key-v1",
    )
    first = await adapter.rate(resolved_hub(), rate_request())
    second = await adapter.rate(resolved_hub(), rate_request())
    assert [offer.provider_product_code for offer in first.offers] == ["P"]
    assert second.result_kind == "no_service"
    assert second.offers == ()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", [[], {}, {"products": None}, {"products": {}}, {"products": ["bad"]}]
)
async def test_malformed_top_level_or_product_schema_is_rejected(
    payload: object,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    adapter = create_sandbox_domestic_rate_adapter(
        config=config(),
        transport=httpx.MockTransport(handler),
        identity_key=IDENTITY_KEY,
        identity_key_version="test-key-v1",
    )
    with pytest.raises(DHLRateAdapterError, match="invalid rate response"):
        await adapter.rate(resolved_hub(), rate_request())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_product",
    [
        product(amount=1),
        product(amount="0"),
        product(amount="-1"),
        product(amount="NaN"),
        product(amount="Infinity"),
        product(amount="1.00001"),
        product(amount="100000000000000.0000"),
        product(currency="ngn"),
        product(currency="USD"),
        product(currency="ZZZ"),
        {**product(), "totalPrice": []},
        {
            **product(),
            "totalPrice": [
                {"price": "1", "priceCurrency": "NGN"},
                {"price": "2", "priceCurrency": "NGN"},
            ],
        },
        product(code="bad/code"),
        product(service_code="bad service"),
        product(label=" control\nlabel"),
        product(label="x" * 201),
        product(transit_days=0),
        product(transit_days=366),
        product(transit_days=True),
        product(delivery_date="2026-07-27"),
        product(delivery_date="not-a-date"),
    ],
)
async def test_strict_product_validation_rejects_ambiguous_unsafe_or_impossible_values(
    bad_product: dict[str, object],
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"products": [bad_product]})

    adapter = create_sandbox_domestic_rate_adapter(
        config=config(),
        transport=httpx.MockTransport(handler),
        identity_key=IDENTITY_KEY,
        identity_key_version="test-key-v1",
    )
    with pytest.raises(DHLRateAdapterError, match="invalid rate response"):
        await adapter.rate(resolved_hub(), rate_request())


@pytest.mark.asyncio
async def test_conflicting_duplicate_service_identity_is_rejected_but_exact_duplicate_collapses() -> (
    None
):
    responses = iter(
        [
            {"products": [product(), product(amount="13000.00")]},
            {"products": [product(), product()]},
        ]
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    adapter = create_sandbox_domestic_rate_adapter(
        config=config(),
        transport=httpx.MockTransport(handler),
        identity_key=IDENTITY_KEY,
        identity_key_version="test-key-v1",
    )
    with pytest.raises(DHLRateAdapterError, match="invalid rate response"):
        await adapter.rate(resolved_hub(), rate_request())
    assert len((await adapter.rate(resolved_hub(), rate_request())).offers) == 1


@pytest.mark.asyncio
async def test_errors_and_logs_do_not_leak_sensitive_input_or_provider_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_values = [
        DUMMY_USERNAME,
        DUMMY_PASSWORD,
        DUMMY_ACCOUNT,
        "Ada Customer",
        "+2348111111111",
        "20 Synthetic Customer Street",
        "synthetic-seal-value",
        "private-provider-reference",
    ]

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"products": [product(label="private-provider-reference\n")]}
        )

    adapter = create_sandbox_domestic_rate_adapter(
        config=config(),
        transport=httpx.MockTransport(handler),
        identity_key=IDENTITY_KEY,
        identity_key_version="test-key-v1",
    )
    with caplog.at_level("INFO"):
        with pytest.raises(DHLRateAdapterError) as exc_info:
            await adapter.rate(resolved_hub(), rate_request())
    material = caplog.text + str(exc_info.value) + repr(exc_info.value)
    assert all(value not in material for value in private_values)
    assert IDENTITY_KEY.decode() not in material


def test_adapter_requires_matching_resolved_hub() -> None:
    with pytest.raises(DHLRateAdapterError, match="resolved hub"):
        # Validation happens before there is any opportunity for transport.
        create_sandbox_domestic_rate_adapter(
            config=config(),
            transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
            identity_key=IDENTITY_KEY,
            identity_key_version="test-key-v1",
        ).validate_request(
            resolved_hub(hub=HubRef(UUID("77777777-7777-4777-8777-777777777777"))),
            rate_request(),
        )


def test_adapter_reuses_existing_dhl_client() -> None:
    adapter = create_sandbox_domestic_rate_adapter(
        config=config(),
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
        identity_key=IDENTITY_KEY,
        identity_key_version="test-key-v1",
    )
    assert isinstance(adapter._client, DHLClient)
