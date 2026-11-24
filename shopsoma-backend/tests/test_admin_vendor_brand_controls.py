"""Admin brand-name and storefront-image controls on vendor management (SOMA-16 follow-up)."""
from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.services.image_service import image_service


async def test_admin_can_rename_vendor_brand_and_it_is_audited(client, db_session, admin_user, vendor_user):
    vendor = vendor_user["vendor"]
    previous = vendor.business_name

    response = await client.put(
        f"/api/v1/admin/vendors/{vendor.id}/brand-name",
        json={"business_name": "  Nouvelle   Gloria  "},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert response.json()["business_name"] == "Nouvelle Gloria"
    await db_session.refresh(vendor)
    assert vendor.business_name == "Nouvelle Gloria"

    log = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == vendor.id,
            AuditLog.action == "vendor_brand_name_updated",
        )
    )
    assert log is not None
    assert log.old_values == {"business_name": previous}
    assert log.new_values == {"business_name": "Nouvelle Gloria"}

    designers = await client.get("/api/v1/designers")
    if designers.status_code == 200:
        names = {item["id"]: item["business_name"] for item in designers.json()}
        if str(vendor.id) in names:
            assert names[str(vendor.id)] == "Nouvelle Gloria"


async def test_admin_brand_rename_rejects_blank_names(client, admin_user, vendor_user):
    vendor = vendor_user["vendor"]
    response = await client.put(
        f"/api/v1/admin/vendors/{vendor.id}/brand-name",
        json={"business_name": "   "},
        headers=admin_user["headers"],
    )
    assert response.status_code == 422


async def test_vendor_cannot_use_admin_brand_rename(client, vendor_user):
    vendor = vendor_user["vendor"]
    response = await client.put(
        f"/api/v1/admin/vendors/{vendor.id}/brand-name",
        json={"business_name": "Hijacked"},
        headers=vendor_user["headers"],
    )
    assert response.status_code in (401, 403)


async def test_admin_brand_rename_unknown_vendor_is_404(client, admin_user):
    response = await client.put(
        "/api/v1/admin/vendors/00000000-0000-0000-0000-000000000000/brand-name",
        json={"business_name": "Nobody"},
        headers=admin_user["headers"],
    )
    assert response.status_code == 404


async def test_admin_can_replace_storefront_image(client, db_session, admin_user, vendor_user, monkeypatch):
    vendor = vendor_user["vendor"]
    captured = {}

    async def fake_upload(file, folder="products", generate_variants=True):
        captured["folder"] = folder
        captured["generate_variants"] = generate_variants
        return {
            "original": "https://cdn.example.com/vendors/x/featured-storefront/new.jpg",
            "s3_key": "vendors/x/featured-storefront/new.jpg",
            "_storage_keys": ["vendors/x/featured-storefront/new.jpg"],
        }

    monkeypatch.setattr(image_service, "upload_image", fake_upload)

    response = await client.post(
        f"/api/v1/admin/vendors/{vendor.id}/storefront-image",
        files={"file": ("banner.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    assert response.json()["featured_storefront_image_url"].endswith("/new.jpg")
    assert captured["folder"] == f"vendors/{vendor.user_id}/featured-storefront"
    assert captured["generate_variants"] is False
    await db_session.refresh(vendor)
    assert vendor.featured_storefront_image_url.endswith("/new.jpg")

    log = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.entity_id == vendor.id,
            AuditLog.action == "vendor_storefront_image_updated",
        )
    )
    assert log is not None


async def test_admin_can_remove_storefront_image_when_not_featured(client, db_session, admin_user, vendor_user):
    vendor = vendor_user["vendor"]
    vendor.featured_storefront_image_url = "https://cdn.example.com/old.jpg"
    vendor.is_featured_storefront = False
    await db_session.commit()

    response = await client.delete(
        f"/api/v1/admin/vendors/{vendor.id}/storefront-image",
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    await db_session.refresh(vendor)
    assert vendor.featured_storefront_image_url is None


async def test_admin_cannot_remove_image_of_featured_vendor(client, db_session, admin_user, vendor_user):
    vendor = vendor_user["vendor"]
    vendor.featured_storefront_image_url = "https://cdn.example.com/keep.jpg"
    vendor.is_featured_storefront = True
    await db_session.commit()

    response = await client.delete(
        f"/api/v1/admin/vendors/{vendor.id}/storefront-image",
        headers=admin_user["headers"],
    )

    assert response.status_code == 409
    await db_session.refresh(vendor)
    assert vendor.featured_storefront_image_url == "https://cdn.example.com/keep.jpg"
