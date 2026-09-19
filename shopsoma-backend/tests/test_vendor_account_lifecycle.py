import uuid

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.user import User


async def test_deactivating_vendor_hides_products_from_public_catalog(
    client,
    db_session,
    admin_user,
    vendor_user,
    sample_product,
):
    deactivate = await client.put(
        f"/api/v1/admin/users/{vendor_user['user'].id}/status?is_active=false",
        headers=admin_user["headers"],
    )

    assert deactivate.status_code == 200
    await db_session.refresh(vendor_user["user"])
    assert vendor_user["user"].is_active is False

    catalog = await client.get("/api/v1/products")
    assert catalog.status_code == 200
    assert str(sample_product.id) not in {item["id"] for item in catalog.json()["products"]}

    detail = await client.get(f"/api/v1/products/{sample_product.id}")
    assert detail.status_code == 404

    persisted_vendor_user = await db_session.scalar(
        select(User).where(User.id == vendor_user["user"].id)
    )
    assert persisted_vendor_user is not None
    assert persisted_vendor_user.is_active is False


async def test_deactivating_user_writes_lifecycle_audit_event(
    client,
    db_session,
    admin_user,
    vendor_user,
):
    response = await client.put(
        f"/api/v1/admin/users/{vendor_user['user'].id}/status?is_active=false",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200

    audit_log = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "user_deactivated",
            AuditLog.entity_type == "user",
            AuditLog.entity_id == vendor_user["user"].id,
        )
    )

    assert audit_log is not None
    assert audit_log.user_id == admin_user["user"].id
    assert audit_log.old_values == {"is_active": True}
    assert audit_log.new_values == {"is_active": False}


async def test_bulk_deactivation_updates_each_selected_account_and_audits_each_transition(
    client,
    db_session,
    admin_user,
    customer_user,
    vendor_user,
):
    response = await client.put(
        "/api/v1/admin/users/status/bulk",
        json={
            "user_ids": [str(customer_user["user"].id), str(vendor_user["user"].id)],
            "is_active": False,
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requested_count"] == 2
    assert payload["updated_count"] == 2
    assert {result["user_id"] for result in payload["results"]} == {
        str(customer_user["user"].id),
        str(vendor_user["user"].id),
    }
    assert all(result["status"] == "updated" for result in payload["results"])

    for account in (customer_user["user"], vendor_user["user"]):
        await db_session.refresh(account)
        assert account.is_active is False

    audit_events = (await db_session.execute(
        select(AuditLog).where(
            AuditLog.action == "user_deactivated",
            AuditLog.user_id == admin_user["user"].id,
        )
    )).scalars().all()
    assert {event.entity_id for event in audit_events} == {
        customer_user["user"].id,
        vendor_user["user"].id,
    }


async def test_bulk_deactivation_rejects_duplicate_ids_before_mutating_accounts(
    client,
    db_session,
    admin_user,
    customer_user,
):
    response = await client.put(
        "/api/v1/admin/users/status/bulk",
        json={
            "user_ids": [str(customer_user["user"].id), str(customer_user["user"].id)],
            "is_active": False,
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 422
    await db_session.refresh(customer_user["user"])
    assert customer_user["user"].is_active is True


async def test_bulk_deactivation_rejects_missing_ids_before_mutating_existing_accounts(
    client,
    db_session,
    admin_user,
    customer_user,
):
    response = await client.put(
        "/api/v1/admin/users/status/bulk",
        json={
            "user_ids": [str(customer_user["user"].id), str(uuid.uuid4())],
            "is_active": False,
        },
        headers=admin_user["headers"],
    )

    assert response.status_code == 404
    await db_session.rollback()
    await db_session.refresh(customer_user["user"])
    assert customer_user["user"].is_active is True


async def test_bulk_status_rejects_the_acting_admin_before_mutation(
    client,
    db_session,
    admin_user,
):
    response = await client.put(
        "/api/v1/admin/users/status/bulk",
        json={"user_ids": [str(admin_user["user"].id)], "is_active": False},
        headers=admin_user["headers"],
    )

    assert response.status_code == 400
    await db_session.refresh(admin_user["user"])
    assert admin_user["user"].is_active is True


async def test_deactivating_vendor_hides_public_designer_profile(
    client,
    admin_user,
    vendor_user,
):
    deactivate = await client.put(
        f"/api/v1/admin/users/{vendor_user['user'].id}/status?is_active=false",
        headers=admin_user["headers"],
    )
    assert deactivate.status_code == 200

    response = await client.get("/api/v1/designers")
    assert response.status_code == 200
    assert str(vendor_user["vendor"].id) not in {vendor["id"] for vendor in response.json()}


async def test_order_review_rejects_product_from_deactivated_vendor(
    client,
    admin_user,
    sample_product,
    vendor_user,
):
    deactivate = await client.put(
        f"/api/v1/admin/users/{vendor_user['user'].id}/status?is_active=false",
        headers=admin_user["headers"],
    )
    assert deactivate.status_code == 200

    response = await client.post(
        "/api/v1/orders/review",
        json={
            "items": [{"product_id": str(sample_product.id), "quantity": 1}],
            "guest_address": {
                "full_name": "Checkout Test",
                "phone_number": "08000000000",
                "address_line1": "123 Test Street",
                "city": "Lagos",
                "state": "Lagos",
                "country": "Nigeria",
            },
        },
    )

    assert response.status_code == 404


async def test_order_creation_rejects_product_from_deactivated_vendor(
    client,
    admin_user,
    sample_product,
    vendor_user,
):
    deactivate = await client.put(
        f"/api/v1/admin/users/{vendor_user['user'].id}/status?is_active=false",
        headers=admin_user["headers"],
    )
    assert deactivate.status_code == 200

    response = await client.post(
        "/api/v1/orders",
        json={
            "items": [{"product_id": str(sample_product.id), "quantity": 1}],
            "guest_address": {
                "full_name": "Checkout Test",
                "phone_number": "08000000000",
                "address_line1": "123 Test Street",
                "city": "Lagos",
                "state": "Lagos",
                "country": "Nigeria",
            },
            "customer_email": "checkout@example.com",
        },
    )

    assert response.status_code == 404


async def test_wishlist_rejects_and_hides_product_from_deactivated_vendor(
    client,
    admin_user,
    customer_user,
    sample_product,
    vendor_user,
):
    added = await client.post(
        "/api/v1/wishlist",
        json={"product_id": str(sample_product.id)},
        headers=customer_user["headers"],
    )
    assert added.status_code == 201

    deactivate = await client.put(
        f"/api/v1/admin/users/{vendor_user['user'].id}/status?is_active=false",
        headers=admin_user["headers"],
    )
    assert deactivate.status_code == 200

    wishlist = await client.get("/api/v1/wishlist", headers=customer_user["headers"])
    assert wishlist.status_code == 200
    assert wishlist.json()["total"] == 0
    assert wishlist.json()["items"] == []

    rejected_add = await client.post(
        "/api/v1/wishlist",
        json={"product_id": str(sample_product.id)},
        headers=customer_user["headers"],
    )
    assert rejected_add.status_code == 404
