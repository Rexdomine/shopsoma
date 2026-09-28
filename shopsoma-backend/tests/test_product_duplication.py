"""PostgreSQL/real-local-storage regressions for ownership-safe Duplicate."""

import asyncio
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, func

from app.models.product import Product, ProductImage, ProductImageStorageCleanup, Variation
from app.services import product_duplication
from app.services.image_service import image_service
from tests.test_product_image_ownership import uploads as _uploads, image_payload


@pytest.fixture
async def uploads(client, vendor_user, tmp_path, monkeypatch):
    return await _uploads.__wrapped__(client, vendor_user, tmp_path, monkeypatch)


@pytest.fixture
async def source(client, vendor_user, uploads):
    response = await client.post("/api/v1/products", headers=vendor_user["headers"], json={
        "title": "Silk dress", "base_price": 15, "currency": "USD",
        "product_type": "variable", "total_stock": 6,
        "images": [{**image_payload(uploads[0]), "is_primary": True, "alt_text": "front"}],
        "variations": [{
            "title": "Red", "images": [uploads[0]["original"]],
            "sizes": [{"size": "M", "stock": 6}],
        }],
    })
    assert response.status_code == 201, response.text
    return response.json()


async def duplicate(client, vendor_user, source):
    return await client.post(
        f"/api/v1/products/{source['id']}/duplicate", headers=vendor_user["headers"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_source", [False, True])
async def test_duplicate_preserves_metadata_and_independent_images(
    client, vendor_user, source, uploads, db_session, delete_source
):
    result = await duplicate(client, vendor_user, source)
    assert result.status_code == 201, result.text
    copy = result.json()
    assert copy["id"] != source["id"]
    assert copy["title"] == "Silk dress (Copy)"
    assert copy["currency"] == "USD"
    assert copy["product_type"] == "variable"
    assert copy["status"] == "draft" and copy["moderation_status"] == "pending"
    assert not copy["is_featured"] and copy["orders_count"] == 0
    assert copy["variations"][0]["size_stocks"][0]["stock"] == 6
    assert copy["variations"][0]["size_stocks"][0]["size"] == "M"
    assert copy["variations"][0]["images"] == [copy["images"][0]["image_url"]]
    assert copy["images"][0]["alt_text"] == "front"
    assert "storage_keys" not in str(copy)
    new_image = await db_session.scalar(select(ProductImage).where(
        ProductImage.product_id == UUID(copy["id"])
    ))
    keys = list(new_image.storage_keys)
    assert len(keys) == 4 and set(keys).isdisjoint(uploads[0]["storage_keys"])
    for old, new in zip(uploads[0]["storage_keys"], keys):
        assert (image_service.upload_dir / new).read_bytes() == (image_service.upload_dir / old).read_bytes()
    assert (await client.get(f"/api/v1/products/{copy['id']}")).status_code == 404
    edited = await client.put(f"/api/v1/products/{copy['id']}", headers=vendor_user["headers"], json={
        "variations": [{"title": "Red", "images": [copy["images"][0]["image_url"]],
                        "sizes": [{"size": "M", "stock": 6}]}],
    })
    assert edited.status_code == 200, edited.text
    deleted = source["id"] if delete_source else copy["id"]
    deleted_image = source["images"][0]["id"] if delete_source else copy["images"][0]["id"]
    response = await client.delete(
        f"/api/v1/products/{deleted}/images/{deleted_image}", headers=vendor_user["headers"]
    )
    assert response.status_code == 204, response.text
    remaining_keys = keys if delete_source else uploads[0]["storage_keys"]
    assert all((image_service.upload_dir / key).exists() for key in remaining_keys)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["single", "made_to_order", "external"])
async def test_duplicate_compatible_sources(client, vendor_user, db_session, mode):
    payload = {"title": "Legacy dress", "base_price": 100, "total_stock": 5, "currency": "NGN"}
    if mode == "made_to_order":
        payload.update(made_to_order=True, made_to_order_timeline="Two weeks")
    if mode == "external":
        payload["images"] = [{"image_url": "https://legacy.test/front.jpg", "thumbnail_url": None}]
        payload["variations"] = [{"title": "Red", "images": ["https://legacy.test/front.jpg"]}]
    created = await client.post("/api/v1/products", headers=vendor_user["headers"], json=payload)
    assert created.status_code == 201, created.text
    response = await duplicate(client, vendor_user, created.json())
    assert response.status_code == 201, response.text
    copy = response.json()
    assert copy["total_stock"] == 0 and copy["currency"] == "NGN"
    assert copy["made_to_order"] == (mode == "made_to_order")
    if mode == "made_to_order":
        assert copy["made_to_order_timeline"] == "Two weeks"
    if mode == "external":
        assert copy["images"][0]["image_url"] == "https://legacy.test/front.jpg"
        assert copy["images"][0]["thumbnail_url"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["foreign", "missing", "unapproved", "incomplete", "anonymous", "customer", "admin"])
async def test_duplicate_permissions_before_io(
    client, vendor_user, customer_user, admin_user, source, db_session, monkeypatch, mode
):
    copy = AsyncMock()
    monkeypatch.setattr(image_service, "copy_image_key", copy)
    product_id = source["id"]
    headers = vendor_user["headers"]
    expected = 403
    if mode == "foreign":
        # A real product owned by another vendor is indistinguishable from missing.
        from app.models.vendor import Vendor
        other = Vendor(user_id=customer_user["user"].id, business_name="Other", approved=True)
        db_session.add(other)
        await db_session.flush()
        product = await db_session.get(Product, UUID(product_id))
        product.vendor_id = other.id
        await db_session.commit()
        expected = 404
    elif mode == "missing":
        product_id, expected = str(uuid4()), 404
    elif mode in ("unapproved", "incomplete"):
        vendor = vendor_user["vendor"]
        if mode == "unapproved":
            vendor.approved = False
        else:
            vendor.is_onboarding = True
        await db_session.commit()
    elif mode == "anonymous":
        headers, expected = {}, 403
    elif mode == "customer":
        headers = customer_user["headers"]
    elif mode == "admin":
        headers = admin_user["headers"]
    response = await client.post(f"/api/v1/products/{product_id}/duplicate", headers=headers)
    assert response.status_code == expected, response.text
    copy.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["gallery", "url", "thumbnail", "keyless", "tombstone", "shared"])
async def test_inconsistent_sources_fail_before_copy(
    client, vendor_user, source, db_session, monkeypatch, mode
):
    image = await db_session.scalar(select(ProductImage).where(ProductImage.product_id == UUID(source["id"])))
    if mode == "gallery":
        variation = await db_session.scalar(select(Variation).where(Variation.product_id == UUID(source["id"])))
        variation.images = ["https://foreign.test/other.jpg"]
    elif mode in ("url", "thumbnail"):
        setattr(image, "image_url" if mode == "url" else "thumbnail_url", "https://foreign.test/wrong.jpg")
    elif mode == "keyless":
        image.storage_keys = None
    elif mode == "tombstone":
        db_session.add(ProductImageStorageCleanup(storage_keys=[image.storage_keys[0]], reason="test"))
    elif mode == "shared":
        db_session.add(ProductImage(
            product_id=image.product_id, image_url=image.image_url, storage_keys=image.storage_keys,
        ))
    await db_session.commit()
    copy = AsyncMock()
    monkeypatch.setattr(image_service, "copy_image_key", copy)
    response = await duplicate(client, vendor_user, source)
    assert response.status_code == 409, response.text
    copy.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["copy", "ack", "build", "serialize"])
async def test_precommit_failures_reserve_only_attempted_destinations(
    client, vendor_user, source, uploads, db_session, monkeypatch, stage
):
    original = image_service.copy_image_key
    attempted = []
    async def copy(old, new, **kwargs):
        attempted.append(new)
        if stage == "copy" and len(attempted) == 2:
            raise OSError("copy failure")
        await original(old, new, **kwargs)
        if stage == "ack" and len(attempted) == 2:
            raise OSError("lost acknowledgement")
    monkeypatch.setattr(image_service, "copy_image_key", copy)
    if stage == "build":
        monkeypatch.setattr(product_duplication, "build_product_graph", AsyncMock(side_effect=ValueError("flush")))
    if stage == "serialize":
        monkeypatch.setattr(product_duplication.ProductResponse, "model_validate", lambda *args: (_ for _ in ()).throw(ValueError("serialize")))
    response = await duplicate(client, vendor_user, source)
    assert response.status_code == 503, response.text
    assert await db_session.scalar(select(func.count()).select_from(Product)) == 1
    cleanup = await db_session.scalar(select(ProductImageStorageCleanup))
    assert set(cleanup.storage_keys) == set(attempted)
    assert set(attempted).isdisjoint(uploads[0]["storage_keys"])
    assert all((image_service.upload_dir / key).exists() for key in uploads[0]["storage_keys"])
    # Existing worker can retry the exact reservation without harming the source.
    from app.tasks.product_image_storage_cleanup import reconcile_product_image_storage_cleanups
    from tests.conftest import TestSessionLocal
    assert (await reconcile_product_image_storage_cleanups(session_factory=TestSessionLocal))["resolved"] == 1
    assert all(not (image_service.upload_dir / key).exists() for key in attempted)
    assert all((image_service.upload_dir / key).exists() for key in uploads[0]["storage_keys"])


@pytest.mark.asyncio
@pytest.mark.parametrize("durable", [False, True])
async def test_commit_acknowledgement_reconciliation(
    client, vendor_user, source, db_session, monkeypatch, durable
):
    original = db_session.commit
    failed = False
    async def commit():
        nonlocal failed
        if not failed:
            failed = True
            if durable:
                await original()
            raise OSError("lost commit acknowledgement")
        await original()
    monkeypatch.setattr(db_session, "commit", commit)
    response = await duplicate(client, vendor_user, source)
    assert response.status_code == (201 if durable else 503), response.text
    assert await db_session.scalar(select(func.count()).select_from(Product)) == (2 if durable else 1)
    cleanup = await db_session.scalar(select(ProductImageStorageCleanup))
    assert (cleanup is None) == durable


@pytest.mark.asyncio
async def test_unknown_commit_outcome_preserves_objects(
    client, vendor_user, source, db_session, monkeypatch
):
    original_load = product_duplication._load_product
    loads = 0
    async def load(*args):
        nonlocal loads
        loads += 1
        if loads > 2:
            raise OSError("database unavailable during reconciliation")
        return await original_load(*args)
    monkeypatch.setattr(product_duplication, "_load_product", load)
    monkeypatch.setattr(db_session, "commit", AsyncMock(side_effect=OSError("uncertain")))
    response = await duplicate(client, vendor_user, source)
    assert response.status_code == 503 and "uncertain" in response.json()["detail"]
    assert await db_session.scalar(select(ProductImageStorageCleanup)) is None
    assert len(list(image_service.upload_dir.glob("vendors/*/products/copies/*"))) == 4


@pytest.mark.asyncio
async def test_duplicate_holds_source_catalog_lock_during_copy(
    vendor_user, source, db_session, monkeypatch
):
    from tests.conftest import TestSessionLocal
    from app.models.stock_payment_persistence import coordinate_catalog_write
    source_id = UUID(source["id"])
    vendor = vendor_user["vendor"]
    entered, release, other_locked = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = image_service.copy_image_key
    async def copy(*args, **kwargs):
        entered.set()
        await asyncio.wait_for(release.wait(), 5)
        await original(*args, **kwargs)
    monkeypatch.setattr(image_service, "copy_image_key", copy)
    async def source_writer():
        async with TestSessionLocal() as other:
            await coordinate_catalog_write(other, product_ids=[source_id], lock_only=True)
            other_locked.set()
            await other.rollback()
    task = asyncio.create_task(product_duplication.duplicate_vendor_product(db_session, vendor, source_id))
    await asyncio.wait_for(entered.wait(), 5)
    writer = asyncio.create_task(source_writer())
    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(other_locked.wait(), .1)
    finally:
        release.set()
        await asyncio.wait_for(task, 10)
        await asyncio.wait_for(writer, 10)
    assert other_locked.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("thumbnail", [None, "original"])
async def test_thumbnail_null_and_original_semantics(
    client, vendor_user, source, db_session, thumbnail
):
    image = await db_session.scalar(select(ProductImage).where(ProductImage.product_id == UUID(source["id"])))
    image.thumbnail_url = image.image_url if thumbnail else None
    await db_session.commit()
    response = await duplicate(client, vendor_user, source)
    assert response.status_code == 201, response.text
    copied = response.json()["images"][0]
    assert copied["thumbnail_url"] == (copied["image_url"] if thumbnail else None)


@pytest.mark.asyncio
async def test_maximum_gallery_copies_all_40_objects_in_order(
    client, vendor_user, source, db_session, monkeypatch, record_property
):
    from time import monotonic
    product_id = UUID(source["id"])
    first = await db_session.scalar(select(ProductImage).where(ProductImage.product_id == product_id))
    originals = [first.image_url]
    for index in range(1, 10):
        keys = [f"vendors/{vendor_user['user'].id}/products/max/{index}-{part}.png" for part in range(4)]
        for key in keys:
            path = image_service.upload_dir / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"image")
        originals.append(f"/uploads/{keys[0]}")
        db_session.add(ProductImage(
            product_id=product_id, image_url=originals[-1], thumbnail_url=f"/uploads/{keys[1]}",
            storage_keys=keys, display_order=index, is_primary=False, alt_text=f"view-{index}",
        ))
    variation = await db_session.scalar(select(Variation).where(Variation.product_id == product_id))
    variation.images = list(reversed(originals))
    await db_session.commit()
    original_copy = image_service.copy_image_key
    copy = AsyncMock(side_effect=original_copy)
    monkeypatch.setattr(image_service, "copy_image_key", copy)
    started = monotonic()
    response = await duplicate(client, vendor_user, source)
    elapsed = monotonic() - started
    record_property("maximum_gallery_local_seconds", elapsed)
    assert response.status_code == 201, response.text
    assert copy.await_count == 40
    images = sorted(response.json()["images"], key=lambda row: row["display_order"])
    assert [row["display_order"] for row in images] == list(range(10))
    assert response.json()["variations"][0]["images"] == [row["image_url"] for row in reversed(images)]
    assert images[0]["is_primary"] and all(not image["is_primary"] for image in images[1:])


@pytest.mark.asyncio
async def test_cleanup_record_failure_retains_copies(
    client, vendor_user, source, db_session, monkeypatch
):
    monkeypatch.setattr(product_duplication, "build_product_graph", AsyncMock(side_effect=ValueError("flush")))
    monkeypatch.setattr(product_duplication, "record_storage_cleanup", AsyncMock(side_effect=OSError("db down")))
    response = await duplicate(client, vendor_user, source)
    assert response.status_code == 503 and "uncertain" in response.json()["detail"]
    assert await db_session.scalar(select(ProductImageStorageCleanup)) is None
    assert len(list(image_service.upload_dir.glob("vendors/*/products/copies/*"))) == 4


@pytest.mark.asyncio
async def test_made_to_order_variable_resets_size_inventory(
    client, vendor_user, source, db_session
):
    product = await db_session.get(Product, UUID(source["id"]))
    product.made_to_order, product.made_to_order_timeline = True, "Three weeks"
    await db_session.commit()
    response = await duplicate(client, vendor_user, source)
    assert response.status_code == 201, response.text
    assert response.json()["total_stock"] == 0
    assert response.json()["variations"][0]["size_stocks"][0]["stock"] == 0


@pytest.mark.asyncio
async def test_cleanup_reservation_preserves_owned_and_consumed_keys(source, db_session):
    image = await db_session.scalar(select(ProductImage).where(ProductImage.product_id == UUID(source["id"])))
    owned = image.storage_keys[0]
    consumed, unowned = "copy/previously-consumed", "copy/unowned"
    db_session.add(ProductImageStorageCleanup(storage_keys=[consumed], reason="prior"))
    await db_session.commit()
    await product_duplication._reserve_cleanup(db_session, [owned, consumed, unowned], uuid4())
    rows = list((await db_session.scalars(select(ProductImageStorageCleanup))).all())
    assert sorted(row.storage_keys for row in rows) == [[consumed], [unowned]]
