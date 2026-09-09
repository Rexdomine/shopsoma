"""Strict sandbox-only typed adapter for MyDHL domestic rate shopping."""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Literal
from uuid import UUID, uuid5

import httpx

from app.core.config import Settings
from app.services.dhl.client import DHLAPIError, DHLClient
from app.services.fulfillment.contracts import DomesticAddress, HubRef, PackageRef
from app.services.shipping.capabilities import domestic_shipping_capabilities
from app.services.shipping.contracts import DomesticRate, DomesticRateRequest
from app.services.shipping.rate_identity import canonical_rate_fingerprint

MYDHL_TEST_BASE_URL = "https://express.api.dhl.com/mydhlapi/test"
ADAPTER_VERSION = "dhl-rates-v1"
SCHEMA_VERSION = "mydhl-rates-v1"
ACCOUNT_ALIAS = "dhl-ng-sandbox"
_PRODUCT_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,5}\Z")
_LOCAL_PRODUCT_CODE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,2}\Z")
_INTERNAL_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,99}\Z")
_CURRENCY = re.compile(r"[A-Z]{3}\Z")


def derive_sandbox_cohort_ids(
    namespaces: frozenset[UUID], order_id: UUID, count: int
) -> frozenset[UUID]:
    """Derive the server-owned cohort IDs authorized by configured namespaces."""
    return frozenset(
        derive_sandbox_cohort_id(namespace, order_id, ordinal)
        for namespace in namespaces
        for ordinal in range(count)
    )


def derive_sandbox_cohort_id(namespace: UUID, order_id: UUID, ordinal: int) -> UUID:
    """Derive one deterministic server-owned cohort ID."""
    return uuid5(namespace, f"{order_id}:cohort:{ordinal}")


_SUPPORTED_CURRENCIES = frozenset({"NGN", "USD"})
_PRICE_TYPE_PRIORITY = ("BILLC", "PULCL", "BASEC")


class DHLRateAdapterError(RuntimeError):
    """Stable error that never contains request or provider response material."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class DHLResolvedHub:
    """Authoritatively resolved provider origin; callers cannot supply an address alone."""

    hub: HubRef
    hub_version: int
    intent_id: UUID
    order_id: UUID
    seal_id: UUID
    package_id: UUID
    package_version: int
    destination: DomesticAddress
    package: PackageRef
    contact_name: str
    phone: str
    line1: str
    line2: str | None
    city: str
    state: str
    postal_code: str | None = None
    country_code: str = "NG"

    def __post_init__(self) -> None:
        if not isinstance(self.hub, HubRef):
            raise TypeError("hub must be a HubRef")
        if (
            not isinstance(self.hub_version, int)
            or isinstance(self.hub_version, bool)
            or self.hub_version <= 0
        ):
            raise ValueError("resolved hub version is invalid")
        if not all(
            isinstance(value, UUID)
            for value in (
                self.intent_id,
                self.order_id,
                self.seal_id,
                self.package_id,
            )
        ):
            raise TypeError("resolved rate subject identity is invalid")
        if (
            not isinstance(self.package_version, int)
            or isinstance(self.package_version, bool)
            or self.package_version <= 0
        ):
            raise ValueError("resolved package version is invalid")
        if not isinstance(self.destination, DomesticAddress) or not isinstance(
            self.package, PackageRef
        ):
            raise TypeError("resolved rate subject facts are invalid")
        if (
            self.package.package_id != self.package_id
            or self.package.package_version != self.package_version
        ):
            raise ValueError("resolved package facts do not match their identity")
        if self.country_code != "NG":
            raise ValueError("resolved hub must be Nigerian")
        for field_name in ("contact_name", "phone", "line1", "city", "state"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("resolved hub field is invalid")
        if self.line2 is not None and (
            not isinstance(self.line2, str) or not self.line2.strip()
        ):
            raise ValueError("resolved hub field is invalid")
        if self.postal_code is not None and (
            not isinstance(self.postal_code, str) or not self.postal_code.strip()
        ):
            raise ValueError("resolved hub field is invalid")


@dataclass(frozen=True, slots=True)
class DHLDomesticRateOffer:
    provider_product_code: str
    provider_service_code: str
    service_label: str
    rate: DomesticRate


@dataclass(frozen=True, slots=True)
class DHLDomesticRateResult:
    result_kind: Literal["success", "no_service"]
    offers: tuple[DHLDomesticRateOffer, ...]

    def __post_init__(self) -> None:
        if self.result_kind == "success" and not self.offers:
            raise ValueError("success requires at least one offer")
        if self.result_kind == "no_service" and self.offers:
            raise ValueError("no_service cannot contain offers")


class DHLDomesticRateAdapter:
    """Nigerian hub-to-customer merchandise rating through exactly POST /rates."""

    def __init__(
        self,
        *,
        config: Settings,
        transport: httpx.AsyncBaseTransport | None,
        identity_key: bytes,
        identity_key_version: str,
    ) -> None:
        self._config = config
        self._identity_key = identity_key
        self._identity_key_version = identity_key_version
        self._account = config.DHL_EXPORT_ACCOUNT_NUMBER.get_secret_value()
        self._guard_sandbox()
        self._client = DHLClient(config=config, transport=transport)

    def _guard_sandbox(self) -> frozenset[UUID]:
        if self._config.DHL_ENVIRONMENT != "sandbox":
            raise DHLRateAdapterError("domestic DHL rates require sandbox environment")
        if self._config.dhl_base_url != MYDHL_TEST_BASE_URL:
            raise DHLRateAdapterError(
                "domestic DHL rates require the fixed MyDHL test base"
            )
        sandbox_cohort_ids = self._config.dhl_domestic_sandbox_cohort_ids
        if not sandbox_cohort_ids:
            raise DHLRateAdapterError(
                "domestic DHL rates require a restricted synthetic sandbox cohort"
            )
        if not domestic_shipping_capabilities(self._config).provider_calls_enabled:
            raise DHLRateAdapterError("domestic DHL provider calls are disabled")
        return sandbox_cohort_ids

    @staticmethod
    def _package_matches_authoritative(
        authoritative: PackageRef, candidate: PackageRef
    ) -> bool:
        if authoritative != candidate:
            return False
        authoritative_measurement = authoritative.measurement
        candidate_measurement = candidate.measurement
        return all(
            getattr(authoritative_measurement, field_name).as_tuple()
            == getattr(candidate_measurement, field_name).as_tuple()
            for field_name in ("weight_kg", "length_cm", "width_cm", "height_cm")
        )

    def validate_request(
        self, resolved_hub: DHLResolvedHub, request: DomesticRateRequest
    ) -> None:
        sandbox_cohort_ids = self._guard_sandbox()
        if not isinstance(resolved_hub, DHLResolvedHub):
            raise DHLRateAdapterError("resolved hub is invalid")
        if not isinstance(request, DomesticRateRequest):
            raise DHLRateAdapterError("domestic rate request is invalid")
        if resolved_hub.hub != request.origin:
            raise DHLRateAdapterError("resolved hub does not match request origin")
        if (
            not self._package_matches_authoritative(
                resolved_hub.package, request.package
            )
            or resolved_hub.destination != request.destination
        ):
            raise DHLRateAdapterError(
                "rate request must match the authoritative shipment subject"
            )
        request_cohort_ids = {item.cohort.id for item in request.package.composition}
        expected_cohort_ids = derive_sandbox_cohort_ids(
            sandbox_cohort_ids, resolved_hub.order_id, len(request_cohort_ids)
        )
        if not request_cohort_ids or not request_cohort_ids.issubset(expected_cohort_ids):
            raise DHLRateAdapterError(
                "domestic DHL rates require a restricted synthetic sandbox cohort"
            )
        if (
            resolved_hub.country_code != "NG"
            or request.destination.country_code != "NG"
            or request.content_type != "merchandise"
            or request.movement_direction != "outbound"
        ):
            raise DHLRateAdapterError(
                "domestic rate request is outside the supported lane"
            )

    def prepare_rate_payload(
        self, resolved_hub: DHLResolvedHub, request: DomesticRateRequest
    ) -> dict[str, object]:
        self.validate_request(resolved_hub, request)
        return self._request_payload(resolved_hub, request)

    async def rate(
        self,
        resolved_hub: DHLResolvedHub,
        request: DomesticRateRequest,
        prepared_payload: dict[str, object] | None = None,
    ) -> DHLDomesticRateResult:
        payload = (
            prepared_payload
            if prepared_payload is not None
            else self.prepare_rate_payload(resolved_hub, request)
        )
        try:
            response = await self._client.request_json("POST", "/rates", json=payload)
        except DHLAPIError as exc:
            message = (
                "DHL returned an invalid rate response"
                if str(exc) == "DHL API returned an invalid response"
                else "DHL rate request failed"
            )
            raise DHLRateAdapterError(
                message,
                retryable=exc.retryable,
                status_code=exc.status_code,
            ) from None
        return self._parse_response(response, request, resolved_hub)

    def _request_payload(
        self, resolved_hub: DHLResolvedHub, request: DomesticRateRequest
    ) -> dict[str, object]:
        measurement = request.package.measurement
        try:
            account = self._provider_text(self._account, 1, 12)
            weight = self._provider_measurement(
                measurement.weight_kg, Decimal("999999999999")
            )
            dimensions = {
                "length": self._provider_measurement(
                    measurement.length_cm, Decimal("9999999")
                ),
                "width": self._provider_measurement(
                    measurement.width_cm, Decimal("9999999")
                ),
                "height": self._provider_measurement(
                    measurement.height_cm, Decimal("9999999")
                ),
            }
            shipper = self._party(resolved_hub)
            receiver = self._party(request.destination)
        except (TypeError, ValueError, InvalidOperation, OverflowError):
            raise DHLRateAdapterError("domestic rate request is invalid") from None
        return {
            # The provider-neutral contract intentionally stores a date only. MyDHL's
            # POST /rates schema requires a local tender time and GMT offset, so use a
            # stable midday Lagos timestamp rather than the wall clock at call time.
            "plannedShippingDateAndTime": (
                f"{request.planned_ship_date.isoformat()}T12:00:00GMT+01:00"
            ),
            "unitOfMeasurement": "metric",
            "isCustomsDeclarable": False,
            "accounts": [{"typeCode": "shipper", "number": account}],
            "customerDetails": {
                "shipperDetails": shipper,
                "receiverDetails": receiver,
            },
            "packages": [
                {
                    "weight": weight,
                    "dimensions": dimensions,
                }
            ],
        }

    @classmethod
    def _party(cls, value: object) -> dict[str, object]:
        postal_code = getattr(value, "postal_code")
        street = cls._provider_text(getattr(value, "line1"), 1, 135)
        line2 = getattr(value, "line2")
        if line2 is not None:
            street = f"{street}, {cls._provider_text(line2, 1, 135)}"
        street = cls._provider_text(street, 1, 135)
        address_lines = [
            street[index : index + 45] for index in range(0, len(street), 45)
        ]
        party: dict[str, object] = {
            "postalCode": (
                "" if postal_code is None else cls._provider_text(postal_code, 0, 12)
            ),
            "cityName": cls._provider_text(getattr(value, "city"), 1, 45),
            "countryCode": cls._provider_text(getattr(value, "country_code"), 2, 2),
            "provinceCode": cls._provider_text(getattr(value, "state"), 2, 35),
        }
        party.update(
            {f"addressLine{index}": line for index, line in enumerate(address_lines, 1)}
        )
        return party

    @staticmethod
    def _provider_text(value: object, minimum: int, maximum: int) -> str:
        if (
            not isinstance(value, str)
            or not minimum <= len(value) <= maximum
            or value != value.strip()
            or not value.isprintable()
        ):
            raise ValueError
        return value

    @staticmethod
    def _provider_measurement(value: object, maximum: Decimal) -> float:
        if not isinstance(value, Decimal):
            raise TypeError
        exponent = value.as_tuple().exponent
        if (
            not value.is_finite()
            or value < Decimal("0.001")
            or value > maximum
            or not isinstance(exponent, int)
            or max(0, -exponent) > 3
        ):
            raise ValueError
        return float(value)

    def _parse_response(
        self,
        payload: object,
        request: DomesticRateRequest,
        resolved_hub: DHLResolvedHub,
    ) -> DHLDomesticRateResult:
        if not isinstance(payload, dict) or "products" not in payload:
            raise DHLRateAdapterError("DHL returned an invalid rate response")
        products = payload["products"]
        if not isinstance(products, list):
            raise DHLRateAdapterError("DHL returned an invalid rate response")
        if not products:
            return DHLDomesticRateResult("no_service", ())

        unique: dict[tuple[str, str], DHLDomesticRateOffer] = {}
        for product in products:
            offer = self._parse_product(product, request, resolved_hub)
            identity = (offer.provider_product_code, offer.provider_service_code)
            existing = unique.get(identity)
            if existing is not None and existing != offer:
                raise DHLRateAdapterError("DHL returned an invalid rate response")
            unique[identity] = offer
        offers = tuple(
            sorted(
                unique.values(),
                key=lambda offer: (
                    offer.provider_product_code,
                    offer.provider_service_code,
                ),
            )
        )
        if not offers:
            return DHLDomesticRateResult("no_service", ())
        return DHLDomesticRateResult("success", offers)

    def _parse_product(
        self,
        product: object,
        request: DomesticRateRequest,
        resolved_hub: DHLResolvedHub,
    ) -> DHLDomesticRateOffer:
        try:
            if not isinstance(product, dict):
                raise ValueError
            product_code = self._code(product.get("productCode"), _PRODUCT_CODE)
            service_code = self._code(
                product.get("localProductCode"), _LOCAL_PRODUCT_CODE
            )
            label = self._label(product.get("productName"))
            amount, currency = self._money(product.get("totalPrice"))
            transit_days, delivery_date = self._delivery(
                product.get("deliveryCapabilities"), request.planned_ship_date
            )
        except (TypeError, ValueError, InvalidOperation, OverflowError):
            raise DHLRateAdapterError("DHL returned an invalid rate response") from None

        fingerprint = canonical_rate_fingerprint(
            request=request,
            resolved_hub=resolved_hub,
            provider="dhl",
            environment="sandbox",
            account_alias=ACCOUNT_ALIAS,
            adapter_version=ADAPTER_VERSION,
            schema_version=SCHEMA_VERSION,
            key_version=self._identity_key_version,
            secret_key=self._identity_key,
        )
        service_key = (
            f"{len(product_code)}:{product_code}:{len(service_code)}:{service_code}"
        )
        service_identity = service_key.encode("ascii")
        digest = hmac.new(
            self._identity_key,
            fingerprint.encode("ascii") + b":" + service_identity,
            sha256,
        ).hexdigest()
        rate = DomesticRate(
            rate_id=f"dhlrate:{digest}",
            service_id=f"dhl:{service_key}",
            package=request.package,
            total_amount=amount,
            currency=currency,
            carrier_transit_days=transit_days,
            estimated_carrier_delivery_date=delivery_date,
        )
        return DHLDomesticRateOffer(product_code, service_code, label, rate)

    @staticmethod
    def _code(value: object, pattern: re.Pattern[str]) -> str:
        if not isinstance(value, str) or pattern.fullmatch(value) is None:
            raise ValueError
        return value

    @staticmethod
    def _label(value: object) -> str:
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value) > 200
            or not value.isascii()
            or not value.isprintable()
        ):
            raise ValueError
        return value

    @staticmethod
    def _money(value: object) -> tuple[Decimal, str]:
        if not isinstance(value, list) or not value:
            raise ValueError

        parsed: list[tuple[str | None, Decimal, str]] = []
        for entry in value:
            if not isinstance(entry, dict):
                raise ValueError
            currency_type = entry.get("currencyType")
            if currency_type is not None and currency_type not in _PRICE_TYPE_PRIORITY:
                raise ValueError
            raw_amount = entry.get("price")
            currency = entry.get("priceCurrency")
            if isinstance(raw_amount, bool) or not isinstance(
                raw_amount, (str, int, float)
            ):
                raise ValueError
            amount = Decimal(str(raw_amount))
            exponent = amount.as_tuple().exponent
            if (
                not amount.is_finite()
                or amount <= 0
                or amount > Decimal("99999999999999.9999")
                or not isinstance(exponent, int)
                or max(0, -exponent) > 4
            ):
                raise ValueError
            if not isinstance(currency, str) or _CURRENCY.fullmatch(currency) is None:
                raise ValueError
            parsed.append((currency_type, amount, currency))

        for currency_type in _PRICE_TYPE_PRIORITY:
            candidates = [
                entry
                for entry in parsed
                if entry[0] == currency_type and entry[2] in _SUPPORTED_CURRENCIES
            ]
            if candidates:
                if len(candidates) != 1:
                    raise ValueError
                _, amount, currency = candidates[0]
                return amount, currency

        untyped = [
            entry
            for entry in parsed
            if entry[0] is None and entry[2] in _SUPPORTED_CURRENCIES
        ]
        if len(untyped) != 1:
            raise ValueError
        _, amount, currency = untyped[0]
        return amount, currency

    @staticmethod
    def _delivery(
        value: object, planned_ship_date: date
    ) -> tuple[int | None, date | None]:
        if value is None:
            return None, None
        if not isinstance(value, dict):
            raise ValueError
        transit = value.get("totalTransitDays")
        raw_delivery = value.get("estimatedDeliveryDateAndTime")
        if transit is not None:
            if (
                isinstance(transit, bool)
                or not isinstance(transit, (int, float))
                or int(transit) != transit
                or not 1 <= transit <= 365
            ):
                raise ValueError
            transit = int(transit)
        delivery = None
        if raw_delivery is not None:
            if not isinstance(raw_delivery, str):
                raise ValueError
            try:
                if "T" in raw_delivery:
                    delivery = datetime.fromisoformat(raw_delivery).date()
                else:
                    delivery = date.fromisoformat(raw_delivery)
            except ValueError:
                raise ValueError from None
            if delivery <= planned_ship_date:
                raise ValueError
        if transit is not None and delivery is not None:
            calendar_days = (delivery - planned_ship_date).days
            if calendar_days < transit or calendar_days > transit + 7:
                raise ValueError
        return transit, delivery


def create_sandbox_domestic_rate_adapter(
    *,
    config: Settings,
    transport: httpx.AsyncBaseTransport | None,
    identity_key: bytes,
    identity_key_version: str,
) -> DHLDomesticRateAdapter:
    """Create an adapter only for the immutable official MyDHL sandbox boundary."""
    if config.DHL_ENVIRONMENT != "sandbox":
        raise DHLRateAdapterError("domestic DHL rates require sandbox environment")
    if config.dhl_base_url != MYDHL_TEST_BASE_URL:
        raise DHLRateAdapterError(
            "domestic DHL rates require the fixed MyDHL test base"
        )
    if not config.dhl_domestic_sandbox_cohort_ids:
        raise DHLRateAdapterError(
            "domestic DHL rates require a restricted synthetic sandbox cohort"
        )
    if not domestic_shipping_capabilities(config).provider_calls_enabled:
        raise DHLRateAdapterError("domestic DHL provider calls are disabled")
    if not isinstance(identity_key, bytes) or not identity_key:
        raise DHLRateAdapterError("rate identity key is invalid")
    if (
        not isinstance(identity_key_version, str)
        or len(identity_key_version) > 50
        or _INTERNAL_IDENTIFIER.fullmatch(identity_key_version) is None
    ):
        raise DHLRateAdapterError("rate identity key version is invalid")
    return DHLDomesticRateAdapter(
        config=config,
        transport=transport,
        identity_key=identity_key,
        identity_key_version=identity_key_version,
    )
