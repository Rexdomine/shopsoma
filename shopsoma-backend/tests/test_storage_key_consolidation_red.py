import uuid
from unittest.mock import AsyncMock, ANY

import pytest
from sqlalchemy import select

from app.models.product import ProductImage, ProductImageStorageCleanup


@pytest.mark.asyncio
async def test_vendor_rejects_storage_key_owned_by_other_product(
    client, vendor_user, sample_product, db_session
):
    other = type(sample_product)(
        id=uuid.uuid4(), vendor_id=sample_product.vendor_id, title="Other",
        base_price=10, total_stock=1,
    )
    db_session.add(other)
    await db_session.flush()
    db_session.add(ProductImage(
        product_id=other.id, image_url="https://example.com/old.jpg",
        storage_keys=["vendors/%s/products/shared.jpg" % vendor_user["vendor"].user_id],
    ))
    await db_session.commit()

    response = await client.post(
        f"/api/v1/products/{sample_product.id}/images",
        json={"image_url": "https://example.com/new.jpg", "storage_keys": [
            "vendors/%s/products/shared.jpg" % vendor_user["vendor"].user_id
        ]},
        headers=vendor_user["headers"],
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_product_creation_rejects_storage_key_owned_by_another_product(
    client, vendor_user, sample_product, db_session
):
    storage_key = f"vendors/{vendor_user['user'].id}/products/shared.jpg"
    db_session.add(ProductImage(
        product_id=sample_product.id,
        image_url="https://example.com/old.jpg",
        storage_keys=[storage_key],
    ))
    await db_session.commit()

    response = await client.post(
        "/api/v1/products",
        json={
            "title": "New product", "base_price": 10,
            "images": [{"image_url": "https://example.com/new.jpg", "storage_keys": [storage_key]}],
        },
        headers=vendor_user["headers"],
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_vendor_rejects_storage_key_reserved_by_unresolved_cleanup(
    client, vendor_user, sample_product, db_session
):
    storage_key = f"vendors/{vendor_user['user'].id}/products/pending-cleanup.jpg"
    db_session.add(ProductImageStorageCleanup(
        storage_keys=[storage_key], reason="vendor_image_delete"
    ))
    await db_session.commit()

    response = await client.post(
        f"/api/v1/products/{sample_product.id}/images",
        json={"image_url": "https://example.com/new.jpg", "storage_keys": [storage_key]},
        headers=vendor_user["headers"],
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_admin_json_image_rejects_client_storage_keys(client, admin_user, sample_product):
    response = await client.post(
        f"/api/v1/admin/products/{sample_product.id}/images",
        json={"image_url": "https://example.com/new.jpg", "storage_keys": ["client/key"]},
        headers=admin_user["headers"],
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_cleanup_reconciler_retries_exact_keys_and_resolves(
    db_session, monkeypatch
):
    from tests.conftest import TestSessionLocal
    from app.tasks.product_image_storage_cleanup import reconcile_product_image_storage_cleanups
    row = ProductImageStorageCleanup(
        id=uuid.uuid4(), storage_keys=["exact/a", "exact/b"], reason="test"
    )
    db_session.add(row)
    await db_session.commit()
    row_id = row.id
    delete = AsyncMock(return_value={"failed_keys": []})
    monkeypatch.setattr("app.tasks.product_image_storage_cleanup.image_service.delete_images", delete)

    result = await reconcile_product_image_storage_cleanups(session_factory=TestSessionLocal)
    db_session.expire_all()
    persisted = await db_session.get(ProductImageStorageCleanup, row_id)
    assert result == {"resolved": 1, "remaining": 0}
    delete.assert_awaited_once_with(["exact/a", "exact/b"])
    assert persisted is not None
    assert persisted.resolved_at is not None


@pytest.mark.asyncio
async def test_admin_upload_coordinates_storage_key_ownership_before_persisting(
    client, admin_user, sample_product, monkeypatch
):
    from io import BytesIO
    from app.api.v1 import admin as admin_api
    from unittest.mock import AsyncMock

    uploaded = {"original": "/uploads/original.jpg", "_storage_keys": ["products/original.jpg"]}
    monkeypatch.setattr(admin_api.image_service, "upload_image", AsyncMock(return_value=uploaded))
    cleanup = AsyncMock()
    monkeypatch.setattr(admin_api.image_service, "delete_images", cleanup)
    coordinate = AsyncMock(side_effect=ValueError("owned"))
    monkeypatch.setattr(admin_api, "lock_and_validate_storage_keys", coordinate)

    response = await client.post(
        f"/api/v1/admin/products/{sample_product.id}/images/upload",
        files={"file": ("tiny.png", BytesIO(b"x"), "image/png")},
        headers=admin_user["headers"],
    )
    assert response.status_code == 409
    coordinate.assert_awaited_once_with(ANY, uploaded["_storage_keys"])
    cleanup.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_record_failure_is_visible_to_compensation_caller(db_session, monkeypatch):
    from app.services.product_image_storage import record_storage_cleanup

    async def fail_commit():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="database unavailable"):
        await record_storage_cleanup(
            db_session, ["products/original.jpg"], reason="upload_compensation"
        )


@pytest.mark.asyncio
async def test_legacy_null_storage_keys_are_not_guessed_or_deleted(
    client, admin_user, sample_product, db_session, monkeypatch
):
    from app.api.v1 import admin as admin_api
    image = ProductImage(
        product_id=sample_product.id,
        image_url="https://cdn.example.com/products/legacy.jpg",
        storage_keys=None,
    )
    db_session.add(image)
    await db_session.commit()
    delete = AsyncMock()
    monkeypatch.setattr(admin_api.image_service, "delete_images", delete)

    response = await client.delete(
        f"/api/v1/admin/products/{sample_product.id}/images/{image.id}",
        headers=admin_user["headers"],
    )
    assert response.status_code == 204
    delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_vendor_legacy_null_storage_keys_are_not_guessed_or_deleted(
    client, vendor_user, sample_product, db_session, monkeypatch
):
    from app.api.v1 import products as products_api
    image = ProductImage(
        product_id=sample_product.id,
        image_url="https://cdn.example.com/products/vendor-legacy.jpg",
        storage_keys=None,
    )
    db_session.add(image)
    await db_session.commit()
    delete = AsyncMock()
    monkeypatch.setattr(products_api.image_service, "delete_images", delete)

    response = await client.delete(
        f"/api/v1/products/{sample_product.id}/images/{image.id}",
        headers=vendor_user["headers"],
    )
    assert response.status_code == 204
    delete.assert_not_awaited()
