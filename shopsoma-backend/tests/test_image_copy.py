from unittest.mock import Mock

import pytest

from app.services.image_service import ImageService


@pytest.mark.asyncio
async def test_local_copy_preserves_bytes_and_refuses_overwrite(tmp_path):
    service = object.__new__(ImageService)
    service.use_local_storage, service.upload_dir = True, tmp_path
    (tmp_path / "source.jpg").write_bytes(b"source")
    await service.copy_image_key("source.jpg", "new/copy.jpg", key_mapping={})
    assert (tmp_path / "new/copy.jpg").read_bytes() == b"source"
    (tmp_path / "source.jpg").write_bytes(b"changed")
    with pytest.raises(FileExistsError):
        await service.copy_image_key("source.jpg", "new/copy.jpg", key_mapping={})
    assert (tmp_path / "new/copy.jpg").read_bytes() == b"source"
    with pytest.raises(ValueError):
        await service.copy_image_key("source.jpg", "source.jpg", key_mapping={})
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await service.copy_image_key("source.jpg", "../outside.jpg", key_mapping={})
    assert service.public_url_for_key("new/copy.jpg") == "/uploads/new/copy.jpg"


@pytest.mark.asyncio
async def test_provider_copy_rewrites_original_metadata_and_preserves_headers():
    service = object.__new__(ImageService)
    service.use_local_storage, service.bucket_name = False, "test-bucket"
    service._copy_client = Mock()
    service._copy_client.head_object.return_value = {
        "Metadata": {"variant": "thumbnail", "original-key": "source.jpg"},
        "ContentType": "image/jpeg", "CacheControl": "public,max-age=31536000",
    }
    await service.copy_image_key(
        "thumb.jpg", "new-thumb.jpg", key_mapping={"source.jpg": "new-source.jpg"}
    )
    service._copy_client.copy_object.assert_called_once_with(
        Bucket="test-bucket", Key="new-thumb.jpg",
        CopySource={"Bucket": "test-bucket", "Key": "thumb.jpg"},
        MetadataDirective="REPLACE",
        Metadata={"variant": "thumbnail", "original-key": "new-source.jpg"},
        ContentType="image/jpeg", CacheControl="public,max-age=31536000",
    )


@pytest.mark.asyncio
async def test_provider_copy_rejects_foreign_derivative_metadata_before_write():
    service = object.__new__(ImageService)
    service.use_local_storage, service.bucket_name = False, "test-bucket"
    service._copy_client = Mock()
    service._copy_client.head_object.return_value = {"Metadata": {"original-key": "foreign.jpg"}}
    with pytest.raises(ValueError):
        await service.copy_image_key("thumb.jpg", "new.jpg", key_mapping={})
    service._copy_client.copy_object.assert_not_called()
