"""Tests for Admin-Side Made-to-Order Production Tracking.

Covers:
- Platform working-day calendar rules (excluding Saturday & Sunday)
- Configured production duration parsing and timeline extraction
- Classification (MTO vs RTW) on Admin Order Detail API
- Working-days-left calculations and overdue tracking
- Completed / early vendor-ready items safe handling
- Missing/invalid date and timeline safety
- Regression protection for RTW and vendor-ready flows
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.models.vendor import KYCStatus, Vendor
from app.models.order import Order, OrderItem, PaymentStatus, FulfillmentStatus
from app.models.address import Address, AddressType
from app.models.product import Product, ProductType, ProductStatus, ModerationStatus
from app.models.vendor_pickup import OrderType, PickupStatus, VendorPickup
from app.core.security import create_access_token, get_password_hash
from app.services.orders.production_tracking import (
    is_working_day,
    add_working_days,
    count_working_days_between,
    parse_production_days,
    get_production_tracking,
)


# ============================================================================
# UNIT TESTS: Working-Day Calendar & Timeline Parsing
# ============================================================================

def test_working_day_rules_and_weekend_exclusion():
    # 2026-10-05 is Monday, 2026-10-09 is Friday, 2026-10-10 is Saturday, 2026-10-11 is Sunday
    monday = date(2026, 10, 5)
    friday = date(2026, 10, 9)
    saturday = date(2026, 10, 10)
    sunday = date(2026, 10, 11)

    assert is_working_day(monday) is True
    assert is_working_day(friday) is True
    assert is_working_day(saturday) is False
    assert is_working_day(sunday) is False

    # Adding 5 working days from Monday should skip Saturday and Sunday and land on next Monday
    due = add_working_days(monday, 5)
    assert due == date(2026, 10, 12)  # Next Monday

    # Adding 1 working day from Friday lands on Monday
    assert add_working_days(friday, 1) == date(2026, 10, 12)

    # Adding 0 working days returns the current date
    assert add_working_days(monday, 0) == monday

    # Counting working days:
    # From Monday Oct 5 to Monday Oct 12: 5 working days (Tue, Wed, Thu, Fri, Mon)
    assert count_working_days_between(monday, date(2026, 10, 12)) == 5
    # From Friday Oct 9 to Monday Oct 12: 1 working day (Mon)
    assert count_working_days_between(friday, date(2026, 10, 12)) == 1
    # From Saturday Oct 10 to Monday Oct 12: 1 working day (Mon)
    assert count_working_days_between(saturday, date(2026, 10, 12)) == 1
    # On due date: 0 working days left
    assert count_working_days_between(date(2026, 10, 12), date(2026, 10, 12)) == 0
    # Past due date (overdue): negative count
    assert count_working_days_between(date(2026, 10, 13), date(2026, 10, 12)) == -1
    assert count_working_days_between(date(2026, 10, 14), date(2026, 10, 12)) == -2


def test_parse_production_days():
    assert parse_production_days("5-7 business days") == 7
    assert parse_production_days("10-14 business days") == 14
    assert parse_production_days("Ships in 2-3 weeks") == 15
    assert parse_production_days("2 weeks") == 10
    assert parse_production_days("3 weeks") == 15
    assert parse_production_days("7 days") == 7
    assert parse_production_days("10 working days") == 10
    assert parse_production_days("5") == 5
    assert parse_production_days(None, estimated_days=12) == 12
    assert parse_production_days("Bespoke custom", None) is None
    assert parse_production_days("", None) is None
    assert parse_production_days(None, None) is None


# ============================================================================
# INTEGRATION FIXTURES & HELPERS
# ============================================================================

async def _create_test_admin(db: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        email="admin-prod-track@shopsoma.test",
        hashed_password=get_password_hash("AdminPass123!"),
        full_name="Admin Tracker",
        role=UserRole.ADMIN,
        email_verified=True,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    return {"user": user, "headers": {"Authorization": f"Bearer {token}"}}


async def _create_test_vendor(db: AsyncSession, name="Vendor Tracker"):
    user = User(
        id=uuid.uuid4(),
        email=f"vendor-{uuid.uuid4().hex[:6]}@shopsoma.test",
        hashed_password=get_password_hash("VendorPass123!"),
        full_name=name,
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user.id,
        business_name=name,
        kyc_status=KYCStatus.APPROVED,
        approved=True,
        is_onboarding=False,
        brand_info_completed=True,
        featured_storefront_image_url="/uploads/fixture.webp",
        payout_info_completed=True,
    )
    db.add(vendor)
    await db.commit()
    token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role.value}
    )
    return {"user": user, "vendor": vendor, "headers": {"Authorization": f"Bearer {token}"}}


async def _create_test_order(
    db: AsyncSession,
    vendor,
    *,
    mto_timeline="5-7 business days",
    confirmed_at=None,
    ready_for_pickup_at=None,
):
    customer = User(
        id=uuid.uuid4(),
        email=f"customer-{uuid.uuid4().hex[:6]}@example.test",
        hashed_password=get_password_hash("CustPass123!"),
        full_name="Test Customer",
        role=UserRole.CUSTOMER,
        email_verified=True,
        is_active=True,
    )
    db.add(customer)
    await db.flush()

    address = Address(
        id=uuid.uuid4(),
        user_id=customer.id,
        address_type=AddressType.SHIPPING,
        full_name="Test Customer",
        phone_number="08012345678",
        address_line1="123 Test Street",
        city="Lagos",
        state="Lagos",
        postal_code="100001",
        country="Nigeria",
        is_default=True,
    )
    db.add(address)
    await db.flush()

    mto_product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor["vendor"].id,
        title="Custom Kaftan",
        description="Custom Kaftan",
        base_price=Decimal("150.00"),
        currency="NGN",
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
        made_to_order=True,
        made_to_order_timeline=mto_timeline,
    )
    rtw_product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor["vendor"].id,
        title="Ready T-Shirt",
        description="Ready T-Shirt",
        base_price=Decimal("50.00"),
        currency="NGN",
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
        made_to_order=False,
        made_to_order_timeline=None,
    )
    db.add_all([mto_product, rtw_product])
    await db.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number=f"SHP-TRK-{uuid.uuid4().hex[:6].upper()}",
        customer_id=customer.id,
        shipping_address_id=address.id,
        billing_address_id=address.id,
        currency="NGN",
        subtotal=Decimal("200.00"),
        total_amount=Decimal("200.00"),
        payment_status=PaymentStatus.PAID,
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        confirmed_at=confirmed_at or datetime.now(timezone.utc),
    )
    db.add(order)
    await db.flush()

    mto_item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=mto_product.id,
        vendor_id=vendor["vendor"].id,
        product_title=mto_product.title,
        unit_price=Decimal("150.00"),
        quantity=1,
        subtotal=Decimal("150.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("15.00"),
        vendor_payout=Decimal("135.00"),
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        inventory_policy="made_to_order",
    )
    rtw_item = OrderItem(
        id=uuid.uuid4(),
        order_id=order.id,
        product_id=rtw_product.id,
        vendor_id=vendor["vendor"].id,
        product_title=rtw_product.title,
        unit_price=Decimal("50.00"),
        quantity=1,
        subtotal=Decimal("50.00"),
        commission_rate=Decimal("10.00"),
        commission_amount=Decimal("5.00"),
        vendor_payout=Decimal("45.00"),
        fulfillment_status=FulfillmentStatus.ORDER_RECEIVED,
        inventory_policy=None,
    )
    db.add_all([mto_item, rtw_item])
    await db.flush()

    mto_pickup = VendorPickup(
        id=uuid.uuid4(),
        vendor_id=vendor["vendor"].id,
        order_id=order.id,
        order_item_id=mto_item.id,
        order_type=OrderType.MADE_TO_ORDER,
        estimated_production_days=parse_production_days(mto_timeline),
        ready_for_pickup_at=ready_for_pickup_at,
        status=PickupStatus.SCHEDULED,
    )
    rtw_pickup = VendorPickup(
        id=uuid.uuid4(),
        vendor_id=vendor["vendor"].id,
        order_id=order.id,
        order_item_id=rtw_item.id,
        order_type=OrderType.RTW,
        estimated_production_days=None,
        status=PickupStatus.SCHEDULED,
    )
    db.add_all([mto_pickup, rtw_pickup])
    await db.commit()

    return order, mto_item, rtw_item, mto_pickup, rtw_pickup


# ============================================================================
# API INTEGRATION TESTS: Admin Order Detail Production Tracking
# ============================================================================

@pytest.mark.asyncio
async def test_admin_order_detail_production_tracking_classification_and_countdown(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin = await _create_test_admin(db_session)
    vendor = await _create_test_vendor(db_session)

    # Order confirmed today (or recent working day) with "5-7 business days" timeline
    now = datetime.now(timezone.utc)
    order, mto_item, rtw_item, _, _ = await _create_test_order(
        db_session, vendor, mto_timeline="5-7 business days", confirmed_at=now
    )

    response = await client.get(f"/api/v1/admin/orders/{order.id}", headers=admin["headers"])
    assert response.status_code == 200, response.text
    payload = response.json()

    # Find the MTO item and RTW item
    items_by_id = {item["id"]: item for item in payload["items"]}
    mto_data = items_by_id[str(mto_item.id)]
    rtw_data = items_by_id[str(rtw_item.id)]

    # 1. Classification is visible per order item
    assert mto_data["made_to_order"] is True
    assert mto_data["order_type"] == "made_to_order"

    assert rtw_data["made_to_order"] is False
    assert rtw_data["order_type"] == "rtw"

    # 2. MTO configured production duration and working days left are populated
    assert mto_data["production_duration"] == "5-7 business days"
    assert mto_data["estimated_production_days"] == 7
    assert mto_data["production_start_date"] is not None
    assert mto_data["production_due_date"] is not None
    assert mto_data["working_days_left"] is not None
    assert mto_data["working_days_left"] > 0
    assert mto_data["is_production_overdue"] is False
    assert mto_data["is_production_completed"] is False

    # 3. RTW items do NOT show MTO countdown data
    assert rtw_data["production_duration"] is None
    assert rtw_data["estimated_production_days"] is None
    assert rtw_data["production_start_date"] is None
    assert rtw_data["production_due_date"] is None
    assert rtw_data["working_days_left"] is None
    assert rtw_data["is_production_overdue"] is False
    assert rtw_data["is_production_completed"] is False


@pytest.mark.asyncio
async def test_admin_order_detail_overdue_mto_item(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin = await _create_test_admin(db_session)
    vendor = await _create_test_vendor(db_session)

    # Order confirmed 30 calendar days ago (~20 working days ago) with a 5-day timeline
    old_date = datetime.now(timezone.utc) - timedelta(days=30)
    order, mto_item, _, _, _ = await _create_test_order(
        db_session, vendor, mto_timeline="5 business days", confirmed_at=old_date
    )

    response = await client.get(f"/api/v1/admin/orders/{order.id}", headers=admin["headers"])
    assert response.status_code == 200, response.text
    payload = response.json()

    items_by_id = {item["id"]: item for item in payload["items"]}
    mto_data = items_by_id[str(mto_item.id)]

    assert mto_data["made_to_order"] is True
    assert mto_data["working_days_left"] is not None
    assert mto_data["working_days_left"] < 0
    assert mto_data["is_production_overdue"] is True
    assert mto_data["is_production_completed"] is False


@pytest.mark.asyncio
async def test_admin_order_detail_completed_mto_item_safely_handled(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin = await _create_test_admin(db_session)
    vendor = await _create_test_vendor(db_session)

    # Order completed (ready_for_pickup_at set)
    ready_time = datetime.now(timezone.utc)
    order, mto_item, _, mto_pickup, _ = await _create_test_order(
        db_session,
        vendor,
        mto_timeline="5-7 business days",
        ready_for_pickup_at=ready_time,
    )

    response = await client.get(f"/api/v1/admin/orders/{order.id}", headers=admin["headers"])
    assert response.status_code == 200, response.text
    payload = response.json()

    items_by_id = {item["id"]: item for item in payload["items"]}
    mto_data = items_by_id[str(mto_item.id)]

    assert mto_data["is_production_completed"] is True
    assert mto_data["is_production_overdue"] is False
    assert mto_data["ready_for_pickup_at"] is not None


@pytest.mark.asyncio
async def test_admin_order_detail_missing_timeline_safe_handling(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin = await _create_test_admin(db_session)
    vendor = await _create_test_vendor(db_session)

    # Order with no timeline string
    order, mto_item, _, _, _ = await _create_test_order(
        db_session, vendor, mto_timeline=""
    )

    response = await client.get(f"/api/v1/admin/orders/{order.id}", headers=admin["headers"])
    assert response.status_code == 200, response.text
    payload = response.json()

    items_by_id = {item["id"]: item for item in payload["items"]}
    mto_data = items_by_id[str(mto_item.id)]

    # Safe defaults without crashing
    assert mto_data["made_to_order"] is True
    assert mto_data["order_type"] == "made_to_order"
    assert mto_data["production_duration"] is None
    assert mto_data["estimated_production_days"] is None
    assert mto_data["working_days_left"] is None
    assert mto_data["is_production_overdue"] is False
