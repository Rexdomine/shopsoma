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
