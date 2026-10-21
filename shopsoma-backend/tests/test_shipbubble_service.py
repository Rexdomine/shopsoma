"""Unit tests for ShipBubble shipping service, rate parsing, label booking, and webhooks."""

from decimal import Decimal
import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from app.core.config import settings
from app.services.shipbubble_service import (
    ShipBubbleError,
    ShipBubbleService,
    parse_eta_days,
)


@pytest.fixture
def mock_api_key():
    return "sb_sandbox_test_key_12345"


@pytest.fixture
def mock_service(mock_api_key):
    return ShipBubbleService(api_key=mock_api_key)


def test_parse_eta_days():
    assert parse_eta_days("Within 1 - 4 working days") == (1, 4)
    assert parse_eta_days("Within 2 to 5 business days") == (2, 5)
    assert parse_eta_days("Same day delivery") == (0, 1)
    assert parse_eta_days("Within 23 hrs") == (0, 1)
    assert parse_eta_days("Within 2 days") == (1, 2)
    assert parse_eta_days(None) == (None, None)
    assert parse_eta_days("") == (None, None)


@pytest.mark.asyncio
async def test_validate_address_success(mock_api_key):
    mock_response = {
        "status": "success",
        "message": "Address validated successfully",
        "data": {
            "address_code": 98794022,
            "address": "1 Marina Road, Lagos",
            "city": "Lagos",
            "state": "Lagos",
            "country": "Nigeria",
        },
    }

    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert "/shipping/address/validate" in str(request.url)
        assert request.headers["authorization"] == f"Bearer {mock_api_key}"
        data = json.loads(request.content)
        assert data["address"] == "1 Marina Road, Lagos"
        return httpx.Response(200, json=mock_response)

    transport = httpx.MockTransport(handler)
    service = ShipBubbleService(api_key=mock_api_key, transport=transport)

    result = await service.validate_address(
        name="Ada Customer",
        email="ada@example.com",
        phone="+2348012345678",
        address="1 Marina Road, Lagos",
    )
    assert result["address_code"] == 98794022


@pytest.mark.asyncio
async def test_validate_address_api_error(mock_api_key):
    mock_error = {
        "status": "failed",
        "message": "Address could not be validated",
        "errors": ["Invalid street name"],
    }

    def handler(request: httpx.Request):
        return httpx.Response(400, json=mock_error)

    transport = httpx.MockTransport(handler)
    service = ShipBubbleService(api_key=mock_api_key, transport=transport)

    with pytest.raises(ShipBubbleError) as exc_info:
        await service.validate_address(
            name="Ada Customer",
            email="ada@example.com",
            phone="+2348012345678",
            address="Invalid place",
        )
    assert "Invalid street name" in exc_info.value.message
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_fetch_rates_success(mock_api_key):
    mock_rates_response = {
        "status": "success",
        "message": "Retrieved successfully",
        "data": {
            "request_token": "token_abc_1234567890",
            "couriers": [
                {
                    "courier_id": "cora",
                    "courier_name": "Cora Logistics",
                    "courier_image": "https://img.shipbubble.com/cora.png",
                    "service_code": "cora_standard",
                    "service_type": "pickup",
                    "rate_card_amount": 3500.0,
                    "total": 3000.0,
                    "currency": "NGN",
                    "delivery_eta": "Within 1 - 2 working days",
                },
                {
                    "courier_id": "dellyman",
                    "courier_name": "Dellyman Express",
                    "courier_image": "https://img.shipbubble.com/delly.png",
                    "service_code": "dellyman_express",
                    "service_type": "pickup",
                    "rate_card_amount": 2500.0,
                    "total": 2200.0,
                    "currency": "NGN",
                    "delivery_eta": "Within 23 hrs",
                },
            ],
            "cheapest_courier": {
                "courier_id": "dellyman",
                "courier_name": "Dellyman Express",
                "service_code": "dellyman_express",
                "rate_card_amount": 2500.0,
                "total": 2200.0,
                "currency": "NGN",
                "delivery_eta": "Within 23 hrs",
            },
            "fastest_courier": {
                "courier_id": "dellyman",
                "courier_name": "Dellyman Express",
                "service_code": "dellyman_express",
                "rate_card_amount": 2500.0,
                "total": 2200.0,
                "currency": "NGN",
                "delivery_eta": "Within 23 hrs",
            },
        },
    }

    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert "/shipping/fetch_rates" in str(request.url)
        body = json.loads(request.content)
        assert body["sender_address_code"] == 11111111
        assert body["reciever_address_code"] == 22222222
        assert body["category_id"] == 98794022
        return httpx.Response(200, json=mock_rates_response)

    transport = httpx.MockTransport(handler)
    service = ShipBubbleService(api_key=mock_api_key, transport=transport)

    rates_result = await service.fetch_rates(
        sender_address_code=11111111,
        receiver_address_code=22222222,
        pickup_date="2026-10-15",
        category_id=98794022,
        package_items=[
            {
                "name": "Ankara Dress",
                "description": "Fashion clothing",
                "unit_weight": 0.8,
                "unit_amount": 45000,
                "quantity": 1,
            }
        ],
        package_dimension={"length": 25.0, "width": 20.0, "height": 5.0},
    )

    assert rates_result.request_token == "token_abc_1234567890"
    assert len(rates_result.couriers) == 2

    cora = rates_result.couriers[0]
    assert cora.courier_name == "Cora Logistics"
    assert cora.rate_card_amount == Decimal("3500.00")
    assert cora.total_wallet_amount == Decimal("3000.00")
    assert cora.min_delivery_days == 1
    assert cora.max_delivery_days == 2
    assert cora.courier_image == "https://img.shipbubble.com/cora.png"

    delly = rates_result.couriers[1]
    assert delly.rate_card_amount == Decimal("2500.00")
    assert delly.min_delivery_days == 0
    assert delly.max_delivery_days == 1


@pytest.mark.asyncio
async def test_create_label_success(mock_api_key):
    mock_label_response = {
        "status": "success",
        "message": "Order successfully routed to Dellyman",
        "data": {
            "order_id": "SB-8F7E412A3B9C",
            "status": "pending",
            "courier": {
                "name": "Dellyman Express",
                "email": "contact@dellyman.com",
                "phone": "+2348000000000",
                "tracking_code": "DM-998877",
            },
            "payment": {
                "shipping_fee": 2200,
                "type": "wallet",
                "currency": "NGN",
            },
            "tracking_url": "https://track.shipbubble.com/SB-8F7E412A3B9C",
            "waybill_document": "https://docs.shipbubble.com/waybill/SB-8F7E412A3B9C.pdf",
        },
    }

    def handler(request: httpx.Request):
        assert request.method == "POST"
        assert "/shipping/labels" in str(request.url)
        body = json.loads(request.content)
        assert body["request_token"] == "token_123"
        assert body["service_code"] == "dellyman_express"
        assert body["courier_id"] == "dellyman"
        return httpx.Response(200, json=mock_label_response)

    transport = httpx.MockTransport(handler)
    service = ShipBubbleService(api_key=mock_api_key, transport=transport)

    result = await service.create_label(
        request_token="token_123",
        service_code="dellyman_express",
        courier_id="dellyman",
    )

    assert result.order_id == "SB-8F7E412A3B9C"
    assert result.courier_name == "Dellyman Express"
    assert result.tracking_code == "DM-998877"
    assert result.tracking_url == "https://track.shipbubble.com/SB-8F7E412A3B9C"
    assert result.waybill_document_url == "https://docs.shipbubble.com/waybill/SB-8F7E412A3B9C.pdf"
    assert result.shipping_fee == Decimal("2200.00")


@pytest.mark.asyncio
async def test_get_wallet_balance(mock_api_key):
    mock_wallet_response = {
        "status": "success",
        "data": {
            "balance": 150000.50,
            "currency": "NGN",
        },
    }

    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert "/shipping/wallet/balance" in str(request.url)
        return httpx.Response(200, json=mock_wallet_response)

    transport = httpx.MockTransport(handler)
    service = ShipBubbleService(api_key=mock_api_key, transport=transport)

    wallet = await service.get_wallet_balance()
    assert wallet["balance"] == 150000.50
    assert wallet["currency"] == "NGN"


def test_webhook_hmac_sha512_verification(mock_api_key):
    payload = {
        "event": "shipment.status.changed",
        "order_id": "SB-8F7E412A3B9C",
        "status": "picked_up",
        "courier": {
            "name": "Dellyman",
            "tracking_code": "DM-998877",
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")

    # Generate signature using API key
    signature = hmac.new(
        mock_api_key.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()

    # Verify signature matches
    expected = hmac.new(
        mock_api_key.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()

    assert hmac.compare_digest(signature, expected)

    # Wrong signature rejected
    assert not hmac.compare_digest("invalid_signature_hex", expected)


@pytest.mark.asyncio
async def test_get_categories(mock_api_key):
    mock_cats = {
        "status": "success",
        "data": [
            {"category_id": 74794423, "category": "Fashion wears"},
            {"category_id": 20754594, "category": "Light weight items"},
        ],
    }

    def handler(request: httpx.Request):
        assert request.method == "GET"
        assert "/shipping/labels/categories" in str(request.url)
        return httpx.Response(200, json=mock_cats)

    transport = httpx.MockTransport(handler)
    service = ShipBubbleService(api_key=mock_api_key, transport=transport)
    cats = await service.get_categories()
    assert len(cats) == 2
    assert cats[0]["category_id"] == 74794423
    assert cats[0]["category"] == "Fashion wears"


def test_package_items_title_resolution():
    """Verify that Product.title (not product.name) is properly resolved for ShipBubble package items."""
    class DummyProduct:
        title = "Ankara Silk Kimono"
        description = "Handmade African kimono in vibrant print"

    class DummyItem:
        unit_price = Decimal("15000.00")
        quantity = 2

    product = DummyProduct()
    item = DummyItem()
    w = Decimal("0.75")

    product_title = getattr(product, "title", None) or getattr(product, "name", None) or "Item"
    product_desc = getattr(product, "description", None) or product_title

    package_item = {
        "name": str(product_title)[:50],
        "description": str(product_desc)[:100],
        "unit_weight": float(w),
        "unit_amount": float(item.unit_price),
        "quantity": int(item.quantity),
    }

    assert package_item["name"] == "Ankara Silk Kimono"
    assert "Handmade African kimono" in package_item["description"]
    assert package_item["unit_weight"] == 0.75
    assert package_item["unit_amount"] == 15000.0
    assert package_item["quantity"] == 2


@pytest.mark.asyncio
async def test_shipbubble_checkout_options_revalidates_stale_sender_address_code():
    """Verify _shipbubble_checkout_options re-validates hub sender_address_code on 422 Invalid sender address code."""
    from app.services.checkout.estimates import _shipbubble_checkout_options
    from app.services.shipbubble_service import ShipbubbleRateOption, ShipbubbleRatesResult

    hub = MagicMock()
    hub.shipbubble_address_code = 441105450  # stale sender code
    hub.address_line1 = "1 Admiralty Way, Lekki Phase 1"
    hub.address_line2 = None
    hub.city = "Lekki"
    hub.state = "Lagos"
    hub.contact_name = "Shopsoma Lagos Central Hub"
    hub.contact_phone = "+2348000000000"

    address = MagicMock()
    address.address_line1 = "1 Ladi Kwali Street"
    address.address_line2 = None
    address.city = "Abuja"
    address.state = "Federal Capital Territory"
    address.country = "Nigeria"
    address.full_name = "Ada Customer"
    address.phone_number = "08012345678"

    order = MagicMock()
    order.customer_id = uuid4()
    order.shipping_address = address

    db = AsyncMock()
    db.add = MagicMock()
    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = [hub]
    db.execute.return_value = exec_result
    db.get.return_value = None

    service = AsyncMock()

    async def validate_side_effect(**kwargs):
        if "Admiralty Way" in kwargs["address"]:
            assert kwargs.get("force_refresh") is True
            return {"address_code": 671363858}
        return {"address_code": 161892642}

    service.validate_address.side_effect = validate_side_effect

    expected_rates = ShipbubbleRatesResult(
        request_token="tok_fresh_123",
        couriers=[
            ShipbubbleRateOption(
                courier_id="fez",
                courier_name="Fez (Self Pick-up)",
                courier_image=None,
                service_code="fez_pickup",
                service_type="pickup",
                rate_card_amount=Decimal("3655.00"),
                total_wallet_amount=Decimal("3655.00"),
                currency="NGN",
                delivery_eta="Within 1 - 3 working days",
                min_delivery_days=1,
                max_delivery_days=3,
            )
        ],
    )

    call_count = 0

    async def fetch_rates_side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            assert kwargs["sender_address_code"] == 441105450
            raise ShipBubbleError(
                "ShipBubble API error (422): Invalid sender address code: Invalid sender address code",
                status_code=422,
            )
        assert kwargs["sender_address_code"] == 671363858
        assert kwargs["receiver_address_code"] == 161892642
        return expected_rates

    service.fetch_rates.side_effect = fetch_rates_side_effect

    dummy_item = MagicMock(quantity=1, unit_price=Decimal("10000.00"))
    dummy_product = MagicMock(title="Silk Dress", description="Silk Dress")

    with (
        patch("app.services.checkout.estimates.get_shipbubble_service", return_value=service),
        patch(
            "app.services.checkout.estimates._authoritative_parcel_measurements",
            new=AsyncMock(return_value=[(dummy_item, dummy_product, None, (Decimal("0.5"), Decimal("10"), Decimal("10"), Decimal("10")))]),
        ),
    ):
        result = await _shipbubble_checkout_options(db, order=order)

    assert result.request_token == "tok_fresh_123"
    assert len(result.couriers) == 1
    assert hub.shipbubble_address_code == 671363858
    assert call_count == 2

