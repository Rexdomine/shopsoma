"""
Image upload and management endpoints
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status, Query
from typing import List
from datetime import datetime, timedelta
from pathlib import PurePosixPath

from app.schemas.image import (
    ImageUploadResponse,
    ImageBatchUploadResponse,
    SignedUrlRequest,
    SignedUrlResponse,
    ImageDeleteResponse,
    ImageBatchDeleteResponse,
    ImageInfoResponse,
)
from app.services.image_service import image_service
from app.api.dependencies import get_current_user, get_current_vendor
from app.models.user import User

router = APIRouter(prefix="/images", tags=["Images"])


def _vendor_storage_folder(current_user: User, folder: str) -> str:
    requested = PurePosixPath(folder)
    if (
        requested.is_absolute()
        or not requested.parts
        or any(part in {"", ".", ".."} for part in requested.parts)
    ):
        raise HTTPException(status_code=400, detail="Invalid storage folder")
    return str(PurePosixPath("vendors", str(current_user.id), *requested.parts))


def _require_vendor_image_key(current_user: User, s3_key: str) -> None:
    raw_parts = s3_key.split("/")
    requested = PurePosixPath(s3_key)
    parts = requested.parts
    if requested.is_absolute() or any(part in {"", ".", ".."} for part in raw_parts):
        raise HTTPException(status_code=400, detail="Invalid image key")

    if len(parts) >= 3 and parts[:2] == ("vendors", str(current_user.id)):
        return

    raise HTTPException(status_code=403, detail="Image does not belong to vendor")


@router.post(
    "/upload", response_model=ImageUploadResponse, status_code=status.HTTP_201_CREATED
)
async def upload_image(
    file: UploadFile = File(..., description="Image file to upload"),
    folder: str = Query(
        default="products", description="Storage folder (products, avatars, etc.)"
    ),
    generate_variants: bool = Query(
        default=True, description="Generate thumbnail/medium/large variants"
    ),
    current_user: User = Depends(get_current_vendor),
):
    """
    Upload a single image with automatic compression and resizing

    **Features:**
    - Automatic image validation (type and size)
    - Compression with quality optimization
    - Multiple size variants (thumbnail, medium, large)
    - S3/CloudFlare R2 storage
    - CDN support
    - Unique filename generation

    **Permissions:** Vendor only
    """
    try:
        result = await image_service.upload_image(
            file=file,
            folder=_vendor_storage_folder(current_user, folder),
            generate_variants=generate_variants,
        )

        return ImageUploadResponse(
            original=result["original"],
            thumbnail=result.get("thumbnail"),
            medium=result.get("medium"),
            large=result.get("large"),
            s3_key=result["s3_key"],
            uploaded_at=datetime.utcnow(),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}")


@router.post("/upload/batch", response_model=ImageBatchUploadResponse)
async def upload_images_batch(
    files: List[UploadFile] = File(..., description="List of image files (max 10)"),
    folder: str = Query(default="products", description="Storage folder"),
    generate_variants: bool = Query(
        default=True, description="Generate variants for each image"
    ),
    current_user: User = Depends(get_current_vendor),
):
    """
    Upload multiple images in a single request

    **Limits:**
    - Maximum 10 images per request
    - Each image subject to standard size limits

    **Permissions:** Vendor only
    """
    # Limit batch size
    if len(files) > 10:
        raise HTTPException(
            status_code=400, detail="Maximum 10 images per batch upload"
        )

    storage_folder = _vendor_storage_folder(current_user, folder)
    uploaded_images = []
    success_count = 0
    failed_count = 0

    for file in files:
        try:
            result = await image_service.upload_image(
                file=file,
                folder=storage_folder,
                generate_variants=generate_variants,
            )

            uploaded_images.append(
                ImageUploadResponse(
                    original=result["original"],
                    thumbnail=result.get("thumbnail"),
                    medium=result.get("medium"),
                    large=result.get("large"),
                    s3_key=result["s3_key"],
                    uploaded_at=datetime.utcnow(),
                )
            )
            success_count += 1

        except Exception as e:
            failed_count += 1
            # Log error but continue with other files
            print(f"Failed to upload {file.filename}: {str(e)}")

    return ImageBatchUploadResponse(
        images=uploaded_images,
        total=len(files),
        success=success_count,
        failed=failed_count,
    )


@router.post("/signed-url", response_model=SignedUrlResponse)
async def generate_signed_url(
    request: SignedUrlRequest, current_user: User = Depends(get_current_user)
):
    """
    Generate a presigned URL for private image access

    **Use Cases:**
    - Temporary access to private images
    - Secure download links
    - Time-limited sharing

    **Permissions:** Authenticated users
    """
    try:
        url = image_service.generate_presigned_url(
            s3_key=request.s3_key, expiration=request.expiration
        )

        expires_at = datetime.utcnow() + timedelta(seconds=request.expiration)

        return SignedUrlResponse(
            url=url, expires_in=request.expiration, expires_at=expires_at
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate signed URL: {str(e)}"
        )


@router.delete("/{s3_key:path}", response_model=ImageDeleteResponse)
async def delete_image(s3_key: str, current_user: User = Depends(get_current_vendor)):
    """
    Delete an image from storage

    **Note:** This operation cannot be undone

    **Permissions:** Vendor only (own images)
    """
    _require_vendor_image_key(current_user, s3_key)

    success = await image_service.delete_image(s3_key)

    if success:
        return ImageDeleteResponse(
            success=True, message="Image deleted successfully", s3_key=s3_key
        )
    else:
        raise HTTPException(status_code=500, detail="Failed to delete image")


@router.post("/delete/batch", response_model=ImageBatchDeleteResponse)
async def delete_images_batch(
    s3_keys: List[str], current_user: User = Depends(get_current_vendor)
):
    """
    Delete multiple images in a single request

    **Limits:**
    - Maximum 100 images per batch

    **Permissions:** Vendor only
    """
    if len(s3_keys) > 100:
        raise HTTPException(
            status_code=400, detail="Maximum 100 images per batch delete"
        )

    for s3_key in s3_keys:
        _require_vendor_image_key(current_user, s3_key)

    result = await image_service.delete_images(s3_keys)

    return ImageBatchDeleteResponse(
        deleted=result["deleted"],
        failed=result["failed"],
        total=len(s3_keys),
        message=f"Deleted {result['deleted']} images, {result['failed']} failed",
    )


@router.get("/{s3_key:path}/info", response_model=ImageInfoResponse)
async def get_image_info(s3_key: str, current_user: User = Depends(get_current_user)):
    """
    Get image metadata and information

    **Returns:**
    - File size
    - Content type
    - Last modified date
    - Custom metadata

    **Permissions:** Authenticated users
    """
    info = image_service.get_image_info(s3_key)

    if not info:
        raise HTTPException(status_code=404, detail="Image not found")

    return ImageInfoResponse(
        s3_key=s3_key,
        size=info["size"],
        content_type=info["content_type"],
        last_modified=info["last_modified"],
        url=image_service._get_public_url(s3_key),
        metadata=info["metadata"],
    )


@router.get("/health")
async def health_check():
    """
    Check if image service is working

    **Public endpoint**
    """
    if image_service.use_local_storage:
        if not image_service.local_storage_is_healthy():
            return {
                "status": "unhealthy",
                "service": "image-storage",
                "backend": "local",
            }
        return {
            "status": "healthy",
            "service": "image-storage",
            "backend": "local",
            "max_size_mb": image_service.max_size_bytes / (1024 * 1024),
            "allowed_types": image_service.allowed_types,
        }

    try:
        # Try to list buckets to verify S3 connection
        image_service.s3_client.head_bucket(Bucket=image_service.bucket_name)
        return {
            "status": "healthy",
            "service": "image-storage",
            "bucket": image_service.bucket_name,
            "max_size_mb": image_service.max_size_bytes / (1024 * 1024),
            "allowed_types": image_service.allowed_types,
        }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
