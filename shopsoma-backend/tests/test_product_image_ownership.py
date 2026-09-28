"""End-to-end regressions for PR #204 upload and variation ownership."""

import io
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.product import Product, ProductImage, ProductImageUpload, ProductImageStorageCleanup, Variation
from app.services.image_service import image_service


@pytest.fixture
async def uploads(client, vendor_user, tmp_path, monkeypatch):
    monkeypatch.setattr(image_service, "use_local_storage", True)
    monkeypatch.setattr(image_service, "upload_dir", tmp_path)
    data = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(data, format="PNG")
    result = []
    for name in ("a.png", "b.png"):
        response = await client.post(
            "/api/v1/images/upload",
            files={"file": (name, data.getvalue(), "image/png")},
            headers=vendor_user["headers"],
        )
        assert response.status_code == 201, response.text
        result.append(response.json())
    return result


def image_payload(upload):
    return {
        "image_url": upload["original"],
        "thumbnail_url": upload["thumbnail"],
        "storage_keys": upload["storage_keys"],
    }


async def associate(client, headers, product_id, image, mode):
    if mode == "create":
        return await client.post(
            "/api/v1/products",
            headers=headers,
            json={
                "title": "Image ownership",
                "base_price": 10,
                "images": [image],
                "variations": [{"title": "Red", "images": [image["image_url"]]}],
            },
        )
    return await client.post(
        f"/api/v1/products/{product_id}/images", headers=headers, json=image
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["create", "associate"])
@pytest.mark.parametrize(
    "mismatch", ["original", "thumbnail", "mixed_keys", "missing_key", "no_keys"]
)
async def test_association_rejects_mixed_or_incomplete_upload(
    client, vendor_user, sample_product, uploads, db_session, mode, mismatch
):
    first, second = uploads
    payload = image_payload(first)
    if mismatch == "original":
        payload["image_url"] = second["original"]
    elif mismatch == "thumbnail":
        payload["thumbnail_url"] = second["thumbnail"]
    elif mismatch == "mixed_keys":
        payload["storage_keys"] = [
            first["storage_keys"][0],
            *second["storage_keys"][1:],
        ]
    elif mismatch == "missing_key":
        payload["storage_keys"] = first["storage_keys"][:1]
    else:
        payload.pop("storage_keys")
    response = await associate(
        client, vendor_user["headers"], sample_product.id, payload, mode
    )
    assert response.status_code == 409, response.text
    assert await db_session.scalar(select(ProductImage.id)) is None
    assert (image_service.upload_dir / first["storage_keys"][0]).exists()
    assert (image_service.upload_dir / second["storage_keys"][0]).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["create", "associate"])
@pytest.mark.parametrize("legacy", [False, True])
async def test_same_product_owned_and_legacy_images_remain_valid(
    client, vendor_user, sample_product, uploads, mode, legacy
):
    payload = (
        {"image_url": "https://legacy.example.test/dress.jpg"}
        if legacy
        else image_payload(uploads[0])
    )
    response = await associate(
        client, vendor_user["headers"], sample_product.id, payload, mode
    )
    assert response.status_code == 201, response.text
    product_id = response.json()["id"] if mode == "create" else str(sample_product.id)
    response = await client.put(
        f"/api/v1/products/{product_id}",
        headers=vendor_user["headers"],
        json={
            "variations": [{"title": "Red", "images": [payload["image_url"]]}],
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["variations"][0]["images"] == [payload["image_url"]]
    assert "storage_keys" not in response.json()["images"][0]
    public = await client.get(f"/api/v1/products/{product_id}")
    assert public.status_code == 404  # Editing still requires moderation.


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["create", "edit"])
@pytest.mark.parametrize("associated", [False, True])
async def test_variations_reject_live_unassociated_and_other_product_uploads(
    client, vendor_user, sample_product, uploads, db_session, mode, associated
):
    upload = uploads[0]
    if associated:
        response = await associate(
            client,
            vendor_user["headers"],
            sample_product.id,
            image_payload(upload),
            "associate",
        )
        assert response.status_code == 201, response.text
    # B must never reference A, even when the same vendor owns both products.
    other = Product(
        vendor_id=sample_product.vendor_id, title="B", base_price=10, total_stock=1
    )
    db_session.add(other)
    await db_session.commit()
    payload = {"variations": [{"title": "Red", "images": [upload["original"]]}]}
    if mode == "create":
        response = await client.post(
            "/api/v1/products",
            headers=vendor_user["headers"],
            json={"title": "Product C", "base_price": 10, **payload},
        )
    else:
        response = await client.put(
            f"/api/v1/products/{other.id}", headers=vendor_user["headers"], json=payload
        )
    assert response.status_code == 409, response.text
    assert "belong to this product" in response.json()["detail"]
    assert (
        await db_session.scalar(
            select(Variation.id).where(Variation.product_id == other.id)
        )
        is None
    )


@pytest.mark.asyncio
async def test_admin_cannot_alias_upload_or_change_owned_urls(
    client, admin_user, vendor_user, sample_product, uploads, db_session
):
    first, second = uploads
    response = await client.post(
        f"/api/v1/admin/products/{sample_product.id}/images",
        headers=admin_user["headers"],
        json={"image_url": first["original"]},
    )
    assert response.status_code == 409
    response = await associate(
        client,
        vendor_user["headers"],
        sample_product.id,
        image_payload(first),
        "associate",
    )
    assert response.status_code == 201, response.text
    image_id = response.json()["id"]
    response = await client.patch(
        f"/api/v1/admin/products/{sample_product.id}/images/{image_id}",
        headers=admin_user["headers"],
        json={"image_url": second["original"]},
    )
    assert response.status_code == 422
    persisted = await db_session.scalar(
        select(ProductImage).where(ProductImage.product_id == sample_product.id)
    )
    assert persisted.image_url == first["original"]
    assert persisted.storage_keys == first["storage_keys"]
    response = await client.patch(
        f"/api/v1/admin/products/{sample_product.id}/images/{image_id}",
        headers=admin_user["headers"],
        json={"alt_text": "Red dress", "is_primary": True},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["customer", "anonymous", "foreign_namespace"])
async def test_image_association_preserves_role_and_vendor_boundaries(
    client, vendor_user, customer_user, sample_product, uploads, role
):
    if role == "foreign_namespace":
        # The request is authenticated as the owner but claims another vendor's key.
        payload = image_payload(uploads[0])
        payload["storage_keys"] = ["vendors/other-vendor/products/image.jpg"]
        headers = vendor_user["headers"]
    else:
        payload = image_payload(uploads[0])
        headers = customer_user["headers"] if role == "customer" else {}
    response = await associate(client, headers, sample_product.id, payload, "associate")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_batch_upload_records_each_identity(
    client, vendor_user, db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(image_service, "use_local_storage", True)
    monkeypatch.setattr(image_service, "upload_dir", tmp_path)
    data = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(data, format="PNG")
    response = await client.post(
        "/api/v1/images/upload/batch",
        headers=vendor_user["headers"],
        files=[
            ("files", (name, data.getvalue(), "image/png"))
            for name in ("a.png", "b.png")
        ],
    )
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 2
    for upload in response.json()["images"]:
        record = await db_session.get(ProductImageUpload, upload["original"])
        assert record.storage_keys == upload["storage_keys"]
        assert record.thumbnail_url == upload["thumbnail"]


@pytest.mark.asyncio
async def test_reset_preflight_failure_preserves_images(
    client, admin_user, sample_product, db_session, monkeypatch
):
    from app.api.v1 import admin as admin_api

    image = ProductImage(
        product_id=sample_product.id,
        image_url="https://legacy.example.test/preserve.jpg",
    )
    db_session.add(image)
    await db_session.commit()
    monkeypatch.setattr(
        admin_api,
        "coordinate_catalog_write",
        AsyncMock(side_effect=ValueError("preflight refused")),
    )
    delete = AsyncMock()
    monkeypatch.setattr(admin_api.image_service, "delete_images", delete)
    response = await client.delete(
        "/api/v1/admin/reset-products", headers=admin_user["headers"]
    )
    assert response.status_code == 500
    assert await db_session.scalar(select(ProductImage.id)) is not None
    delete.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["vendor", "admin"])
async def test_deleting_owned_image_clears_same_product_variation(
    client, vendor_user, admin_user, sample_product, uploads, db_session, role
):
    response = await associate(
        client,
        vendor_user["headers"],
        sample_product.id,
        image_payload(uploads[0]),
        "associate",
    )
    assert response.status_code == 201, response.text
    image_id = response.json()["id"]
    response = await client.put(
        f"/api/v1/products/{sample_product.id}",
        headers=vendor_user["headers"],
        json={"variations": [{"title": "Red", "images": [uploads[0]["original"]]}]},
    )
    assert response.status_code == 200, response.text
    prefix = "/api/v1/admin/products" if role == "admin" else "/api/v1/products"
    headers = admin_user["headers"] if role == "admin" else vendor_user["headers"]
    response = await client.delete(
        f"{prefix}/{sample_product.id}/images/{image_id}", headers=headers
    )
    assert response.status_code == 204, response.text
    db_session.expire_all()
    variation = await db_session.scalar(select(Variation))
    assert variation.images == []
    assert not (image_service.upload_dir / uploads[0]["storage_keys"][0]).exists()
    assert (image_service.upload_dir / uploads[1]["storage_keys"][0]).exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("batch", [False, True])
@pytest.mark.parametrize("durable", [False, True])
async def test_upload_identity_commit_failure_reconciles_only_missing_identity(
    client, vendor_user, db_session, tmp_path, monkeypatch, batch, durable
):
    monkeypatch.setattr(image_service, "use_local_storage", True)
    monkeypatch.setattr(image_service, "upload_dir", tmp_path)
    data = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(data, format="PNG")
    real_commit = db_session.commit
    calls = 0

    async def fail_first_commit():
        nonlocal calls
        calls += 1
        if calls == 1:
            if durable:
                await real_commit()
            raise RuntimeError("lost commit acknowledgement")
        await real_commit()

    monkeypatch.setattr(db_session, "commit", fail_first_commit)
    response = await client.post(
        "/api/v1/images/upload/batch" if batch else "/api/v1/images/upload",
        headers=vendor_user["headers"],
        files={"files" if batch else "file": ("a.png", data.getvalue(), "image/png")},
    )
    if batch:
        assert response.status_code == 200
        assert response.json()["failed"] == 1
        assert response.json()["images"] == []
    else:
        assert response.status_code == 500
    upload = await db_session.scalar(select(ProductImageUpload))
    cleanup = await db_session.scalar(select(ProductImageStorageCleanup))
    stored_keys = {str(path.relative_to(tmp_path)) for path in tmp_path.rglob("*") if path.is_file()}
    assert stored_keys
    if durable:
        assert upload is not None
        assert set(upload.storage_keys) == stored_keys
        assert cleanup is None
    else:
        assert upload is None
        assert cleanup is not None
        assert set(cleanup.storage_keys) == stored_keys
        assert cleanup.reason == "upload_identity_commit_reconciliation"
        assert cleanup.resolved_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize("alias", ["encoded", "query", "dot_segments"])
async def test_keyless_managed_url_aliases_are_rejected(
    client, vendor_user, sample_product, uploads, alias
):
    url = uploads[0]["original"]
    if alias == "encoded":
        url = url.replace("vendors", "%76endors")
    elif alias == "query":
        url += "?width=200"
    else:
        url = url.replace("/vendors/", "/unused/../vendors/")
    response = await associate(
        client,
        vendor_user["headers"],
        sample_product.id,
        {"image_url": url},
        "associate",
    )
    assert response.status_code == 409, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["image_url", "thumbnail_url"])
async def test_legacy_image_url_patch_preserves_editable_variation_gallery(
    client, admin_user, vendor_user, sample_product, db_session, field
):
    original = "https://legacy.example.test/original.jpg"
    thumbnail = "https://legacy.example.test/thumb.jpg"
    image = ProductImage(
        product_id=sample_product.id, image_url=original,
        thumbnail_url=thumbnail, is_primary=True,
    )
    variation = Variation(product_id=sample_product.id, title="Red", images=[original])
    db_session.add_all([image, variation])
    await db_session.commit()

    response = await client.patch(
        f"/api/v1/admin/products/{sample_product.id}/images/{image.id}",
        headers=admin_user["headers"],
        json={field: "https://legacy.example.test/replacement.jpg"},
    )
    assert response.status_code == 422, response.text
    await db_session.refresh(image)
    await db_session.refresh(variation)
    assert image.image_url == original
    assert image.thumbnail_url == thumbnail
    assert variation.images == [original]
    assert image.storage_keys is None

    # Sending unchanged URLs with metadata remains compatible.
    response = await client.patch(
        f"/api/v1/admin/products/{sample_product.id}/images/{image.id}",
        headers=admin_user["headers"],
        json={"image_url": original, "thumbnail_url": thumbnail, "alt_text": "Red"},
    )
    assert response.status_code == 200, response.text
    response = await client.put(
        f"/api/v1/products/{sample_product.id}",
        headers=vendor_user["headers"],
        json={"variations": [{"id": str(variation.id), "title": "Red", "images": [original]}]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["variations"][0]["images"] == [original]


@pytest.mark.asyncio
@pytest.mark.parametrize("initially_empty", [False, True])
async def test_reset_preserves_product_created_after_catalog_snapshot(
    client, admin_user, vendor_user, db_session, monkeypatch, tmp_path, initially_empty
):
    from app.api.v1 import admin as admin_api
    from app.models.product import (
        ProductImageStorageCleanup, ProductVariant, SizeEnum, SizeStock,
    )
    from app.models.vendor import Vendor
    from tests.conftest import TestSessionLocal

    monkeypatch.setattr(image_service, "use_local_storage", True)
    monkeypatch.setattr(image_service, "upload_dir", tmp_path)
    vendor_id = vendor_user["vendor"].id
    old_key = "vendors/reset/products/old.jpg"
    late_key = "vendors/reset/products/late.jpg"
    for key in (old_key, late_key):
        path = tmp_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic image")
    old_id = None
    if not initially_empty:
        old = Product(vendor_id=vendor_id, title="Snapshot product", base_price=10)
        db_session.add(old)
        await db_session.flush()
        old_id = old.id
        db_session.add(ProductImage(
            product_id=old_id, image_url="/uploads/" + old_key, storage_keys=[old_key],
        ))
        await db_session.commit()

    coordinate = admin_api.coordinate_catalog_write
    late_ids = {}

    async def create_after_snapshot(db, **kwargs):
        assert kwargs["product_ids"] == ([] if initially_empty else [old_id])
        # A separate committed transaction deterministically reproduces the
        # concurrent-create window after reset has chosen its coordinated IDs.
        async with TestSessionLocal() as other:
            product = Product(vendor_id=vendor_id, title="Concurrent product", base_price=20)
            other.add(product)
            await other.flush()
            image = ProductImage(
                product_id=product.id, image_url="/uploads/" + late_key,
                storage_keys=[late_key],
            )
            variant = ProductVariant(product_id=product.id, price=20, stock=3)
            variation = Variation(
                product_id=product.id, title="Blue", images=[image.image_url],
            )
            other.add_all([image, variant, variation])
            await other.flush()
            size = SizeStock(variation_id=variation.id, size=SizeEnum.M, stock=3)
            other.add(size)
            vendor = await other.get(Vendor, vendor_id)
            vendor.featured_storefront_image_url = image.image_url
            await other.commit()
            late_ids.update({
                Product: product.id, ProductImage: image.id, ProductVariant: variant.id,
                Variation: variation.id, SizeStock: size.id,
            })
        await coordinate(db, **kwargs)

    monkeypatch.setattr(admin_api, "coordinate_catalog_write", create_after_snapshot)
    response = await client.delete(
        "/api/v1/admin/reset-products", headers=admin_user["headers"],
    )
    # Preserve the existing empty-key coordinator fail-closed behavior.
    assert response.status_code == (500 if initially_empty else 200), response.text
    for model, row_id in late_ids.items():
        assert await db_session.scalar(select(model.id).where(model.id == row_id)) == row_id
    assert (tmp_path / late_key).exists()
    featured = await db_session.scalar(
        select(Vendor.featured_storefront_image_url).where(Vendor.id == vendor_id)
    )
    assert featured == "/uploads/" + late_key
    cleanup_keys = list((await db_session.scalars(
        select(ProductImageStorageCleanup.storage_keys)
    )).all())
    assert all(late_key not in keys for keys in cleanup_keys)
    if old_id:
        assert await db_session.scalar(select(Product.id).where(Product.id == old_id)) is None
        assert not (tmp_path / old_key).exists()
        assert any(old_key in keys for keys in cleanup_keys)
    else:
        assert cleanup_keys == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["vendor", "admin"])
@pytest.mark.parametrize("other_url", [
    "https://legacy-b.example/catalog/dress.jpg",
    "https://legacy-a.example/catalog/dress.jpg?version=2",
    "https://legacy-a.example/catalog/shirt.jpg",
])
async def test_legacy_delete_preserves_distinct_image_after_reload(
    client, vendor_user, admin_user, sample_product, db_session, monkeypatch,
    role, other_url,
):
    original = "https://legacy-a.example/catalog/dress.jpg"
    deleted = ProductImage(product_id=sample_product.id, image_url=original)
    retained = ProductImage(product_id=sample_product.id, image_url=other_url)
    variation = Variation(
        product_id=sample_product.id, title="Red", images=[original, other_url]
    )
    other_product = Product(
        vendor_id=sample_product.vendor_id, title="Other", base_price=10,
    )
    db_session.add(other_product)
    await db_session.flush()
    other_variation = Variation(
        product_id=other_product.id, title="Blue", images=[original, other_url]
    )
    db_session.add_all([deleted, retained, variation, other_variation])
    await db_session.commit()
    product_id, deleted_id, retained_id = sample_product.id, deleted.id, retained.id
    variation_id, other_variation_id = variation.id, other_variation.id
    delete_storage = AsyncMock()
    monkeypatch.setattr(image_service, "delete_images", delete_storage)
    prefix = "/api/v1/admin/products" if role == "admin" else "/api/v1/products"
    headers = admin_user["headers"] if role == "admin" else vendor_user["headers"]
    url = f"{prefix}/{product_id}/images/{deleted_id}"

    response = await client.delete(url, headers=headers)
    assert response.status_code == 204, response.text
    # A fresh session proves the endpoint committed both gallery changes.
    from tests.conftest import TestSessionLocal
    async with TestSessionLocal() as reloaded:
        assert await reloaded.get(ProductImage, deleted_id) is None
        assert (await reloaded.get(ProductImage, retained_id)).image_url == other_url
        assert (await reloaded.get(Variation, variation_id)).images == [other_url]
        assert (await reloaded.get(Variation, other_variation_id)).images == [original, other_url]
    response = await client.delete(url, headers=headers)
    assert response.status_code == 404
    async with TestSessionLocal() as reloaded:
        assert (await reloaded.get(ProductImage, retained_id)).image_url == other_url
        assert (await reloaded.get(Variation, variation_id)).images == [other_url]
    delete_storage.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["vendor", "admin"])
@pytest.mark.parametrize("public_prefix", ["/uploads/", "https://cdn.example.test/media/"])
async def test_managed_delete_clears_aliases_but_preserves_external_identity(
    client, vendor_user, admin_user, sample_product, db_session, monkeypatch,
    role, public_prefix,
):
    monkeypatch.setattr(image_service, "_get_public_url", lambda key: "https://cdn.example.test/media/" + key)
    keys = ["products/dress.jpg", "products/dress-thumb.jpg"]
    original = public_prefix + keys[0]
    external = "https://legacy.example/uploads/products/dress.jpg"
    deleted = ProductImage(product_id=sample_product.id, image_url=original, storage_keys=keys)
    retained = ProductImage(product_id=sample_product.id, image_url=external)
    variation = Variation(product_id=sample_product.id, title="Red", images=[
        original, "/uploads/" + keys[1],
        "https://cdn.example.test/media/" + keys[0] + "?cache=1", external,
    ])
    db_session.add_all([deleted, retained, variation])
    await db_session.commit()
    product_id, deleted_id, retained_id, variation_id = sample_product.id, deleted.id, retained.id, variation.id
    # Failed object deletion must leave retry bookkeeping without losing unrelated references.
    delete_storage = AsyncMock(side_effect=RuntimeError("synthetic storage failure"))
    monkeypatch.setattr(image_service, "delete_images", delete_storage)
    prefix = "/api/v1/admin/products" if role == "admin" else "/api/v1/products"
    headers = admin_user["headers"] if role == "admin" else vendor_user["headers"]
    response = await client.delete(f"{prefix}/{product_id}/images/{deleted_id}", headers=headers)
    assert response.status_code == 204, response.text
    from tests.conftest import TestSessionLocal
    async with TestSessionLocal() as reloaded:
        assert await reloaded.get(ProductImage, deleted_id) is None
        assert (await reloaded.get(ProductImage, retained_id)).image_url == external
        assert (await reloaded.get(Variation, variation_id)).images == [external]
        pending = await reloaded.scalar(select(ProductImageStorageCleanup))
        assert pending.storage_keys == keys
        assert pending.resolved_at is None
    delete_storage.assert_awaited_once_with(keys)
