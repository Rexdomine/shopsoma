import pytest

from app.services.image_service import ImageService


@pytest.mark.asyncio
async def test_local_upload_result_exposes_all_storage_keys(tmp_path, monkeypatch):
    service = object.__new__(ImageService)
    service.upload_dir = tmp_path
    service.thumbnail_size = (10, 10)
    service.medium_size = (20, 20)
    service.large_size = (30, 30)

    def filename(_original, size="original"):
        return f"image_{size}.jpg"

    monkeypatch.setattr(service, "_generate_unique_filename", filename)
    monkeypatch.setattr(service, "_compress_and_resize", lambda *args, **kwargs: (b"data", "jpeg"))

    result = await service._upload_local(
        image_data=b"source",
        original_filename="image.jpg",
        base_filename="image_original.jpg",
        folder="products",
        generate_variants=True,
    )

    assert len(result["_storage_keys"]) == 4
    assert [key.rsplit("/", 1)[-1] for key in result["_storage_keys"]] == [
        "image_original.jpg",
        "image_thumbnail.jpg",
        "image_medium.jpg",
        "image_large.jpg",
    ]
    assert all(key.startswith("products/") for key in result["_storage_keys"])


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_stage", [1, 2, 3])
@pytest.mark.parametrize("cleanup_raises", [False, True])
async def test_local_variant_failure_preserves_retry_keys_and_original_error(
    tmp_path, monkeypatch, failed_stage, cleanup_raises
):
    from unittest.mock import AsyncMock
    from fastapi import HTTPException

    service = object.__new__(ImageService)
    service.upload_dir = tmp_path
    service.thumbnail_size = (10, 10)
    service.medium_size = (20, 20)
    service.large_size = (30, 30)
    monkeypatch.setattr(service, "_generate_unique_filename", lambda _, size: f"{size}.jpg")
    calls = 0
    original_error = OSError("variant write failed")

    def compress(*args, **kwargs):
        nonlocal calls
        stage = calls
        calls += 1
        if stage == failed_stage:
            raise original_error
        return b"data", "jpeg"

    cleanup = AsyncMock(side_effect=RuntimeError("cleanup unavailable")) if cleanup_raises else AsyncMock(
        side_effect=lambda keys: {"failed_keys": keys[1:]}
    )
    monkeypatch.setattr(service, "_compress_and_resize", compress)
    monkeypatch.setattr(service, "delete_images", cleanup)
    with pytest.raises(HTTPException) as caught:
        await service._upload_local(
            image_data=b"source", original_filename="image.jpg",
            base_filename="original.jpg", folder="products", generate_variants=True,
        )
    attempted = cleanup.await_args.args[0]
    assert len(attempted) == failed_stage + 1
    assert [key.rsplit("/", 1)[-1] for key in attempted] == [
        "original.jpg", "thumbnail.jpg", "medium.jpg", "large.jpg"
    ][:failed_stage + 1]
    assert caught.value.status_code == 500
    assert caught.value.__cause__ is original_error
    assert caught.value.storage_keys == (attempted if cleanup_raises else attempted[1:])
