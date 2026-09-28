from pathlib import Path
import uuid

import pytest


ROOT = Path(__file__).parents[2]
BACKEND_ORDERS = ROOT / "shopsoma-backend/app/api/v1/orders.py"
FRONTEND_CART = ROOT / "shopsoma-frontend/src/pages/cart/Cart.tsx"


def test_review_and_create_order_have_no_universal_minimum_order_rejection():
    source = BACKEND_ORDERS.read_text()

    assert "MIN_ORDER_AMOUNT_NGN" not in source
    assert source.count("Minimum order amount is") == 0


def test_cart_checkout_has_no_universal_minimum_order_preflight():
    source = FRONTEND_CART.read_text()

    assert "minimumOrderInSelectedCurrency" not in source
    assert "Minimum order is" not in source
    assert "subtotalInNgn < 60000" not in source


async def _create_below_minimum_product_and_shipping(db_session, vendor_user):
    from app.models.product import Product, ProductStatus, ModerationStatus
    from app.models.shipping_rate import ShippingRate

    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Below Minimum Product",
        description="Regression fixture below NGN 60,000",
        base_price=50000.00,
        currency="NGN",
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    shipping_rate = ShippingRate(
        id=uuid.uuid4(),
        name="Standard",
        description="Standard shipping",
        base_rate=1500.00,
        country="Nigeria",
        state="Lagos",
        is_active=True,
        is_default=True,
        priority=0,
    )
    db_session.add_all([product, shipping_rate])
    await db_session.commit()
    return product


def _below_minimum_guest_address():
    return {
        "full_name": "Guest User",
        "phone_number": "08000000000",
        "address_line1": "123 Test Street",
        "address_line2": "",
        "city": "Lagos",
        "state": "Lagos",
        "postal_code": "100001",
        "country": "Nigeria",
    }


@pytest.mark.asyncio
async def test_review_order_succeeds_below_ngn_60000(client, db_session, vendor_user):
    product = await _create_below_minimum_product_and_shipping(db_session, vendor_user)

    response = await client.post(
        "/api/v1/orders/review",
        json={
            "currency": "NGN",
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "guest_address": _below_minimum_guest_address(),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["summary"]["subtotal"] == "50000.00"


@pytest.mark.asyncio
async def test_create_order_succeeds_below_ngn_60000(client, db_session, vendor_user):
    product = await _create_below_minimum_product_and_shipping(db_session, vendor_user)

    response = await client.post(
        "/api/v1/orders",
        json={
            "currency": "NGN",
            "items": [{"product_id": str(product.id), "quantity": 1}],
            "guest_address": _below_minimum_guest_address(),
            "customer_email": "guest@example.com",
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["subtotal"] == "50000.00"
