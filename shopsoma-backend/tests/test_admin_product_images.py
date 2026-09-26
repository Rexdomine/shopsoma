import uuid
from io import BytesIO

import pytest
from sqlalchemy import select

from app.models.product import ProductImage


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.mark.asyncio
async def test_admin_multipart_upload_persists_product_image(
    client, admin_user, sample_product, db_session, monkeypatch
):
    from app.api.v1 import admin as admin_api

    uploaded = {
        "original": "/uploads/products/2026/09/original.jpg",
        "thumbnail": "/uploads/products/2026/09/thumb.jpg",
        "s3_key": "products/2026/09/original.jpg",
        "thumbnail_s3_key": "products/2026/09/thumb.jpg",
        "_storage_keys": [
            "products/2026/09/original.jpg",
            "products/2026/09/thumb.jpg",
            "products/2026/09/medium.jpg",
            "products/2026/09/large.jpg",
        ],
    }
    upload = pytest.importorskip("unittest.mock").AsyncMock(return_value=uploaded)
    monkeypatch.setattr(admin_api.image_service, "upload_image", upload)

    response = await client.post(
        f"/api/v1/admin/products/{sample_product.id}/images/upload",
        files={"file": ("tiny.png", BytesIO(TINY_PNG), "image/png")},
        headers=admin_user["headers"],
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["product_id"] == str(sample_product.id)
    assert payload["image_url"] == uploaded["original"]
    image = await db_session.get(ProductImage, uuid.UUID(payload["id"]))
    assert image is not None
    assert image.product_id == sample_product.id
    upload.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_upload_failure_cleans_every_generated_storage_key(
    client, admin_user, sample_product, db_session, monkeypatch
):
    from unittest.mock import AsyncMock
    from app.api.v1 import admin as admin_api
    from app.models.product import ProductImageStorageCleanup

    uploaded = {
        "original": "/uploads/products/original.jpg",
        "thumbnail": "/uploads/products/thumbnail.jpg",
        "medium": "/uploads/products/medium.jpg",
        "large": "/uploads/products/large.jpg",
        "s3_key": "products/original.jpg",
        "_storage_keys": [
            "products/original.jpg",
            "products/thumbnail.jpg",
            "products/medium.jpg",
            "products/large.jpg",
        ],
    }
    monkeypatch.setattr(admin_api.image_service, "upload_image", AsyncMock(return_value=uploaded))
    cleanup = AsyncMock()
    monkeypatch.setattr(admin_api.image_service, "delete_images", cleanup)
    original_commit = db_session.commit

    async def fail_commit():
        await original_commit()
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(db_session, "commit", fail_commit)

    response = await client.post(
        f"/api/v1/admin/products/{sample_product.id}/images/upload",
        files={"file": ("tiny.png", BytesIO(TINY_PNG), "image/png")},
        headers=admin_user["headers"],
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to persist uploaded product image"
    cleanup.assert_not_awaited()
    image = await db_session.scalar(
        select(ProductImage).where(ProductImage.product_id == sample_product.id)
    )
    assert image is not None
    assert image.image_url == uploaded["original"]
    assert await db_session.scalar(select(ProductImageStorageCleanup)) is None


@pytest.mark.asyncio
async def test_admin_upload_definitive_commit_failure_enqueues_ownership_reconciliation(
    client, admin_user, sample_product, db_session, monkeypatch
):
    from unittest.mock import AsyncMock
    from app.api.v1 import admin as admin_api
    from app.models.product import ProductImageStorageCleanup

    uploaded = {
        "original": "/uploads/products/aborted.jpg",
        "_storage_keys": ["products/aborted.jpg", "products/aborted-thumb.jpg"],
    }
    monkeypatch.setattr(admin_api.image_service, "upload_image", AsyncMock(return_value=uploaded))
    original_commit = db_session.commit
    commits = 0

    async def fail_only_the_image_commit():
        nonlocal commits
        commits += 1
        if commits == 1:
            raise RuntimeError("commit aborted before database write")
        await original_commit()

    monkeypatch.setattr(db_session, "commit", fail_only_the_image_commit)
    response = await client.post(
        f"/api/v1/admin/products/{sample_product.id}/images/upload",
        files={"file": ("tiny.png", BytesIO(TINY_PNG), "image/png")},
        headers=admin_user["headers"],
    )

    assert response.status_code == 500
    pending = await db_session.scalar(select(ProductImageStorageCleanup))
    assert pending is not None
    assert pending.storage_keys == uploaded["_storage_keys"]
    assert pending.reason == "upload_commit_reconciliation"


@pytest.mark.asyncio
async def test_admin_upload_precommit_refresh_failure_cleans_storage_and_rolls_back(
    client, admin_user, sample_product, db_session, monkeypatch
):
    from unittest.mock import AsyncMock
    from app.api.v1 import admin as admin_api

    uploaded = {
        "original": "/uploads/products/original.jpg",
        "thumbnail": "/uploads/products/thumbnail.jpg",
        "s3_key": "products/original.jpg",
        "_storage_keys": ["products/original.jpg", "products/thumbnail.jpg"],
    }
    monkeypatch.setattr(admin_api.image_service, "upload_image", AsyncMock(return_value=uploaded))
    cleanup = AsyncMock()
    monkeypatch.setattr(admin_api.image_service, "delete_images", cleanup)

    async def fail_refresh(_instance):
        raise RuntimeError("refresh unavailable")

    monkeypatch.setattr(db_session, "refresh", fail_refresh)
    product_id = sample_product.id

    response = await client.post(
        f"/api/v1/admin/products/{product_id}/images/upload",
        files={"file": ("tiny.png", BytesIO(TINY_PNG), "image/png")},
        headers=admin_user["headers"],
    )

    assert response.status_code == 500
    cleanup.assert_awaited_once_with(uploaded["_storage_keys"])
    image = await db_session.scalar(
        select(ProductImage).where(ProductImage.product_id == product_id)
    )
    assert image is None


@pytest.mark.asyncio
async def test_admin_upload_cleanup_failure_persists_retry_keys(
    client, admin_user, sample_product, db_session, monkeypatch
):
    from unittest.mock import AsyncMock
    from app.api.v1 import admin as admin_api
    from app.models.product import ProductImageStorageCleanup

    uploaded = {
        "original": "/uploads/products/original.jpg",
        "s3_key": "products/original.jpg",
        "_storage_keys": ["products/original.jpg", "products/thumb.jpg"],
    }
    monkeypatch.setattr(admin_api.image_service, "upload_image", AsyncMock(return_value=uploaded))
    monkeypatch.setattr(
        admin_api.image_service,
        "delete_images",
        AsyncMock(side_effect=RuntimeError("storage unavailable")),
    )

    async def fail_refresh(_instance):
        raise RuntimeError("refresh unavailable")

    monkeypatch.setattr(db_session, "refresh", fail_refresh)
    response = await client.post(
        f"/api/v1/admin/products/{sample_product.id}/images/upload",
        files={"file": ("tiny.png", BytesIO(TINY_PNG), "image/png")},
        headers=admin_user["headers"],
    )

    assert response.status_code == 500
    pending = await db_session.scalar(select(ProductImageStorageCleanup))
    assert pending.storage_keys == uploaded["_storage_keys"]
    assert pending.reason == "upload_compensation"


@pytest.mark.asyncio
async def test_admin_multipart_upload_cap_rejects_before_storage(
    client, admin_user, sample_product, db_session, monkeypatch
):
    from app.api.v1 import admin as admin_api

    for index in range(10):
        await _add_image(db_session, sample_product.id, index, index == 0, str(index))
    await db_session.commit()
    upload = pytest.importorskip("unittest.mock").AsyncMock()
    monkeypatch.setattr(admin_api.image_service, "upload_image", upload)

    response = await client.post(
        f"/api/v1/admin/products/{sample_product.id}/images/upload",
        files={"file": ("tiny.png", BytesIO(TINY_PNG), "image/png")},
        headers=admin_user["headers"],
    )

    assert response.status_code == 409
    upload.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_can_set_primary_and_reorder_product_scoped_images(
    client, admin_user, sample_product, db_session
):
    first = ProductImage(
        id=uuid.uuid4(), product_id=sample_product.id,
        image_url="https://example.com/first.jpg", display_order=0, is_primary=True,
    )
    second = ProductImage(
        id=uuid.uuid4(), product_id=sample_product.id,
        image_url="https://example.com/second.jpg", display_order=1,
    )
    db_session.add_all([first, second])
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/admin/products/{sample_product.id}/images/{second.id}",
        json={"display_order": 0, "is_primary": True},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == str(second.id)
    assert payload["display_order"] == 0
    assert payload["is_primary"] is True

    await db_session.refresh(first)
    await db_session.refresh(second)
    assert first.is_primary is False
    assert second.is_primary is True
    assert first.display_order == 1
    assert second.display_order == 0


async def _add_image(db_session, product_id, order=0, primary=False, suffix="x"):
    image = ProductImage(
        id=uuid.uuid4(), product_id=product_id,
        image_url=f"https://example.com/{suffix}.jpg", display_order=order, is_primary=primary,
    )
    db_session.add(image)
    await db_session.flush()
    return image


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path,payload", [
    ("post", "/images", {"image_url": "https://example.com/new.jpg"}),
    ("patch", "/images/{image_id}", {"is_primary": True}),
    ("delete", "/images/{image_id}", None),
])
async def test_product_image_mutations_require_admin(method, path, payload, client, sample_product, db_session, customer_user):
    image = await _add_image(db_session, sample_product.id, primary=True)
    await db_session.commit()
    path = f"/api/v1/admin/products/{sample_product.id}" + path.format(image_id=image.id)
    if payload is None:
        response = await getattr(client, method)(path, headers=customer_user["headers"])
    else:
        response = await getattr(client, method)(path, json=payload, headers=customer_user["headers"])
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_image_scope_mismatch_returns_404(client, admin_user, sample_product, vendor_user, db_session):
    from app.models.product import Product, ProductStatus, ModerationStatus
    other = Product(id=uuid.uuid4(), vendor_id=vendor_user["vendor"].id, title="Other", base_price=10, total_stock=1, status=ProductStatus.ACTIVE, moderation_status=ModerationStatus.APPROVED)
    db_session.add(other)
    await db_session.flush()
    image = await _add_image(db_session, other.id, primary=True)
    await db_session.commit()
    response = await client.patch(f"/api/v1/admin/products/{sample_product.id}/images/{image.id}", json={"is_primary": True}, headers=admin_user["headers"])
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_first_upload_forces_primary_and_zero_order_and_marks_pending(client, admin_user, sample_product, db_session):
    response = await client.post(f"/api/v1/admin/products/{sample_product.id}/images", json={"image_url": "https://example.com/first.jpg", "display_order": 8, "is_primary": False}, headers=admin_user["headers"])
    assert response.status_code == 201
    assert response.json()["display_order"] == 0
    assert response.json()["is_primary"] is True
    await db_session.refresh(sample_product)
    assert sample_product.moderation_status.value == "pending"


@pytest.mark.asyncio
async def test_new_primary_clears_old_primary_and_reorders(client, admin_user, sample_product, db_session):
    first = await _add_image(db_session, sample_product.id, 0, True, "first")
    second = await _add_image(db_session, sample_product.id, 1, False, "second")
    await db_session.commit()
    response = await client.patch(f"/api/v1/admin/products/{sample_product.id}/images/{second.id}", json={"is_primary": True, "display_order": 0}, headers=admin_user["headers"])
    assert response.status_code == 200
    await db_session.refresh(first); await db_session.refresh(second)
    assert (first.is_primary, first.display_order) == (False, 1)
    assert (second.is_primary, second.display_order) == (True, 0)


@pytest.mark.asyncio
async def test_setting_primary_without_order_moves_image_to_first(client, admin_user, sample_product, db_session):
    first = await _add_image(db_session, sample_product.id, 0, True, "first-only")
    second = await _add_image(db_session, sample_product.id, 1, False, "second-only")
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/admin/products/{sample_product.id}/images/{second.id}",
        json={"is_primary": True},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    await db_session.refresh(first)
    await db_session.refresh(second)
    assert (first.is_primary, first.display_order) == (False, 1)
    assert (second.is_primary, second.display_order) == (True, 0)

@pytest.mark.asyncio
async def test_clearing_primary_moves_replacement_to_first(client, admin_user, sample_product, db_session):
    first = await _add_image(db_session, sample_product.id, 0, True, "demoted")
    second = await _add_image(db_session, sample_product.id, 1, False, "replacement")
    third = await _add_image(db_session, sample_product.id, 2, False, "remaining")
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/admin/products/{sample_product.id}/images/{first.id}",
        json={"is_primary": False},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    await db_session.refresh(first)
    await db_session.refresh(second)
    await db_session.refresh(third)
    assert (first.is_primary, first.display_order) == (False, 1)
    assert (second.is_primary, second.display_order) == (True, 0)
    assert third.display_order == 2


@pytest.mark.asyncio
async def test_reordering_cannot_place_non_primary_before_primary(client, admin_user, sample_product, db_session):
    first = await _add_image(db_session, sample_product.id, 0, True, "primary")
    second = await _add_image(db_session, sample_product.id, 1, False, "second")
    third = await _add_image(db_session, sample_product.id, 2, False, "third")
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/admin/products/{sample_product.id}/images/{third.id}",
        json={"display_order": 0},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    await db_session.refresh(first)
    await db_session.refresh(second)
    await db_session.refresh(third)
    assert (first.is_primary, first.display_order) == (True, 0)
    assert third.display_order == 1
    assert second.display_order == 2


@pytest.mark.asyncio
async def test_reordering_primaryless_gallery_promotes_reordered_first_image(
    client, admin_user, sample_product, db_session
):
    first = await _add_image(db_session, sample_product.id, 0, False, "first")
    second = await _add_image(db_session, sample_product.id, 1, False, "second")
    third = await _add_image(db_session, sample_product.id, 2, False, "third")
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/admin/products/{sample_product.id}/images/{third.id}",
        json={"display_order": 0},
        headers=admin_user["headers"],
    )

    assert response.status_code == 200
    await db_session.refresh(first)
    await db_session.refresh(second)
    await db_session.refresh(third)
    assert (third.is_primary, third.display_order) == (True, 0)
    assert first.display_order == 1
    assert second.display_order == 2


@pytest.mark.asyncio
async def test_delete_primary_falls_back_and_reorders_remaining(client, admin_user, sample_product, db_session):
    first = await _add_image(db_session, sample_product.id, 0, True, "first")
    second = await _add_image(db_session, sample_product.id, 1, False, "second")
    third = await _add_image(db_session, sample_product.id, 2, False, "third")
    await db_session.commit()
    response = await client.delete(f"/api/v1/admin/products/{sample_product.id}/images/{first.id}", headers=admin_user["headers"])
    assert response.status_code == 204
    await db_session.refresh(second); await db_session.refresh(third)
    assert (second.is_primary, second.display_order) == (True, 0)
    assert third.display_order == 1


@pytest.mark.asyncio
async def test_admin_delete_removes_exact_persisted_storage_keys_after_commit(
    client, admin_user, sample_product, db_session, monkeypatch
):
    from unittest.mock import AsyncMock
    from app.api.v1 import admin as admin_api

    image = await _add_image(db_session, sample_product.id, 0, True, "uploaded")
    expected_keys = ["products/original.jpg", "products/thumb.jpg", "products/medium.jpg"]
    image.storage_keys = expected_keys
    await db_session.commit()
    cleanup = AsyncMock()
    monkeypatch.setattr(admin_api.image_service, "delete_images", cleanup)

    response = await client.delete(
        f"/api/v1/admin/products/{sample_product.id}/images/{image.id}",
        headers=admin_user["headers"],
    )

    assert response.status_code == 204
    cleanup.assert_awaited_once_with(expected_keys)
    assert await db_session.get(ProductImage, image.id) is None


@pytest.mark.asyncio
async def test_admin_delete_storage_failure_does_not_restore_deleted_row(
    client, admin_user, sample_product, db_session, monkeypatch, caplog
):
    from unittest.mock import AsyncMock
    from app.api.v1 import admin as admin_api

    image = await _add_image(db_session, sample_product.id, 0, True, "uploaded-failure")
    image.storage_keys = ["products/original-failure.jpg"]
    await db_session.commit()
    cleanup = AsyncMock(side_effect=RuntimeError("storage unavailable"))
    monkeypatch.setattr(admin_api.image_service, "delete_images", cleanup)

    response = await client.delete(
        f"/api/v1/admin/products/{sample_product.id}/images/{image.id}",
        headers=admin_user["headers"],
    )

    assert response.status_code == 204
    cleanup.assert_awaited_once_with(["products/original-failure.jpg"])
    assert await db_session.get(ProductImage, image.id) is None
    assert "storage cleanup failed after durable row deletion" in caplog.text
    from app.models.product import ProductImageStorageCleanup
    pending = await db_session.scalar(select(ProductImageStorageCleanup))
    assert pending.storage_keys == ["products/original-failure.jpg"]


@pytest.mark.asyncio
async def test_image_cap_rejects_eleventh_upload(client, admin_user, sample_product, db_session):
    for index in range(10):
        await _add_image(db_session, sample_product.id, index, index == 0, str(index))
    await db_session.commit()
    response = await client.post(f"/api/v1/admin/products/{sample_product.id}/images", json={"image_url": "https://example.com/eleven.jpg"}, headers=admin_user["headers"])
    assert response.status_code == 409
    assert "at most 10" in response.json()["detail"]
