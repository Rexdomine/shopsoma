import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_public_designers_list_only_returns_approved(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from app.core.security import get_password_hash
    from app.models.user import User, UserRole
    from app.models.vendor import Vendor, KYCStatus

    approved_user = User(
        id=uuid.uuid4(),
        email="approved@test.com",
        hashed_password=get_password_hash("VendorPass123"),
        full_name="Approved Vendor",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    pending_user = User(
        id=uuid.uuid4(),
        email="pending@test.com",
        hashed_password=get_password_hash("VendorPass123"),
        full_name="Pending Vendor",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    inactive_user = User(
        id=uuid.uuid4(),
        email="inactive@test.com",
        hashed_password=get_password_hash("VendorPass123"),
        full_name="Inactive Vendor",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=False,
    )
    paused_user = User(
        id=uuid.uuid4(),
        email="paused@test.com",
        hashed_password=get_password_hash("VendorPass123"),
        full_name="Paused Vendor",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    db_session.add_all([approved_user, pending_user, inactive_user, paused_user])
    await db_session.flush()

    approved_vendor = Vendor(
        id=uuid.uuid4(),
        user_id=approved_user.id,
        business_name="Approved Brand",
        kyc_status=KYCStatus.APPROVED,
        approved=True,
        is_onboarding=False,
        store_active=True,
        total_products=3,
        total_orders=2,
    )
    pending_vendor = Vendor(
        id=uuid.uuid4(),
        user_id=pending_user.id,
        business_name="Pending Brand",
        kyc_status=KYCStatus.PENDING,
        approved=False,
        is_onboarding=False,
    )
    inactive_vendor = Vendor(
        id=uuid.uuid4(),
        user_id=inactive_user.id,
        business_name="Inactive User Brand",
        kyc_status=KYCStatus.APPROVED,
        approved=True,
        is_onboarding=False,
        store_active=True,
    )
    paused_vendor = Vendor(
        id=uuid.uuid4(),
        user_id=paused_user.id,
        business_name="Paused Store Brand",
        kyc_status=KYCStatus.APPROVED,
        approved=True,
        is_onboarding=False,
        store_active=False,
    )
    db_session.add_all([approved_vendor, pending_vendor, inactive_vendor, paused_vendor])
    await db_session.commit()

    response = await client.get("/api/v1/designers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["business_name"] == "Approved Brand"


@pytest.mark.asyncio
async def test_designer_storefront_detail_and_published_only_hydration(
    client: AsyncClient,
    db_session: AsyncSession,
):
    from decimal import Decimal
    from app.core.security import get_password_hash
    from app.models.category import Category
    from app.models.product import (
        ModerationStatus,
        Product,
        ProductImage,
        ProductStatus,
    )
    from app.models.user import User, UserRole
    from app.models.vendor import KYCStatus, Vendor

    user_a = User(
        id=uuid.uuid4(),
        email="atelier-a@test.com",
        hashed_password=get_password_hash("VendorPass123"),
        full_name="Atelier A",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    user_b = User(
        id=uuid.uuid4(),
        email="pending-b@test.com",
        hashed_password=get_password_hash("VendorPass123"),
        full_name="Pending B",
        role=UserRole.VENDOR,
        email_verified=True,
        is_active=True,
    )
    db_session.add_all([user_a, user_b])
    await db_session.flush()

    published_category = Category(
        id=uuid.uuid4(),
        name="Evening Wear",
        slug="evening-wear-test",
        display_order=1,
        is_active=True,
    )
    unpublished_category = Category(
        id=uuid.uuid4(),
        name="Draft Only Category",
        slug="draft-only-test",
        display_order=2,
        is_active=True,
    )
    db_session.add_all([published_category, unpublished_category])
    await db_session.flush()

    vendor_a = Vendor(
        id=uuid.uuid4(),
        user_id=user_a.id,
        business_name="Amaka Couture",
        business_description="Bespoke evening wear crafted in Lagos.",
        logo_url="https://cdn.shopsoma.com/amaka-logo.png",
        kyc_status=KYCStatus.APPROVED,
        approved=True,
        is_onboarding=False,
        store_active=True,
    )
    unapproved_vendor = Vendor(
        id=uuid.uuid4(),
        user_id=user_b.id,
        business_name="Unapproved Studio",
        kyc_status=KYCStatus.PENDING,
        approved=False,
        is_onboarding=False,
        store_active=True,
    )
    db_session.add_all([vendor_a, unapproved_vendor])
    await db_session.flush()

    published_product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_a.id,
        category_id=published_category.id,
        title="Published Silk Gown",
        base_price=Decimal("120000.00"),
        currency="NGN",
        total_stock=5,
        status=ProductStatus.ACTIVE,
        moderation_status=ModerationStatus.APPROVED,
    )
    draft_product = Product(
        id=uuid.uuid4(),
        vendor_id=vendor_a.id,
        category_id=unpublished_category.id,
        title="Unpublished Draft Coat",
        base_price=Decimal("95000.00"),
        currency="NGN",
        total_stock=3,
        status=ProductStatus.DRAFT,
        moderation_status=ModerationStatus.PENDING,
    )
    db_session.add_all([published_product, draft_product])
    await db_session.flush()

    db_session.add_all(
        [
            ProductImage(
                id=uuid.uuid4(),
                product_id=published_product.id,
                image_url="https://cdn.shopsoma.com/published-gown.jpg",
                is_primary=True,
                display_order=0,
            ),
            ProductImage(
                id=uuid.uuid4(),
                product_id=draft_product.id,
                image_url="https://cdn.shopsoma.com/secret-draft.jpg",
                is_primary=True,
                display_order=0,
            ),
        ]
    )
    await db_session.commit()

    # Detail endpoint returns hydrated designer with published product image and category only
    detail_resp = await client.get(f"/api/v1/designers/{vendor_a.id}")
    assert detail_resp.status_code == 200
    payload = detail_resp.json()
    assert payload["id"] == str(vendor_a.id)
    assert payload["business_name"] == "Amaka Couture"
    assert payload["business_description"] == "Bespoke evening wear crafted in Lagos."
    assert payload["campaign_image_url"] == "https://cdn.shopsoma.com/published-gown.jpg"
    assert payload["image_url"] == "https://cdn.shopsoma.com/published-gown.jpg"
    assert payload["published_products_count"] == 1
    assert [cat["name"] for cat in payload["categories"]] == ["Evening Wear"]

    # Unapproved designer returns 404 on storefront detail endpoint
    unapproved_resp = await client.get(f"/api/v1/designers/{unapproved_vendor.id}")
    assert unapproved_resp.status_code == 404
