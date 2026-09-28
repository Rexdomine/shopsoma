"""End-to-end regressions for PR #204 upload and variation ownership."""

import io
from unittest.mock import AsyncMock

import pytest
from PIL import Image
from sqlalchemy import select

from app.models.product import Product, ProductImage, ProductImageUpload, Variation
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
async def test_upload_record_failure_does_not_return_upload_success(
    client, vendor_user, db_session, tmp_path, monkeypatch
):
    monkeypatch.setattr(image_service, "use_local_storage", True)
    monkeypatch.setattr(image_service, "upload_dir", tmp_path)
    data = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(data, format="PNG")
    monkeypatch.setattr(
        db_session, "commit", AsyncMock(side_effect=RuntimeError("record unavailable"))
    )
    response = await client.post(
        "/api/v1/images/upload",
        headers=vendor_user["headers"],
        files={"file": ("a.png", data.getvalue(), "image/png")},
    )
    assert response.status_code == 500
    assert await db_session.scalar(select(ProductImageUpload.image_url)) is None


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
