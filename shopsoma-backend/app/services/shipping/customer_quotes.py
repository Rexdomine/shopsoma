"""Customer-owned shipping quote orchestration over persisted rate evidence.

This service deliberately does not call a carrier. It projects an eligible,
normalized domestic rate response into the immutable customer quote aggregate.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_shipping_quote import (
    CustomerShippingQuote,
    CustomerShippingQuoteOption,
    CustomerShippingQuoteSelection,
)
from app.models.domestic_rate_quote import (
    DomesticRateAttempt,
    DomesticRateOffer,
    DomesticRateResponse,
)
from app.models.order import Order
from app.models.package_custody import (
    HubPackage,
    HubPackageSeal,
    OutboundShipmentIntent,
    OutboundShipmentIntentInvalidation,
)
from app.services.shipping.capabilities import DomesticShippingCapabilities


class ShippingQuoteError(Exception):
    """Base class for stable, sanitized quote errors."""


class ShippingQuoteNotFound(ShippingQuoteError):
    """The requested customer-owned resource is not visible."""


class ShippingQuoteUnavailable(ShippingQuoteError):
    """No safe quote can currently be created or selected."""


class ShippingQuoteConflict(ShippingQuoteError):
    """The request conflicts with durable idempotency or selection truth."""


def validate_idempotency_key(value: str) -> str:
    """Accept only bounded visible ASCII without whitespace."""
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 200
        or any(ord(char) < 33 or ord(char) > 126 for char in value)
    ):
        raise ValueError("idempotency key is invalid")
    return value


def _fingerprint(operation: str, **values: object) -> str:
    payload = {
        "operation": operation,
        **{key: str(value) for key, value in values.items()},
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class CustomerShippingQuoteService:
    """Create, read, and select immutable customer-owned quotes."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        capabilities: DomesticShippingCapabilities,
        quote_ttl_seconds: int = 1800,
    ) -> None:
        if not 1 <= quote_ttl_seconds <= 86400:
            raise ValueError("quote TTL is invalid")
        self.session = session
        self.capabilities = capabilities
        self.quote_ttl_seconds = quote_ttl_seconds

    async def _clock(self) -> datetime:
        return await self.session.scalar(select(func.clock_timestamp()))

    async def _options(self, quote_id: UUID) -> list[CustomerShippingQuoteOption]:
        result = await self.session.scalars(
            select(CustomerShippingQuoteOption)
            .where(CustomerShippingQuoteOption.quote_id == quote_id)
            .order_by(
                CustomerShippingQuoteOption.total_amount,
                CustomerShippingQuoteOption.id,
            )
        )
        return list(result)

    async def _decorate(self, quote: CustomerShippingQuote) -> CustomerShippingQuote:
        options = await self._options(quote.id)
        selection = await self.session.scalar(
            select(CustomerShippingQuoteSelection).where(
                CustomerShippingQuoteSelection.quote_id == quote.id
            )
        )
        superseded = await self.session.scalar(
            select(CustomerShippingQuote.id).where(
                CustomerShippingQuote.supersedes_quote_id == quote.id
            )
        )
        now = await self._clock()
        if selection is not None:
            status = "selected"
        elif superseded is not None:
            status = "superseded"
        elif quote.expires_at <= now:
            status = "expired"
        else:
            status = "available"
        quote.options = options
        quote.selected_option_id = selection.option_id if selection else None
        quote.status = status
        return quote

    async def _owned_order(
        self, order_id: UUID, customer_id: UUID, *, lock: bool = False
    ) -> Order:
        statement = select(Order).where(
            Order.id == order_id, Order.customer_id == customer_id
        )
        if lock:
            statement = statement.with_for_update()
        order = await self.session.scalar(statement)
        if order is None:
            raise ShippingQuoteNotFound("shipping quote was not found")
        return order

    async def _active_subject(
        self, order_id: UUID
    ) -> tuple[OutboundShipmentIntent, HubPackage, HubPackageSeal]:
        row = (
            await self.session.execute(
                select(OutboundShipmentIntent, HubPackage, HubPackageSeal)
                .join(HubPackage, HubPackage.id == OutboundShipmentIntent.package_id)
                .join(
                    HubPackageSeal, HubPackageSeal.id == OutboundShipmentIntent.seal_id
                )
                .outerjoin(
                    OutboundShipmentIntentInvalidation,
                    OutboundShipmentIntentInvalidation.intent_id
                    == OutboundShipmentIntent.id,
                )
                .where(
                    OutboundShipmentIntent.order_id == order_id,
                    OutboundShipmentIntentInvalidation.id.is_(None),
                    HubPackage.state == "ready",
                    HubPackage.current_version
                    == OutboundShipmentIntent.package_version,
                    HubPackageSeal.retired_at.is_(None),
                )
                .order_by(OutboundShipmentIntent.created_at.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            raise ShippingQuoteUnavailable("shipping quote subject is unavailable")
        return row[0], row[1], row[2]

    async def _eligible_rate_evidence(
        self,
        *,
        intent_id: UUID,
        currency: str,
        minimum_expiry: datetime,
    ) -> tuple[DomesticRateResponse, DomesticRateAttempt, list[DomesticRateOffer]]:
        row = (
            await self.session.execute(
                select(DomesticRateResponse, DomesticRateAttempt)
                .join(
                    DomesticRateAttempt,
                    DomesticRateAttempt.id == DomesticRateResponse.attempt_id,
                )
                .where(
                    DomesticRateAttempt.intent_id == intent_id,
                    DomesticRateAttempt.classification == "success",
                    DomesticRateResponse.result_kind == "success",
                    DomesticRateResponse.expires_at >= minimum_expiry,
                )
                .order_by(DomesticRateResponse.received_at.desc())
                .limit(1)
            )
        ).first()
        if row is None:
            raise ShippingQuoteUnavailable("eligible shipping rates are unavailable")
        response, attempt = row
        offers = list(
            await self.session.scalars(
                select(DomesticRateOffer)
                .where(
                    DomesticRateOffer.response_id == response.id,
                    DomesticRateOffer.currency == currency,
                )
                .order_by(DomesticRateOffer.total_amount, DomesticRateOffer.id)
            )
        )
        if not offers:
            raise ShippingQuoteUnavailable("eligible shipping rates are unavailable")
        return response, attempt, offers

    async def create_quote(
        self, *, order_id: UUID, customer_id: UUID, idempotency_key: str
    ) -> CustomerShippingQuote:
        validate_idempotency_key(idempotency_key)
        if not self.capabilities.workflow_enabled:
            raise ShippingQuoteUnavailable("shipping quotes are unavailable")

        fingerprint = _fingerprint("create_quote", order_id=order_id)
        replay = await self.session.scalar(
            select(CustomerShippingQuote).where(
                CustomerShippingQuote.customer_id == customer_id,
                CustomerShippingQuote.idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            if replay.request_fingerprint != fingerprint:
                raise ShippingQuoteConflict("idempotency key was already used")
            return await self._decorate(replay)

        order = await self._owned_order(order_id, customer_id, lock=True)
        replay = await self.session.scalar(
            select(CustomerShippingQuote).where(
                CustomerShippingQuote.customer_id == customer_id,
                CustomerShippingQuote.idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            if replay.request_fingerprint != fingerprint:
                raise ShippingQuoteConflict("idempotency key was already used")
            return await self._decorate(replay)

        intent, package, seal = await self._active_subject(order.id)
        now = await self._clock()
        minimum_expiry = now + timedelta(seconds=self.quote_ttl_seconds)
        response, attempt, offers = await self._eligible_rate_evidence(
            intent_id=intent.id,
            currency=order.currency,
            minimum_expiry=minimum_expiry,
        )
        if (
            attempt.order_id != order.id
            or attempt.package_id != package.id
            or attempt.package_version != intent.package_version
            or attempt.seal_id != seal.id
            or attempt.destination_snapshot_hash != intent.destination_snapshot_hash
        ):
            raise ShippingQuoteUnavailable("eligible shipping rates are unavailable")

        predecessor = await self.session.scalar(
            select(CustomerShippingQuote)
            .where(CustomerShippingQuote.intent_id == intent.id)
            .outerjoin(
                CustomerShippingQuoteSelection,
                CustomerShippingQuoteSelection.quote_id == CustomerShippingQuote.id,
            )
            .where(CustomerShippingQuoteSelection.id.is_(None))
            .order_by(CustomerShippingQuote.created_at.desc())
            .limit(1)
        )
        quote = CustomerShippingQuote(
            order_id=order.id,
            customer_id=customer_id,
            intent_id=intent.id,
            package_id=intent.package_id,
            package_version=intent.package_version,
            seal_id=intent.seal_id,
            origin_hub_id=intent.origin_hub_id,
            destination_snapshot_hash=intent.destination_snapshot_hash,
            source_rate_response_id=response.id,
            supersedes_quote_id=predecessor.id if predecessor else None,
            currency=order.currency,
            ttl_seconds=self.quote_ttl_seconds,
            initiating_actor_type="customer",
            initiating_actor_id=str(customer_id),
            source_command="create_customer_shipping_quote",
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            schema_version="customer_quote_v1",
        )
        self.session.add(quote)
        await self.session.flush()

        options: list[CustomerShippingQuoteOption] = []
        for offer in offers:
            option = CustomerShippingQuoteOption(
                quote_id=quote.id,
                source_rate_offer_id=offer.id,
                option_key=str(offer.id),
                provider=attempt.provider,
                product_code=offer.provider_product_code,
                service_code=offer.provider_service_code,
                service_label=offer.service_label,
                source_amount=offer.total_amount,
                adjustment_amount=0,
                total_amount=offer.total_amount,
                currency=offer.currency,
                transit_days=offer.transit_days,
                delivery_date=offer.delivery_date,
            )
            self.session.add(option)
            options.append(option)
        await self.session.flush()
        quote.options = options
        quote.selected_option_id = None
        quote.status = "available"
        return quote

    async def list_quotes(
        self, *, order_id: UUID, customer_id: UUID
    ) -> list[CustomerShippingQuote]:
        await self._owned_order(order_id, customer_id)
        quotes = list(
            await self.session.scalars(
                select(CustomerShippingQuote)
                .where(
                    CustomerShippingQuote.order_id == order_id,
                    CustomerShippingQuote.customer_id == customer_id,
                )
                .order_by(CustomerShippingQuote.created_at.desc())
            )
        )
        return [await self._decorate(quote) for quote in quotes]

    async def get_quote(
        self, *, order_id: UUID, quote_id: UUID, customer_id: UUID
    ) -> CustomerShippingQuote:
        await self._owned_order(order_id, customer_id)
        quote = await self.session.scalar(
            select(CustomerShippingQuote).where(
                CustomerShippingQuote.id == quote_id,
                CustomerShippingQuote.order_id == order_id,
                CustomerShippingQuote.customer_id == customer_id,
            )
        )
        if quote is None:
            raise ShippingQuoteNotFound("shipping quote was not found")
        return await self._decorate(quote)

    async def select_option(
        self,
        *,
        order_id: UUID,
        quote_id: UUID,
        option_id: UUID,
        customer_id: UUID,
        idempotency_key: str,
    ) -> CustomerShippingQuote:
        validate_idempotency_key(idempotency_key)
        if not self.capabilities.workflow_enabled:
            raise ShippingQuoteUnavailable("shipping quotes are unavailable")
        await self._owned_order(order_id, customer_id, lock=True)

        replay = await self.session.scalar(
            select(CustomerShippingQuoteSelection).where(
                CustomerShippingQuoteSelection.customer_id == customer_id,
                CustomerShippingQuoteSelection.idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            if replay.quote_id != quote_id or replay.option_id != option_id:
                raise ShippingQuoteConflict("idempotency key was already used")
            return await self.get_quote(
                order_id=order_id, quote_id=quote_id, customer_id=customer_id
            )

        quote = await self.session.scalar(
            select(CustomerShippingQuote)
            .where(
                CustomerShippingQuote.id == quote_id,
                CustomerShippingQuote.order_id == order_id,
                CustomerShippingQuote.customer_id == customer_id,
            )
            .with_for_update()
        )
        if quote is None:
            raise ShippingQuoteNotFound("shipping quote was not found")
        option = await self.session.scalar(
            select(CustomerShippingQuoteOption).where(
                CustomerShippingQuoteOption.id == option_id,
                CustomerShippingQuoteOption.quote_id == quote.id,
            )
        )
        if option is None:
            raise ShippingQuoteNotFound("shipping quote was not found")
        decorated = await self._decorate(quote)
        if decorated.status != "available":
            raise ShippingQuoteConflict("shipping quote is no longer selectable")

        selection = CustomerShippingQuoteSelection(
            quote_id=quote.id,
            intent_id=quote.intent_id,
            option_id=option.id,
            customer_id=customer_id,
            selected_by_id=customer_id,
            source_command="select_customer_shipping_quote",
            idempotency_key=idempotency_key,
        )
        self.session.add(selection)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            raise ShippingQuoteConflict(
                "shipping quote is no longer selectable"
            ) from exc
        return await self._decorate(quote)
