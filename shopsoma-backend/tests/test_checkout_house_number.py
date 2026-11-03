"""Tests for optional House number field on checkout addresses and fulfilment/delivery flows."""
import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.admin_orders import build_address_info
from app.models.address import Address, AddressType
from app.models.order import FulfillmentStatus, Order, OrderItem, PaymentStatus
from app.models.product import ModerationStatus, Product, ProductStatus
from app.models.shipping_rate import ShippingRate
from app.schemas.address import AddressCreate, AddressResponse, AddressUpdate
from app.schemas.order import GuestAddressData


def test_address_schemas_and_model_sync_house_number_and_address_line2():
    # 1. Creating with house_number populates both house_number and address_line2
    created = AddressCreate(
        full_name="Ada Lovelace",
        phone_number="08012345678",
        address_line1="12 Admiralty Way",
        house_number="House 14B",
        city="Lekki",
        state="Lagos",
        postal_code="106104",
        country="Nigeria",
    )
    assert created.house_number == "House 14B"
    assert created.address_line2 == "House 14B"

    # 2. Creating with blank/omitted house_number leaves both None
    blank = AddressCreate(
        full_name="Ada Lovelace",
        phone_number="08012345678",
        address_line1="12 Admiralty Way",
        house_number="   ",
        city="Lekki",
        state="Lagos",
        country="Nigeria",
    )
    assert blank.house_number is None
    assert blank.address_line2 is None

    # 3. AddressUpdate partial update without house_number does not set address_line2
    partial_update = AddressUpdate(city="Abuja")
    dumped_partial = partial_update.model_dump(exclude_unset=True)
    assert "house_number" not in dumped_partial
    assert "address_line2" not in dumped_partial

    # 4. AddressUpdate with house_number sets both; clearing house_number clears both
    set_hn = AddressUpdate(house_number="Plot 7")
    assert set_hn.house_number == "Plot 7"
    assert set_hn.address_line2 == "Plot 7"

    clear_hn = AddressUpdate(house_number="")
    dumped_clear = clear_hn.model_dump(exclude_unset=True)
    assert dumped_clear["address_line2"] is None
    assert dumped_clear["house_number"] is None

    # 5. GuestAddressData syncs house_number and address_line2
    guest = GuestAddressData(
        full_name="Guest Buyer",
        phone_number="08012345678",
        address_line1="10 Maitama Way",
        house_number="Flat 2B",
        city="Abuja",
        state="FCT",
    )
    assert guest.house_number == "Flat 2B"
    assert guest.address_line2 == "Flat 2B"

    # 6. Address ORM model property & init
    orm_addr = Address(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        address_type=AddressType.SHIPPING,
        full_name="Ada Lovelace",
        phone_number="08012345678",
        address_line1="12 Admiralty Way",
        house_number="Suite 5",
        city="Lekki",
        state="Lagos",
        postal_code="106104",
        country="Nigeria",
        is_default=True,
    )
    assert orm_addr.address_line2 == "Suite 5"
    assert orm_addr.house_number == "Suite 5"

    info = build_address_info(orm_addr)
    assert info.house_number == "Suite 5"
    assert info.address_line2 == "Suite 5"
    assert info.street_address == "12 Admiralty Way, Suite 5"

    # Existing address without house number remains unaffected
    orm_addr_no_hn = Address(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        address_type=AddressType.SHIPPING,
        full_name="Ada Lovelace",
        phone_number="08012345678",
        address_line1="12 Admiralty Way",
        city="Lekki",
        state="Lagos",
        postal_code="106104",
        country="Nigeria",
        is_default=True,
    )
    info_no_hn = build_address_info(orm_addr_no_hn)
    assert info_no_hn.house_number is None
    assert info_no_hn.address_line2 is None
    assert info_no_hn.street_address == "12 Admiralty Way"


@pytest.mark.asyncio
async def test_address_crud_and_fulfilment_with_and_without_house_number(
    client: AsyncClient,
    db_session: AsyncSession,
    customer_user,
    vendor_user,
    admin_user,
):
    headers = {"Authorization": f"Bearer {customer_user['token']}"}

    # 1. Create address with house_number
    create_resp = await client.post(
        "/api/v1/addresses",
        headers=headers,
        json={
            "full_name": "Customer One",
            "phone_number": "08012345678",
            "address_line1": "15 Awolowo Road",
            "house_number": "House 9A",
            "city": "Ikoyi",
            "state": "Lagos",
            "postal_code": "101233",
            "country": "Nigeria",
            "is_default": True,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    addr_data = create_resp.json()
    assert addr_data["house_number"] == "House 9A"
    assert addr_data["address_line2"] == "House 9A"
    address_id = addr_data["id"]

    # 2. Update address house_number
    update_resp = await client.put(
        f"/api/v1/addresses/{address_id}",
        headers=headers,
        json={"house_number": "House 11C"},
    )
    assert update_resp.status_code == 200, update_resp.text
    updated_data = update_resp.json()
    assert updated_data["house_number"] == "House 11C"
    assert updated_data["address_line2"] == "House 11C"

    # 3. Create address with blank house_number (optional)
    blank_resp = await client.post(
        "/api/v1/addresses",
        headers=headers,
        json={
            "full_name": "Customer One",
            "phone_number": "08012345678",
            "address_line1": "20 Marina Street",
            "house_number": "",
            "city": "Lagos Island",
            "state": "Lagos",
            "postal_code": "100001",
            "country": "Nigeria",
            "is_default": False,
        },
    )
    assert blank_resp.status_code == 201, blank_resp.text
    blank_data = blank_resp.json()
    assert blank_data["house_number"] is None
    assert blank_data["address_line2"] is None

    # 4. Verify order fulfilment endpoints (admin & vendor) carry house_number
    product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_user["vendor"].id,
        title="Fulfilment Test Dress",
        description="Test product",
        base_price=Decimal("45000.00"),
        currency="NGN",
        total_stock=10,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    db_session.add(product)
    await db_session.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number=f"SHP-HN-{uuid.uuid4().hex[:6].upper()}",
        customer_id=customer_user["user"].id,
        shipping_address_id=uuid.UUID(address_id),
        billing_address_id=uuid.UUID(address_id),
        currency="NGN",
        subtotal=Decimal("45000.00"),
        shipping_cost=Decimal("2500.00"),
        tax_amount=Decimal("3562.50"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("51062.50"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order)
    await db_session.flush()

    order_item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=product.id,
        vendor_id=vendor_user["vendor"].id,
        product_title=product.title,
        unit_price=Decimal("45000.00"),
        currency="NGN",
        quantity=1,
        subtotal=Decimal("45000.00"),
        commission_rate=Decimal("15.00"),
        commission_amount=Decimal("6750.00"),
        vendor_payout=Decimal("38250.00"),
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
    )
    db_session.add(order_item)
    await db_session.commit()

    admin_headers = {"Authorization": f"Bearer {admin_user['token']}"}
    admin_detail_resp = await client.get(
        f"/api/v1/admin/orders/{order.id}",
        headers=admin_headers,
    )
    assert admin_detail_resp.status_code == 200, admin_detail_resp.text
    admin_order_json = admin_detail_resp.json()
    assert admin_order_json["shipping_address"]["house_number"] == "House 11C"
    assert admin_order_json["shipping_address"]["address_line2"] == "House 11C"
    assert "House 11C" in admin_order_json["shipping_address"]["street_address"]

    vendor_headers = {"Authorization": f"Bearer {vendor_user['token']}"}
    vendor_detail_resp = await client.get(
        f"/api/v1/vendor/orders/{order.id}",
        headers=vendor_headers,
    )
    assert vendor_detail_resp.status_code == 200, vendor_detail_resp.text
    vendor_order_json = vendor_detail_resp.json()
    assert vendor_order_json["shipping_address"]["house_number"] == "House 11C"
    assert vendor_order_json["shipping_address"]["address_line2"] == "House 11C"
